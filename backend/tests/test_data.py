"""Data loading, schema detection and cleaning."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.data import (CATEGORY, DATE, DEMAND, LEAD_TIME, RECEIVED, SKU,
                         STOCK, detect_schema, load_clean_panel,
                         sku_history_lengths)


class TestSchemaDetection:
    def test_detects_the_real_columns(self, raw_csv):
        s = detect_schema(raw_csv)
        assert s.date == "date"
        assert s.sku == "sku_id"
        assert s.demand == "units_sold"
        assert s.received == "units_received"
        assert s.stock == "closing_stock"
        assert s.lead_time == "lead_time_days"
        assert s.category == "category"

    def test_detection_survives_renamed_headers(self, raw_csv):
        """The point of detection is that a renamed extract still loads."""
        renamed = raw_csv.rename(columns={
            "date": "BusinessDate", "sku_id": "Item Code",
            "units_sold": "qty_sold", "closing_stock": "eod_inventory",
            "units_received": "goods_received", "lead_time_days": "supplier_lead",
            "category": "product_group",
        })
        s = detect_schema(renamed)
        assert s.date == "BusinessDate"
        assert s.sku == "Item Code"
        assert s.demand == "qty_sold"
        assert s.stock == "eod_inventory"
        assert s.received == "goods_received"
        assert s.lead_time == "supplier_lead"

    def test_raises_without_a_date_column(self):
        df = pd.DataFrame({"a": ["x", "y"], "b": [1, 2]})
        with pytest.raises(ValueError):
            detect_schema(df)


class TestCleanPanel:
    def test_required_fields_present(self, panel):
        for col in (DATE, SKU, CATEGORY, DEMAND, RECEIVED, STOCK, LEAD_TIME):
            assert col in panel.columns, f"missing {col}"
        assert "is_stockout_day" in panel.columns

    def test_no_missing_values_remain(self, panel):
        for col in (DEMAND, STOCK, RECEIVED, LEAD_TIME):
            assert panel[col].isna().sum() == 0, f"{col} still has NaN"

    def test_exact_duplicates_removed(self, clean_report, panel):
        assert clean_report.exact_duplicates_dropped == 15
        assert panel.duplicated([SKU, DATE]).sum() == 0

    def test_category_case_normalised(self, panel, clean_report):
        assert clean_report.category_case_normalised > 0
        cats = set(panel[CATEGORY].unique())
        assert cats == {"Beverages", "Snacks", "Sugar", "Pasta", "Flour"}
        # A SKU must have exactly one category after normalisation.
        assert (panel.groupby(SKU)[CATEGORY].nunique() == 1).all()

    def test_imputation_counts_match_the_source(self, clean_report, raw_csv):
        deduped = raw_csv.drop_duplicates()
        assert clean_report.demand_values_imputed == int(deduped["units_sold"].isna().sum())

    def test_demand_imputation_is_causal(self, settings):
        """
        A fill for day t must not change when data after t changes. Truncating the
        panel and re-imputing has to reproduce the same values.
        """
        panel, _, _ = load_clean_panel(settings.data_csv)
        cutoff = pd.Timestamp("2026-04-30")

        raw = pd.read_csv(settings.data_csv)
        raw["date"] = pd.to_datetime(raw["date"])
        truncated_path = raw[raw["date"] <= cutoff]

        import tempfile, os
        fd, tmp = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            truncated_path.to_csv(tmp, index=False)
            early, _, _ = load_clean_panel(tmp)
        finally:
            os.unlink(tmp)

        merged = panel[panel[DATE] <= cutoff].merge(
            early, on=[SKU, DATE], suffixes=("_full", "_early")
        )
        assert len(merged) == 25 * 120, "expected every established SKU over the window"
        diff = (merged[f"{DEMAND}_full"] - merged[f"{DEMAND}_early"]).abs()
        assert diff.max() < 1e-9, "imputed demand changed when future data was removed"

    def test_daily_grid_is_complete_per_sku(self, panel):
        for sku, g in panel.groupby(SKU):
            span = (g[DATE].max() - g[DATE].min()).days + 1
            assert len(g) == span, f"{sku} has gaps in its daily grid"

    def test_lead_time_repaired_for_new_skus(self, panel, clean_report):
        assert set(clean_report.lead_time_imputed_skus) == {
            "SKU-2000", "SKU-2001", "SKU-2002",
        }
        # After repair every SKU has exactly one lead time.
        assert (panel.groupby(SKU)[LEAD_TIME].nunique() == 1).all()
        for sku in clean_report.lead_time_imputed_skus:
            lt = panel.loc[panel[SKU] == sku, LEAD_TIME].iloc[0]
            assert 3 <= lt <= 14

    def test_balance_audit_measures_the_source_not_our_fills(self, clean_report):
        """
        Every violation in the supplied file is explained by stock being censored
        at zero. If imputation leaked into the audit this ratio would drop.
        """
        assert clean_report.balance_violations > 0
        assert (clean_report.balance_violations_explained_by_zero_floor
                == clean_report.balance_violations)

    def test_stockout_days_flagged(self, panel, clean_report):
        assert clean_report.observed_stockout_days > 0
        assert int(panel["is_stockout_day"].sum()) == clean_report.observed_stockout_days
        assert ((panel[STOCK] <= 0) == (panel["is_stockout_day"] == 1)).all()

    def test_no_negative_values(self, panel):
        for col in (DEMAND, RECEIVED, STOCK):
            assert (panel[col] >= 0).all(), f"{col} has negatives"


class TestGrouping:
    def test_sku_count_and_history(self, panel):
        lengths = sku_history_lengths(panel)
        assert len(lengths) == 28
        cold = lengths[lengths < 30]
        assert set(cold.index) == {"SKU-2000", "SKU-2001", "SKU-2002"}
        assert (cold == 12).all()
        assert (lengths[lengths >= 30] == 180).all()

    def test_date_range(self, panel):
        assert str(panel[DATE].min().date()) == "2026-01-01"
        assert str(panel[DATE].max().date()) == "2026-06-29"

    def test_every_sku_reaches_the_snapshot_date(self, panel):
        last = panel[DATE].max()
        assert panel.groupby(SKU)[DATE].max().eq(last).all()


class TestMissingDataBehaviour:
    def test_handles_a_column_of_all_missing_demand_for_one_sku(self, raw_csv, tmp_path):
        """A SKU with no demand at all must not crash the loader."""
        df = raw_csv.copy()
        df.loc[df.sku_id == "SKU-1000", "units_sold"] = np.nan
        p = tmp_path / "gap.csv"
        df.to_csv(p, index=False)
        panel, rep, _ = load_clean_panel(p)
        assert panel[panel[SKU] == "SKU-1000"][DEMAND].isna().sum() == 0
        assert rep.demand_values_imputed >= 180

    def test_handles_missing_receipts(self, raw_csv, tmp_path):
        df = raw_csv.copy()
        df.loc[df.index[:50], "units_received"] = np.nan
        p = tmp_path / "recv.csv"
        df.to_csv(p, index=False)
        panel, _, _ = load_clean_panel(p)
        assert panel[RECEIVED].isna().sum() == 0
