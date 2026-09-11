# Supply Chain Risk Monitor — How It Works

A complete walkthrough of the system: what every feature does, how it is
computed, and why it was built that way.

This document is the **reference**. [`README.md`](../README.md) is the shorter
project overview; [`backend/reports/`](../backend/reports/) holds the generated
data profile, model evaluation and model summary. Every figure quoted here is
computed from the supplied dataset and reproduced by
`python -m app.ml.training`.

---

## Contents

1. [The problem, and how it was translated](#1-the-problem-and-how-it-was-translated)
2. [The system in one picture](#2-the-system-in-one-picture)
3. [Stage 1 — Loading and cleaning the data](#3-stage-1--loading-and-cleaning-the-data)
4. [Stage 2 — Feature engineering](#4-stage-2--feature-engineering)
5. [Stage 3 — Forecasting](#5-stage-3--forecasting)
6. [Stage 4 — Validation](#6-stage-4--validation)
7. [Stage 5 — The risk engine](#7-stage-5--the-risk-engine)
8. [Stage 6 — The artifact bundle](#8-stage-6--the-artifact-bundle)
9. [The API, endpoint by endpoint](#9-the-api-endpoint-by-endpoint)
10. [AI explanations](#10-ai-explanations)
11. [Grounded Q&A](#11-grounded-qa)
12. [The interface, screen by screen](#12-the-interface-screen-by-screen)
13. [Loading, empty and error states](#13-loading-empty-and-error-states)
14. [Performance](#14-performance)
15. [Security](#15-security)
16. [Testing](#16-testing)
17. [Running it](#17-running-it)
18. [Deployment](#18-deployment)
19. [Field glossary](#19-field-glossary)
20. [Limitations](#20-limitations)

---

## 1. The problem, and how it was translated

The sponsor's brief:

> "We keep getting caught off guard — some SKUs run out and delay production,
> others sit overstocked and tie up working capital. I don't have anything today
> that tells me, ahead of time, which SKUs need attention and why."

That is not a forecasting request. It is a **triage** request that happens to need
a forecast. The measurable question the system actually answers is:

> For each SKU, what is the probability that demand over the replenishment lead
> time exceeds what will be available — and how far is stock above the maximum
> the replenishment policy justifies?

| Sponsor's words | What the system computes |
|---|---|
| "which SKUs need attention" | A ranked list: severity first, then how soon stock runs out |
| "some SKUs run out" | `stockout_probability` — chance of running dry inside the lead time |
| "others sit overstocked" | `excess_units` above the order-up-to level implied by the forecast |
| "ahead of time" | A 28-day daily demand forecast per SKU |
| "and why" | Ranked quantified drivers, plus an LLM explanation written from them |

**The forecast is a means, not the deliverable.** No planner acts on "we expect
179 units a day". They act on *"you have 0.6 days of cover against a 3-day lead
time, and you're receiving 76 units for every 100 you sell."*

---

## 2. The system in one picture

```
project1_supply_chain_demand.csv   (4,551 raw rows, 28 SKUs, 180 days)
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│  OFFLINE   python -m app.ml.training     (runs once)     │
│                                                          │
│  data.py       detect schema → clean → audit             │
│  features.py   leakage-safe features, ratio target       │
│  evaluation.py 5 rolling-origin folds + cold-start fold  │
│  forecasting.py 3 baselines + 2 candidates → pick winner │
│  risk.py       score all 28 SKUs                         │
│                                                          │
│  → models/supply_chain/supply_chain_bundle.joblib (~250KB)│
│  → backend/reports/*.md                                  │
└──────────────────────────────────────────────────────────┘
        │  loaded once at process start
        ▼
┌──────────────────────────────────────────────────────────┐
│  ONLINE    FastAPI                                       │
│  data_service      serves slices of the bundle           │
│  explanation_svc   evidence → Anthropic → grounding check│
│  qa_service        intent → retrieval → Anthropic        │
└──────────────────────────────────────────────────────────┘
        │  REST / JSON
        ▼
┌──────────────────────────────────────────────────────────┐
│  Next.js — renders only. No ML, no thresholds, no secrets│
└──────────────────────────────────────────────────────────┘
```

**The split that matters.** The frontend contains no risk arithmetic, no
thresholds, no model files and no API keys. Every number it shows was computed by
the backend. This is enforced by an automated check
(`scripts/final_check.py`), not just by convention.

**Nothing is trained or recomputed per request.** Training happens once, offline.
The API loads a single artifact bundle at startup and serves slices of it.

---

## 3. Stage 1 — Loading and cleaning the data

`backend/app/ml/data.py`

### 3.1 Column roles are detected, not assumed

The brief warned against assuming column names, so `detect_schema()` infers them
from content:

- **Date column** — the non-numeric column that parses most reliably as a date
  and has many distinct values.
- **SKU column** — the column that best partitions the table into date-unique
  panels (an entity key has almost no duplicate dates within a group).
- **Numeric roles** — matched by name fragments (`sold`/`demand`, `receiv`,
  `stock`/`inventory`, `lead`) with content-based fallbacks.
- **Category** — a low-cardinality non-numeric column that is not the ID.

A test renames *every* column (`date` → `BusinessDate`, `sku_id` → `Item Code`,
and so on) and confirms detection still resolves each role correctly.

### 3.2 What profiling found, and what was done about it

Seven issues materially affect modelling. Each is handled explicitly and audited
through `GET /api/metadata`.

| # | Finding | Evidence | Response |
|---|---|---|---|
| 1 | **15 byte-identical duplicate rows** | 4 SKUs had 181–182 rows over a 180-day span | Dropped. Left in, they double-weight those days in every rolling statistic. |
| 2 | **Category case inconsistency** | `BEVERAGES` vs `Beverages` — 20 stray rows across 16 SKUs | Case normalised, then each SKU's category set to its **modal** value. Case was the only inconsistency; no SKU genuinely changes category. |
| 3 | **Missing values** | 90 `units_sold` (1.98%), 46 `closing_stock` (1.01%), spread evenly across months | Imputed **causally** — see §3.3. |
| 4 | **Lead time is noise for the 3 new SKUs** | They report 4–5 different lead times in 12 rows; all 25 established SKUs report exactly one | Replaced with the category median taken from SKUs with a stable value. |
| 5 | **Closing stock is censored at zero** | 268 inventory-balance violations — **100%** on days where the balance would have gone negative and stock was recorded as 0 | Not "corrected". Those 277 SKU-days are flagged as observed stockouts and used as a risk driver. |
| 6 | **Weekly seasonality, no trend** | Day-of-week ratio 1.39 pooled (1.11–1.91 per SKU); lag-7 autocorrelation 0.13–0.47 vs lag-1 0.06–0.24; pooled monthly mean varies < 2% over six months | Model the weekly shape; no trend terms. |
| 7 | **Demand spikes** | 34 observations at \|z\| > 4 | Train with absolute-error loss so spikes cannot distort the everyday forecast. |

### 3.3 Causal imputation

A fill for day *t* must never use data from after *t* — otherwise the model is
quietly trained on the future.

- **Demand** is filled with the SKU's **trailing same-weekday median**, computed
  only from days strictly before *t*. It falls back to the trailing overall
  median, then to a back-fill for a leading gap.
- **Stock** is filled by rolling the inventory balance forward:
  `stock[t] = max(0, stock[t-1] + received[t] - sold[t])`. The `max(0, …)`
  mirrors the censoring already present in the source.
- **Receipts** fill with 0 — a missing receipt means no delivery was logged.
- A SKU with **no** observed demand at all falls back to its category median,
  then the global median, so one unusable series cannot leave NaNs that break
  every downstream rolling window.

**Proof it is causal:** `test_demand_imputation_is_causal` truncates the panel at
2026-04-30, re-imputes from scratch, and asserts every filled value for the
remaining days is byte-identical. A fill that peeked forward would move.

### 3.4 The balance audit

The inventory identity is
`closing_stock[t] = closing_stock[t-1] + units_received[t] - units_sold[t]`.

The audit runs **before** imputation and only on days where all four inputs are
observed — otherwise it would count residuals our own fills created and overstate
the source data's problems. Result: **268 violations, 268 of them (100%)** on
days where the balance would have gone negative and stock was recorded as zero.

This is not noise, it is a signal: closing stock is **censored at zero**. Those
277 SKU-days become `is_stockout_day = 1` and feed the risk drivers.

### 3.5 Output

A tidy, gap-free daily panel — every SKU reindexed onto a complete daily grid
over its own observed span, so `lag_7` always means "seven calendar days ago" —
plus a `CleaningReport` that is exposed verbatim through the API.

---

## 4. Stage 2 — Feature engineering

`backend/app/ml/features.py`

### 4.1 The two design decisions

**A pooled model on a ratio target.** SKU mean demand spans 85 → 536 units/day.
A model predicting raw units would spend its capacity learning SKU scale.
Instead the target is:

```
y = units_sold(t + h) / trailing_28d_mean(t)
```

One pooled model learns the shared *shape* — weekly pattern, mean reversion,
horizon decay — while each SKU's own history supplies the level. This is also
what makes a 12-day-old SKU forecastable at all.

**Direct multi-horizon.** Risk needs demand summed over a 3–14 day lead time.
Recursive forecasting compounds error, so `horizon` is a feature and **one model
serves h = 1…28**.

### 4.2 The feature set

23 features in total.

| Group | Features | Why |
|---|---|---|
| Lagged demand | `lag_1, lag_2, lag_3, lag_7, lag_14` | Recent level and the weekly echo |
| Rolling level | `roll_mean_7`, `roll_mean_14`, `roll_mean_28`, `roll_median_28` | 28 days = 4 whole weeks, so the mean is not itself distorted by the weekly cycle |
| Rolling dispersion | `roll_std_7`, `roll_std_28`, `cv_28` | Feeds the safety buffer and the confidence band |
| Trend / velocity | `trend_7_over_28`, `velocity_7_over_14` | Is demand accelerating or fading |
| Weekly shape | `dow_index`, `target_dow` | Shrunk per-SKU weekday index — the dominant signal in this data |
| Inventory context | `stock_level_ratio`, `received_28d_ratio`, `stockout_rate_28` | Scale-free inventory position |
| Static attributes | `lead_time_days`, `category_code`, `days_history` | SKU characteristics and history depth |
| Horizon | `horizon` | Lets one model serve every horizon |

### 4.3 The weekday index — and how cold start rides on it

`dow_index` is the single most important engineered feature, because weekly
seasonality dominates this dataset. It is built **causally and with shrinkage**:

```
sku_index[t, d]  = (mean demand for this SKU on weekday d, days ≤ t)
                   ÷ (mean demand for this SKU, days ≤ t)

cat_index[t, d]  = same, pooled across the category, computed on scale-free
                   demand so a large SKU cannot dominate its category

dow_index        = w · sku_index + (1 − w) · cat_index,     w = n / (n + 3)
```

`n` is how many times that weekday has been observed for that SKU. With one
observation, `w = 0.25` and the category pattern supplies three quarters of the
signal. With 26 weeks of history, `w = 0.90` and the SKU speaks for itself.

**This is the cold-start mechanism for demand shape** — it needs no special
casing, it falls out of the shrinkage formula.

### 4.4 Leakage control

Every feature for origin day *t* uses observations from days ≤ *t* only. The one
forward-looking input is the **calendar weekday of the target day**, which is
genuinely known in advance.

Three independent guards:

1. `assert_no_leakage()` re-derives `lag_1` and `roll_mean_28` from the raw panel
   and fails the training run on any mismatch.
2. `test_features_unchanged_when_future_is_removed` truncates the panel,
   recomputes **every** feature, and asserts nothing changed for the days that
   remain. A feature that peeked forward would move.
3. Rolling windows are rebuilt **inside each backtest fold**, so no window can
   span a fold boundary.

---

## 5. Stage 3 — Forecasting

`backend/app/ml/forecasting.py`

Five models, all behind one interface (`fit` / `predict`), so a naive rule and a
gradient-boosting model are scored by identical code.

### 5.1 The three baselines

Each answers a specific question rather than being a formality.

| Model | Question it answers |
|---|---|
| `naive_last_value` | Is any modelling justified at all? |
| `seasonal_naive_weekly` | Is the weekly pattern the whole story? |
| `moving_average_28` | Is the weekly pattern worth modelling *on top of* the level? |

### 5.2 The two candidates

- **`ridge_pooled_ratio`** — linear control. If a penalised linear map on the same
  features scores as well, the extra machinery is not earning its place.
- **`hist_gradient_boosting_ratio`** — `HistGradientBoostingRegressor`,
  absolute-error loss, `max_depth=4`, `max_leaf_nodes=15`,
  `min_samples_leaf=40`, early stopping.

**Absolute-error loss** was chosen deliberately: profiling found 34 demand spikes
at |z| > 4, and a squared-error objective would chase them at the expense of the
everyday forecast.

**Why not deep learning.** ~4.5k usable observations across 28 short series with
no trend and one seasonal cycle. A sequence model has nowhere near enough data to
justify its parameter count, and would forfeit the native handling of missing
lags and categorical inputs a histogram gradient-boosting tree gives for free.

### 5.3 The cold-start router

`ColdStartRouter` sends each SKU to whichever model the backtest showed serves it
best: established SKUs to the primary model, SKUs under the 30-day threshold to
the fallback.

This exists because of a **measured** result: on the cold-start fold,
`moving_average_28` **beat** the gradient-boosting model. That is mechanically
unsurprising — with 7 days of history `lag_14` is missing and the weekday index
is almost entirely the category prior, so the pooled model has little to work with
while a trailing mean stays robust.

The evidence is thin (15 forecast points), so the routing is deliberately biased
toward the **simpler** model for the SKUs we know least about — the safe
direction to be wrong in.

---

## 6. Stage 4 — Validation

`backend/app/ml/evaluation.py`

### 6.1 Rolling-origin, expanding window

Five folds. Each trains on everything up to its origin, then forecasts the next
14 days from that single origin — the same act a planner performs. Test windows
are contiguous and non-overlapping, together covering the last 70 days.

| Fold | Train through | Test window | Training rows |
|---|---|---|---|
| 1 | 2026-04-20 | 2026-04-21 → 2026-05-04 | 2,750 |
| 2 | 2026-05-04 | 2026-05-05 → 2026-05-18 | 3,100 |
| 3 | 2026-05-18 | 2026-05-19 → 2026-06-01 | 3,450 |
| 4 | 2026-06-01 | 2026-06-02 → 2026-06-15 | 3,800 |
| 5 | 2026-06-15 | 2026-06-16 → 2026-06-29 | 4,150 |

A **sixth fold** scores the three cold-start SKUs separately, at an origin where
each has exactly 7 days of history. It is reported separately and **never blended
into the headline** — it scores only 15 forecasts.

A fresh model is fitted inside every fold. Nothing fitted on later data is ever
reused.

### 6.2 Why a random split would be invalid

1. **Leakage through rolling features.** `roll_mean_28` for a day is built from
   its 27 neighbours. Under a random split most of those sit in the training set,
   so the model is graded on days whose own inputs already encode the answer.
2. **It measures the wrong task.** A planner never interpolates a missing Tuesday
   between two known days; they stand on the last day of real data and look
   forward.
3. **It is optimistic by construction.** Training on June to predict February
   hides drift, so reported error would flatter production error.

### 6.3 Why WAPE is the primary metric

```
WAPE = Σ |actual − forecast| ÷ Σ actual
```

- **MAPE rejected** — divides by actual demand, so one quiet day on SKU-1008
  (minimum 29 units/day) dominates the average, and it punishes over-forecasting
  far more than under-forecasting: the wrong asymmetry for a stockout tool.
- **RMSE rejected as primary** — dominated by the 34 demand spikes. Still
  reported.
- **WAPE is unit-free**, so 28 SKUs spanning 85–536 units/day aggregate honestly,
  and it reads as *"we are off by X% of the volume we actually shipped."*

Aggregation across folds is **pooled**, not averaged: WAPE is a ratio of sums, so
recomputing over the union of fold predictions is the correct operation and stops
a low-volume fold carrying the same weight as a high-volume one.

### 6.4 Results

1,750 forecasts, five folds pooled:

| Model | Role | WAPE | MAE (units) |
|---|---|---|---|
| `naive_last_value` | baseline | 0.2736 | 82.2 |
| `seasonal_naive_weekly` | baseline | 0.2393 | 71.9 |
| `moving_average_28` | baseline | **0.1962** | 59.0 |
| `ridge_pooled_ratio` | candidate | 0.1745 | 52.4 |
| **`hist_gradient_boosting_ratio`** | **selected** | **0.1721** | **51.7** |

**12.3% relative improvement** over the strongest baseline.
RMSE 87.6 units/day · Bias −1.48% · fold-to-fold spread ±0.0065.

Per-fold WAPE: 0.1769, 0.1707, 0.1789, 0.1603, 0.1737 — stable, no single fold
carrying the result.

**Two honest observations.** The flat 28-day mean *beats* seasonal naive, which
says the level matters more than the weekly shape alone — and a winning model
needs both. And ridge scores 0.1745 against the tree's 0.1721: a **1.4% margin**.
The tree won, but barely, and that is reported rather than hidden.

---

## 7. Stage 5 — The risk engine

`backend/app/ml/risk.py` — this is the business core.

### 7.1 Inventory *position*, not just stock on hand

A first implementation scored risk on stock on hand alone. On this dataset that
flagged **13 of 28 SKUs Critical** — because roughly half the catalogue is simply
mid-replenishment-cycle at any given moment. That is precisely the meaningless
red dashboard the brief warns against.

The dataset has no open-purchase-order table, but it records **475 historical
deliveries**, and they are regular: median inter-arrival CV 0.40 and **receipt
quantity CV just 0.11**. Replenishment is therefore modelled as an *observed
rate* rather than assumed away.

### 7.2 The stockout calculation

Demand and supply over the lead time *L* are treated as independent Normals:

```
μ_net    = forecast demand over L  −  expected inflow over L
σ_net    = √(σ_demand_L² + σ_supply_L²)

stockout_probability = P(net requirement > stock on hand)
                     = 1 − Φ((stock − μ_net) / σ_net)
```

Where:

- `σ_demand_L = cv · forecast_daily · √L · √(1 + 1/n)` — the `√(1 + 1/n)` term is
  the standard inflation for estimating a mean from *n* observations, and is what
  makes a 12-day-old SKU score less confidently **without inventing a number**.
- `σ_supply_L` comes from a compound renewal process,
  `Var = E[N]·Var(Q) + E[Q]²·Var(N)`, every input measured from that SKU's own
  delivery record.
- `safety_stock = 1.645 · σ_daily · √L` (95% cycle service level)
- `reorder_point = lead_time_demand + safety_stock`

**The score IS that probability.** 0.87 means "87% chance of running dry inside
the lead time" — not an arbitrary index.

### 7.3 Two signals that fall out of the same arithmetic

**`days_to_projected_stockout`** — stock walked forward day by day at the
forecast demand and the observed replenishment rate. The most intuitive number on
the dashboard: *"you run out in 3 days."*

**`supply_coverage_ratio`** — units received ÷ units sold over a window
**aligned to whole delivery cycles**. Below 1.0 the SKU is structurally
under-supplied and will drain regardless of today's stock.

> **Why the window is cycle-aligned.** A fixed-length window was the obvious
> choice and the wrong one. Deliveries are discrete and large — a median receipt
> here is 8–18 days of supply — so a fixed window either clips a delivery or
> catches an extra one, swinging the ratio by a third for a SKU delivered every
> 19 days. That noise alone manufactures shortfalls that do not exist.
>
> The window instead runs from the *N*th-most-recent delivery to the most recent
> one, covering a whole number of cycles, with *N* chosen so the window spans at
> least 4 cycles **and** at least 56 days.
>
> After the fix the ratio tracks reality: SKUs at 0.76 are the ones with 22–25%
> of days at zero stock; SKUs above 0.95 have near zero.

### 7.4 Overstock

Measured against the order-up-to level of a periodic-review policy — **never**
against raw units:

```
S            = forecast_daily · (L + R) + z · σ_daily · √(L + R)   [R = 7-day review]
excess_units = max(0, stock − S)
score        = clip(stock/S − 1, 0, 1)
```

A SKU at 10,000 units is healthy if S is 10,000; a SKU at 500 units is
overstocked if S is 200. Both cases are covered by tests.

Two amplifiers, because excess against a shrinking baseline takes longer to
clear:

- **Declining demand** scales the score by up to 1.5×
- **Inflow still above demand** scales it by 1.2×

Excess below **3 days of demand** is treated as noise, not a working-capital
problem.

### 7.5 The bands

Absolute and documented, **not percentiles** — percentile banding would guarantee
something is always "Critical" even in a perfectly healthy month.

| Stockout probability | Level |  | Excess above order-up-to | Level |
|---|---|---|---|---|
| ≥ 0.70 | Critical |  | ≥ 60% | High |
| ≥ 0.40 | High |  | ≥ 30% | Medium |
| ≥ 0.20 | Medium |  | ≥ 12% | Low |
| ≥ 0.08 | Low |  | | |
| otherwise | Healthy |  | | |

**Overrides and lifts:**

- Zero stock with positive demand is **always Critical**.
- A standing supply shortfall lifts an otherwise-quiet SKU into view, but never
  beyond what the probability justifies.
- Under-supply is ignored when forecast demand is zero — a shortfall against no
  demand is not a shortfall.

**Resulting distribution on this dataset:** 4 Critical · 1 High · 4 Medium ·
7 Low · 12 Healthy. Graded and actionable. Both degenerate outcomes (everything
red, everything green) are asserted against in the test suite.

`stockout_probability_no_inbound` is published alongside, for a planner who knows
nothing is actually on order.

### 7.6 Cold start — all five mechanisms

`SKU-2000`, `SKU-2001`, `SKU-2002` have **12 days** of history against 180 for
everything else.

| # | Mechanism | Detail |
|---|---|---|
| 1 | **Weekly shape borrowed** | Weekday index shrunk toward the category, `w = n/(n+3)` (§4.3) |
| 2 | **Variability borrowed** | Coefficient of variation shrunk toward the category median of established SKUs, `w = n/(n+14)` |
| 3 | **Level uncertainty priced in** | `√(1 + 1/n)` inflation on the lead-time sigma |
| 4 | **Lead time repaired** | These SKUs report 4–5 different lead times in 12 rows → category median |
| 5 | **A simpler model serves them** | `moving_average_28` beat the tree on the cold-start fold (§5.3) |

**In the interface**, these SKUs carry a `New · 12d` badge everywhere they
appear, and the detail page states plainly:

> *Limited history — this SKU has 12 days of observed demand. Its risk estimate
> is less certain than for established SKUs.*

No invented confidence percentage. The observed history length is stated instead.

### 7.7 Drivers

Every assessment carries an ordered list of `Driver` objects — the quantified
reasons behind the flag, most decisive first. Each has a `name`, a human `label`,
a `value`, a `unit`, and a `detail` sentence.

The driver set adapts to the risk type. For a stockout:

1. `current_stock` (only when already at zero)
2. `days_to_projected_stockout`
3. `inventory_coverage_days`
4. `supply_coverage_ratio` (only when under-supplied)
5. `lead_time_demand`
6. `expected_inbound_within_lead_time`
7. `reorder_point_units`
8. `observed_stockout_days_28d` (only when non-zero)

For an overstock: `excess_units`, `inventory_coverage_days`,
`replenishment_rate_per_day`. Both types then append `demand_change_pct`,
`demand_cv` and `days_since_last_receipt`.

**This ordered list is exactly what the LLM is given** — the UI says so, and the
drivers card on the detail page shows the same list the model sees.

---

## 8. Stage 6 — The artifact bundle

`python -m app.ml.training` writes one file:
`models/supply_chain/supply_chain_bundle.joblib` (~250 KB).

It contains the fitted model, the fallback model, the cleaned panel, the origin
features, the 28-day forecast, every SKU's risk assessment, the category CV
table, the cold-start SKU list, the cleaning report, the full evaluation results,
the risk configuration and library versions.

It also regenerates three reports:

| Report | Contents |
|---|---|
| [`data_profile.md`](../backend/reports/data_profile.md) | Schema detection, size, per-SKU history, quality checks, category and lead-time distributions, balance consistency, demand behaviour, day-of-week effect, and the implications acted on |
| [`model_evaluation.md`](../backend/reports/model_evaluation.md) | Validation design, metric choice, full results, per-fold and per-horizon tables, cold-start results, risk-band calibration, cleaning summary, limitations |
| [`model_summary.md`](../backend/reports/model_summary.md) | One page for both technical and business readers: problem, target, features, baselines, chosen model, validation, metrics, cold-start treatment, limitations |

---

## 9. The API, endpoint by endpoint

Interactive documentation at `/docs`.

### `GET /health`

Liveness plus diagnostics: `status`, `version`, `artifacts_loaded`,
`llm_configured`, `as_of`. Used as the Render health check. Returns `degraded`
rather than failing if artifacts did not load, so the problem is visible.

### `GET /api/dashboard`

Everything the dashboard needs in one call:

- **`kpis`** — total SKUs, high-risk count, critical count, stockout count,
  overstock count, healthy count, newly-launched count, out-of-stock-now count,
  structurally-under-supplied count, total excess units
- **`risk_distribution`** — count per band, always all five
- **`category_risk`** — per category: total, critical+high, stockout, overstock,
  average coverage days
- **`attention_list`** — all 28 SKUs, ranked
- **`model_name`**, **`llm_available`**, **`as_of`**, **`generated_at`**

**The ranking rule:** severity first, then the most decisive tiebreaker within a
band — soonest projected stockout, then highest score, then SKU id.

### `GET /api/skus`

Filterable list. Query parameters:

| Parameter | Behaviour |
|---|---|
| `risk_level` | Comma-separated, e.g. `CRITICAL,HIGH` |
| `risk_type` | Comma-separated: `STOCKOUT`, `OVERSTOCK`, `NONE` |
| `category` | Comma-separated, case-insensitive |
| `cold_start` | `true` = newly launched only, `false` = established only |
| `search` | Substring match on SKU id or category |
| `limit` | 1–1000, default 200 |

An unknown filter value returns an empty list, not an error.

### `GET /api/skus/{sku_id}`

Full drill-down. Includes every risk field, the full ordered driver list, the
last `history_days` (default 90, range 7–400) of daily history, and the 28-day
forecast.

SKU lookup is **case- and whitespace-insensitive**, so `sku-1004` resolves.
An unknown SKU returns **404** with the id echoed back.

### `GET /api/skus/{sku_id}/explanation`

Triggers the runtime LLM call. `?force=true` bypasses the cache. Returns the
explanation, `source` (`llm` or `fallback`), the model name, whether it was
cached, and **the full evidence object** so the caller can see exactly what the
model was given. See §10.

### `POST /api/qa`

Body: `{"question": "..."}` — 3 to 500 characters, non-blank; anything else is
**422**. Returns the answer, `source`, `intent`, `grounded_on` (which records
were used) and the evidence. See §11.

### `GET /api/qa/suggestions`

Starter questions, with one dynamically naming a SKU that is **actually flagged
right now** — so the suggestion is never stale.

### `GET /api/metadata`

Dataset summary and the **cleaning audit**: date range, row count, SKU count,
categories, cold-start and established SKU lists, the full `CleaningReport`, the
risk configuration (bands, service level, thresholds), and LLM availability.

### `GET /api/model-info`

The model card: selected model, serving model, cold-start model, trained-at,
forecast horizon, primary metric, headline metrics, every baseline with its WAPE,
the validation design (including `random_split_used: false` and why), the
cold-start configuration and results, and library versions.

A test asserts the reported selected model really is the best-scoring one, and
that it beats every baseline — so the API cannot drift from the artifact.

### `GET /api/categories`

Per-category risk rollup, sorted by critical+high descending.

---

## 10. AI explanations

`backend/app/services/explanation_service.py` and `llm_client.py`

Every explanation is generated by a **runtime Anthropic API call**. There are no
hardcoded explanations, no templates presented as model output, and nothing
pre-generated in the dataset.

### 10.1 The pipeline

```
RiskAssessment (computed)
   └─> build_evidence()          ~38 real numbers + ranked drivers + reading guide
        └─> SYSTEM_PROMPT        9 absolute rules
             └─> Anthropic       claude-sonnet-5 (via MODEL_NAME)
                  └─> verify_grounding()   every number traced to the evidence
                       ├── pass → served,  source = "llm"
                       └── fail → fallback, source = "fallback"
```

**The model never sees the dataset.** It receives one evidence object built from
the SKU's own risk record — about **3.3 KB** against a 4,536-row panel.

### 10.2 What the prompt forbids

1. Any number not in the evidence
2. Invented business facts — promotions, suppliers, seasonality, contracts
3. Conflating observed facts with model estimates (stock on hand is a fact;
   forecasts and probabilities are estimates and must be worded as such)
4. Burying the lede — the first driver is the reason the SKU is flagged
5. Inventing a confidence figure for a cold-start SKU; it must state the observed
   history length
6. Presenting inferred inbound as a confirmed purchase order
7. **Unchecked comparisons** — see §10.4
8. Omitting a practical action
9. Markdown, headings or preamble — two short paragraphs of plain prose

### 10.3 Grounding verification

`verify_grounding()` re-reads the generated text and checks that every number
traces back to the evidence, allowing the derivations a human writer would make
(rounding, probability ↔ percentage, simple differences). Small integers (≤ 31)
are exempt as ordinary prose. Ungrounded output is **rejected** and the
deterministic fallback served, labelled `source="fallback"`.

> **A bug this caught.** `"SKU-1010"` was being parsed as the number **−1010**
> (the hyphen read as a minus sign), so *every* explanation that named its own
> SKU was silently rejected and the app fell back every time. Identifiers and ISO
> dates are now stripped before numbers are extracted, with regression tests.

### 10.4 Grounding numbers is not grounding relations

Live testing produced:

> *"lead-time demand of 725 units — **well above** the reorder point of 872.4
> units"*

Both figures are real, so number-level verification passed. But 725 is *below*
872.4, and comparing those two quantities is not even meaningful.

The fix: the evidence object now carries a `_how_to_read` list naming which
quantities are meaningfully comparable —

- `current_stock` vs `reorder_point_units` → below it, raise an order
- `inventory_coverage_days` vs `lead_time_days` → less cover than lead time means
  an order placed today arrives too late
- `current_stock` vs `order_up_to_units` → above it is excess
- `reorder_point_units` **equals** `lead_time_demand + safety_stock_units`, so it
  is always the larger; never compare them as if either could exceed the other
- `days_to_projected_stockout` vs `lead_time_days`
- `supply_coverage_ratio` below 1.0 means receiving less than selling

— and the prompt forbids asserting a comparison without checking it. Re-running
produced correct pairings.

### 10.5 Caching

Keyed by SKU **and a hash of the evidence**, so a cached explanation is only ever
reused while the underlying numbers are unchanged. Any movement in the risk state
produces a new key and a genuine new call. Failures are never cached. The
"Regenerate" button bypasses the cache entirely.

### 10.6 Resilience

`llm_client.py` enforces:

- a hard **30-second timeout**
- retries on **transient failures only** (overloaded, rate limit, timeout,
  connection, 503/529) — anything else fails fast, because a business dashboard
  should degrade in a second, not hang
- **response validation** — non-empty, length-capped, at least four words, and
  not an echo of the evidence JSON
- **logging** of model, latency and token counts — never the key, never a full
  prompt

If the LLM is unavailable the app stays fully usable: risk scores, charts and
figures are unaffected, and the UI says plainly that the generated explanation is
temporarily unavailable rather than passing the fallback off as model output.

### 10.7 Verified against the live API

4/4 explanations generated by `claude-sonnet-5` across a stockout, an overstock,
a cold-start and a healthy SKU — every one passing grounding verification.
Typical latency 4–7 s, ~1.5–3.7k input tokens.

Reproduce with `python scripts/verify_live_llm.py`.

---

## 11. Grounded Q&A

`backend/app/services/qa_service.py`

### 11.1 Why there is a retrieval layer

Pasting the CSV into the prompt fails three ways: 4,536 rows of daily movements
do not fit a sensible prompt budget; the model would have to re-derive risk
arithmetic it is bad at; and its answers could not be reconciled with what the
dashboard shows.

So the LLM **never sees the dataset**.

```
question
  ├─ 1. CLASSIFY   10 intents + entity extraction (SKU ids, categories, risk levels)
  ├─ 2. RETRIEVE   only the structured records that intent needs — the same
  │                RiskAssessment objects the dashboard renders
  ├─ 3. COMPACT    drop unneeded fields, cap lists at 12 SKUs (1.6–5.9 KB)
  └─ 4. ANSWER     from that evidence alone, under a grounding system prompt
```

### 11.2 The ten intents

| Intent | Triggered by | Retrieves |
|---|---|---|
| `sku_explanation` | A SKU id + "why"/"explain"/"reason" | That SKU's full assessment + top 4 drivers |
| `sku_detail` | A SKU id without a "why" | Same, without the explanatory framing |
| `attention_list` | "attention", "need", "priorit", "focus", "action" — **also the default** | Ranked non-healthy list + portfolio KPIs |
| `stockout_list` | "stockout", "run out", "shortage", "out of stock" | Stockout-type SKUs, ranked |
| `overstock_list` | "overstock", "excess", "tied up", "working capital", "slow moving" | Overstock SKUs + total excess units |
| `coverage_list` | "coverage", "days of cover", "lead time", "cover" | SKUs ranked by least cover |
| `category_risk` | "category"/"categories", or a category name | Per-category rollup + worst SKUs each |
| `new_skus` | "new", "newly launched", "cold start", "limited history" | Cold-start SKUs + a limited-history note |
| `summary` | "how many", "count", "overview", "status", "total" | Portfolio KPIs + top 6 priorities |
| `model_info` | "model", "accurate", "wape", "trained", "how does" | The model card and validation results |

> **An ordering detail that matters.** `coverage_list` is checked *before*
> `stockout_list`, because "which SKUs have **short** inventory coverage?" would
> otherwise be swallowed by the stockout keywords. Regression-tested.

### 11.3 Why answers can never contradict the dashboard

Retrieval returns **the same computed records the dashboard renders**. A test
asserts this directly: for every SKU in a retrieved attention list, the
`risk_level` and `risk_score` in the evidence must equal the live values from the
data service.

### 11.4 What the caller gets back

`grounded_on` — a list of the record sets used, each with a `kind`, a
human-readable `label` and the SKU ids involved. The UI renders these as badges
plus clickable SKU links, so the user can see exactly what the model was looking
at and jump straight to any SKU mentioned.

### 11.5 Verified against the live API

9/9 answers generated live. Two behaviours worth noting:

- *"What is the capital of France?"* → declined, and redirected to what the
  dashboard actually shows.
- *"How many units of SKU-9999 do we have?"* → declined without inventing a
  figure, and offered real SKUs instead.

---

## 12. The interface, screen by screen

Next.js 16 · TypeScript · Tailwind · shadcn/ui-style primitives · Recharts ·
Lucide icons.

Light theme only, with gradients used as **surface treatment**: the only colours
carrying meaning are the risk colours, and a gradient never competes with them.
Gradients are defined once as CSS custom properties in `globals.css` and applied
through `.grad-*` and `.surface-gradient` helpers.

### 12.1 `/supply-chain` — the dashboard

**Header** — "Supply Chain Risk Monitor", the subtitle *"Identify SKUs likely to
require attention before inventory becomes a problem"*, the data date, the
serving model, and a Refresh button.

**Four KPI cards** — each with a gradient accent bar in the colour of what it
measures, and an `i` hint explaining the number in plain English:

| Card | Shows | Clicking it |
|---|---|---|
| SKUs monitored | Total, with newly-launched and healthy counts | — |
| Need attention | Critical + High, with out-of-stock-now | Filters to Critical & High |
| Stockout risk | Count, with under-supplied count | Filters to stockout type |
| Overstock risk | Count, with total excess units | Filters to overstock type |

**Three charts:**

1. **Inventory coverage vs lead time** *(the most decision-relevant view on the
   dashboard)* — a scatter of every SKU with a diagonal reference line. Anything
   **below the line** has less cover than it takes to restock, so an order placed
   today would arrive too late. This turns "needs an order now" into a *position
   on a page* rather than a number in a table. Points are coloured by risk band;
   coverage is capped at 30 days for readability, and the cap is stated.
2. **Risk distribution** — how the portfolio splits across the five bands.
3. **Risk by category** — a stacked bar showing where high and critical SKUs
   concentrate.

**Ask panel** — see §11 and §12.4.

**SKUs requiring attention** — the table, with filters.

| Column | Note |
|---|---|
| SKU | With `New · 12d` and `Under-supplied` badges beneath |
| Category | |
| Risk | Badge |
| Type | Stockout / Overstock badge |
| Stock | |
| Cover | **Red when below the lead time**, with a tooltip explaining why |
| Lead time | |
| Forecast/day | |
| Main reason | The computed headline |

**Filters** — search (SKU or category), risk level (including a "Needs attention"
shortcut), risk type, category, and new vs established. Plus a live
"Showing *n* of 28" count and a Clear control.

Filtering is applied **client-side**: the full list is 28 rows, so a round trip
per keystroke would add latency without adding correctness.

**Deep links** — `?risk=CRITICAL,HIGH` and `?type=STOCKOUT` are read once as the
initial filter state, which is what the KPI cards link to.

### 12.2 `/supply-chain/sku/[skuId]` — the drill-down

**Header** — SKU id, risk badge, type badge, plus `New · 12d` and
`Under-supplied` badges where they apply, and the computed headline.

**Cold-start notice** (only for new SKUs) — a violet panel stating the observed
history length and naming all four ways the estimate is softened.

**Recommended action** — the computed action sentence, with the suggested order
quantity called out as a figure.

**AI explanation card** — a "Generate explanation" button that triggers the
backend LLM call. Shows the model name when the answer came from the LLM, a
"Regenerate" control after the first call, and a clear amber notice when the
fallback was served. See §10.

**Four stat cards** — stock on hand, inventory coverage (red when below lead
time), forecast demand, and stockout probability (or risk score for overstock).
Each has an `i` hint explaining the calculation.

**Two charts:**

1. **Demand — last 60 days and 28-day forecast.** One continuous x-axis with a
   "today" marker, so the handover from recorded to forecast is *visible* rather
   than implied. Solid line = recorded units sold; dashed = the model forecast.
2. **Inventory and deliveries — last 60 days.** Closing stock as a gradient area,
   deliveries as bars, and both policy lines (reorder point, order-up-to). The
   y-axis is deliberately extended to include those lines, so the caption never
   names a line the reader cannot see. Watching stock sawtooth across the reorder
   point *is* the argument for acting.

**Risk drivers** — the ordered, numbered list with value, unit and explanation,
captioned *"These are exactly what the AI explanation is given."*

**Replenishment policy** — lead-time demand, safety stock, reorder point,
order-up-to level, excess, and days to projected stockout.

**Demand and supply behaviour** — last 7 days vs previous 7 with a trend arrow,
demand CV, replenishment rate, expected inbound (with a hint that it is inferred,
not a confirmed PO), supply vs demand over the cycle-aligned window, days since
last delivery, and the all-time zero-stock rate.

**Model confidence** — observed history, confidence level, and the conservative
"if nothing is on order" probability, with a sentence explaining the difference.

### 12.3 `/supply-chain/model` — How it works

A transparency page, because a planner is being asked to act on a model's output.
Shows forecast accuracy (WAPE, MAE, RMSE, bias, fold spread), the full model
selection table with the winner marked, the validation design including
`random_split_used: No` and the reason, the cold-start treatment, the dataset and
cleaning summary, and a candid **"What this tool cannot tell you"** section.

All values come from `/api/model-info` and `/api/metadata` — nothing on this page
is hardcoded.

### 12.4 The Ask panel

A question box — *"Ask about your inventory…"* — with suggestion chips, one of
which names a currently-flagged SKU.

The answer renders with:

- a **"Grounded in live dashboard data"** badge
- a badge per retrieved record set, naming exactly what was used
- the model name when the answer came from the LLM
- an amber notice when the fallback was served
- **clickable SKU chips** for every SKU referenced, linking straight to its
  detail page

---

## 13. Loading, empty and error states

No screen is ever allowed to render blank.

| State | Treatment |
|---|---|
| **Loading** | Shaped skeletons — KPI skeletons, table skeletons, chart skeletons — matching the layout that will replace them |
| **LLM loading** | Text skeleton plus *"Sending the computed evidence to the model…"* |
| **Empty** | *"No SKUs match these filters"* with a hint and a Clear-all-filters action |
| **API error** | A card distinguishing a **network failure** (with the API URL, so a misconfigured `NEXT_PUBLIC_API_URL` is obvious) from a server error, with a Retry button |
| **LLM error** | Inline notice, the reason, and a Try again link |
| **LLM unavailable** | A dashboard-level banner explaining that scores and charts are unaffected and only written explanations degrade |
| **Not found** | A 404 page suggesting the SKU may no longer be in the dataset |
| **Unhandled** | An error boundary reassuring that data is unaffected, with a reset control |
| **Starting up** | A request before artifacts load returns **503** with *"Service is still starting up"* rather than a stack trace |

---

## 14. Performance

- **Training is offline.** No request path trains a model or re-reads the CSV.
- **The bundle loads once** at process start (~250 KB resident) and every request
  is a dictionary lookup or a frame slice.
- **Per-SKU history and forecast are pre-sliced** at load, so a detail request is
  a dict hit rather than a groupby.
- **LLM explanations are cached** by SKU + evidence hash, bounded by
  `LLM_CACHE_SIZE` (default 256) with LRU eviction.
- **Filtering is client-side** for the 28-row table.
- **If the bundle is missing** (a fresh clone), the API trains it once on startup
  rather than serving errors.

---

## 15. Security

- `ANTHROPIC_API_KEY` is read **server-side only** and never reaches the browser.
  There is no `NEXT_PUBLIC_ANTHROPIC_API_KEY`; the frontend never contacts
  Anthropic.
- **CORS uses an explicit allowlist**, never `"*"` — localhost for development
  plus whatever `FRONTEND_URL` names, with a regex for Vercel previews. A test
  asserts the wildcard is not used.
- **Logs record** model, latency and token counts — never the key, never a full
  prompt.
- **`.gitignore`** covers `.env`, `node_modules`, Python caches and the model
  artifact; `.env.example` documents every variable with none filled in.
- **`scripts/final_check.py`** automatically verifies: no key literal anywhere in
  the tree, no secret-bearing `NEXT_PUBLIC_` variable, no Anthropic reference in
  the frontend, no hardcoded SKU ids or risk thresholds in the frontend, and that
  the metrics quoted in the README match the trained artifact.

---

## 16. Testing

**169 tests**, all passing, running offline in about 20–40 seconds.

| File | Tests | Protects |
|---|---|---|
| `test_data.py` | 19 | Schema detection including fully renamed columns, duplicate removal, category normalisation, **causal imputation** (truncate-and-recompare), lead-time repair, the balance audit measuring source data rather than our own fills, missing-data edge cases |
| `test_features.py` | 14 | **No leakage** — three independent proofs: re-derivation from the raw panel for every SKU, truncate-and-recompute across every feature, and target alignment. Plus rolling-window correctness and cold-start shrinkage behaviour |
| `test_risk.py` | 28 | The brief's worked example, zero-stock override, monotonicity of probability in stock and lead time, structural under-supply, overstock measured relative to demand (10,000 units healthy / 500 units overstocked), band monotonicity, ranking, cold-start confidence, JSON safety |
| `test_evaluation.py` | 19 | Metric correctness, fold construction (chronological, non-overlapping, expanding), **training slice never contains the test window**, a fresh model per fold, baseline correctness |
| `test_llm.py` | 49 | Evidence construction, prompt rules present, dataset never sent, grounding accepts real numbers and rejects invented ones, identifier/date false-positive regressions, the comparison-guidance regression, cache behaviour, malformed and error responses |
| `test_api.py` | 40 | Every endpoint, KPI self-consistency, ranking, filters, 404s, 422 validation, no NaN in JSON, CORS not using `*`, and that the reported selected model really is the best-scoring one |

The API suite runs with the LLM **disabled** — those tests assert the HTTP
contract, not the model, so letting them reach Anthropic would make the suite
slow, non-deterministic, network-dependent and costly. Live-model behaviour is
covered by mocks in `test_llm.py` and by `scripts/verify_live_llm.py` against the
real API.

Frontend: `npm run lint`, `npm run typecheck`, `npm run format:check` and
`npm run build` all pass cleanly.

---

## 17. Running it

**Prerequisites:** Python 3.11+, Node.js 20+.

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.ml.training                          # ~40 s: trains, scores, writes reports
uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> — it redirects to `/supply-chain`.

**Environment.** Copy `.env.example`. The backend reads `ANTHROPIC_API_KEY`,
`MODEL_NAME`, `FRONTEND_URL` and `LOG_LEVEL` from `backend/.env` **or** a `.env`
at the repository root (root takes precedence). The frontend reads
`NEXT_PUBLIC_API_URL` from `frontend/.env.local`.

Without an API key the app runs normally; explanations and Q&A fall back to a
deterministic read-out of the same figures, clearly labelled in the UI.

### Useful scripts

| Script | Purpose |
|---|---|
| `scripts/profile_data.py` | Regenerates the data profile from the raw CSV |
| `scripts/probe_anomalies.py` | Deep dive into duplicates, case variants, lead times, missingness, balance violations, autocorrelation, spikes |
| `scripts/probe_replenishment.py` | Delivery cadence per SKU — the analysis behind the supply model |
| `scripts/inspect_results.py` | Backtest results: per-fold, pooled, per-horizon, per-SKU |
| `scripts/inspect_risk.py` | The full risk table plus a forecast sanity check |
| `scripts/smoke_api.py` | End-to-end API check with no server needed |
| `scripts/demo_llm_path.py` | Whole LLM path with a mocked client |
| `scripts/verify_live_llm.py` | Whole LLM path against the **real** Anthropic API |
| `scripts/final_check.py` | Quality gate: secrets, hardcoded data, encoding, README metrics vs artifact |

---

## 18. Deployment

**Backend → Render.** `backend/render.yaml` is a blueprint using the native
Python runtime. The build runs
`pip install -r requirements.txt && python -m app.ml.training`, so the model is
trained during deployment with the exact pinned library versions and the first
request is served warm. Start command binds correctly:
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Health check: `/health`.
Set `ANTHROPIC_API_KEY` and `FRONTEND_URL` in the dashboard.

`backend/Dockerfile` is provided as an alternative — build context is the
**repository root**, since the image needs both the app and `data/`.

**Frontend → Vercel.** Import the repo, set Root Directory to `frontend`, add
`NEXT_PUBLIC_API_URL` pointing at the Render URL. No localhost is hardcoded into
any production code path.

**Neither is currently deployed.** The configuration is complete and verified
locally; there is no live URL to claim.

---

## 19. Field glossary

Every field in the SKU detail response.

### Identity and classification

| Field | Meaning |
|---|---|
| `sku_id`, `category`, `as_of` | Identity and the snapshot date |
| `risk_level` | CRITICAL / HIGH / MEDIUM / LOW / HEALTHY |
| `risk_type` | STOCKOUT / OVERSTOCK / NONE |
| `risk_score` | The winning score, 0–1 |

### Stockout

| Field | Meaning |
|---|---|
| `stockout_probability` | P(running dry inside the lead time), crediting expected inbound |
| `stockout_probability_no_inbound` | The same, assuming nothing is on order — the conservative view |
| `lead_time_demand` | Model forecast summed over the lead time |
| `days_to_projected_stockout` | Days until stock hits zero, walking forward at forecast demand and observed replenishment. `null` = survives the horizon |
| `inventory_coverage_days` | Stock ÷ forecast daily demand |
| `safety_stock_units` | `1.645 · σ_daily · √L` |
| `reorder_point_units` | `lead_time_demand + safety_stock_units` |
| `suggested_order_qty` | Units to reach the order-up-to level, net of expected inbound |

### Overstock

| Field | Meaning |
|---|---|
| `order_up_to_units` | Policy maximum: `demand·(L+R) + z·σ·√(L+R)` |
| `excess_units` | `max(0, stock − order_up_to)` |
| `excess_ratio` | `stock ÷ order_up_to` |
| `overstock_score` | 0 at the policy maximum, 1 at twice it |

### Demand

| Field | Meaning |
|---|---|
| `forecast_daily_demand` | Mean of the model's forecast for the next 7 days |
| `demand_sigma_daily`, `demand_cv` | Daily volatility, shrunk toward the category for short history |
| `recent_7d_avg_demand`, `previous_7d_avg_demand`, `demand_change_pct` | Trend |

### Supply

| Field | Meaning |
|---|---|
| `replenishment_rate_per_day` | Units received ÷ days, over the cycle-aligned window |
| `expected_inbound_within_lead_time` | `rate × L` — **inferred from cadence, not a confirmed PO** |
| `supply_coverage_ratio` | Units received ÷ units sold over the window. Below 1.0 = draining |
| `supply_window_days` | Length of that cycle-aligned window |
| `is_structurally_undersupplied` | Ratio below 0.95 with positive demand |
| `units_received_in_window`, `days_since_last_receipt`, `avg_replenishment_interval_days`, `avg_receipt_qty` | Observed delivery behaviour |

### History and confidence

| Field | Meaning |
|---|---|
| `observed_stockout_days_28d`, `observed_stockout_rate_all_time` | Days recorded at zero stock |
| `days_of_history`, `is_cold_start`, `confidence` | HIGH ≥ 90 days · MEDIUM ≥ 30 · LOW below |

### Narrative

| Field | Meaning |
|---|---|
| `headline` | One-line computed reason |
| `recommended_action` | Computed action sentence |
| `drivers` | Ordered quantified reasons — what the LLM is given |

---

## 20. Limitations

Stated plainly, and surfaced in the app's own "How it works" page.

1. **No open purchase orders in the dataset.** `units_received` is a record of
   past deliveries, not a forward order book. Expected inbound is *inferred* from
   each SKU's cadence, labelled as an estimate everywhere it appears, with the
   conservative no-inbound probability published alongside. A confirmed order a
   planner knows about is not reflected.
2. **Six months of history, one seasonal cycle.** Weekly patterns are supported
   by the data; annual seasonality, promotions and holiday effects cannot be
   learned or validated.
3. **Demand is recorded, not true, demand.** Closing stock is censored at zero on
   277 SKU-days; on those days real demand may have exceeded the sales figure, so
   the model under-states demand for chronically short SKUs.
4. **Cold-start metrics rest on 15 forecast points.** They show direction, not a
   dependable error rate.
5. **Lead times are treated as fixed.** Safety stock covers demand variability but
   not late deliveries, so it is a lower bound.
6. **No cost or margin data.** Risk is ranked by likelihood and days of excess
   cover, not financial impact — a high-value SKU is not prioritised over a
   low-value one at equal risk.
7. **Single-node in-memory cache.** A multi-instance deployment would want a
   shared cache.
8. **No scheduled retraining or drift monitoring.** The artifact is rebuilt on
   deploy.

### The natural next steps

1. **Ingest open purchase orders** — the single biggest accuracy gain available,
   and it removes the largest caveat in the product.
2. **Add cost and margin** so the attention list ranks by money at risk.
3. **Model lead-time variability** — the delivery dates are already in the data.
4. **Censored-demand correction** so chronically short SKUs stop being
   under-forecast.
5. **Scheduled retraining with drift monitoring.**
6. **Alerting and a "mark as actioned" state** so the list reflects what the team
   has already dealt with.
