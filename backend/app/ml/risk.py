"""
Inventory risk scoring.

The forecast answers "how much will we sell?". This module answers the sponsor's
actual question: "which SKU needs attention, and why?". Every quantity here is an
ordinary inventory-planning number a planner already knows, so a flag can be
argued with in a planning meeting rather than taken on trust.

Modelling inventory *position*, not just stock on hand
------------------------------------------------------
A first cut scored risk on stock on hand alone. On this dataset that flagged 13 of
28 SKUs Critical — because roughly half the catalogue is simply mid-replenishment
cycle at any moment. That is the meaningless red dashboard the brief warns about.

The dataset has no open-purchase-order table, but it does record 475 historical
deliveries, and they are regular: median inter-arrival CV 0.40 and *receipt
quantity* CV just 0.11. Replenishment is therefore modelled as an observed rate
rather than assumed away:

    replenishment_rate_per_day = units received / days, measured over a window
                                 aligned to whole delivery cycles (see
                                 `_supply_window`, which explains why a fixed
                                 window is the wrong choice here)

Over a lead time L the SKU is expected to receive `rate * L` units, with the
uncertainty of that inflow priced in (see `_supply_uncertainty`). This is an
inference from the SKU's own behaviour, clearly labelled as such throughout the
API, and `stockout_probability_no_inbound` is published alongside it for a planner
who knows nothing is actually on order.

Stockout risk
-------------
Net requirement over the lead time, treating demand and supply as independent
Normals:

    mu_net    = forecast demand over L  -  expected inflow over L
    sigma_net = sqrt(sigma_demand_L^2 + sigma_supply_L^2)
    stockout_probability = P(net requirement > stock on hand)
                         = 1 - Phi((stock - mu_net) / sigma_net)

The score IS that probability: 0.87 means "87% chance of running dry inside the
lead time". Two structural signals fall out of the same arithmetic and are
surfaced as drivers:

* `days_to_projected_stockout` — walking stock forward day by day at the forecast
  demand and the observed replenishment rate. The single most intuitive number on
  the dashboard: "you run out in 4 days".
* `supply_coverage_ratio` — units received divided by units sold over that same
  cycle-aligned window. Below 1.0 the SKU is structurally under-supplied and will
  drain no matter what today's stock looks like. The SKUs that sit well below 1.0
  in this dataset are precisely the ones with the most historical days at zero
  stock.

Overstock risk
--------------
Measured against the order-up-to level S of a periodic-review policy, never
against raw units:

    S = mu_daily * (L + R) + z * sigma_daily * sqrt(L + R)
    excess_units = max(0, stock - S)

A SKU at 10,000 units is healthy if S is 10,000; a SKU at 500 units is overstocked
if S is 200. Falling demand and a still-rising stock projection both amplify the
score, because excess against a shrinking baseline takes longer to clear.

Thresholds
----------
Bands are absolute and documented (below), not percentiles of the current panel.
Percentile banding would guarantee something is always "Critical" even in a
healthy month. The distribution the bands actually produce is printed in
`backend/reports/model_evaluation.md` so the calibration can be checked.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

RiskLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "HEALTHY"]
RiskType = Literal["STOCKOUT", "OVERSTOCK", "NONE"]

# Stockout bands read directly as probabilities of running out within the lead time.
STOCKOUT_BANDS: list[tuple[float, RiskLevel]] = [
    (0.70, "CRITICAL"),
    (0.40, "HIGH"),
    (0.20, "MEDIUM"),
    (0.08, "LOW"),
]
# Overstock bands read as a fraction above the order-up-to level.
OVERSTOCK_BANDS: list[tuple[float, RiskLevel]] = [
    (0.60, "HIGH"),
    (0.30, "MEDIUM"),
    (0.12, "LOW"),
]

MIN_MATERIAL_EXCESS_DAYS = 3.0   # excess below this is noise, not working capital
Z_SERVICE = 1.645                # 95% cycle service level
CV_SHRINK_N = 14.0               # observations before a SKU's own CV outweighs its category's
MIN_CV = 0.05                    # floor so a freak-quiet SKU cannot produce sigma = 0
SUPPLY_WINDOW_DAYS = 56          # 8 weeks, the floor for the supply-ratio window
SUPPLY_CYCLES_IN_WINDOW = 4      # ...extended to span at least this many delivery cycles
STRUCTURAL_UNDERSUPPLY = 0.95    # supply/demand below this is a standing shortfall


@dataclass
class Driver:
    """One quantified reason behind a flag, most decisive first."""

    name: str
    label: str
    value: float
    unit: str
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RiskAssessment:
    sku_id: str
    category: str
    as_of: str

    risk_level: RiskLevel
    risk_type: RiskType
    risk_score: float

    stockout_probability: float
    stockout_probability_no_inbound: float
    overstock_score: float

    current_stock: float
    forecast_daily_demand: float
    lead_time_days: float
    lead_time_demand: float
    inventory_coverage_days: float
    days_to_projected_stockout: float | None
    safety_stock_units: float
    reorder_point_units: float
    order_up_to_units: float
    suggested_order_qty: float
    excess_units: float
    excess_ratio: float

    demand_sigma_daily: float
    demand_cv: float
    recent_7d_avg_demand: float
    previous_7d_avg_demand: float | None
    demand_change_pct: float | None

    replenishment_rate_per_day: float
    expected_inbound_within_lead_time: float
    supply_coverage_ratio: float | None
    is_structurally_undersupplied: bool
    units_received_in_window: float
    supply_window_days: int
    days_since_last_receipt: float | None
    avg_replenishment_interval_days: float | None
    avg_receipt_qty: float | None
    observed_stockout_days_28d: int
    observed_stockout_rate_all_time: float

    days_of_history: int
    is_cold_start: bool
    confidence: Literal["HIGH", "MEDIUM", "LOW"]

    headline: str
    recommended_action: str
    drivers: list[Driver] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["drivers"] = [x.as_dict() if isinstance(x, Driver) else x for x in self.drivers]
        return d


# ---------------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _band(score: float, bands: list[tuple[float, RiskLevel]]) -> RiskLevel:
    for threshold, level in bands:
        if score >= threshold:
            return level
    return "HEALTHY"


def _f(x, default=0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _r(x, nd=1):
    """Round for JSON, mapping non-finite to None so the API never emits NaN."""
    if x is None:
        return None
    v = float(x)
    return round(v, nd) if math.isfinite(v) else None


def _supply_window(
    hist: pd.DataFrame,
    recv: pd.Series,
    demand: pd.Series,
    receipt_days: pd.Series,
) -> tuple[float, float, int]:
    """
    Units received and units sold over a window aligned to whole delivery cycles.

    Returns (received, sold, window_days).

    A window of a fixed number of days is the obvious choice and the wrong one.
    Deliveries are discrete and large — a median receipt here is 8-18 days of
    supply — so a fixed window either clips a delivery or catches an extra one,
    and the supply ratio swings by a third for a SKU that receives every 19 days.
    That noise alone would manufacture shortfalls that do not exist.

    Instead the window runs from the Nth-most-recent delivery to the most recent
    one, so it contains exactly N complete replenishment cycles. Supply and demand
    are then measured over the same whole number of cycles and the phase of the
    window cannot bias the ratio. The trailing partial cycle since the last
    delivery is excluded deliberately: this measures the standing balance between
    inflow and outflow, not the last few days.
    """
    n_hist = len(hist)
    dates = hist["date"]

    if len(receipt_days) >= 2:
        gaps = receipt_days.diff().dt.days.dropna()
        avg_interval = float(gaps.mean()) if len(gaps) and gaps.mean() > 0 else 0.0
        # At least SUPPLY_CYCLES_IN_WINDOW cycles, and at least
        # SUPPLY_WINDOW_DAYS of calendar time — a SKU delivered every four days
        # would otherwise be judged on a fortnight.
        cycles = SUPPLY_CYCLES_IN_WINDOW
        if avg_interval:
            cycles = max(cycles, int(math.ceil(SUPPLY_WINDOW_DAYS / avg_interval)))
        cycles = min(cycles, len(receipt_days) - 1)

        start = receipt_days.iloc[-(cycles + 1)]
        end = receipt_days.iloc[-1]
        mask = (dates > start) & (dates <= end)
        window = int((end - start).days)
        if window >= 7:
            return float(recv[mask].sum()), float(demand[mask].sum()), window

    # Too few deliveries to define a cycle (including SKUs that have never been
    # replenished at all): fall back to a plain trailing window.
    window = min(SUPPLY_WINDOW_DAYS, n_hist)
    return float(recv.tail(window).sum()), float(demand.tail(window).sum()), window


def _supply_uncertainty(
    n_expected: float, qty_mean: float, qty_std: float, gap_cv: float
) -> float:
    """
    Standard deviation of total units received over a window in which `n_expected`
    deliveries are due.

    Compound renewal process: total = sum of N deliveries of size Q.

        Var(total) = E[N] * Var(Q) + E[Q]^2 * Var(N)

    with Var(N) approximated as E[N] * gap_cv^2, the usual renewal-process result.
    Both inputs are measured from the SKU's own delivery record.
    """
    if n_expected <= 0 or qty_mean <= 0:
        return 0.0
    var_q = qty_std ** 2 if math.isfinite(qty_std) else (0.15 * qty_mean) ** 2
    var_n = n_expected * (gap_cv ** 2 if math.isfinite(gap_cv) else 0.25)
    return float(math.sqrt(n_expected * var_q + qty_mean ** 2 * var_n))


# ---------------------------------------------------------------------------
def assess_sku(
    *,
    sku_id: str,
    category: str,
    as_of: pd.Timestamp,
    history: pd.DataFrame,
    forecast: pd.Series,
    lead_time_days: float,
    category_cv: float,
    cold_start_max_days: int = 30,
    review_period_days: int = 7,
    z: float = Z_SERVICE,
) -> RiskAssessment:
    """
    Score one SKU.

    Parameters
    ----------
    history : the SKU's cleaned daily panel up to and including `as_of`.
    forecast : daily demand forecast indexed 1..H (days ahead of `as_of`).
    category_cv : median coefficient of variation of established SKUs in the same
        category — the shrinkage target for a short-history SKU's own CV.
    """
    hist = history.sort_values("date")
    n_hist = int(len(hist))
    demand = hist["units_sold"].astype(float)
    stock = _f(hist["closing_stock"].iloc[-1])

    lead_time = max(1, int(round(_f(lead_time_days, 7))))
    horizon = int(forecast.index.max()) if len(forecast) else 0

    # --- demand level over the decision window ------------------------------
    if horizon:
        forecast_daily = max(float(forecast.loc[1:min(7, horizon)].mean()), 0.0)
        in_horizon = min(lead_time, horizon)
        lead_time_demand = float(forecast.loc[1:in_horizon].sum())
        if in_horizon < lead_time:
            lead_time_demand += forecast_daily * (lead_time - in_horizon)
    else:
        forecast_daily = max(float(demand.tail(7).mean()), 0.0)
        lead_time_demand = forecast_daily * lead_time

    # --- demand variability, shrunk toward the category for short history ----
    tail28 = demand.tail(28)
    sku_std = float(tail28.std(ddof=1)) if len(tail28) >= 3 else float("nan")
    sku_mean = float(tail28.mean()) if len(tail28) else 0.0
    sku_cv = sku_std / sku_mean if (sku_mean > 0 and math.isfinite(sku_std)) else float("nan")

    w = n_hist / (n_hist + CV_SHRINK_N)
    cv = (w * sku_cv + (1 - w) * category_cv) if math.isfinite(sku_cv) else category_cv
    cv = max(cv, MIN_CV)

    sigma_daily = cv * max(forecast_daily, 1e-9)
    # sqrt(1 + 1/n): the standard inflation for estimating a level from n
    # observations. It is what makes a 12-day-old SKU score less confidently
    # without inventing an uncertainty figure.
    level_uncertainty = math.sqrt(1.0 + 1.0 / max(n_hist, 1))
    sigma_demand_lead = sigma_daily * math.sqrt(lead_time) * level_uncertainty

    # --- observed replenishment behaviour -----------------------------------
    recv = hist["units_received"].astype(float)
    receipt_days = hist.loc[recv > 0, "date"]
    days_since_receipt = (
        float((pd.Timestamp(as_of) - receipt_days.iloc[-1]).days) if len(receipt_days) else None
    )
    if len(receipt_days) >= 2:
        gaps = receipt_days.diff().dt.days.dropna()
        avg_interval = float(gaps.mean())
        gap_cv = float(gaps.std(ddof=1) / gaps.mean()) if gaps.mean() > 0 else 0.5
    else:
        avg_interval, gap_cv = None, 0.5

    units_received_window, demand_window, window = _supply_window(
        hist, recv, demand, receipt_days
    )
    replen_rate = units_received_window / window if window else 0.0
    supply_ratio = (units_received_window / demand_window) if demand_window > 0 else None
    pos = recv[recv > 0]
    avg_qty = float(pos.mean()) if len(pos) else None
    qty_std = float(pos.std(ddof=1)) if len(pos) > 1 else (0.15 * avg_qty if avg_qty else 0.0)

    expected_inbound = replen_rate * lead_time
    n_expected = (lead_time / avg_interval) if avg_interval and avg_interval > 0 else 0.0
    sigma_supply_lead = _supply_uncertainty(n_expected, avg_qty or 0.0, qty_std or 0.0, gap_cv)

    # --- stockout probability -----------------------------------------------
    mu_net = lead_time_demand - expected_inbound
    sigma_net = math.sqrt(sigma_demand_lead ** 2 + sigma_supply_lead ** 2)

    def _p(mu, sigma) -> float:
        if forecast_daily <= 0:
            return 0.0
        if sigma <= 0:
            return 1.0 if stock < mu else 0.0
        return float(min(max(1.0 - _norm_cdf((stock - mu) / sigma), 0.0), 1.0))

    stockout_p = _p(mu_net, sigma_net)
    # The conservative alternative, for a planner who knows nothing is on order.
    stockout_p_no_inbound = _p(lead_time_demand, sigma_demand_lead)

    # --- day-by-day inventory projection ------------------------------------
    days_to_stockout: float | None = None
    projected = stock
    for d in range(1, horizon + 1):
        projected += replen_rate - float(forecast.get(d, forecast_daily))
        if projected <= 0:
            days_to_stockout = float(d)
            break
    if stock <= 0 and forecast_daily > 0:
        days_to_stockout = 0.0
    projected_stock_end = stock + (replen_rate - forecast_daily) * horizon

    coverage = stock / forecast_daily if forecast_daily > 0 else float("inf")

    # --- overstock -----------------------------------------------------------
    protection = lead_time + review_period_days
    order_up_to = forecast_daily * protection + z * sigma_daily * math.sqrt(protection)
    safety_stock = z * sigma_daily * math.sqrt(lead_time)
    reorder_point = lead_time_demand + safety_stock
    excess_units = max(0.0, stock - order_up_to)
    excess_ratio = stock / order_up_to if order_up_to > 0 else 0.0
    excess_days = excess_units / forecast_daily if forecast_daily > 0 else 0.0
    suggested_order = max(0.0, order_up_to - stock - expected_inbound)

    overstock_score = float(min(max(excess_ratio - 1.0, 0.0), 1.0))

    # --- demand trend --------------------------------------------------------
    recent7 = float(demand.tail(7).mean()) if n_hist else 0.0
    prev7 = float(demand.tail(14).head(7).mean()) if n_hist >= 14 else float("nan")
    change_pct = ((recent7 - prev7) / prev7 * 100.0) if (math.isfinite(prev7) and prev7 > 0) \
        else float("nan")

    if overstock_score > 0:
        # Falling demand makes excess worse: it takes longer to clear.
        if math.isfinite(change_pct) and change_pct < 0:
            overstock_score = min(1.0, overstock_score * (1.0 + min(0.5, -change_pct / 100.0)))
        # Still accumulating (inflow above demand) makes it worse again.
        if replen_rate > forecast_daily > 0:
            overstock_score = min(1.0, overstock_score * 1.2)
    if excess_days < MIN_MATERIAL_EXCESS_DAYS:
        overstock_score = 0.0

    # --- combine -------------------------------------------------------------
    already_out = stock <= 0 and forecast_daily > 0
    # A shortfall against zero forecast demand is not a shortfall.
    undersupplied = bool(
        supply_ratio is not None
        and supply_ratio < STRUCTURAL_UNDERSUPPLY
        and forecast_daily > 0
    )

    stockout_level = _band(stockout_p, STOCKOUT_BANDS)
    overstock_level = _band(overstock_score, OVERSTOCK_BANDS)

    if already_out:
        risk_type: RiskType = "STOCKOUT"
        risk_level: RiskLevel = "CRITICAL"
        risk_score = 1.0
    elif stockout_p >= overstock_score and stockout_level != "HEALTHY":
        risk_type, risk_level, risk_score = "STOCKOUT", stockout_level, stockout_p
    elif overstock_level != "HEALTHY":
        risk_type, risk_level, risk_score = "OVERSTOCK", overstock_level, overstock_score
    else:
        risk_type, risk_level = "NONE", "HEALTHY"
        risk_score = max(stockout_p, overstock_score)

    # A standing supply shortfall is a real problem even when today's stock looks
    # comfortable, so it lifts an otherwise-quiet SKU into view — but never past
    # what the probability itself justifies.
    if undersupplied and risk_type != "OVERSTOCK" and risk_level in ("HEALTHY", "LOW"):
        risk_type = "STOCKOUT"
        risk_level = "MEDIUM" if risk_level == "LOW" else "LOW"
        risk_score = max(risk_score, 0.10)

    stockout_days_28 = int(hist.tail(28)["is_stockout_day"].sum()) \
        if "is_stockout_day" in hist.columns else 0
    stockout_rate_all = float(hist["is_stockout_day"].mean()) \
        if "is_stockout_day" in hist.columns else 0.0

    is_cold = n_hist < cold_start_max_days
    confidence = "HIGH" if n_hist >= 90 else ("MEDIUM" if n_hist >= cold_start_max_days else "LOW")

    ctx = dict(
        risk_type=risk_type, already_out=already_out, stock=stock, coverage=coverage,
        lead_time=lead_time, forecast_daily=forecast_daily,
        lead_time_demand=lead_time_demand, safety_stock=safety_stock,
        reorder_point=reorder_point, order_up_to=order_up_to,
        excess_units=excess_units, excess_days=excess_days, change_pct=change_pct,
        cv=cv, stockout_p=stockout_p, stockout_p_no_inbound=stockout_p_no_inbound,
        stockout_days_28=stockout_days_28, stockout_rate_all=stockout_rate_all,
        days_since_receipt=days_since_receipt, replen_rate=replen_rate,
        expected_inbound=expected_inbound, supply_ratio=supply_ratio,
        supply_window=window,
        undersupplied=undersupplied, days_to_stockout=days_to_stockout,
        projected_stock_end=projected_stock_end, horizon=horizon,
        avg_interval=avg_interval, avg_qty=avg_qty, suggested_order=suggested_order,
    )
    drivers = _build_drivers(ctx)
    headline, action = _headline_and_action(risk_level, ctx)

    return RiskAssessment(
        sku_id=sku_id, category=category, as_of=str(pd.Timestamp(as_of).date()),
        risk_level=risk_level, risk_type=risk_type, risk_score=round(risk_score, 4),
        stockout_probability=round(stockout_p, 4),
        stockout_probability_no_inbound=round(stockout_p_no_inbound, 4),
        overstock_score=round(overstock_score, 4),
        current_stock=_r(stock), forecast_daily_demand=_r(forecast_daily),
        lead_time_days=float(lead_time), lead_time_demand=_r(lead_time_demand),
        inventory_coverage_days=_r(coverage, 2) if math.isfinite(coverage) else None,
        days_to_projected_stockout=days_to_stockout,
        safety_stock_units=_r(safety_stock), reorder_point_units=_r(reorder_point),
        order_up_to_units=_r(order_up_to), suggested_order_qty=_r(suggested_order),
        excess_units=_r(excess_units), excess_ratio=_r(excess_ratio, 3),
        demand_sigma_daily=_r(sigma_daily), demand_cv=_r(cv, 3),
        recent_7d_avg_demand=_r(recent7),
        previous_7d_avg_demand=_r(prev7), demand_change_pct=_r(change_pct),
        replenishment_rate_per_day=_r(replen_rate),
        expected_inbound_within_lead_time=_r(expected_inbound),
        supply_coverage_ratio=_r(supply_ratio, 3),
        is_structurally_undersupplied=undersupplied,
        units_received_in_window=_r(units_received_window),
        supply_window_days=int(window),
        days_since_last_receipt=days_since_receipt,
        avg_replenishment_interval_days=_r(avg_interval),
        avg_receipt_qty=_r(avg_qty),
        observed_stockout_days_28d=stockout_days_28,
        observed_stockout_rate_all_time=round(stockout_rate_all, 3),
        days_of_history=n_hist, is_cold_start=is_cold, confidence=confidence,
        headline=headline, recommended_action=action, drivers=drivers,
    )


# ---------------------------------------------------------------------------
def _build_drivers(k: dict) -> list[Driver]:
    """Quantified reasons, most decisive first. This list is the LLM's evidence."""
    d: list[Driver] = []
    rt, cov = k["risk_type"], k["coverage"]
    cov_v = round(cov, 2) if math.isfinite(cov) else None

    if rt == "STOCKOUT" or k["stockout_p"] >= 0.08:
        if k["already_out"]:
            d.append(Driver(
                "current_stock", "Stock on hand", _r(k["stock"]), "units",
                "Already at zero — every unit of demand from here is a lost sale.",
            ))
        if k["days_to_stockout"] is not None:
            d.append(Driver(
                "days_to_projected_stockout", "Days until projected stockout",
                k["days_to_stockout"], "days",
                f"Stock walked forward day by day at the forecast demand of "
                f"{k['forecast_daily']:.0f} units/day and the observed "
                f"replenishment rate of {k['replen_rate']:.0f} units/day. "
                f"Lead time is {k['lead_time']:.0f} days.",
            ))
        d.append(Driver(
            "inventory_coverage_days", "Inventory coverage", cov_v, "days",
            f"Stock on hand divided by forecast daily demand of "
            f"{k['forecast_daily']:.1f} units, against a "
            f"{k['lead_time']:.0f}-day lead time.",
        ))
        if k["undersupplied"] and k["supply_ratio"] is not None:
            d.append(Driver(
                "supply_coverage_ratio",
                f"Supply vs demand (last {k['supply_window']:.0f} days)",
                round(k["supply_ratio"], 3), "ratio",
                f"Only {k['supply_ratio'] * 100:.0f} units received for every 100 "
                f"sold over the last {k['supply_window']:.0f} days, a window "
                f"covering whole delivery cycles. Inventory is structurally "
                f"draining, independent of today's stock level.",
            ))
        d.append(Driver(
            "lead_time_demand", "Forecast demand over lead time",
            _r(k["lead_time_demand"]), "units",
            f"Model forecast summed over the next {k['lead_time']:.0f} days.",
        ))
        d.append(Driver(
            "expected_inbound_within_lead_time", "Expected inbound in lead time",
            _r(k["expected_inbound"]), "units",
            "Inferred from this SKU's own delivery record"
            + (f" (about one delivery of {k['avg_qty']:.0f} units every "
               f"{k['avg_interval']:.1f} days)" if k["avg_qty"] and k["avg_interval"] else "")
            + ". The dataset has no open purchase orders, so this is an estimate, "
              "not confirmed stock.",
        ))
        d.append(Driver(
            "reorder_point_units", "Reorder point", _r(k["reorder_point"]), "units",
            f"Lead-time demand plus a {k['safety_stock']:.0f}-unit safety buffer "
            f"for demand variability at a 95% service level.",
        ))
        if k["stockout_days_28"] > 0:
            d.append(Driver(
                "observed_stockout_days_28d", "Days at zero stock (last 28)",
                float(k["stockout_days_28"]), "days",
                f"This SKU has been at zero on {k['stockout_rate_all'] * 100:.0f}% "
                f"of all days on record.",
            ))

    if rt == "OVERSTOCK" or k["excess_days"] >= 1:
        d.append(Driver(
            "excess_units", "Stock above the order-up-to level",
            _r(k["excess_units"]), "units",
            f"About {k['excess_days']:.1f} days of demand more than the policy "
            f"maximum of {k['order_up_to']:.0f} units, which already allows for a "
            f"{k['lead_time']:.0f}-day lead time plus a review cycle.",
        ))
        d.append(Driver(
            "inventory_coverage_days", "Inventory coverage", cov_v, "days",
            f"Against a {k['lead_time']:.0f}-day lead time.",
        ))
        if k["replen_rate"] > k["forecast_daily"] > 0:
            d.append(Driver(
                "replenishment_rate_per_day", "Replenishment rate",
                _r(k["replen_rate"]), "units/day",
                f"Still arriving faster than the {k['forecast_daily']:.0f} units/day "
                f"being sold, so the excess is growing.",
            ))

    if k["change_pct"] is not None and math.isfinite(k["change_pct"]):
        d.append(Driver(
            "demand_change_pct", "Recent demand change", round(k["change_pct"], 1), "%",
            f"Last 7 days versus the 7 before — demand is "
            f"{'up' if k['change_pct'] >= 0 else 'down'}.",
        ))
    d.append(Driver(
        "demand_cv", "Demand variability", round(k["cv"], 3), "ratio",
        "Standard deviation divided by mean daily demand; drives the safety buffer.",
    ))
    if k["days_since_receipt"] is not None:
        d.append(Driver(
            "days_since_last_receipt", "Days since last delivery",
            float(k["days_since_receipt"]), "days",
            "How long since inventory was last replenished.",
        ))
    return d


def _headline_and_action(risk_level: RiskLevel, k: dict) -> tuple[str, str]:
    """
    Deterministic fallback wording, used ONLY when the LLM is unavailable.

    This is not the product's explanation — `explanation_service` generates that at
    runtime through Anthropic. This exists so the dashboard degrades to something
    truthful instead of a blank card.
    """
    cov = k["coverage"]
    cov_s = f"{cov:.1f}" if math.isfinite(cov) else "unlimited"
    if k["already_out"]:
        return (
            "Out of stock now",
            f"Expedite a replenishment. Demand is forecast at "
            f"{k['forecast_daily']:.0f} units/day and a new order takes "
            f"{k['lead_time']:.0f} days to arrive.",
        )
    if k["risk_type"] == "STOCKOUT":
        extra = ""
        if k["undersupplied"] and k["supply_ratio"] is not None:
            extra = (f" Deliveries are running at {k['supply_ratio'] * 100:.0f}% of "
                     f"units sold, so stock is draining structurally.")
        action = (
            f"Raise a replenishment order of about {k['suggested_order']:.0f} units "
            f"to reach the order-up-to level of {k['order_up_to']:.0f} units.{extra}"
        )

        # When the immediate picture is comfortable, saying "14 days of cover
        # against a 10-day lead time" would leave the planner wondering why the
        # SKU is flagged at all. Lead with the reason that actually raised it.
        cover_is_comfortable = (
            math.isfinite(cov) and cov >= k["lead_time"]
            and (k["days_to_stockout"] is None or k["days_to_stockout"] > k["lead_time"])
        )
        if k["undersupplied"] and k["supply_ratio"] is not None and cover_is_comfortable:
            return (
                f"Receiving only {k['supply_ratio'] * 100:.0f} units for every 100 "
                f"sold — stock is draining",
                action,
            )

        when = (f"projected to run out in {k['days_to_stockout']:.0f} days"
                if k["days_to_stockout"] is not None
                else f"{cov_s} days of cover")
        return (f"{when}, against a {k['lead_time']:.0f}-day lead time", action)
    if k["risk_type"] == "OVERSTOCK":
        return (
            f"{k['excess_days']:.1f} days of demand above the policy maximum",
            f"Hold or cut the next order. Stock is {k['stock']:.0f} units against an "
            f"order-up-to level of {k['order_up_to']:.0f} units.",
        )
    return (
        f"{cov_s} days of cover, within policy",
        "No action needed. Continue normal replenishment.",
    )


def category_cv_table(panel: pd.DataFrame, established_skus: list[str]) -> dict[str, float]:
    """
    Median coefficient of variation per category, from established SKUs only.

    This is the shrinkage target that lets a 12-day-old SKU inherit a credible
    variability estimate from products that behave like it.
    """
    est = panel[panel["sku_id"].isin(established_skus)]
    per_sku = est.groupby(["category", "sku_id"])["units_sold"].agg(["mean", "std"])
    per_sku["cv"] = per_sku["std"] / per_sku["mean"].replace(0, np.nan)
    out = per_sku.groupby("category")["cv"].median().to_dict()
    return {"__global__": float(per_sku["cv"].median()),
            **{k: float(v) for k, v in out.items()}}
