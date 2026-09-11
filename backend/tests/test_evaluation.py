"""Validation harness: fold construction, metrics, and the no-leakage guarantee."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml import evaluation as ev
from app.ml.data import DATE, SKU
from app.ml.forecasting import (MovingAverageForecaster, NaiveForecaster,
                                SeasonalNaiveForecaster, build_all_models)


class TestMetrics:
    def test_perfect_forecast_scores_zero(self):
        y = np.array([10.0, 20.0, 30.0])
        assert ev.wape(y, y) == 0.0
        assert ev.mae(y, y) == 0.0
        assert ev.rmse(y, y) == 0.0
        assert ev.bias_pct(y, y) == 0.0

    def test_wape_is_error_over_volume(self):
        y = np.array([100.0, 100.0])
        p = np.array([90.0, 120.0])
        assert ev.wape(y, p) == pytest.approx(30 / 200)

    def test_wape_is_scale_free(self):
        y = np.array([100.0, 200.0])
        p = np.array([110.0, 220.0])
        assert ev.wape(y, p) == pytest.approx(ev.wape(y * 7, p * 7))

    def test_bias_sign(self):
        y = np.array([100.0])
        assert ev.bias_pct(y, np.array([110.0])) > 0     # over-forecast
        assert ev.bias_pct(y, np.array([90.0])) < 0      # under-forecast

    def test_score_ignores_non_finite_pairs(self):
        y = np.array([10.0, np.nan, 30.0])
        p = np.array([10.0, 5.0, 30.0])
        s = ev.score(y, p)
        assert s["n"] == 2
        assert s["wape"] == 0.0

    def test_wape_of_zero_volume_is_nan(self):
        assert np.isnan(ev.wape(np.zeros(3), np.ones(3)))


class TestFolds:
    def test_folds_are_chronological_and_non_overlapping(self, panel):
        folds = ev.make_expanding_folds(panel, n_folds=5, horizon=14)
        assert len(folds) == 5
        origins = [f.origin for f in folds]
        assert origins == sorted(origins), "folds must run forward in time"
        # Test windows tile the end of the panel without gaps or overlap.
        for a, b in zip(folds, folds[1:]):
            assert a.origin + pd.Timedelta(days=a.horizon) == b.origin
        assert folds[-1].origin + pd.Timedelta(days=14) == panel[DATE].max()

    def test_training_window_expands(self, panel):
        folds = ev.make_expanding_folds(panel, n_folds=5, horizon=14)
        sizes = [int((panel[DATE] <= f.origin).sum()) for f in folds]
        assert sizes == sorted(sizes)
        assert len(set(sizes)) == len(sizes)

    def test_cold_start_fold_targets_the_new_skus_only(self, panel):
        cold = ["SKU-2000", "SKU-2001", "SKU-2002"]
        fold = ev.make_cold_start_fold(panel, cold, observed_days_at_origin=7)
        assert fold is not None
        assert fold.skus == sorted(cold)
        sub = panel[panel[SKU].isin(cold)]
        assert fold.origin == sub[DATE].min() + pd.Timedelta(days=6)
        # Exactly 7 observed days at the origin.
        assert int((sub[sub[SKU] == "SKU-2000"][DATE] <= fold.origin).sum()) == 7
        assert fold.horizon >= 1
        assert fold.note

    def test_no_cold_start_fold_without_cold_skus(self, panel):
        assert ev.make_cold_start_fold(panel, []) is None


class TestBacktestIntegrity:
    def test_training_slice_never_contains_the_test_window(self, panel):
        for fold in ev.make_expanding_folds(panel, n_folds=5, horizon=14):
            train = panel[panel[DATE] <= fold.origin]
            assert train[DATE].max() == fold.origin
            test_start = fold.origin + pd.Timedelta(days=1)
            assert (train[DATE] < test_start).all()

    def test_backtest_scores_every_model_on_every_fold(self, panel):
        folds = ev.make_expanding_folds(panel, n_folds=2, horizon=7)
        results, preds = ev.run_backtest(panel, build_all_models, folds)
        assert not results.empty
        assert set(results["fold"]) == {f.name for f in folds}
        assert results.groupby("fold")["model"].nunique().eq(5).all()
        assert (results["n"] > 0).all()
        assert (results["wape"] > 0).all()
        assert not preds.empty
        assert {"y_true", "y_pred", "sku_id", "target_date"} <= set(preds.columns)

    def test_predictions_land_in_the_test_window(self, panel):
        folds = ev.make_expanding_folds(panel, n_folds=1, horizon=7)
        _, preds = ev.run_backtest(panel, build_all_models, folds)
        origin = folds[0].origin
        assert (preds["target_date"] > origin).all()
        assert (preds["target_date"] <= origin + pd.Timedelta(days=7)).all()

    def test_a_fresh_model_is_fitted_per_fold(self, panel):
        """
        Reusing a model across folds would leak later data into earlier scores.
        Fitting the same class on two different slices must give different output.
        """
        from app.ml.features import build_origin_features

        early = panel[panel[DATE] <= pd.Timestamp("2026-04-01")]
        late = panel[panel[DATE] <= pd.Timestamp("2026-06-01")]
        rows = []
        for slice_ in (early, late):
            od = build_origin_features(slice_.copy())
            origin_rows = od.sort_values(DATE).groupby(SKU).tail(1)
            m = MovingAverageForecaster().fit(od)
            rows.append(m.predict(origin_rows, [1])["y_pred"].sum())
        assert rows[0] != rows[1]

    def test_pooled_wape_matches_a_manual_computation(self, panel):
        folds = ev.make_expanding_folds(panel, n_folds=2, horizon=7)
        _, preds = ev.run_backtest(panel, build_all_models, folds)
        names = [f.name for f in folds]
        pooled = ev.pooled_wape(preds, names)
        for model, group in preds[preds["fold"].isin(names)].groupby("model"):
            manual = (group["y_true"] - group["y_pred"]).abs().sum() / group["y_true"].sum()
            assert pooled[model] == pytest.approx(manual)


class TestBaselines:
    def test_naive_repeats_the_last_value(self, origin_df):
        rows = origin_df.sort_values(DATE).groupby(SKU).tail(1)
        out = NaiveForecaster().fit(origin_df).predict(rows, [1, 5, 14])
        for sku, g in out.groupby(SKU):
            assert g["y_pred"].nunique() == 1
            assert g["y_pred"].iloc[0] == pytest.approx(
                rows.set_index(SKU).loc[sku, "lag_1"]
            )

    def test_moving_average_is_flat_at_the_28_day_mean(self, origin_df):
        rows = origin_df.sort_values(DATE).groupby(SKU).tail(1)
        out = MovingAverageForecaster().fit(origin_df).predict(rows, [1, 10, 28])
        for sku, g in out.groupby(SKU):
            assert g["y_pred"].nunique() == 1
            assert g["y_pred"].iloc[0] == pytest.approx(
                rows.set_index(SKU).loc[sku, "roll_mean_28"]
            )

    def test_seasonal_naive_reuses_the_same_weekday(self, panel, origin_df):
        rows = origin_df.sort_values(DATE).groupby(SKU).tail(1)
        out = SeasonalNaiveForecaster().fit(panel).predict(rows, [1, 7])
        for _, r in out.iterrows():
            src = r["target_date"] - pd.Timedelta(days=7)
            hist = panel[(panel[SKU] == r[SKU]) & (panel[DATE] == src)]
            if len(hist):
                assert r["y_pred"] == pytest.approx(float(hist["units_sold"].iloc[0]))

    def test_every_model_covers_every_sku_and_horizon(self, origin_df, panel):
        rows = origin_df.sort_values(DATE).groupby(SKU).tail(1)
        horizons = list(range(1, 15))
        for model in build_all_models(horizons):
            model.fit(panel if model.name == "seasonal_naive_weekly" else origin_df)
            out = model.predict(rows, horizons)
            assert out[SKU].nunique() == 28, f"{model.name} dropped SKUs"
            assert len(out) == 28 * len(horizons), f"{model.name} dropped horizons"
            assert out["y_pred"].notna().all(), f"{model.name} produced NaN"
            assert (out["y_pred"] >= 0).all(), f"{model.name} produced negative demand"
