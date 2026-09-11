"""
Feature engineering — above all, that no feature can see the future.

Leakage is the single failure mode that would make every metric in the report a
lie, so it is tested three independent ways: by re-deriving features from the raw
panel, by truncating the panel and checking features are unchanged, and by
checking the supervised frame's target alignment.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.data import DATE, DEMAND, SKU
from app.ml.features import (FEATURE_COLUMNS, MIN_LEVEL_PERIODS, assert_no_leakage,
                             build_dow_index, build_origin_features,
                             build_category_codes, attach_category_code,
                             make_supervised)


class TestNoLeakage:
    def test_builtin_guard_passes(self, panel, origin_df):
        assert_no_leakage(panel, origin_df)

    def test_lag_and_rolling_features_are_backward_looking(self, panel, origin_df):
        """Re-derive from raw values for every SKU, not just a sample."""
        p = panel.sort_values([SKU, DATE]).reset_index(drop=True)
        o = origin_df.sort_values([SKU, DATE]).reset_index(drop=True)
        for sku, g in p.groupby(SKU, sort=False):
            og = o[o[SKU] == sku].reset_index(drop=True)
            y = g[DEMAND].values.astype(float)
            n = len(y)
            for i in range(MIN_LEVEL_PERIODS, n, 7):
                assert og["lag_1"].iat[i] == pytest.approx(y[i]), f"{sku}@{i}"
                if i >= 6:
                    assert og["lag_7"].iat[i] == pytest.approx(y[i - 6])
                lo = max(0, i - 27)
                assert og["roll_mean_28"].iat[i] == pytest.approx(
                    float(np.mean(y[lo:i + 1])), rel=1e-9
                ), f"roll_mean_28 mismatch for {sku} at {i}"
                lo7 = max(0, i - 6)
                assert og["roll_mean_7"].iat[i] == pytest.approx(
                    float(np.mean(y[lo7:i + 1])), rel=1e-9
                )

    def test_features_unchanged_when_future_is_removed(self, panel):
        """
        The decisive test: truncate the panel and recompute. A feature that peeked
        forward would change value for days that are still present.
        """
        cutoff = pd.Timestamp("2026-05-15")
        full = build_origin_features(panel)
        early = build_origin_features(panel[panel[DATE] <= cutoff].copy())

        merged = full[full[DATE] <= cutoff].merge(
            early, on=[SKU, DATE], suffixes=("_f", "_e")
        )
        assert len(merged) > 3000
        numeric = [c for c in FEATURE_COLUMNS if c not in ("horizon", "target_dow", "dow_index",
                                                           "category_code")]
        for col in numeric:
            a, b = merged[f"{col}_f"], merged[f"{col}_e"]
            both = a.notna() & b.notna()
            assert (a.isna() == b.isna()).all(), f"{col} NaN pattern changed"
            assert (a[both] - b[both]).abs().max() < 1e-9, f"{col} leaked future data"

    def test_dow_index_is_causal(self, panel):
        cutoff = pd.Timestamp("2026-05-15")
        full = build_origin_features(panel)
        early = build_origin_features(panel[panel[DATE] <= cutoff].copy())
        cols = [f"_dowidx_{d}" for d in range(7)]
        merged = full[full[DATE] <= cutoff].merge(
            early, on=[SKU, DATE], suffixes=("_f", "_e")
        )
        for c in cols:
            assert (merged[f"{c}_f"] - merged[f"{c}_e"]).abs().max() < 1e-9

    def test_supervised_target_is_the_future_value(self, origin_df, panel):
        sup = make_supervised(origin_df, [1, 7, 14], min_history=7)
        truth = panel.set_index([SKU, DATE])[DEMAND]
        sample = sup.sample(300, random_state=0)
        for _, r in sample.iterrows():
            expected = truth.get((r[SKU], r["target_date"]))
            assert r["y_true"] == pytest.approx(expected), (
                f"{r[SKU]} h={r['horizon']} target={r['target_date']}"
            )

    def test_target_date_equals_origin_plus_horizon(self, origin_df):
        sup = make_supervised(origin_df, [1, 5, 28], min_history=7, require_target=False)
        delta = (sup["target_date"] - sup[DATE]).dt.days
        assert (delta == sup["horizon"]).all()


class TestRollingFeatures:
    def test_rolling_std_matches_pandas(self, panel, origin_df):
        g = panel.sort_values([SKU, DATE]).groupby(SKU)[DEMAND]
        expected = g.transform(lambda s: s.rolling(28, min_periods=3).std(ddof=1))
        got = origin_df.sort_values([SKU, DATE])["roll_std_28"].reset_index(drop=True)
        exp = expected.reset_index(drop=True)
        both = got.notna() & exp.notna()
        assert (got[both] - exp[both]).abs().max() < 1e-9

    def test_days_history_counts_from_one(self, origin_df):
        first = origin_df.sort_values(DATE).groupby(SKU).head(1)
        assert (first["days_history"] == 1).all()
        last = origin_df.sort_values(DATE).groupby(SKU).tail(1)
        assert last.set_index(SKU)["days_history"]["SKU-2000"] == 12
        assert last.set_index(SKU)["days_history"]["SKU-1000"] == 180

    def test_derived_ratios(self, origin_df):
        d = origin_df.dropna(subset=["roll_mean_7", "roll_mean_28", "trend_7_over_28"])
        assert (d["trend_7_over_28"]
                - d["roll_mean_7"] / d["roll_mean_28"]).abs().max() < 1e-9


class TestColdStartShrinkage:
    def test_new_sku_dow_index_leans_on_the_category(self, panel):
        """
        With 1-2 observations of a weekday, w = n/(n+3) is at most 0.4, so the
        category prior must dominate — that is the cold-start mechanism.
        """
        idx = build_dow_index(panel)
        df = panel.sort_values([SKU, DATE]).reset_index(drop=True)
        new_rows = df.index[df[SKU] == "SKU-2000"]
        vals = idx[new_rows]
        # A 12-day SKU cannot produce an extreme weekday index; heavy shrinkage
        # pulls everything toward 1.0.
        assert np.nanmax(np.abs(vals - 1.0)) < 0.6, (
            "cold-start weekday index is not being shrunk toward the category"
        )

    def test_established_sku_keeps_its_own_pattern(self, panel):
        idx = build_dow_index(panel)
        df = panel.sort_values([SKU, DATE]).reset_index(drop=True)
        rows = df.index[df[SKU] == "SKU-1004"]
        late = idx[rows][-1]
        assert np.nanmax(np.abs(late - 1.0)) > 0.05, (
            "an established SKU's weekday index should differ from flat"
        )

    def test_new_skus_survive_the_supervised_build(self, origin_df):
        sup = make_supervised(origin_df, [1, 3, 5], min_history=7, require_target=True)
        assert (sup[SKU] == "SKU-2000").any(), "cold-start SKU dropped from training"


class TestMatrix:
    def test_feature_matrix_has_no_duplicate_columns(self, origin_df):
        codes = build_category_codes(origin_df)
        sup = make_supervised(origin_df, [1, 14], min_history=7, require_target=False)
        X = attach_category_code(sup, codes)[FEATURE_COLUMNS]
        assert list(X.columns) == FEATURE_COLUMNS
        assert X.shape[1] == len(FEATURE_COLUMNS)

    def test_category_code_is_low_cardinality(self, origin_df):
        codes = build_category_codes(origin_df)
        assert len(codes) == 5
        sup = make_supervised(origin_df, [1], min_history=7, require_target=False)
        X = attach_category_code(sup, codes)
        assert X["category_code"].nunique() <= 5
        assert X["category_code"].min() >= 0
