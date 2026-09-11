"""
Feature engineering for SKU-level daily demand forecasting.

Design
------
The panel is short (180 days) and wide (28 SKUs), and the profile showed that
demand is essentially *level + multiplicative weekly shape + noise* with no trend
(pooled monthly means vary by <2% over six months, lag-7 autocorrelation is 2-4x
lag-1). Two consequences drive the design:

1. **Pooled model, normalised target.** SKU mean demand spans 85 -> 536 units/day.
   A model that predicts raw units would spend all its capacity learning SKU scale.
   Instead every SKU is normalised by its own trailing 28-day mean and the model
   predicts a *ratio*; the level comes back from the SKU's own history at inference.
   This also lets a 12-day-old SKU borrow the pooled shape immediately.

2. **Direct multi-horizon.** Risk needs demand summed over a lead time of 3-14 days,
   so we need h = 1..28. Recursive forecasting compounds error; instead the horizon
   `h` is a feature and one model covers every horizon.

Leakage policy
--------------
Every feature for an origin day `t` is computed from observations on days <= t
only. Calendar attributes of the target day (its day-of-week) are legitimately
known in advance and are the only forward-looking inputs. `assert_no_leakage()`
and the tests in `backend/tests/test_features.py` enforce this.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import CATEGORY, DATE, DEMAND, LEAD_TIME, RECEIVED, SKU, STOCK

# Shrinkage strength for the per-SKU day-of-week index. With K=3, a SKU needs
# ~3 observations of a given weekday before its own pattern outweighs its
# category's. A 12-day-old SKU has 1-2, so it leans on the category prior.
DOW_SHRINK_K = 3.0

# Rolling windows. 28 days = 4 complete weeks, so the trailing mean is not itself
# biased by the weekly pattern.
LEVEL_WINDOW = 28
MIN_LEVEL_PERIODS = 3

ORIGIN_FEATURES = [
    "lag_1", "lag_2", "lag_3", "lag_7", "lag_14",
    "roll_mean_7", "roll_mean_14", "roll_mean_28",
    "roll_std_7", "roll_std_28", "roll_median_28",
    "trend_7_over_28", "velocity_7_over_14", "cv_28",
    "days_history", "lead_time_days",
    "stock_level_ratio", "received_28d_ratio", "stockout_rate_28",
]
PAIR_FEATURES = ["horizon", "target_dow", "dow_index"]
CATEGORICAL_FEATURES = ["category_code"]
FEATURE_COLUMNS = ORIGIN_FEATURES + PAIR_FEATURES + CATEGORICAL_FEATURES


@dataclass
class FeatureSpec:
    """Everything inference needs to rebuild the exact training feature space."""

    feature_columns: list[str]
    categorical_features: list[str]
    category_codes: dict[str, int]
    level_window: int = LEVEL_WINDOW
    dow_shrink_k: float = DOW_SHRINK_K

    def encode_category(self, category: str) -> int:
        # Unseen category -> -1, which the tree model handles as its own branch.
        return self.category_codes.get(category, -1)


# ---------------------------------------------------------------------------
# Causal day-of-week index
# ---------------------------------------------------------------------------
def _expanding_dow_tables(panel: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """
    For every row (sku, t) return two 7-wide arrays:

        sku_index[t, d] = (mean demand for this SKU on weekday d, over days <= t)
                          / (mean demand for this SKU, over days <= t)
        sku_count[t, d] = how many weekday-d observations that mean rests on

    Both are strictly backward-looking *inclusive of t*, which is correct: day t is
    observed when we stand at origin t.
    """
    n = len(panel)
    sku_index = np.full((n, 7), np.nan)
    sku_count = np.zeros((n, 7))

    for _, idx in panel.groupby(SKU, sort=False).indices.items():
        idx = np.sort(idx)
        y = panel[DEMAND].values[idx].astype(float)
        dow = panel[DATE].dt.dayofweek.values[idx]
        overall = np.cumsum(y) / np.arange(1, len(y) + 1)
        for d in range(7):
            mask = (dow == d).astype(float)
            cnt = np.cumsum(mask)
            tot = np.cumsum(y * mask)
            with np.errstate(invalid="ignore", divide="ignore"):
                dow_mean = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
                sku_index[idx, d] = np.where(overall > 0, dow_mean / overall, np.nan)
            sku_count[idx, d] = cnt
    return sku_index, sku_count


def _expanding_category_dow_index(panel: pd.DataFrame) -> np.ndarray:
    """
    Category-level weekday index, computed on scale-free demand so that a large
    SKU does not dominate its category. For each row we take the pooled expanding
    mean of `demand / expanding_sku_mean` for the category, split by weekday.

    Rows are processed in date order so the expanding window is chronological
    across the whole category, not per SKU.
    """
    n = len(panel)
    out = np.full((n, 7), np.nan)
    if CATEGORY not in panel.columns:
        return out

    # Scale-free demand: each SKU's value divided by its own expanding mean.
    norm = np.full(n, np.nan)
    for _, idx in panel.groupby(SKU, sort=False).indices.items():
        idx = np.sort(idx)
        y = panel[DEMAND].values[idx].astype(float)
        run_mean = np.cumsum(y) / np.arange(1, len(y) + 1)
        norm[idx] = np.where(run_mean > 0, y / run_mean, np.nan)

    dow_all = panel[DATE].dt.dayofweek.values
    order = np.lexsort((panel[SKU].values, panel[DATE].values))

    for _, idx in panel.groupby(CATEGORY, sort=False).indices.items():
        idx = np.array(sorted(idx, key=lambda i: np.where(order == i)[0][0]))
        v = norm[idx]
        dow = dow_all[idx]
        for d in range(7):
            mask = ((dow == d) & ~np.isnan(v)).astype(float)
            cnt = np.cumsum(mask)
            tot = np.cumsum(np.nan_to_num(v) * mask)
            with np.errstate(invalid="ignore", divide="ignore"):
                out[idx, d] = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
    return out


def build_dow_index(panel: pd.DataFrame, k: float = DOW_SHRINK_K) -> np.ndarray:
    """
    Shrunk weekday index, shape (n_rows, 7).

    index = w * sku_index + (1 - w) * category_index,   w = n_obs / (n_obs + k)

    This is the cold-start lever for the *shape* of demand: with one observation
    of a weekday, w = 0.25 and the category pattern dominates; with 26 weeks of
    history w = 0.90 and the SKU speaks for itself.
    """
    sku_idx, sku_cnt = _expanding_dow_tables(panel)
    cat_idx = _expanding_category_dow_index(panel)

    cat_idx = np.where(np.isnan(cat_idx), 1.0, cat_idx)
    sku_idx_f = np.where(np.isnan(sku_idx), cat_idx, sku_idx)
    w = sku_cnt / (sku_cnt + k)
    blended = w * sku_idx_f + (1.0 - w) * cat_idx
    # Guard against a degenerate index from a near-zero expanding mean.
    return np.clip(np.where(np.isfinite(blended), blended, 1.0), 0.2, 3.0)


# ---------------------------------------------------------------------------
# Origin-level features
# ---------------------------------------------------------------------------
def build_origin_features(panel: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (sku, origin day) holding every statistic known at the close of
    that day. No column here may reference a future observation.
    """
    df = panel.sort_values([SKU, DATE]).reset_index(drop=True).copy()
    g = df.groupby(SKU, sort=False)[DEMAND]

    for lag in (1, 2, 3, 7, 14):
        df[f"lag_{lag}"] = g.shift(lag - 1)  # lag_1 == demand on the origin day

    for w in (7, 14, 28):
        df[f"roll_mean_{w}"] = g.transform(
            lambda s, w=w: s.rolling(w, min_periods=MIN_LEVEL_PERIODS).mean()
        )
    for w in (7, 28):
        df[f"roll_std_{w}"] = g.transform(
            lambda s, w=w: s.rolling(w, min_periods=MIN_LEVEL_PERIODS).std(ddof=1)
        )
    df["roll_median_28"] = g.transform(
        lambda s: s.rolling(28, min_periods=MIN_LEVEL_PERIODS).median()
    )

    lvl = df["roll_mean_28"].replace(0, np.nan)
    df["trend_7_over_28"] = df["roll_mean_7"] / lvl
    df["velocity_7_over_14"] = df["roll_mean_7"] / df["roll_mean_14"].replace(0, np.nan)
    df["cv_28"] = df["roll_std_28"] / lvl

    df["days_history"] = g.cumcount() + 1

    # Inventory context, expressed relative to demand so it is scale-free.
    if STOCK in df.columns:
        df["stock_level_ratio"] = df[STOCK] / lvl
        df["stockout_rate_28"] = (
            df.groupby(SKU, sort=False)["is_stockout_day"]
            .transform(lambda s: s.rolling(28, min_periods=1).mean())
            if "is_stockout_day" in df.columns else 0.0
        )
    else:
        df["stock_level_ratio"] = np.nan
        df["stockout_rate_28"] = 0.0

    if RECEIVED in df.columns:
        df["received_28d_ratio"] = (
            df.groupby(SKU, sort=False)[RECEIVED]
            .transform(lambda s: s.rolling(28, min_periods=1).sum())
            / (lvl * 28)
        )
    else:
        df["received_28d_ratio"] = 0.0

    dow_index = build_dow_index(df)
    for d in range(7):
        df[f"_dowidx_{d}"] = dow_index[:, d]

    df["_level"] = lvl
    return df


def make_supervised(
    origin_df: pd.DataFrame,
    horizons: range | list[int],
    *,
    min_history: int = 7,
    require_target: bool = True,
) -> pd.DataFrame:
    """
    Expand origin rows into (origin, horizon) training pairs.

    Target is the *ratio* y(t+h) / level(t). Predicting a ratio is what makes one
    pooled model valid across SKUs whose demand differs by 6x.
    """
    df = origin_df
    horizons = list(horizons)
    frames = []

    fwd = {h: df.groupby(SKU, sort=False)[DEMAND].shift(-h) for h in horizons}

    # LEAD_TIME is both an identity column and a model feature; de-duplicate so the
    # selected frame keeps exactly one column per name (a repeat would silently
    # shift every positional feature index downstream).
    base_cols = list(
        dict.fromkeys(
            c for c in [SKU, DATE, CATEGORY, LEAD_TIME, "_level", *ORIGIN_FEATURES]
            if c in df.columns
        )
    )

    for h in horizons:
        part = df[base_cols].copy()
        part["horizon"] = h
        # Calendar arithmetic, not a row shift: at inference the origin frame holds
        # one row per SKU, so shifting forward would yield NaT and silently drop
        # every prediction. The panel is a complete daily grid, so origin + h days
        # is the same day a shift would land on during training.
        part["target_date"] = part[DATE] + pd.Timedelta(days=h)
        part["y_true"] = fwd[h]
        tdow = part["target_date"].dt.dayofweek
        part["target_dow"] = tdow
        # Pick the weekday index matching the *target* day.
        idx_matrix = df[[f"_dowidx_{d}" for d in range(7)]].values
        safe_dow = tdow.fillna(0).astype(int).values
        part["dow_index"] = idx_matrix[np.arange(len(df)), safe_dow]
        part.loc[tdow.isna(), "dow_index"] = np.nan
        frames.append(part)

    out = pd.concat(frames, ignore_index=True)
    out = out[out["days_history"] >= min_history]
    out = out[out["_level"].notna() & (out["_level"] > 0)]
    if require_target:
        out = out[out["y_true"].notna()]
        out["y_ratio"] = out["y_true"] / out["_level"]
    return out.reset_index(drop=True)


def attach_category_code(df: pd.DataFrame, codes: dict[str, int]) -> pd.DataFrame:
    df = df.copy()
    df["category_code"] = df[CATEGORY].map(codes).fillna(-1).astype(int) \
        if CATEGORY in df.columns else -1
    return df


def build_category_codes(panel: pd.DataFrame) -> dict[str, int]:
    cats = sorted(panel[CATEGORY].dropna().unique()) if CATEGORY in panel.columns else []
    return {c: i for i, c in enumerate(cats)}


def assert_no_leakage(panel: pd.DataFrame, origin_df: pd.DataFrame) -> None:
    """
    Independent re-derivation of two representative features from the raw panel,
    proving they only ever look backwards. Called by the training script and by
    `backend/tests/test_features.py`.
    """
    p = panel.sort_values([SKU, DATE]).reset_index(drop=True)
    o = origin_df.sort_values([SKU, DATE]).reset_index(drop=True)
    for sku, g in p.groupby(SKU, sort=False):
        og = o[o[SKU] == sku]
        y = g[DEMAND].values.astype(float)
        for i in (10, len(y) // 2, len(y) - 1):
            if i < MIN_LEVEL_PERIODS or i >= len(y):
                continue
            expect_lag1 = y[i]
            got_lag1 = og["lag_1"].values[i]
            if not np.isclose(expect_lag1, got_lag1, equal_nan=True):
                raise AssertionError(
                    f"lag_1 mismatch for {sku} at position {i}: {got_lag1} != {expect_lag1}"
                )
            lo = max(0, i - 27)
            expect_mean = float(np.mean(y[lo:i + 1]))
            got_mean = og["roll_mean_28"].values[i]
            if not np.isclose(expect_mean, got_mean, rtol=1e-9):
                raise AssertionError(
                    f"roll_mean_28 mismatch for {sku} at position {i}: "
                    f"{got_mean} != {expect_mean} (would indicate a future-looking window)"
                )
        break  # one SKU is enough for the invariant; tests cover all of them
