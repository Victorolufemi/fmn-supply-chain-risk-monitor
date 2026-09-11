# Supply Chain Risk Monitor

**FMN AI Engineer Internship Technical Assessment — Project 1**

A forecast-driven decision-support tool that tells a supply-chain planner which SKUs
need attention today, why, and what to do about it — in plain English, with the
numbers behind every claim.

- **Backend** — Python · FastAPI · scikit-learn · Anthropic (deployable to Render)
- **Frontend** — Next.js 16 · TypeScript · Tailwind CSS · shadcn/ui-style components · Recharts (deployable to Vercel)

> **Looking for the full walkthrough?** [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md) explains every feature, how each number is computed, and why it was built that way. This README is the overview.

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [The sponsor's problem](#2-the-sponsors-problem)
3. [Business interpretation](#3-business-interpretation)
4. [Architecture](#4-architecture)
5. [Data description](#5-data-description)
6. [Data-quality findings](#6-data-quality-findings)
7. [Feature engineering](#7-feature-engineering)
8. [Model selection](#8-model-selection)
9. [Baselines](#9-baselines)
10. [Validation methodology](#10-validation-methodology)
11. [Evaluation metrics](#11-evaluation-metrics)
12. [Cold-start strategy](#12-cold-start-strategy)
13. [Stockout methodology](#13-stockout-methodology)
14. [Overstock methodology](#14-overstock-methodology)
15. [Explainability architecture](#15-explainability-architecture)
16. [Grounded Q&A architecture](#16-grounded-qa-architecture)
17. [Local setup](#17-local-setup)
18. [Environment variables](#18-environment-variables)
19. [Backend setup](#19-backend-setup)
20. [Frontend setup](#20-frontend-setup)
21. [Tests](#21-tests)
22. [Deployment to Render](#22-deployment-to-render)
23. [Deployment to Vercel](#23-deployment-to-vercel)
24. [API overview](#24-api-overview)
25. [Limitations](#25-limitations)
26. [Next steps](#26-next-steps)
27. [Demo and deployed URLs](#27-demo-and-deployed-urls)

---

## 1. Project overview

The tool turns six months of daily SKU movements into a ranked list of products
that need a decision today. For each one it gives a risk level, a risk type
(stockout or overstock), the quantified drivers behind the flag, an AI-written
explanation generated at request time from those same figures, and a suggested
order quantity.

A planner can also ask questions in plain language — *"Which SKUs need
attention?"*, *"Why is SKU-1010 flagged?"* — and get answers grounded in the live
dashboard state rather than the model's general knowledge.

**Headline result:** the selected model reduces forecast error by **12.3%**
(WAPE 0.1962 → 0.1721) against the strongest baseline, measured over 1,750
forecasts across five chronological validation folds.

---

## 2. The sponsor's problem

> "We keep getting caught off guard — some SKUs run out and delay production,
> others sit overstocked and tie up working capital. I don't have anything today
> that tells me, ahead of time, which SKUs need attention and why."

Three things are being asked for: **advance warning**, **prioritisation**, and
**a reason a human can act on**.

---

## 3. Business interpretation

The sponsor's request is not a forecasting problem — it is a *triage* problem that
happens to need a forecast. The measurable question is:

> **For each SKU, what is the probability that demand over the replenishment lead
> time exceeds what will be available, and how far is stock above the maximum the
> replenishment policy justifies?**

That framing yields the whole product:

| Sponsor's words | What the system computes |
|---|---|
| "which SKUs need attention" | A ranked list: severity first, then how soon stock is projected to run out |
| "some SKUs run out" | `stockout_probability` — the chance of running dry inside the lead time |
| "others sit overstocked" | `excess_units` above the order-up-to level implied by the forecast |
| "ahead of time" | A 28-day daily demand forecast, covering the longest lead time (14 days) plus a review cycle |
| "and why" | Ranked, quantified drivers, plus an LLM explanation written from them |

The forecast is a means, not the deliverable. A planner never acts on "we expect
179 units a day"; they act on "you have 0.6 days of cover against a 3-day lead
time, and you are receiving 76 units for every 100 you sell".

---

## 4. Architecture

```
fmn-ai-assessment/
├── data/
│   └── project1_supply_chain_demand.csv
├── models/supply_chain/
│   └── supply_chain_bundle.joblib      # built by training; not in source control
├── backend/
│   ├── app/
│   │   ├── main.py                     # FastAPI app, CORS, lifespan
│   │   ├── config.py                   # settings from environment
│   │   ├── api/                        # dashboard.py, skus.py, qa.py, meta.py
│   │   ├── ml/
│   │   │   ├── data.py                 # schema detection + cleaning
│   │   │   ├── features.py             # leakage-safe feature engineering
│   │   │   ├── forecasting.py          # baselines + candidates + cold-start router
│   │   │   ├── evaluation.py           # rolling-origin backtest, metrics
│   │   │   ├── risk.py                 # stockout / overstock scoring
│   │   │   └── training.py             # offline pipeline -> artifact bundle
│   │   ├── services/
│   │   │   ├── data_service.py         # loads the bundle once at startup
│   │   │   ├── llm_client.py           # Anthropic wrapper: timeout, retry, validation
│   │   │   ├── explanation_service.py  # evidence -> prompt -> grounding check
│   │   │   └── qa_service.py           # intent -> retrieval -> grounded answer
│   │   ├── schemas/models.py           # Pydantic response contracts
│   │   └── utils/
│   ├── reports/                        # generated: data profile, evaluation, model summary
│   ├── tests/                          # 169 tests
│   ├── requirements.txt
│   ├── Dockerfile
│   └── render.yaml
├── frontend/
│   ├── app/
│   │   ├── supply-chain/page.tsx               # dashboard
│   │   ├── supply-chain/sku/[skuId]/page.tsx   # SKU drill-down
│   │   └── supply-chain/model/page.tsx         # model transparency page
│   ├── components/                     # KPI cards, charts, table, filters, Ask panel
│   ├── lib/                            # API client, formatting, fetch hook
│   └── types/api.ts                    # mirrors the backend schemas
├── presentation/project1_outline.md
├── scripts/                            # profiling and diagnostic scripts
└── .env.example
```

**Separation of concerns.** The frontend contains no ML logic, no risk arithmetic,
no thresholds, no model files, and no secrets. It renders what the API computed.
The backend owns data loading, feature engineering, forecasting, risk scoring,
explainability, LLM calls, Q&A retrieval and all business rules.

**Request path.** Nothing is trained or recomputed per request. `python -m
app.ml.training` produces one artifact bundle (~250 KB) containing the fitted
model, the cleaned panel, the forecast and every SKU's risk assessment. The API
loads it once at startup and serves slices of it.

---

## 5. Data description

`data/project1_supply_chain_demand.csv` — 4,551 raw rows.

| Column | Meaning |
|---|---|
| `date` | Calendar day, 2026-01-01 to 2026-06-29 (180 days) |
| `sku_id` | 28 SKUs: 25 established, 3 newly launched |
| `category` | Beverages, Snacks, Sugar, Pasta, Flour |
| `units_sold` | Daily demand — the forecast target |
| `units_received` | Goods received that day (0 on 89% of days) |
| `closing_stock` | End-of-day inventory |
| `lead_time_days` | Replenishment lead time, 3–14 days |

Column roles are **detected, not assumed** (`app/ml/data.py::detect_schema`), so a
renamed extract still loads. A test renames every column and confirms detection
still works.

Full profile: [`backend/reports/data_profile.md`](backend/reports/data_profile.md).

---

## 6. Data-quality findings

Profiling found seven issues that materially affect modelling. Every one is
handled explicitly and audited through `GET /api/metadata`.

| Finding | Evidence | How it is handled |
|---|---|---|
| **15 byte-identical duplicate rows** | 4 SKUs have 181–182 rows over a 180-day span | Dropped. Left in, they double-weight those days in every rolling statistic. |
| **Category case inconsistency** | `BEVERAGES` vs `Beverages` — 20 stray rows across 16 SKUs | Case normalised, then each SKU's category set to its modal value. Case was the *only* inconsistency; no SKU genuinely changes category. |
| **Missing values** | 90 `units_sold` (1.98%), 46 `closing_stock` (1.01%), scattered evenly across months | Imputed **causally**: demand from the trailing same-weekday median, stock by rolling the inventory balance forward. A test truncates the panel and confirms the fills do not change. |
| **Lead time is noise for the 3 new SKUs** | They report 4–5 different lead times in 12 rows; all 25 established SKUs report exactly one | Replaced with the category median taken from SKUs with a stable value. |
| **Closing stock is censored at zero** | 268 inventory-balance violations — **100%** of them on days where the balance would have gone negative and stock was recorded as 0 | Not "corrected". Those 277 SKU-days are flagged as observed stockouts and used as a risk driver. |
| **Weekly seasonality, no trend** | Day-of-week ratio 1.39 pooled (1.11–1.91 per SKU); lag-7 autocorrelation 0.13–0.47 vs lag-1 0.06–0.24; pooled monthly mean varies <2% over six months | Weekly shape modelled through a shrunk per-SKU weekday index. No trend terms. |
| **Demand spikes** | 34 observations at \|z\| > 4 | Model trained with absolute-error loss so a handful of spikes cannot distort the everyday forecast. |

Two further facts shaped the design rather than the cleaning:

- **Scale spread.** Mean demand ranges 85–536 units/day, so the model predicts a
  *ratio* to each SKU's own trailing mean rather than raw units.
- **Structural under-supply.** Several SKUs receive materially less than they
  sell, and they are precisely the ones with the most historical days at zero
  stock. This became a first-class risk signal (§13).

---

## 7. Feature engineering

One row per (SKU, origin day, horizon). Target: `units_sold(t+h) / trailing_28d_mean(t)`.

| Group | Features | Rationale |
|---|---|---|
| Lagged demand | `lag_1, lag_2, lag_3, lag_7, lag_14` | Recent level and the weekly echo |
| Rolling level | `roll_mean_7/14/28`, `roll_median_28` | 28 days = 4 whole weeks, so the mean is not itself distorted by the weekly cycle |
| Rolling dispersion | `roll_std_7/28`, `cv_28` | Feeds the safety buffer and the confidence band |
| Trend / velocity | `trend_7_over_28`, `velocity_7_over_14` | Is demand accelerating or fading |
| Weekly shape | `dow_index`, `target_dow` | Per-SKU weekday index shrunk toward the category — the dominant signal in this data |
| Inventory context | `stock_level_ratio`, `received_28d_ratio`, `stockout_rate_28` | Scale-free inventory position |
| Static attributes | `lead_time_days`, `category_code`, `days_history` | SKU characteristics and history depth |
| Horizon | `horizon` | Lets one model serve h = 1…28 directly |

**Why a ratio target.** SKU demand spans 6×. Predicting raw units would spend the
model's capacity learning SKU scale. Predicting a ratio lets one pooled model
learn the shared *shape* — weekly pattern, mean reversion, horizon decay — while
each SKU's own history supplies the level. It is also what makes a 12-day-old SKU
forecastable at all.

**Why direct multi-horizon.** Risk needs demand summed over a 3–14 day lead time.
Recursive forecasting compounds error; instead `horizon` is a feature and one
model covers every horizon.

### Leakage control

Every feature for origin day *t* uses observations from days ≤ *t* only. The one
forward-looking input is the **calendar weekday of the target day**, which is
genuinely known in advance.

Three independent guards:

1. `assert_no_leakage()` re-derives `lag_1` and `roll_mean_28` from the raw panel
   and fails the training run on mismatch.
2. `test_features_unchanged_when_future_is_removed` truncates the panel, recomputes
   every feature, and asserts nothing changed for the days that remain — a feature
   that peeked forward would move.
3. Rolling windows are rebuilt **inside each backtest fold**, so no window can span
   a fold boundary.

---

## 8. Model selection

**Selected: `hist_gradient_boosting_ratio`** — `HistGradientBoostingRegressor`
with absolute-error loss, `max_depth=4`, `max_leaf_nodes=15`,
`min_samples_leaf=40`, early stopping.

**Why not deep learning.** The panel holds ~4.5k usable observations across 28
short series with no trend and one seasonal cycle. A sequence model has nowhere
near enough data to justify its parameter count, and it would forfeit the native
handling of missing lags and categorical inputs a histogram gradient-boosting tree
gives for free. Complexity was escalated only as far as validation paid for it —
and the results show the honest picture: ridge regression on the same features
scores 0.1745 against the tree's 0.1721, a 1.4% relative difference. The tree was
selected because it won, but the margin over a linear model is small, and that is
reported rather than hidden.

**Absolute-error loss** was chosen deliberately: profiling found 34 demand spikes
at |z| > 4, and a squared-error objective would chase them at the expense of the
everyday forecast the planner actually uses.

Full detail: [`backend/reports/model_summary.md`](backend/reports/model_summary.md).

---

## 9. Baselines

Three baselines, each answering a specific question.

| Model | Question it answers | Pooled WAPE |
|---|---|---|
| `naive_last_value` | Is any modelling justified at all? | 0.2736 |
| `seasonal_naive_weekly` | Is the weekly pattern the whole story? | 0.2393 |
| `moving_average_28` | Is the weekly pattern worth modelling on top of the level? | **0.1962** |
| `ridge_pooled_ratio` (candidate) | Does a linear map suffice? | 0.1745 |
| `hist_gradient_boosting_ratio` (**selected**) | | **0.1721** |

Notably the *flat 28-day mean beats seasonal naive*, which tells us the level
matters more than the weekly shape on its own — and that a model needs both to
win. It does: 12.3% better than the strongest baseline.

---

## 10. Validation methodology

**Rolling-origin (expanding-window) backtest.** Five folds, each training on
everything up to its origin and forecasting the next 14 days from that single
origin — the same act a planner performs. Test windows are contiguous and
non-overlapping, together covering the last 70 days.

| Fold | Train through | Test window | Training rows |
|---|---|---|---|
| 1 | 2026-04-20 | 2026-04-21 → 2026-05-04 | 2,750 |
| 2 | 2026-05-04 | 2026-05-05 → 2026-05-18 | 3,100 |
| 3 | 2026-05-18 | 2026-05-19 → 2026-06-01 | 3,450 |
| 4 | 2026-06-01 | 2026-06-02 → 2026-06-15 | 3,800 |
| 5 | 2026-06-15 | 2026-06-16 → 2026-06-29 | 4,150 |

A **sixth fold** scores the cold-start SKUs separately, at an origin where they
have 7 days of history (§12). It is never blended into the headline.

### Why a random split would be invalid

1. **Leakage through rolling features.** `roll_mean_28` for a given day is built
   from its 27 neighbours. Under a random split most of those neighbours sit in
   the training set, so the model is graded on days whose own inputs already
   encode the answer.
2. **It measures the wrong task.** A planner never interpolates a missing Tuesday
   between two known days; they stand on the last day of real data and look
   forward.
3. **It is optimistic by construction.** Training on June to predict February
   hides drift, so reported error would flatter production error.

A fresh model is fitted inside every fold; nothing fitted on later data is reused.

---

## 11. Evaluation metrics

**Primary: WAPE** = Σ|actual − forecast| / Σactual.

- **MAPE rejected** — divides by actual demand, so one quiet day on SKU-1008
  (minimum 29 units/day) dominates the average, and it punishes over-forecasting
  far more than under-forecasting: the wrong asymmetry for a stockout tool.
- **RMSE rejected as primary** — dominated by the 34 demand spikes. Still reported.
- **WAPE is unit-free**, so 28 SKUs spanning 85–536 units/day aggregate honestly,
  and it reads as "we are off by X% of the volume we actually shipped".

### Results — selected model, 5 folds pooled, 1,750 forecasts

| Metric | Value |
|---|---|
| **WAPE** | **0.1721** (17.2%) |
| MAE | 51.7 units/day |
| RMSE | 87.6 units/day |
| Bias | −1.48% (slight under-forecast) |
| WAPE spread across folds | ±0.0065 |

Per-fold WAPE: 0.1769, 0.1707, 0.1789, 0.1603, 0.1737 — stable, no fold carrying
the result.

Full tables including per-horizon breakdown:
[`backend/reports/model_evaluation.md`](backend/reports/model_evaluation.md).

---

## 12. Cold-start strategy

`SKU-2000`, `SKU-2001`, `SKU-2002` have **12 days** of history against 180 for
everything else. Five distinct mechanisms handle them.

| # | Mechanism | Detail |
|---|---|---|
| 1 | **Weekly shape is borrowed** | The weekday index is shrunk toward the category's: `w = n/(n+3)`. With one observation of a Tuesday, 75% of the signal comes from the category. |
| 2 | **Variability is borrowed** | The coefficient of variation is shrunk toward the category median of established SKUs, `w = n/(n+14)`, so the safety buffer is not built on 12 noisy days. |
| 3 | **Level uncertainty is priced in** | Lead-time sigma carries a `sqrt(1 + 1/n)` factor — the standard inflation for estimating a mean from n observations. A 12-day SKU therefore scores less confidently, without inventing an uncertainty figure. |
| 4 | **Lead time is repaired** | These SKUs report 4–5 different lead times in 12 rows. Each is replaced with its category median from SKUs with a stable value. |
| 5 | **A simpler model serves them** | On the cold-start fold, `moving_average_28` **beat** the gradient-boosting model. Production routes SKUs under the 30-day threshold to the trailing mean (`ColdStartRouter`). |

On mechanism 5, the honest caveat: that fold scores only 15 forecast points, so the
evidence is thin. The routing is deliberately biased toward the *simpler* model for
the SKUs we know least about — the safe direction to be wrong in.

**In the interface**, these SKUs carry a `New · 12d` badge everywhere they appear,
and the detail page states plainly:

> *Limited history — this SKU has 12 days of observed demand. Its risk estimate is
> less certain than for established SKUs.*

No invented confidence percentage. The observed history length is stated instead.

---

## 13. Stockout methodology

### Modelling inventory *position*, not just stock on hand

A first implementation scored risk on stock on hand alone. On this dataset that
flagged **13 of 28 SKUs Critical** — because roughly half the catalogue is simply
mid-replenishment-cycle at any given moment. That is exactly the meaningless
red dashboard the brief warns against.

The dataset has no open-purchase-order table, but it records 475 historical
deliveries, and they are regular: median inter-arrival CV 0.40 and **receipt
quantity CV just 0.11**. Replenishment is therefore modelled as an *observed rate*
rather than assumed away.

### The calculation

Demand and supply over the lead time L are treated as independent Normals:

```
mu_net    = forecast demand over L  −  expected inflow over L
sigma_net = sqrt(sigma_demand_L² + sigma_supply_L²)

stockout_probability = P(net requirement > stock on hand)
                     = 1 − Φ((stock − mu_net) / sigma_net)
```

- `sigma_demand_L = cv · forecast_daily · sqrt(L) · sqrt(1 + 1/n)`
- `sigma_supply_L` from a compound renewal process: `Var = E[N]·Var(Q) + E[Q]²·Var(N)`,
  every input measured from the SKU's own delivery record
- `safety_stock = 1.645 · sigma_daily · sqrt(L)` (95% cycle service level)
- `reorder_point = lead_time_demand + safety_stock`

The score **is** that probability: 0.87 means "87% chance of running dry inside the
lead time" — not an arbitrary index.

### Two signals fall out of the same arithmetic

- **`days_to_projected_stockout`** — stock walked forward day by day at the
  forecast demand and the observed replenishment rate. The most intuitive number
  on the dashboard: *"you run out in 3 days"*.
- **`supply_coverage_ratio`** — units received ÷ units sold over a window
  **aligned to whole delivery cycles**. Below 1.0 the SKU is structurally
  under-supplied and will drain regardless of today's stock level.

  A fixed-length window was the obvious choice and the wrong one: deliveries are
  discrete and large (8–18 days of supply each), so a fixed window either clips a
  delivery or catches an extra one, swinging the ratio by a third for a SKU
  delivered every 19 days. The window instead runs from the Nth-most-recent
  delivery to the most recent, covering a whole number of cycles. After the fix the
  ratio tracks reality: SKUs at 0.76 are the ones with 22–25% of days at zero
  stock; SKUs above 0.95 have near zero.

### Bands

Absolute and documented, **not percentiles** — percentile banding would guarantee
something is always "Critical" even in a healthy month.

| Stockout probability | Level |
|---|---|
| ≥ 0.70 | Critical |
| ≥ 0.40 | High |
| ≥ 0.20 | Medium |
| ≥ 0.08 | Low |
| otherwise | Healthy |

Zero stock with positive demand is always Critical. A standing supply shortfall
lifts an otherwise-quiet SKU into view, but never beyond what the probability
justifies.

**Resulting distribution on this dataset:** 4 Critical · 1 High · 4 Medium ·
7 Low · 12 Healthy — graded and actionable. Both degenerate outcomes (everything
red, everything green) are asserted against in the test suite.

`stockout_probability_no_inbound` is published alongside, for a planner who knows
nothing is actually on order.

---

## 14. Overstock methodology

Measured against the order-up-to level of a periodic-review policy, **never**
against raw units:

```
S = forecast_daily · (L + R) + z · sigma_daily · sqrt(L + R)      [R = 7-day review]
excess_units = max(0, stock − S)
overstock_score = clip(stock/S − 1, 0, 1)
```

A SKU at 10,000 units is healthy if S is 10,000; a SKU at 500 units is overstocked
if S is 200. Both cases are covered by tests.

Two amplifiers, because excess against a shrinking baseline takes longer to clear:

- **Declining demand** scales the score by up to 1.5×
- **Inflow still above demand** scales it by 1.2×

Excess below **3 days of demand** is treated as noise, not a working-capital
problem.

| Excess above order-up-to | Level |
|---|---|
| ≥ 60% | High |
| ≥ 30% | Medium |
| ≥ 12% | Low |

---

## 15. Explainability architecture

Every explanation is generated by a **runtime Anthropic API call**. There are no
hardcoded explanations, no templates presented as model output, and nothing
pre-generated in the dataset.

```
RiskAssessment (computed)
   └─> build_evidence()      compact JSON of ~38 real numbers + ranked drivers
        └─> SYSTEM_PROMPT     8 absolute rules
             └─> Anthropic    claude-sonnet-5 via MODEL_NAME
                  └─> verify_grounding()   every number traced back to evidence
                       ├── pass -> served, source="llm"
                       └── fail -> deterministic fallback, source="fallback"
```

**The model never sees the dataset.** It receives one evidence object built from
the SKU's own risk record — 3.3 KB against a 4,536-row panel.

**The system prompt forbids**: introducing any number not in the evidence;
inventing business facts (promotions, suppliers, seasonality, contracts);
conflating observed facts with model estimates; and inventing a confidence figure
for a cold-start SKU.

**`verify_grounding()` is the enforcement.** It re-reads the generated text and
checks every number traces back to the evidence, allowing the obvious derivations
a human writer makes (rounding, probability↔percentage). Ungrounded output is
rejected and the fallback is served, labelled `source="fallback"`.

> A bug found by exactly this check: `"SKU-1010"` parsed as the number **−1010**
> (the hyphen read as a minus sign), so every explanation naming its own SKU was
> rejected. Identifiers and ISO dates are now stripped before numbers are
> extracted, with regression tests.

**Caching** is keyed by SKU *and* a hash of the evidence, so a cached explanation
is only reused while the underlying numbers are unchanged. Any movement in the risk
state produces a new key and a genuine new call. "Regenerate" bypasses it entirely.

**Resilience** — `llm_client.py` enforces a 30 s timeout, retries only transient
failures, validates the response (non-empty, length-capped, not an echo of the
evidence), and logs model, latency and token counts but **never the key**. If the
LLM is unavailable the app stays fully usable: risk scores, charts and figures are
unaffected, and the UI says plainly that the generated explanation is temporarily
unavailable.

The key is read from `ANTHROPIC_API_KEY` **server-side only**. There is no
`NEXT_PUBLIC_ANTHROPIC_API_KEY` and the browser never contacts Anthropic.

---

## 16. Grounded Q&A architecture

Pasting the CSV into the prompt fails on three counts: 4,536 rows of daily
movements do not fit a sensible prompt budget; the model would have to re-derive
risk arithmetic it is bad at; and its answers could not be reconciled with what the
dashboard shows.

So there is a retrieval layer, and **the LLM never sees the dataset**.

```
question
  ├─ 1. CLASSIFY   11 intents + entity extraction (SKU ids, categories, risk levels)
  ├─ 2. RETRIEVE   only the structured records that intent needs — the same
  │                RiskAssessment objects the dashboard renders
  ├─ 3. COMPACT    drop unneeded fields, cap lists at 12 SKUs (1.6–5.9 KB)
  └─ 4. ANSWER     from that evidence alone, under a grounding system prompt
```

| Question | Intent | Retrieved |
|---|---|---|
| "Why is SKU-1010 flagged?" | `sku_explanation` | That SKU's full assessment + top 4 drivers (2.3 KB) |
| "Which SKUs need attention?" | `attention_list` | Ranked non-healthy list + portfolio KPIs (5.8 KB) |
| "Which products have the highest stockout risk?" | `stockout_list` | Stockout-type SKUs, ranked |
| "Which SKUs are overstocked?" | `overstock_list` | Overstock SKUs + total excess units |
| "Which categories have the greatest risk?" | `category_risk` | Per-category rollup + worst SKUs |
| "How are the newly launched SKUs doing?" | `new_skus` | Cold-start SKUs + limited-history note |
| "Which SKUs have short inventory coverage?" | `coverage_list` | SKUs ranked by cover |
| "How accurate is the model?" | `model_info` | Model card and validation results |

Because retrieval returns the *same computed records the dashboard renders*, an
answer can never disagree with the table on screen — a property the test suite
asserts directly.

The response carries `grounded_on`, so the UI shows a **"Grounded in live
dashboard data"** badge naming exactly which records were used, plus clickable
links to every SKU referenced.

---

## 17. Local setup

**Prerequisites:** Python 3.11+, Node.js 20+, npm.

```bash
git clone <repository-url>
cd fmn-ai-assessment
cp .env.example backend/.env          # then add your ANTHROPIC_API_KEY
cp .env.example frontend/.env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
```

Then follow [Backend setup](#19-backend-setup) and [Frontend setup](#20-frontend-setup).

---

## 18. Environment variables

### Backend (`backend/.env`, or Render dashboard)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | No¹ | — | Server-side only. Never exposed to the browser. |
| `MODEL_NAME` | No | `claude-sonnet-5` | Model used for explanations and Q&A |
| `FRONTEND_URL` | Production | — | Deployed frontend origin, added to the CORS allowlist (comma-separated accepted) |
| `LOG_LEVEL` | No | `INFO` | |

¹ Without it the app runs normally; explanations and Q&A fall back to a
deterministic read-out of the same computed figures, clearly labelled in the UI.

### Frontend (`frontend/.env.local`, or Vercel dashboard)

| Variable | Required | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes | Backend base URL. Local `http://localhost:8000`; production the Render URL. |

**Never** create `NEXT_PUBLIC_ANTHROPIC_API_KEY` or any other `NEXT_PUBLIC_`
secret — those values are inlined into the shipped JavaScript and are publicly
readable.

---

## 19. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Train once: profiles the data, runs the backtest, selects the model,
# writes the artifact bundle and regenerates the reports (~40 s).
python -m app.ml.training

uvicorn app.main:app --reload --port 8000
```

- API: <http://localhost:8000>
- Interactive docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

If the artifact bundle is missing, the API trains it once on startup rather than
serving errors.

<details>
<summary>If <code>pip install</code> fails to resolve packages</summary>

Some machines have a stale `extra-index-url` in the global pip config that breaks
resolution. Bypass it:

```bash
pip install --isolated --index-url https://pypi.org/simple -r requirements.txt
```
</details>

### Regenerating the data profile

```bash
python scripts/profile_data.py       # from the repository root
```

---

## 20. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000> — it redirects to `/supply-chain`.

| Script | Purpose |
|---|---|
| `npm run dev` | Development server |
| `npm run build` | Production build |
| `npm run lint` | ESLint (flat config) |
| `npm run typecheck` | `tsc --noEmit` |

---

## 21. Tests

```bash
cd backend
python -m pytest tests -q
```

**169 tests, all passing.** Coverage by area:

| File | What it protects |
|---|---|
| `test_data.py` | Schema detection (including fully renamed columns), duplicate removal, category normalisation, **causal imputation** (truncate-and-recompare), lead-time repair, the balance audit measuring source data rather than our own fills, missing-data edge cases |
| `test_features.py` | **No leakage** — three independent proofs: re-derivation from the raw panel for every SKU, truncate-and-recompute, and target alignment. Plus rolling-window correctness and cold-start shrinkage behaviour. |
| `test_risk.py` | The brief's worked example, zero-stock override, monotonicity of probability in stock and lead time, structural under-supply, overstock measured relative to demand (10,000 units healthy / 500 units overstocked), band monotonicity, ranking, cold-start confidence, JSON safety |
| `test_evaluation.py` | Metric correctness, fold construction (chronological, non-overlapping, expanding), **training slice never contains the test window**, a fresh model per fold, baseline correctness |
| `test_llm.py` | Evidence construction, prompt grounding rules present, dataset never sent, grounding verification accepts real numbers and rejects invented ones, identifier/date false-positive regressions, cache behaviour, malformed and error responses |
| `test_api.py` | Every endpoint, KPI self-consistency, ranking, filters, 404s, 422 validation, no NaN in JSON, CORS not using `*`, and that the reported selected model really is the best-scoring one |

Frontend:

```bash
cd frontend && npm run lint && npm run typecheck && npm run build
```

---

## 22. Deployment to Render

**Option A — Blueprint (recommended).** In Render: **New → Blueprint**, point at
this repository. [`backend/render.yaml`](backend/render.yaml) defines the service.

Then set two variables in the dashboard (both `sync: false`, never committed):

| Variable | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your key |
| `FRONTEND_URL` | your Vercel URL, e.g. `https://your-app.vercel.app` |

The build runs `pip install -r requirements.txt && python -m app.ml.training`, so
the model is trained during deployment and the first request is served warm. The
start command binds correctly for Render:

```
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check path: `/health`.

**Option B — Docker.** [`backend/Dockerfile`](backend/Dockerfile) builds from the
**repository root** (it needs both the app and `data/`):

```bash
docker build -f backend/Dockerfile -t fmn-supply-chain-api .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-... fmn-supply-chain-api
```

### CORS

`allow_origins` is an explicit list — never `"*"`. It always contains
`localhost:3000` for development, plus whatever `FRONTEND_URL` names. Vercel
preview deployments are matched by regex (`https://*.vercel.app`). A test asserts
the wildcard is not used.

---

## 23. Deployment to Vercel

1. **New Project** → import this repository.
2. Set **Root Directory** to `frontend`.
3. Framework preset: **Next.js** (auto-detected). No build overrides needed.
4. Add the environment variable:

   | Variable | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://<your-service>.onrender.com` |

5. Deploy, then set `FRONTEND_URL` on the Render service to the resulting Vercel
   URL so CORS allows it.

No `localhost` is hardcoded in any production code path — the API base URL comes
from `NEXT_PUBLIC_API_URL` only.

---

## 24. API overview

Interactive documentation at `/docs`.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness, artifact status, whether the LLM is configured |
| `GET` | `/api/dashboard` | KPIs, risk distribution, category rollup, ranked attention list |
| `GET` | `/api/skus` | SKU list; filters: `risk_level`, `risk_type`, `category`, `cold_start`, `search` |
| `GET` | `/api/skus/{sku_id}` | Full drill-down: risk, policy, drivers, 90-day history, 28-day forecast |
| `GET` | `/api/skus/{sku_id}/explanation` | Runtime LLM explanation (`?force=true` bypasses cache) |
| `POST` | `/api/qa` | Grounded natural-language answer |
| `GET` | `/api/qa/suggestions` | Starter questions, one naming a currently flagged SKU |
| `GET` | `/api/metadata` | Dataset summary, cleaning audit, risk configuration |
| `GET` | `/api/model-info` | Model card: selection, metrics, validation design, cold-start handling |
| `GET` | `/api/categories` | Per-category risk rollup |

Example — `GET /api/skus/SKU-1010` (abridged, real values):

```json
{
  "sku_id": "SKU-1010",
  "category": "Snacks",
  "risk_level": "HIGH",
  "risk_type": "STOCKOUT",
  "risk_score": 0.5671,
  "stockout_probability": 0.5671,
  "stockout_probability_no_inbound": 1.0,
  "current_stock": 112.0,
  "forecast_daily_demand": 179.0,
  "inventory_coverage_days": 0.63,
  "days_to_projected_stockout": 3.0,
  "lead_time_days": 3.0,
  "lead_time_demand": 592.2,
  "reorder_point_units": 729.5,
  "order_up_to_units": 2040.6,
  "suggested_order_qty": 1505.5,
  "replenishment_rate_per_day": 141.0,
  "expected_inbound_within_lead_time": 423.0,
  "supply_coverage_ratio": 0.76,
  "is_structurally_undersupplied": true,
  "observed_stockout_rate_all_time": 0.217,
  "days_of_history": 180,
  "is_cold_start": false,
  "confidence": "HIGH",
  "drivers": [
    { "name": "days_to_projected_stockout", "label": "Days until projected stockout",
      "value": 3.0, "unit": "days",
      "detail": "Stock walked forward day by day at the forecast demand of 179 units/day and the observed replenishment rate of 141 units/day. Lead time is 3 days." },
    { "name": "inventory_coverage_days", "label": "Inventory coverage",
      "value": 0.63, "unit": "days", "detail": "…" },
    { "name": "supply_coverage_ratio", "label": "Supply vs demand (last 65 days)",
      "value": 0.76, "unit": "ratio", "detail": "…" }
  ]
}
```

---

## 25. Limitations

Stated plainly, and surfaced in the app's own "How it works" page.

1. **No open purchase orders in the dataset.** `units_received` is a record of past
   deliveries, not a forward order book. Expected inbound is *inferred* from each
   SKU's delivery cadence, clearly labelled as an estimate everywhere it appears,
   and the conservative `stockout_probability_no_inbound` is published alongside.
   A confirmed order a planner knows about is not reflected.
2. **Six months of history, one seasonal cycle.** Weekly patterns are supported by
   the data; annual seasonality, promotions and holiday effects cannot be learned
   or validated.
3. **Demand is recorded, not true, demand.** Closing stock is censored at zero on
   277 SKU-days; on those days real customer demand may have exceeded the sales
   figure, so the model under-states demand for chronically short SKUs.
4. **Cold-start metrics rest on few points.** The cold-start fold scores 15
   forecasts across 3 SKUs. It shows direction, not a dependable error rate.
5. **Lead times are treated as fixed.** Safety stock covers demand variability but
   not late deliveries, so it is a lower bound on the buffer actually required.
6. **No cost or margin data.** Risk is ranked by likelihood and days of excess
   cover, not financial impact, so a high-value SKU is not prioritised over a
   low-value one at equal risk.
7. **Single-node in-memory cache.** LLM explanation caching is per-process; a
   multi-instance deployment would want a shared cache.
8. **The model is retrained offline.** There is no scheduled retraining or drift
   monitoring; the artifact is rebuilt on deploy.

---

## 26. Next steps

**Highest value first:**

1. **Ingest open purchase orders.** The single biggest accuracy gain available.
   It would replace the inferred inbound estimate with fact and remove the largest
   caveat in the product.
2. **Add cost and margin data** so the attention list can be ranked by money at
   risk rather than probability alone — the natural next question a sponsor asks.
3. **Model lead-time variability.** Supplier delivery dates are already in the
   data; measuring their variance would turn safety stock from a lower bound into
   a real service-level guarantee.
4. **Censored-demand correction.** Treat zero-stock days as right-censored
   observations (Tobit or a simple lost-sales uplift) so chronically short SKUs
   stop being under-forecast.
5. **Scheduled retraining with drift monitoring** — nightly retrain, alert when
   rolling WAPE degrades against the validation baseline.
6. **Alerting and workflow** — email or Teams digest of newly Critical SKUs, and
   a "mark as actioned" state so the list reflects what the team has already dealt
   with.
7. **Prediction intervals in the UI** — the machinery exists (`sigma_daily`); a
   fan chart around the forecast would make uncertainty visible rather than
   implied.
8. **Persist Q&A history** so planners can revisit and share answers.

---

## 27. Demo and deployed URLs

| Environment | URL | Status |
|---|---|---|
| Frontend (Vercel) | `<not yet deployed>` | Deployment configuration is complete and verified locally; the app has not been deployed to Vercel. |
| Backend (Render) | `<not yet deployed>` | `render.yaml` and `Dockerfile` are provided; the service has not been created. |

Both applications run locally as described above, and the frontend production
build, lint and typecheck all pass.

### What has and has not been verified

**Verified locally:**

- All 169 backend tests pass.
- Frontend `lint`, `typecheck` and production `build` all pass cleanly.
- Backend startup, and every API endpoint exercised through a live server.
- Model training end to end, with the reported metrics asserted to match the
  trained artifact (`scripts/final_check.py`).
- The full UI, including no horizontal overflow, a
  working sticky header, and internal scrolling for the SKU table.
- **The live Anthropic API**, via `scripts/verify_live_llm.py`:
  - 4/4 explanations generated by `claude-sonnet-5` across a stockout, an
    overstock, a cold-start and a healthy SKU — every one passing grounding
    verification.
  - 9/9 Q&A answers generated live. An off-topic question ("What is the capital
    of France?") was declined and redirected to dashboard data, and a question
    about a non-existent SKU-9999 was declined without inventing a figure.
  - Typical latency 4–7 s, ~1.5–3.7k input tokens per call.

One issue that surfaced only under live testing: the model wrote *"lead-time
demand of 725 units — well above the reorder point of 872.4 units"*. Both figures
were real, so grounding verification passed, but the comparison is arithmetically
wrong. Number-level grounding cannot catch a bad *relation*. The evidence object
now carries a `_how_to_read` list naming which quantities are meaningfully
comparable, and the prompt forbids unchecked comparisons; re-running produced
correct pairings. Covered by
`test_evidence_states_which_comparisons_are_meaningful`.

**Not verified:** the Docker image build, as Docker is not installed in this
environment. The equivalent Render native build (`pip install -r requirements.txt`
→ `python -m app.ml.training` → `uvicorn`) was run successfully, which is the path
`render.yaml` actually uses.
