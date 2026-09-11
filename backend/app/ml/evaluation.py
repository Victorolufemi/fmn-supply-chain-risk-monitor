"""
Rolling-origin (expanding-window) temporal validation.

Why not a random split
----------------------
A random train/test split on this panel is invalid for three compounding reasons:

1. **Leakage through rolling features.** `roll_mean_28` on a test day is computed
   from its 27 neighbours. Under a random split most of those neighbours land in
   the training set, so the model is scored on days whose own inputs it has
   already seen the answer to.
2. **It scores the wrong task.** The planner never interpolates a missing Tuesday
   between two known days. They stand on the last day of real data and look
   forward. Only a chronological split measures that.
3. **Optimistic by construction.** Random splitting lets the model learn from
   June to predict February, so any drift or regime change is invisible and the
   reported error is systematically better than production error would be.

Design
------
Five expanding-window folds. Each fold picks an origin date, trains on everything
up to and including it, then forecasts h = 1..14 from that single origin — exactly
the operational act being modelled. Fold test windows are contiguous and
non-overlapping, together covering the final 70 days of the panel.

A sixth, separately reported fold evaluates the three newly launched SKUs at an
origin where they have only 7 days of history, because the main folds sit before
those SKUs exist and would otherwise say nothing about cold start.

Primary metric: WAPE
--------------------
    WAPE = sum |y - yhat| / sum y

Chosen over MAPE and RMSE deliberately.

* MAPE is unusable here: it divides by actual demand, so a single quiet day on
  SKU-1008 (min 29 units) swamps the average, and it punishes over-forecasting
  far more than under-forecasting — the wrong asymmetry for a stockout tool.
* RMSE is dominated by the 34 demand spikes (|z| > 4) the profile identified; the
  planner does not want a model that distorts its everyday forecast to chase them.
* WAPE is unit-free, so 28 SKUs spanning 85-536 units/day aggregate honestly, and
  it reads directly as "we are off by X% of the volume we actually shipped",
  which is the sentence a supply-chain manager can act on.

MAE, RMSE and bias are reported alongside it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import DATE, DEMAND, SKU
from .features import build_origin_features

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = float(np.sum(np.abs(y_true)))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(y_true - y_pred)) / denom)


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def bias_pct(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Signed error as a share of actual volume. Positive = over-forecasting."""
    denom = float(np.sum(y_true))
    if denom == 0:
        return float("nan")
    return float(np.sum(y_pred - y_true) / denom * 100.0)


def score(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    m = np.isfinite(y_true) & np.isfinite(y_pred)
    if m.sum() == 0:
        return {"wape": float("nan"), "mae": float("nan"),
                "rmse": float("nan"), "bias_pct": float("nan"), "n": 0}
    yt, yp = y_true[m], y_pred[m]
    return {
        "wape": wape(yt, yp),
        "mae": mae(yt, yp),
        "rmse": rmse(yt, yp),
        "bias_pct": bias_pct(yt, yp),
        "n": int(m.sum()),
    }


# ---------------------------------------------------------------------------
# Fold construction
# ---------------------------------------------------------------------------
@dataclass
class Fold:
    name: str
    origin: pd.Timestamp
    horizon: int
    skus: list[str] | None = None   # None = all SKUs with enough history
    note: str = ""


def make_expanding_folds(
    panel: pd.DataFrame,
    n_folds: int = 5,
    horizon: int = 14,
) -> list[Fold]:
    """
    Contiguous, non-overlapping test windows ending on the last day of data and
    walking backwards. Fold k trains on everything up to its own origin, so the
    training set grows with each fold (expanding window).
    """
    last = panel[DATE].max()
    folds: list[Fold] = []
    for k in range(n_folds):
        origin = last - pd.Timedelta(days=horizon * (k + 1))
        folds.append(Fold(name=f"fold_{n_folds - k}", origin=origin, horizon=horizon))
    return list(reversed(folds))


def make_cold_start_fold(
    panel: pd.DataFrame,
    cold_skus: list[str],
    observed_days_at_origin: int = 7,
) -> Fold | None:
    """
    Origin placed so the new SKUs have exactly `observed_days_at_origin` days of
    history, with the remainder of their (very short) life as the test window.
    """
    if not cold_skus:
        return None
    sub = panel[panel[SKU].isin(cold_skus)]
    if sub.empty:
        return None
    first = sub[DATE].min()
    origin = first + pd.Timedelta(days=observed_days_at_origin - 1)
    last = sub[DATE].max()
    h = int((last - origin).days)
    if h < 1:
        return None
    return Fold(
        name="cold_start",
        origin=origin,
        horizon=h,
        skus=sorted(cold_skus),
        note=(f"New SKUs only, {observed_days_at_origin} days of history at the "
              f"forecast origin. Reported separately — the sample is small and "
              f"these errors are not comparable with the established-SKU folds."),
    )


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
@dataclass
class FoldResult:
    fold: str
    model: str
    origin: str
    horizon: int
    metrics: dict[str, float]
    per_horizon: dict[int, float] = field(default_factory=dict)


def run_backtest(
    panel: pd.DataFrame,
    model_factory,
    folds: list[Fold],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Evaluate every model produced by `model_factory()` over every fold.

    Critically, a *fresh* model is built and fitted inside each fold from that
    fold's training slice only. Nothing fitted on later data is ever reused.

    Returns (results_df, predictions_df).
    """
    rows: list[dict] = []
    all_preds: list[pd.DataFrame] = []

    for fold in folds:
        train_panel = panel[panel[DATE] <= fold.origin].copy()
        horizons = list(range(1, fold.horizon + 1))

        # Features for the training slice, recomputed per fold so that no rolling
        # window can reach across the origin.
        train_origin_df = build_origin_features(train_panel)

        # The forecast origin: the last row of each SKU inside the training slice.
        origin_rows = (
            train_origin_df.sort_values(DATE)
            .groupby(SKU, sort=False).tail(1)
            .reset_index(drop=True)
        )
        if fold.skus is not None:
            origin_rows = origin_rows[origin_rows[SKU].isin(fold.skus)]
        origin_rows = origin_rows[origin_rows[DATE] == fold.origin]
        if origin_rows.empty:
            log.warning("fold %s: no SKU reaches the origin %s", fold.name, fold.origin)
            continue

        # Truth: actual demand on the forecast days.
        truth = panel[(panel[DATE] > fold.origin) &
                      (panel[DATE] <= fold.origin + pd.Timedelta(days=fold.horizon))]
        truth = truth[[SKU, DATE, DEMAND]].rename(
            columns={DATE: "target_date", DEMAND: "y_true"}
        )

        for model in model_factory(horizons):
            model.fit(train_panel if model.name == "seasonal_naive_weekly"
                      else train_origin_df)
            pred = model.predict(origin_rows, horizons)
            if pred.empty:
                continue
            joined = pred.merge(truth, on=[SKU, "target_date"], how="inner")
            joined = joined[joined["y_true"].notna()]
            if joined.empty:
                continue

            m = score(joined["y_true"].values, joined["y_pred"].values)
            per_h = {
                int(h): wape(g["y_true"].values, g["y_pred"].values)
                for h, g in joined.groupby("horizon")
            }
            rows.append({
                "fold": fold.name, "model": model.name,
                "origin": str(fold.origin.date()), "horizon": fold.horizon,
                "is_baseline": model.is_baseline, "note": fold.note,
                **m,
            })
            joined["fold"] = fold.name
            joined["model"] = model.name
            all_preds.append(joined)
            log.info("fold=%s model=%-30s WAPE=%.4f MAE=%.1f n=%d",
                     fold.name, model.name, m["wape"], m["mae"], m["n"])

    results = pd.DataFrame(rows)
    preds = pd.concat(all_preds, ignore_index=True) if all_preds else pd.DataFrame()
    return results, preds


def aggregate(results: pd.DataFrame, folds: list[str]) -> pd.DataFrame:
    """
    Pool the selected folds into one WAPE per model.

    Pooled, not averaged: WAPE is a ratio of sums, so recomputing it over the
    union of fold predictions is the mathematically correct aggregation and stops
    a low-volume fold from carrying the same weight as a high-volume one.
    """
    sub = results[results["fold"].isin(folds)]
    if sub.empty:
        return pd.DataFrame()
    # Reconstruct pooled sums from per-fold MAE * n and WAPE.
    g = sub.groupby("model").apply(
        lambda d: pd.Series({
            "folds": len(d),
            "n_points": int(d["n"].sum()),
            "mae": float((d["mae"] * d["n"]).sum() / d["n"].sum()),
            "rmse": float(np.sqrt((d["rmse"] ** 2 * d["n"]).sum() / d["n"].sum())),
            "wape_mean_of_folds": float(d["wape"].mean()),
            "wape_std_of_folds": float(d["wape"].std(ddof=0)),
            "bias_pct": float((d["bias_pct"] * d["n"]).sum() / d["n"].sum()),
            "is_baseline": bool(d["is_baseline"].iloc[0]),
        }),
        include_groups=False,
    )
    return g.sort_values("wape_mean_of_folds")


def pooled_wape(preds: pd.DataFrame, folds: list[str]) -> pd.Series:
    """Exact pooled WAPE per model over the given folds, from raw predictions."""
    sub = preds[preds["fold"].isin(folds)]
    return (
        sub.groupby("model")
        .apply(lambda d: wape(d["y_true"].values, d["y_pred"].values),
               include_groups=False)
        .sort_values()
    )
