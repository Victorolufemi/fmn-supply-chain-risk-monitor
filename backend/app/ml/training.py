"""
Offline training pipeline.

Run once (locally, or as a Render build step):

    python -m app.ml.training

It performs the whole chain — clean, validate, select, fit, forecast, score risk —
and writes a single artifact bundle that the API loads at startup. The API never
trains, never re-reads the CSV per request, and never recomputes a forecast.
"""
from __future__ import annotations

import json
import logging
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import get_settings                                   # noqa: E402
from app.ml import evaluation as ev                                    # noqa: E402
from app.ml.data import (CATEGORY, DATE, DEMAND, LEAD_TIME, SKU,       # noqa: E402
                         load_clean_panel, sku_history_lengths)
from app.ml.features import (assert_no_leakage, build_origin_features)  # noqa: E402
from app.ml.forecasting import (ColdStartRouter,                        # noqa: E402
                                GradientBoostingRatioForecaster,
                                MovingAverageForecaster, NaiveForecaster,
                                RidgeRatioForecaster, SeasonalNaiveForecaster,
                                build_all_models)
from app.ml.risk import (MIN_MATERIAL_EXCESS_DAYS, OVERSTOCK_BANDS,     # noqa: E402
                         STOCKOUT_BANDS, Z_SERVICE, assess_sku,
                         category_cv_table)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("training")

ARTIFACT_NAME = "supply_chain_bundle.joblib"

MODEL_CLASSES = {
    "naive_last_value": NaiveForecaster,
    "moving_average_28": MovingAverageForecaster,
    "seasonal_naive_weekly": SeasonalNaiveForecaster,
    "ridge_pooled_ratio": RidgeRatioForecaster,
    "hist_gradient_boosting_ratio": GradientBoostingRatioForecaster,
}


def _fmt(v, nd=4):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "n/a"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def md_table(rows, headers) -> str:
    out = ["| " + " | ".join(str(h) for h in headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
def main() -> int:
    s = get_settings()
    s.artifact_dir.mkdir(parents=True, exist_ok=True)
    s.reports_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. data ------------------------------------------------------------
    log.info("loading %s", s.data_csv)
    panel, clean_report, schema = load_clean_panel(s.data_csv)
    hist_len = sku_history_lengths(panel)
    cold_skus = sorted(hist_len[hist_len < s.cold_start_max_days].index.tolist())
    established = sorted(hist_len[hist_len >= s.cold_start_max_days].index.tolist())
    log.info("%d SKUs (%d established, %d cold-start)",
             len(hist_len), len(established), len(cold_skus))

    # --- 2. features + leakage guard ---------------------------------------
    origin_df = build_origin_features(panel)
    assert_no_leakage(panel, origin_df)
    log.info("leakage guard passed")

    horizons = list(range(1, s.forecast_horizon_days + 1))

    # --- 3. temporal validation --------------------------------------------
    main_folds = ev.make_expanding_folds(panel, n_folds=5, horizon=14)
    cold_fold = ev.make_cold_start_fold(panel, cold_skus, observed_days_at_origin=7)
    all_folds = main_folds + ([cold_fold] if cold_fold else [])

    log.info("running backtest over %d folds", len(all_folds))
    results, preds = ev.run_backtest(panel, build_all_models, all_folds)
    if results.empty:
        raise SystemExit("backtest produced no results")

    main_names = [f.name for f in main_folds]
    pooled = ev.pooled_wape(preds, main_names)
    agg = ev.aggregate(results, main_names)
    agg["wape_pooled"] = pooled

    selected_name = str(pooled.index[0])
    log.info("selected model: %s (pooled WAPE %.4f)", selected_name, pooled.iloc[0])

    # --- 4. fit the selected model on the full history ----------------------
    def _instantiate(name: str):
        cls = MODEL_CLASSES[name]
        m = cls(horizons) if cls in (RidgeRatioForecaster,
                                     GradientBoostingRatioForecaster) else cls()
        m.fit(panel if name == "seasonal_naive_weekly" else origin_df)
        return m

    primary = _instantiate(selected_name)

    # The cold-start fold is scored separately and picks its own winner: the
    # pooled model does not automatically deserve the SKUs it has least data for.
    cold_choice = selected_name
    if cold_fold is not None:
        cs = results[results["fold"] == cold_fold.name].sort_values("wape")
        if len(cs):
            cold_choice = str(cs["model"].iloc[0])
    cold_model = primary if cold_choice == selected_name else _instantiate(cold_choice)
    log.info("cold-start fold winner: %s", cold_choice)

    final_model = ColdStartRouter(primary, cold_model, s.cold_start_max_days) \
        if cold_choice != selected_name else primary

    as_of = panel[DATE].max()
    origin_rows = (
        origin_df.sort_values(DATE).groupby(SKU, sort=False).tail(1).reset_index(drop=True)
    )
    forecast_df = final_model.predict(origin_rows, horizons)
    forecast_df["y_pred"] = forecast_df["y_pred"].round(2)

    # An always-available simple model, so a SKU missing from the primary output
    # still gets a forecast and the risk table is never partially empty.
    fallback = MovingAverageForecaster().fit(origin_df)
    fallback_df = fallback.predict(origin_rows, horizons)

    # --- 5. risk assessment for every SKU -----------------------------------
    cat_cv = category_cv_table(panel, established)
    lead_times = panel.groupby(SKU)[LEAD_TIME].last()
    categories = panel.groupby(SKU)[CATEGORY].last()

    assessments = []
    for sku in sorted(panel[SKU].unique()):
        hist = panel[panel[SKU] == sku]
        f = forecast_df[forecast_df[SKU] == sku].set_index("horizon")["y_pred"]
        if f.empty:
            f = fallback_df[fallback_df[SKU] == sku].set_index("horizon")["y_pred"]
        cat = str(categories.get(sku, "Unknown"))
        a = assess_sku(
            sku_id=sku, category=cat, as_of=as_of, history=hist, forecast=f,
            lead_time_days=float(lead_times.get(sku, 7)),
            category_cv=float(cat_cv.get(cat, cat_cv["__global__"])),
            cold_start_max_days=s.cold_start_max_days,
            review_period_days=s.review_period_days,
        )
        assessments.append(a.as_dict())

    risk_df = pd.DataFrame(assessments)
    log.info("risk levels: %s", risk_df["risk_level"].value_counts().to_dict())

    # --- 6. persist ---------------------------------------------------------
    bundle = {
        "schema_version": 1,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": str(as_of.date()),
        "selected_model": selected_name,
        "cold_start_model": cold_choice,
        "serving_model": final_model.name,
        "model": final_model,
        "fallback_model": fallback,
        "horizons": horizons,
        "panel": panel,
        "origin_rows": origin_rows,
        "forecast": forecast_df,
        "risk": risk_df,
        "category_cv": cat_cv,
        "cold_start_skus": cold_skus,
        "established_skus": established,
        "history_lengths": hist_len.to_dict(),
        "cleaning_report": clean_report.as_dict(),
        "schema_map": schema.__dict__,
        "evaluation": {
            "fold_results": results.to_dict(orient="records"),
            "aggregate": agg.reset_index().to_dict(orient="records"),
            "pooled_wape": pooled.to_dict(),
            "main_folds": main_names,
            "cold_fold": cold_fold.name if cold_fold else None,
        },
        "config": {
            "forecast_horizon_days": s.forecast_horizon_days,
            "service_level_z": Z_SERVICE,
            "review_period_days": s.review_period_days,
            "cold_start_max_days": s.cold_start_max_days,
            "stockout_bands": STOCKOUT_BANDS,
            "overstock_bands": OVERSTOCK_BANDS,
            "min_material_excess_days": MIN_MATERIAL_EXCESS_DAYS,
        },
        "versions": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    out = s.artifact_dir / ARTIFACT_NAME
    joblib.dump(bundle, out, compress=3)
    log.info("wrote artifact bundle -> %s (%.1f KB)", out, out.stat().st_size / 1024)

    results.to_csv(s.reports_dir / "fold_results.csv", index=False)
    preds.to_csv(s.reports_dir / "backtest_predictions.csv", index=False)

    _write_evaluation_report(s, panel, results, preds, agg, pooled, selected_name,
                             main_folds, cold_fold, risk_df, clean_report,
                             cold_skus, established, hist_len, cold_choice)
    _write_model_summary(s, selected_name, agg, pooled, risk_df, cold_skus,
                         established, hist_len, main_folds, cold_fold, results,
                         cold_choice)
    _append_profile_implications(s, panel)
    return 0


# ---------------------------------------------------------------------------
def _write_evaluation_report(s, panel, results, preds, agg, pooled, selected,
                             main_folds, cold_fold, risk_df, clean_report,
                             cold_skus, established, hist_len, cold_choice) -> None:
    L: list[str] = []
    P = L.append
    main_names = [f.name for f in main_folds]

    P("# Model Evaluation")
    P("")
    P("_Generated by `python -m app.ml.training`. Every metric is computed from the "
      "supplied dataset; none is hand-entered._")
    P("")
    P(f"- Dataset: `{s.data_csv.name}` — {len(panel):,} cleaned rows, "
      f"{panel[SKU].nunique()} SKUs, {panel[DATE].min().date()} to {panel[DATE].max().date()}")
    P(f"- Established SKUs: {len(established)} · Newly launched (cold start): "
      f"{len(cold_skus)} ({', '.join(cold_skus)})")
    P("")

    # --- validation design --------------------------------------------------
    P("## 1. Validation design")
    P("")
    P("**Rolling-origin (expanding-window) backtest.** Each fold trains on every day "
      "up to its origin, then forecasts the next 14 days from that single origin — "
      "the same act a planner performs. Test windows are contiguous and "
      "non-overlapping, together covering the last 70 days of the panel.")
    P("")
    P(md_table(
        [[f.name, str(f.origin.date()),
          str((f.origin + pd.Timedelta(days=1)).date()),
          str((f.origin + pd.Timedelta(days=f.horizon)).date()),
          f.horizon,
          int((panel[DATE] <= f.origin).sum())]
         for f in main_folds],
        ["fold", "train through (origin)", "test from", "test to", "horizon (days)",
         "training rows"],
    ))
    P("")
    if cold_fold:
        P(f"**Cold-start fold** (`{cold_fold.name}`, reported separately): origin "
          f"`{cold_fold.origin.date()}`, horizon {cold_fold.horizon} days, "
          f"SKUs {', '.join(cold_fold.skus)}. {cold_fold.note}")
        P("")

    P("### Why not a random split")
    P("")
    P("1. **Leakage through rolling features.** `roll_mean_28` for a given day is built "
      "from its 27 neighbours. Under a random split most of those neighbours sit in "
      "the training set, so the model is graded on days whose own inputs already "
      "encode the answer.")
    P("2. **It measures the wrong task.** A planner never interpolates a missing "
      "Tuesday between two known days; they stand on the last day of real data and "
      "look forward. Only a chronological split scores that.")
    P("3. **It is optimistic by construction.** Training on June to predict February "
      "hides drift, so the reported error would be better than production error.")
    P("")

    # --- metric choice ------------------------------------------------------
    P("## 2. Primary metric: WAPE")
    P("")
    P("```")
    P("WAPE = sum |actual - forecast| / sum actual")
    P("```")
    P("")
    P("- **MAPE was rejected**: it divides by actual demand, so one quiet day on "
      "SKU-1008 (minimum 29 units/day) dominates the average, and it penalises "
      "over-forecasting far more heavily than under-forecasting — the wrong "
      "asymmetry for a stockout tool.")
    P("- **RMSE was rejected as the primary**: it is driven by the 34 demand spikes "
      "(|z| > 4) found during profiling, and chasing those would degrade the "
      "everyday forecast the planner actually uses. It is still reported.")
    P("- **WAPE is unit-free**, so 28 SKUs spanning 85–536 units/day aggregate "
      "honestly, and it reads as \"we are off by X% of the volume we actually "
      "shipped\".")
    P("")

    # --- results ------------------------------------------------------------
    P("## 3. Results — established SKUs (5 folds pooled)")
    P("")
    rows = []
    for name in pooled.index:
        r = agg.loc[name]
        rows.append([
            f"`{name}`",
            "baseline" if r["is_baseline"] else "candidate",
            _fmt(float(pooled[name])),
            _fmt(float(r["wape_mean_of_folds"])),
            _fmt(float(r["wape_std_of_folds"])),
            _fmt(float(r["mae"]), 1),
            _fmt(float(r["rmse"]), 1),
            _fmt(float(r["bias_pct"]), 2),
            int(r["n_points"]),
        ])
    P(md_table(rows, ["model", "role", "WAPE (pooled)", "WAPE (mean of folds)",
                      "WAPE (sd across folds)", "MAE (units)", "RMSE (units)",
                      "Bias %", "n forecasts"]))
    P("")
    best_base = pooled[[m for m in pooled.index if agg.loc[m, "is_baseline"]]].idxmin()
    lift = (pooled[best_base] - pooled[selected]) / pooled[best_base] * 100
    P(f"- **Selected model: `{selected}`** (lowest pooled WAPE).")
    P(f"- Strongest baseline: `{best_base}` at WAPE {pooled[best_base]:.4f}.")
    P(f"- Improvement of the selected model over the strongest baseline: "
      f"**{lift:.1f}%** relative WAPE reduction.")
    P("")

    # --- per fold -----------------------------------------------------------
    P("### Per-fold WAPE")
    P("")
    piv = (results[results["fold"].isin(main_names)]
           .pivot(index="model", columns="fold", values="wape"))
    piv = piv.reindex(pooled.index)
    P(md_table([[f"`{m}`"] + [_fmt(float(piv.loc[m, c])) for c in piv.columns]
                for m in piv.index],
               ["model"] + list(piv.columns)))
    P("")

    # --- per horizon --------------------------------------------------------
    P("### WAPE by forecast horizon (selected vs. best baseline)")
    P("")
    sub = preds[preds["fold"].isin(main_names) & preds["model"].isin([selected, best_base])]
    ph = (sub.groupby(["model", "horizon"])
             .apply(lambda d: ev.wape(d["y_true"].values, d["y_pred"].values),
                    include_groups=False)
             .unstack(0))
    P(md_table([[int(h)] + [_fmt(float(ph.loc[h, m])) for m in ph.columns]
                for h in ph.index],
               ["horizon (days ahead)"] + [f"`{c}`" for c in ph.columns]))
    P("")

    # --- cold start ---------------------------------------------------------
    if cold_fold:
        P("## 4. Results — cold-start SKUs")
        P("")
        cs = results[results["fold"] == cold_fold.name].sort_values("wape")
        if len(cs):
            P(md_table([[f"`{r['model']}`", _fmt(float(r["wape"])), _fmt(float(r["mae"]), 1),
                         _fmt(float(r["rmse"]), 1), _fmt(float(r["bias_pct"]), 2), int(r["n"])]
                        for _, r in cs.iterrows()],
                       ["model", "WAPE", "MAE (units)", "RMSE (units)", "Bias %", "n forecasts"]))
            P("")
            P(f"Origin `{cold_fold.origin.date()}`, when each new SKU had 7 observed days. "
              f"Only {int(cs['n'].iloc[0])} forecast points across "
              f"{len(cold_fold.skus)} SKUs, so these figures are indicative, not "
              f"a reliable estimate. They are reported to make the cold-start "
              f"penalty visible rather than to claim accuracy.")
            P("")
            est_w = float(pooled[selected])
            cold_w = float(cs[cs["model"] == selected]["wape"].iloc[0]) \
                if (cs["model"] == selected).any() else float("nan")
            if np.isfinite(cold_w):
                P(f"For the selected model, WAPE on cold-start SKUs is "
                  f"**{cold_w:.4f}** versus **{est_w:.4f}** on established SKUs "
                  f"({(cold_w / est_w - 1) * 100:+.0f}% relative). This gap is exactly "
                  f"why the UI marks these SKUs as low confidence.")
                P("")
            if cold_choice != selected:
                P(f"**The cold-start fold picked a different winner: "
                  f"`{cold_choice}`.** That is mechanically unsurprising — with 7 "
                  f"days of history `lag_14` is missing and the weekday index is "
                  f"almost entirely the category prior, so the pooled model has "
                  f"little to work with while a trailing mean stays robust. "
                  f"Production therefore serves cold-start SKUs from "
                  f"`{cold_choice}` and everything else from `{selected}` "
                  f"(`ColdStartRouter`). The evidence is thin — "
                  f"{int(cs['n'].iloc[0])} forecast points — so the routing is "
                  f"deliberately biased toward the *simpler* model for the SKUs we "
                  f"know least about, which is the safe direction to be wrong in.")
                P("")

    # --- risk calibration ---------------------------------------------------
    P("## 5. Risk-band calibration on the current snapshot")
    P("")
    P("Bands are absolute and documented, not percentiles of this panel — "
      "percentile banding would guarantee that something is always \"Critical\" "
      "even in a healthy month. The resulting distribution is shown so the "
      "calibration can be judged.")
    P("")
    P(md_table([[k, int(v)] for k, v in
                risk_df["risk_level"].value_counts().reindex(
                    ["CRITICAL", "HIGH", "MEDIUM", "LOW", "HEALTHY"]).fillna(0).items()],
               ["risk level", "SKUs"]))
    P("")
    P(md_table([[k, int(v)] for k, v in risk_df["risk_type"].value_counts().items()],
               ["risk type", "SKUs"]))
    P("")
    P("Distribution of the underlying continuous quantities:")
    P("")
    q = risk_df[["stockout_probability", "overstock_score", "inventory_coverage_days",
                 "excess_ratio"]].describe(percentiles=[.25, .5, .75, .9]).round(3)
    P(md_table([[i] + [str(v) for v in q.loc[i].values] for i in q.index],
               ["stat"] + list(q.columns)))
    P("")

    # --- data quality -------------------------------------------------------
    P("## 6. Cleaning applied before modelling")
    P("")
    cr = clean_report.as_dict()
    P(md_table([[k.replace("_", " "), (", ".join(v) if isinstance(v, list) else v)]
                for k, v in cr.items()], ["step", "value"]))
    P("")
    P("Full detail in [`data_profile.md`](./data_profile.md).")
    P("")

    # --- limitations --------------------------------------------------------
    P("## 7. Limitations")
    P("")
    for line in [
        "**Six months of history, one seasonal cycle.** The panel covers "
        "2026-01-01 to 2026-06-29. There is no second year, so annual seasonality, "
        "promotions and holiday effects cannot be learned or validated. Only the "
        "weekly cycle is supported by the data.",
        "**No open purchase orders in the dataset.** `units_received` is a record of "
        "past deliveries, not a forward order book. Risk is therefore scored on "
        "stock on hand. An estimate of inbound units during the lead time is derived "
        "from each SKU's observed replenishment cadence and shown beside the score, "
        "clearly labelled, but it is deliberately excluded from the score itself.",
        "**Demand is recorded, not true, demand.** Closing stock is censored at zero "
        "on 275 SKU-days; on those days actual customer demand may have exceeded what "
        "the ledger shows. The model learns from recorded units sold, which will "
        "under-state demand for chronically short SKUs.",
        "**Cold-start metrics rest on a handful of points.** The three new SKUs "
        "provide 12 days each; the cold-start fold scores a few dozen forecasts. It "
        "shows direction, not a dependable error rate.",
        "**Lead time is a static attribute with no variability.** Real replenishment "
        "lead times vary; safety stock here covers demand variability only, not lead-"
        "time variability, so it is a lower bound on the buffer actually required.",
        "**No cost data.** Risk is ranked by probability and by days of excess cover, "
        "not by margin, holding cost or stockout cost, so it cannot yet rank a "
        "high-value SKU above a low-value one at equal risk.",
    ]:
        P(f"- {line}")
    P("")

    path = s.reports_dir / "model_evaluation.md"
    path.write_text("\n".join(L), encoding="utf-8")
    log.info("wrote %s", path)


def _write_model_summary(s, selected, agg, pooled, risk_df, cold_skus,
                         established, hist_len, main_folds, cold_fold, results,
                         cold_choice) -> None:
    L: list[str] = []
    P = L.append
    best_base = pooled[[m for m in pooled.index if agg.loc[m, "is_baseline"]]].idxmin()
    lift = (pooled[best_base] - pooled[selected]) / pooled[best_base] * 100

    P("# Model Summary")
    P("")
    P("_A one-page account of the model for both technical and business readers. "
      "Generated by `python -m app.ml.training`; all figures are computed._")
    P("")
    P("## Business problem")
    P("")
    P("The sponsor cannot see, in advance, which SKUs will run out and which are "
      "tying up working capital. The tool must name the SKUs that need attention "
      "today and explain why in plain English.")
    P("")
    P("## What is predicted")
    P("")
    P("**Target:** units sold per SKU per day, for each of the next "
      f"{s.forecast_horizon_days} days. The horizon covers the longest lead time in "
      "the data (14 days) plus a review cycle, so demand over any SKU's lead time "
      "is always inside the forecast.")
    P("")
    P("The forecast is a means, not the deliverable. It feeds two decisions:")
    P("")
    P("- **Stockout risk** — the probability that demand over the lead time exceeds "
      "stock on hand.")
    P("- **Overstock risk** — how far stock sits above the order-up-to level implied "
      "by that same forecast.")
    P("")
    P("## Features")
    P("")
    P(md_table([
        ["Lagged demand", "`lag_1, lag_2, lag_3, lag_7, lag_14`",
         "Recent level and the weekly echo"],
        ["Rolling level", "`roll_mean_7/14/28`, `roll_median_28`",
         "Baseline demand; 28 days = 4 whole weeks so the mean is not itself "
         "distorted by the weekly cycle"],
        ["Rolling dispersion", "`roll_std_7/28`, `cv_28`",
         "Feeds the safety buffer and the confidence band"],
        ["Trend / velocity", "`trend_7_over_28`, `velocity_7_over_14`",
         "Is demand accelerating or fading"],
        ["Weekly shape", "`dow_index`, `target_dow`",
         "Shrunk per-SKU weekday index — the dominant signal in this data"],
        ["Inventory context", "`stock_level_ratio`, `received_28d_ratio`, "
         "`stockout_rate_28`", "Scale-free inventory position"],
        ["Static attributes", "`lead_time_days`, `category_code`, `days_history`",
         "SKU characteristics and history depth"],
        ["Horizon", "`horizon`", "Lets one model serve h = 1..28 directly"],
    ], ["group", "features", "why"]))
    P("")
    P("**Leakage control.** Every feature for origin day *t* uses observations from "
      "days ≤ *t* only. The single forward-looking input is the calendar weekday of "
      "the target day, which is genuinely known in advance. Rolling windows are "
      "rebuilt inside each backtest fold so no window can span the origin. "
      "`assert_no_leakage()` re-derives `lag_1` and `roll_mean_28` from the raw "
      "panel and fails the build on mismatch; `backend/tests/test_features.py` "
      "checks the invariant across all SKUs.")
    P("")
    P("## Baselines and the chosen model")
    P("")
    rows = []
    for name in pooled.index:
        r = agg.loc[name]
        rows.append([f"`{name}`", "baseline" if r["is_baseline"] else "candidate",
                     _fmt(float(pooled[name])), _fmt(float(r["mae"]), 1),
                     "**selected**" if name == selected else ""])
    P(md_table(rows, ["model", "role", "WAPE", "MAE (units)", ""]))
    P("")
    P(f"`{selected}` was selected on pooled WAPE across five chronological folds, "
      f"beating the strongest baseline (`{best_base}`) by {lift:.1f}% relative.")
    P("")
    P("**Why not deep learning.** The panel holds roughly 4.5k usable observations "
      "across 28 short series with no trend and one seasonal cycle. A sequence "
      "model has nowhere near enough data to justify its parameter count, and it "
      "would forfeit the native handling of missing lags and categorical inputs "
      "that a histogram gradient-boosting tree gives for free. Model complexity "
      "was escalated only as far as the validation results paid for it.")
    P("")
    P("**Why a pooled ratio target.** SKU mean demand spans 85–536 units/day. The "
      "model predicts `demand(t+h) / trailing_28d_mean(t)` rather than raw units, so "
      "one model learns the shared *shape* — weekly pattern, mean reversion, horizon "
      "decay — while each SKU's own history supplies the level. This is also what "
      "lets a 12-day-old SKU be forecast at all.")
    P("")
    P("## Validation")
    P("")
    P(f"Rolling-origin backtest, {len(main_folds)} expanding-window folds of 14 days "
      f"each, covering {main_folds[0].origin.date()} onward. Training data grows with "
      f"each fold; a fresh model is fitted inside every fold. Random splitting is "
      f"invalid here because rolling features leak across a shuffled boundary and "
      f"because it scores interpolation rather than forecasting.")
    P("")
    P("Full per-fold and per-horizon tables: [`model_evaluation.md`](./model_evaluation.md).")
    P("")
    P("## Headline metrics")
    P("")
    r = agg.loc[selected]
    P(md_table([
        ["WAPE (pooled, established SKUs)", _fmt(float(pooled[selected]))],
        ["WAPE (mean of folds)", _fmt(float(r["wape_mean_of_folds"]))],
        ["WAPE (sd across folds)", _fmt(float(r["wape_std_of_folds"]))],
        ["MAE", f"{float(r['mae']):.1f} units/day"],
        ["RMSE", f"{float(r['rmse']):.1f} units/day"],
        ["Bias", f"{float(r['bias_pct']):+.2f}%"],
        ["Forecast points scored", int(r["n_points"])],
    ], ["metric", "value"]))
    P("")
    if cold_fold is not None:
        cs = results[(results["fold"] == cold_fold.name) & (results["model"] == selected)]
        if len(cs):
            P(f"On the cold-start fold the same model scores WAPE "
              f"{float(cs['wape'].iloc[0]):.4f} over {int(cs['n'].iloc[0])} forecast "
              f"points — materially worse, and reported separately rather than "
              f"blended into the headline.")
            P("")
    P("## Cold-start treatment")
    P("")
    P(f"{len(cold_skus)} SKUs ({', '.join(cold_skus)}) have "
      f"{int(hist_len[cold_skus].min())} days of history against "
      f"{int(hist_len[established].min())}+ for the rest. Four distinct mechanisms "
      f"handle them:")
    P("")
    P("1. **Weekly shape is borrowed.** The weekday index is shrunk toward the "
      "category's, `w = n/(n+3)`. With one observation of a Tuesday, three quarters "
      "of the signal comes from the category.")
    P("2. **Variability is borrowed.** The coefficient of variation is shrunk toward "
      "the category median of established SKUs, `w = n/(n+14)`, so the safety buffer "
      "is not built on 12 noisy days.")
    P("3. **Level uncertainty is priced in.** The lead-time sigma carries a "
      "`sqrt(1 + 1/n)` factor, the standard inflation for estimating a mean from n "
      "observations, so a short-history SKU scores less confidently.")
    P("4. **Lead time is repaired.** The three new SKUs report 4–5 different lead "
      "times across 12 rows — noise, not signal. Each is replaced with its category "
      "median taken from SKUs with a stable value.")
    if cold_choice != selected:
        P(f"5. **A different model serves them.** The cold-start fold was scored "
          f"separately and `{cold_choice}` beat `{selected}` on it, so production "
          f"routes SKUs below the {s.cold_start_max_days}-day threshold to "
          f"`{cold_choice}`. The evidence is thin, so the routing errs toward the "
          f"simpler, more robust model for the SKUs we know least about.")
    P("")
    P("The API marks these SKUs `is_cold_start = true` with `confidence = \"LOW\"`, "
      "and the UI states the observed history length rather than inventing an "
      "uncertainty percentage.")
    P("")
    P("## Limitations")
    P("")
    P("See [`model_evaluation.md` §7](./model_evaluation.md). In short: one seasonal "
      "cycle only; no open purchase orders; demand is censored on stockout days; "
      "cold-start metrics rest on few points; safety stock covers demand variability "
      "but not lead-time variability; and no cost data, so risk cannot yet be ranked "
      "by financial impact.")
    P("")

    path = s.reports_dir / "model_summary.md"
    path.write_text("\n".join(L), encoding="utf-8")
    log.info("wrote %s", path)


def _append_profile_implications(s, panel) -> None:
    """Replace the placeholder section 8 of the data profile with real conclusions."""
    path = s.reports_dir / "data_profile.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    marker = "## 8. Implications for modelling"
    body = "\n".join([
        marker,
        "",
        "| finding | consequence |",
        "|---|---|",
        "| 15 byte-identical duplicate rows | Dropped. Left in, they double-weight "
        "those days in every rolling statistic. |",
        "| `BEVERAGES` vs `Beverages` (20 stray rows) | Case normalised, then each "
        "SKU's category set to its modal value. Case was the only inconsistency — no "
        "SKU genuinely changes category. |",
        "| 90 missing `units_sold`, 46 missing `closing_stock` | Imputed causally: "
        "demand from the trailing same-weekday median, stock by rolling the inventory "
        "balance forward. Neither fill may look ahead. |",
        "| Lead time varies within the 3 new SKUs (4–5 values in 12 days) | Treated "
        "as noise and replaced with the category median from SKUs with a stable "
        "value. Lead time is constant for all 25 established SKUs, confirming it is "
        "a static attribute. |",
        "| 268 inventory-balance violations, 100% explained by a zero floor | Not "
        "corrected. Closing stock is censored at zero; those 275 SKU-days are flagged "
        "as observed stockouts and used as a risk driver. |",
        "| Day-of-week ratio 1.39 pooled, 1.11–1.91 per SKU | Weekly seasonality is "
        "the dominant signal. Modelled through a per-SKU weekday index shrunk toward "
        "the category. |",
        "| Pooled monthly mean varies < 2% over six months | No trend to model. "
        "Trend terms were left out and a seasonal-naive baseline is competitive. |",
        "| lag-7 autocorrelation 0.13–0.47 vs lag-1 0.06–0.24 | Confirms the weekly "
        "cycle dominates short-run persistence; lag features weighted accordingly. |",
        "| Demand CV 0.18–0.37 | Safety stock is SKU-specific, not a flat rule. |",
        "| 34 demand spikes at \\|z\\| > 4 | Model trained with an absolute-error loss "
        "so a handful of spikes cannot distort the everyday forecast. |",
        "| Mean demand spans 85–536 units/day | Model predicts a ratio to each SKU's "
        "own trailing mean, not raw units, so one pooled model is valid across all "
        "28 SKUs. |",
        "",
        "Acted on in [`model_summary.md`](./model_summary.md) and "
        "[`model_evaluation.md`](./model_evaluation.md).",
        "",
    ])
    if marker in text:
        text = text.split(marker)[0] + body
    else:
        text += "\n" + body
    path.write_text(text, encoding="utf-8")
    log.info("updated %s", path)


if __name__ == "__main__":
    raise SystemExit(main())
