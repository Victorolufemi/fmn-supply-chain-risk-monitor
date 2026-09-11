"""
Forecasting models: three baselines and two candidates, behind one interface.

Every model implements `fit(origin_df) -> self` and
`predict(origin_rows, horizons) -> DataFrame[sku_id, horizon, y_pred]`, where
`origin_rows` holds exactly one row per SKU (the forecast origin). That uniform
shape is what makes the rolling-origin harness in `evaluation.py` able to score
a naive rule and a gradient-boosting model with identical code.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .data import CATEGORY, DATE, DEMAND, SKU
from .features import (
    CATEGORICAL_FEATURES,
    FEATURE_COLUMNS,
    attach_category_code,
    build_category_codes,
    make_supervised,
)

log = logging.getLogger(__name__)


class BaseForecaster(ABC):
    name: str = "base"
    description: str = ""
    is_baseline: bool = False

    @abstractmethod
    def fit(self, origin_df: pd.DataFrame) -> "BaseForecaster":
        ...

    @abstractmethod
    def predict(self, origin_rows: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
        ...

    @staticmethod
    def _skeleton(origin_rows: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
        out = origin_rows[[SKU, DATE]].copy()
        out = out.loc[out.index.repeat(len(horizons))].reset_index(drop=True)
        out["horizon"] = np.tile(horizons, len(origin_rows))
        out["target_date"] = out[DATE] + pd.to_timedelta(out["horizon"], unit="D")
        return out


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------
class NaiveForecaster(BaseForecaster):
    """Tomorrow looks like today. The floor any model must clear."""

    name = "naive_last_value"
    description = "Repeats the most recent observed day for every horizon."
    is_baseline = True

    def fit(self, origin_df):
        return self

    def predict(self, origin_rows, horizons):
        out = self._skeleton(origin_rows, horizons)
        last = origin_rows.set_index(SKU)["lag_1"]
        out["y_pred"] = out[SKU].map(last).astype(float)
        return out


class MovingAverageForecaster(BaseForecaster):
    """
    Flat 28-day trailing mean. Ignores the weekly shape entirely, which is exactly
    what makes it the right control for asking "is the weekly pattern worth
    modelling?".
    """

    name = "moving_average_28"
    description = "Flat forecast at the trailing 28-day mean."
    is_baseline = True

    def fit(self, origin_df):
        return self

    def predict(self, origin_rows, horizons):
        out = self._skeleton(origin_rows, horizons)
        lvl = origin_rows.set_index(SKU)["roll_mean_28"]
        out["y_pred"] = out[SKU].map(lvl).astype(float)
        return out


class SeasonalNaiveForecaster(BaseForecaster):
    """
    Value from the same weekday in the most recent complete week. The standard
    benchmark for weekly-seasonal series and, given lag-7 autocorrelation of
    0.13-0.47 in this panel, a genuinely competitive one.
    """

    name = "seasonal_naive_weekly"
    description = "Repeats the value observed on the same weekday one week ago."
    is_baseline = True

    def __init__(self) -> None:
        self._history: dict[str, pd.Series] = {}

    def fit(self, origin_df):
        self._history = {
            sku: g.set_index(DATE)[DEMAND]
            for sku, g in origin_df.groupby(SKU, sort=False)
        }
        return self

    def predict(self, origin_rows, horizons):
        out = self._skeleton(origin_rows, horizons)
        preds = []
        for sku, target in zip(out[SKU], out["target_date"]):
            s = self._history.get(sku)
            if s is None or s.empty:
                preds.append(np.nan)
                continue
            # Step back in whole weeks until we land on an observed day.
            d = target - pd.Timedelta(days=7)
            while d > s.index.max():
                d -= pd.Timedelta(days=7)
            preds.append(float(s.get(d, s.iloc[-1])))
        out["y_pred"] = preds
        return out


# ---------------------------------------------------------------------------
# Candidates
# ---------------------------------------------------------------------------
class _PooledRatioModel(BaseForecaster):
    """
    Shared machinery for the two learned models: build (origin, horizon) pairs,
    fit on the demand *ratio* y(t+h)/level(t), and multiply the predicted ratio
    back by each SKU's own trailing level at inference.
    """

    def __init__(self, horizons: list[int], min_history: int = 7) -> None:
        self.horizons = horizons
        self.min_history = min_history
        self.category_codes: dict[str, int] = {}
        self.model = None
        self.feature_columns = list(FEATURE_COLUMNS)

    def _make_matrix(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = attach_category_code(frame, self.category_codes)
        X = frame[self.feature_columns].astype(float)
        # Positional feature indices are handed to sklearn (categorical_features),
        # so the column set must match the spec exactly, once each.
        if list(X.columns) != self.feature_columns:
            raise ValueError(
                f"feature matrix columns {list(X.columns)} do not match the spec "
                f"{self.feature_columns}"
            )
        return X

    def fit(self, origin_df: pd.DataFrame):
        self.category_codes = build_category_codes(origin_df)
        train = make_supervised(
            origin_df, self.horizons, min_history=self.min_history, require_target=True
        )
        if train.empty:
            raise ValueError(f"{self.name}: no training rows after filtering")
        X = self._make_matrix(train)
        y = train["y_ratio"].astype(float)
        self.model = self._build_estimator()
        self.model.fit(X.values, y.values)
        log.info("%s fitted on %d (origin, horizon) pairs", self.name, len(train))
        return self

    def predict(self, origin_rows: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
        pairs = make_supervised(
            origin_rows, horizons, min_history=1, require_target=False
        )
        if pairs.empty:
            return pd.DataFrame(columns=[SKU, DATE, "horizon", "target_date", "y_pred"])
        X = self._make_matrix(pairs)
        ratio = self.model.predict(X.values)
        pred = np.clip(ratio, 0.0, None) * pairs["_level"].values
        out = pairs[[SKU, DATE, "horizon", "target_date"]].copy()
        out["y_pred"] = np.clip(pred, 0.0, None)
        return out

    @abstractmethod
    def _build_estimator(self):
        ...


class RidgeRatioForecaster(_PooledRatioModel):
    """
    Linear control for the gradient-boosting model. If a penalised linear map from
    the same features scores as well, the extra machinery is not earning its place.
    """

    name = "ridge_pooled_ratio"
    description = (
        "Ridge regression on the pooled demand-ratio target, with median imputation "
        "and standardised features."
    )

    def _build_estimator(self):
        return Pipeline([
            # Short-history SKUs legitimately have NaN lags; a tree splits on that
            # directly, a linear model needs them filled.
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("ridge", Ridge(alpha=1.0)),
        ])


class GradientBoostingRatioForecaster(_PooledRatioModel):
    """
    Histogram gradient boosting on the pooled ratio target.

    Chosen over a deep model deliberately: ~4.5k observations across 28 series
    cannot support a sequence network, and a tree ensemble handles the native NaNs
    of short-history SKUs, the categorical `category_code`, and the interaction
    between `horizon` and `dow_index` without manual encoding. Depth and leaf
    counts are held small for the same reason.
    """

    name = "hist_gradient_boosting_ratio"
    description = (
        "HistGradientBoostingRegressor on the pooled demand-ratio target; "
        "horizon and target weekday are inputs, so one model serves h=1..28."
    )

    def _build_estimator(self):
        return HistGradientBoostingRegressor(
            loss="absolute_error",       # matches the MAE/WAPE objective; robust to the
                                         # 34 demand spikes found in the profile
            max_iter=300,
            learning_rate=0.06,
            max_depth=4,
            max_leaf_nodes=15,
            min_samples_leaf=40,
            l2_regularization=1.0,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=25,
            categorical_features=[FEATURE_COLUMNS.index(c) for c in CATEGORICAL_FEATURES],
            random_state=42,
        )


class ColdStartRouter(BaseForecaster):
    """
    Routes each SKU to whichever model the backtest showed serves it best.

    Established SKUs (>= `cold_start_max_days` of history) go to the primary model
    selected on the main folds. Newly launched SKUs go to the fallback.

    This exists because of a specific measured result: on the cold-start fold the
    pooled gradient-boosting model was *beaten* by the plain 28-day trailing mean.
    That is mechanically unsurprising — with 7 days of history `lag_14` is missing,
    the weekday index is almost entirely the category prior, and the trailing mean
    is the more robust estimator. The evidence is thin (15 forecast points), so the
    routing is deliberately conservative: it falls back to the *simpler* model for
    the SKUs we know least about, which is the safe direction to be wrong in.

    Both members' cold-start scores are published in
    `backend/reports/model_evaluation.md`.
    """

    name = "cold_start_router"
    description = (
        "Primary model for established SKUs; a 28-day trailing mean for SKUs with "
        "less history than the cold-start threshold."
    )

    def __init__(self, primary: BaseForecaster, fallback: BaseForecaster,
                 cold_start_max_days: int) -> None:
        self.primary = primary
        self.fallback = fallback
        self.cold_start_max_days = cold_start_max_days
        self.name = f"cold_start_router[{primary.name} | {fallback.name}]"

    def fit(self, origin_df: pd.DataFrame):
        return self  # members are fitted by the caller; this only routes

    def route(self, origin_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        cold = origin_rows["days_history"] < self.cold_start_max_days
        return origin_rows[~cold], origin_rows[cold]

    def predict(self, origin_rows: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
        established, cold = self.route(origin_rows)
        parts = []
        if len(established):
            parts.append(self.primary.predict(established, horizons))
        if len(cold):
            parts.append(self.fallback.predict(cold, horizons))
        if not parts:
            return pd.DataFrame(columns=[SKU, DATE, "horizon", "target_date", "y_pred"])
        return pd.concat(parts, ignore_index=True)


def build_all_models(horizons: list[int]) -> list[BaseForecaster]:
    """Registry used by the evaluation harness. Order = report order."""
    return [
        NaiveForecaster(),
        MovingAverageForecaster(),
        SeasonalNaiveForecaster(),
        RidgeRatioForecaster(horizons),
        GradientBoostingRatioForecaster(horizons),
    ]
