"""Risk scoring: stockout, overstock, ranking and cold-start behaviour."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from app.ml.risk import (MIN_MATERIAL_EXCESS_DAYS, OVERSTOCK_BANDS, STOCKOUT_BANDS,
                         assess_sku, category_cv_table)


def make_history(
    n_days: int = 180,
    demand: float = 100.0,
    stock: float = 1000.0,
    received_every: int | None = 10,
    receipt_qty: float = 1000.0,
    noise: float = 0.0,
    seed: int = 0,
) -> pd.DataFrame:
    """A synthetic SKU history with controllable supply and demand."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-01-01", periods=n_days, freq="D")
    d = np.full(n_days, demand, dtype=float)
    if noise:
        d = np.clip(d + rng.normal(0, noise, n_days), 1, None)
    recv = np.zeros(n_days)
    if received_every:
        recv[::received_every] = receipt_qty
    return pd.DataFrame({
        "date": dates, "sku_id": "TEST", "category": "Test",
        "units_sold": d, "units_received": recv,
        "closing_stock": np.full(n_days, stock, dtype=float),
        "lead_time_days": 7.0,
        "is_stockout_day": np.zeros(n_days, dtype=int),
    })


def flat_forecast(value: float, horizon: int = 28) -> pd.Series:
    return pd.Series({h: value for h in range(1, horizon + 1)})


def assess(history, forecast, **kw):
    defaults = dict(
        sku_id="TEST", category="Test", as_of=history["date"].max(),
        history=history, forecast=forecast, lead_time_days=7.0, category_cv=0.25,
    )
    defaults.update(kw)
    return assess_sku(**defaults)


class TestStockoutLogic:
    def test_the_brief_example_is_high_risk(self):
        """
        The brief's illustration: ~20 units on hand, 10/day expected demand, 5-day
        lead time, and no replenishment history. Two days of cover against five
        days of lead time must not come out healthy.
        """
        h = make_history(n_days=180, demand=10, stock=20, received_every=None)
        r = assess(h, flat_forecast(10), lead_time_days=5.0)
        assert r.risk_type == "STOCKOUT"
        assert r.risk_level in ("CRITICAL", "HIGH")
        assert r.stockout_probability > 0.7
        assert r.inventory_coverage_days == pytest.approx(2.0, abs=0.01)

    def test_zero_stock_is_always_critical(self):
        h = make_history(stock=0.0)
        r = assess(h, flat_forecast(100))
        assert r.risk_level == "CRITICAL"
        assert r.risk_type == "STOCKOUT"
        assert r.risk_score == 1.0
        assert r.days_to_projected_stockout == 0.0

    def test_ample_stock_is_healthy(self):
        h = make_history(demand=100, stock=1500, received_every=10, receipt_qty=1000)
        r = assess(h, flat_forecast(100))
        assert r.risk_level == "HEALTHY"
        assert r.stockout_probability < 0.08

    def test_probability_falls_as_stock_rises(self):
        probs = [
            assess(make_history(demand=100, stock=s, received_every=None),
                   flat_forecast(100)).stockout_probability
            for s in (100, 400, 700, 1000, 2000)
        ]
        assert probs == sorted(probs, reverse=True)
        assert probs[0] > 0.9 and probs[-1] < 0.05

    def test_longer_lead_time_raises_risk(self):
        h = make_history(demand=100, stock=800, received_every=None)
        short = assess(h, flat_forecast(100), lead_time_days=3.0)
        long = assess(h, flat_forecast(100), lead_time_days=14.0)
        assert long.stockout_probability > short.stockout_probability
        assert long.lead_time_demand > short.lead_time_demand

    def test_expected_inbound_reduces_risk_but_is_reported_separately(self):
        no_supply = assess(
            make_history(demand=100, stock=500, received_every=None), flat_forecast(100)
        )
        with_supply = assess(
            make_history(demand=100, stock=500, received_every=5, receipt_qty=500),
            flat_forecast(100),
        )
        assert with_supply.stockout_probability < no_supply.stockout_probability
        assert with_supply.expected_inbound_within_lead_time > 0
        # The conservative number must still be published.
        assert with_supply.stockout_probability_no_inbound > with_supply.stockout_probability

    def test_structural_undersupply_lifts_an_otherwise_quiet_sku(self):
        """
        Receiving 60 units for every 100 sold drains stock regardless of today's
        level. Stock here is 12 days of cover against a 7-day lead time — healthy
        on the immediate view, so only the standing shortfall can raise it.
        """
        h = make_history(demand=100, stock=1200, received_every=10, receipt_qty=600)
        r = assess(h, flat_forecast(100))
        assert r.is_structurally_undersupplied
        assert r.supply_coverage_ratio < 0.95
        assert r.excess_units == 0, "scenario must not also be overstocked"
        assert r.risk_level != "HEALTHY"
        assert r.risk_type == "STOCKOUT"
        assert "100 sold" in r.headline, "the headline must name the actual reason"

    def test_balanced_supply_is_not_flagged_undersupplied(self):
        h = make_history(demand=100, stock=2000, received_every=10, receipt_qty=1000)
        r = assess(h, flat_forecast(100))
        assert not r.is_structurally_undersupplied
        assert r.supply_coverage_ratio == pytest.approx(1.0, abs=0.08)

    def test_days_to_projected_stockout(self):
        # 500 units, 100/day demand, no replenishment -> runs out on day 5.
        h = make_history(demand=100, stock=500, received_every=None)
        r = assess(h, flat_forecast(100))
        assert r.days_to_projected_stockout == 5.0

    def test_reorder_point_exceeds_lead_time_demand(self):
        h = make_history(demand=100, stock=500, noise=20, received_every=None)
        r = assess(h, flat_forecast(100))
        assert r.reorder_point_units > r.lead_time_demand
        assert r.safety_stock_units > 0

    def test_higher_variability_means_a_bigger_buffer(self):
        calm = assess(make_history(demand=100, stock=800, noise=2, received_every=None),
                      flat_forecast(100))
        wild = assess(make_history(demand=100, stock=800, noise=45, received_every=None),
                      flat_forecast(100))
        assert wild.safety_stock_units > calm.safety_stock_units
        assert wild.demand_cv > calm.demand_cv


class TestOverstockLogic:
    def test_large_stock_is_healthy_when_demand_is_large(self):
        """10,000 units against 2,000/day demand is under two days of cover."""
        h = make_history(demand=2000, stock=10000, received_every=3, receipt_qty=6000)
        r = assess(h, flat_forecast(2000))
        assert r.risk_type != "OVERSTOCK"
        assert r.excess_units == 0

    def test_small_stock_is_overstocked_when_demand_is_tiny(self):
        """500 units against 2/day demand is 250 days of cover."""
        h = make_history(demand=2, stock=500, received_every=30, receipt_qty=60)
        r = assess(h, flat_forecast(2))
        assert r.risk_type == "OVERSTOCK"
        assert r.excess_units > 0
        assert r.inventory_coverage_days > 200

    def test_overstock_is_measured_against_the_order_up_to_level(self):
        h = make_history(demand=10, stock=10_000, received_every=30, receipt_qty=300)
        r = assess(h, flat_forecast(10))
        assert r.order_up_to_units > 0
        assert r.excess_units == pytest.approx(
            max(0.0, r.current_stock - r.order_up_to_units), abs=0.5
        )

    def test_immaterial_excess_is_not_flagged(self):
        """A day or two above the maximum is noise, not a working-capital problem."""
        h = make_history(demand=100, stock=1000, received_every=10, receipt_qty=1000)
        r = assess(h, flat_forecast(100))
        excess_days = (r.excess_units or 0) / (r.forecast_daily_demand or 1)
        if excess_days < MIN_MATERIAL_EXCESS_DAYS:
            assert r.overstock_score == 0.0

    def test_declining_demand_amplifies_overstock(self):
        base = make_history(n_days=180, demand=50, stock=6000,
                            received_every=20, receipt_qty=1000)
        falling = base.copy()
        falling.loc[falling.index[-7:], "units_sold"] = 25.0   # demand halves
        a = assess(base, flat_forecast(50))
        b = assess(falling, flat_forecast(50))
        assert b.demand_change_pct < 0
        assert b.overstock_score >= a.overstock_score


class TestBandsAndRanking:
    def test_bands_are_monotone(self):
        for bands in (STOCKOUT_BANDS, OVERSTOCK_BANDS):
            thresholds = [t for t, _ in bands]
            assert thresholds == sorted(thresholds, reverse=True)

    def test_real_panel_produces_a_graded_distribution(self, panel):
        """
        Guards against the failure mode the brief calls out: a dashboard where
        everything is red is as useless as one where nothing is.
        """
        import joblib
        from app.config import get_settings
        from app.ml.training import ARTIFACT_NAME

        path = get_settings().artifact_dir / ARTIFACT_NAME
        if not path.exists():
            pytest.skip("artifact bundle not built")
        risk = joblib.load(path)["risk"]
        counts = risk["risk_level"].value_counts()
        assert counts.get("CRITICAL", 0) < len(risk) * 0.35, "too many critical flags"
        assert counts.get("HEALTHY", 0) < len(risk) * 0.9, "nothing is being flagged"
        assert risk["risk_level"].nunique() >= 3, "bands are not discriminating"

    def test_ranking_puts_critical_first(self, panel):
        import joblib
        from app.config import get_settings
        from app.ml.training import ARTIFACT_NAME
        from app.services.data_service import DataService

        path = get_settings().artifact_dir / ARTIFACT_NAME
        if not path.exists():
            pytest.skip("artifact bundle not built")
        svc = DataService(joblib.load(path))
        ranked = svc.ranked()
        order = [r["risk_level"] for r in ranked]
        rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "HEALTHY": 4}
        assert [rank[o] for o in order] == sorted(rank[o] for o in order)

    def test_drivers_are_populated_and_quantified(self):
        h = make_history(demand=100, stock=200, received_every=None)
        r = assess(h, flat_forecast(100))
        assert len(r.drivers) >= 3
        for d in r.drivers:
            assert d.label and d.unit and d.detail
            assert d.value is None or math.isfinite(d.value)
        # The most decisive driver comes first for a stockout.
        assert r.drivers[0].name in (
            "current_stock", "days_to_projected_stockout", "inventory_coverage_days"
        )


class TestColdStart:
    def test_short_history_is_flagged_low_confidence(self):
        h = make_history(n_days=12, demand=100, stock=500, received_every=None)
        r = assess(h, flat_forecast(100), cold_start_max_days=30)
        assert r.is_cold_start
        assert r.confidence == "LOW"
        assert r.days_of_history == 12

    def test_long_history_is_high_confidence(self):
        h = make_history(n_days=180)
        r = assess(h, flat_forecast(100))
        assert not r.is_cold_start
        assert r.confidence == "HIGH"

    def test_short_history_borrows_category_variability(self):
        """
        A 12-day SKU that happens to look calm must not get a tiny safety buffer;
        the category CV should pull it up.
        """
        short = assess(
            make_history(n_days=12, demand=100, stock=500, noise=1, received_every=None),
            flat_forecast(100), category_cv=0.40,
        )
        long = assess(
            make_history(n_days=180, demand=100, stock=500, noise=1, received_every=None),
            flat_forecast(100), category_cv=0.40,
        )
        assert short.demand_cv > long.demand_cv, (
            "short history should be shrunk toward the category CV"
        )

    def test_short_history_widens_the_uncertainty(self):
        """sqrt(1 + 1/n) makes a 12-day SKU score less confidently than a 180-day one."""
        kw = dict(demand=100, stock=700, noise=25, received_every=None)
        short = assess(make_history(n_days=12, **kw), flat_forecast(100), category_cv=0.25)
        long = assess(make_history(n_days=180, **kw), flat_forecast(100), category_cv=0.25)
        # Same central case, but the short-history SKU carries more spread, so its
        # probability is pulled toward 0.5 rather than being confidently low/high.
        assert abs(short.stockout_probability - 0.5) <= abs(long.stockout_probability - 0.5) + 1e-9

    def test_category_cv_table_uses_established_skus_only(self, panel):
        est = [s for s in panel["sku_id"].unique() if not s.startswith("SKU-2")]
        table = category_cv_table(panel, est)
        assert "__global__" in table
        for cat in ("Beverages", "Snacks", "Sugar", "Pasta", "Flour"):
            assert cat in table
            assert 0 < table[cat] < 1


class TestEdgeCases:
    def test_zero_demand_does_not_divide_by_zero(self):
        h = make_history(demand=1, stock=100, received_every=None)
        r = assess(h, flat_forecast(0.0))
        assert r.stockout_probability == 0.0
        assert r.risk_level == "HEALTHY"

    def test_no_receipts_on_record(self):
        h = make_history(received_every=None)
        r = assess(h, flat_forecast(100))
        assert r.days_since_last_receipt is None
        assert r.avg_replenishment_interval_days is None
        assert r.expected_inbound_within_lead_time == 0

    def test_all_outputs_are_json_safe(self):
        h = make_history(n_days=5, demand=100, stock=0, received_every=None)
        d = assess(h, flat_forecast(100)).as_dict()
        for k, v in d.items():
            if isinstance(v, float):
                assert math.isfinite(v), f"{k} is not finite"
