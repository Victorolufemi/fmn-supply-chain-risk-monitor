# Project 1 — Supply Chain Risk Monitor
## Presentation outline (7 slides, ~10 minutes)

All figures below are computed from the supplied dataset and reproduced by
`python -m app.ml.training`. Nothing here is estimated or illustrative.

---

## Slide 1 — The problem

**Title:** "Which SKUs need attention, and why?"

> *"We keep getting caught off guard — some SKUs run out and delay production,
> others sit overstocked and tie up working capital. I don't have anything today
> that tells me, ahead of time, which SKUs need attention and why."*

**Three things are being asked for:**
- Advance warning, not a rear-view report
- Prioritisation — 28 SKUs, limited planner attention
- A reason a human can act on

**The translation into a measurable question:**

> For each SKU, what is the probability that demand over the replenishment lead
> time exceeds what will be available, and how far is stock above the maximum the
> replenishment policy justifies?

**Talking point:** the forecast is a means, not the deliverable. Nobody acts on
"we expect 179 units a day". They act on *"0.6 days of cover against a 3-day lead
time, and you're receiving 76 units for every 100 you sell."*

---

## Slide 2 — The solution and the user's workflow

**Title:** A working web application, not a notebook

**Live walkthrough (60 seconds):**
1. Land on the dashboard → four KPIs answer "how bad is it?" at a glance
2. *Inventory coverage vs lead time* scatter → anything below the diagonal cannot
   be replenished in time. Position on a page, not a number in a table.
3. Attention table, ranked by severity then by days-to-stockout
4. Click **SKU-1010** → drill-down
5. Press **Generate explanation** → AI writes the reason from that SKU's figures
6. Type into **Ask about your inventory** → grounded answer with source badges

**Architecture in one line:**
`Next.js (Vercel) → REST → FastAPI (Render) → artifact bundle loaded once at startup`

The frontend holds no ML logic, no thresholds, no model files and no secrets.

---

## Slide 3 — Data and modelling approach

**Title:** What the data actually said

**Seven findings that changed the build** (from `data_profile.md`):

| Found | Consequence |
|---|---|
| 15 duplicate rows | Dropped — they double-weight days in every rolling statistic |
| `BEVERAGES` vs `Beverages`, 20 rows | Normalised; case was the only inconsistency |
| 90 missing demand values | Imputed *causally* — the fill never looks forward |
| The 3 new SKUs report 4–5 lead times in 12 days | Noise, not signal → category median |
| 268 inventory-balance violations, **100%** explained by stock censored at zero | Not "fixed" — flagged as 277 observed stockout days and used as a risk driver |
| Weekly cycle 1.39×, monthly trend < 2% | Model the weekly shape; no trend terms |
| Demand spans 85–536 units/day | Predict a **ratio** to each SKU's own level, so one pooled model works |

**Modelling approach:**
- Target: `units_sold(t+h) / trailing_28d_mean(t)`, horizon a feature → one model
  serves h = 1…28
- Every feature at origin *t* uses days ≤ *t* only; the sole forward input is the
  target day's calendar weekday
- **Not deep learning**: ~4.5k observations, 28 short series, one seasonal cycle.
  Complexity was escalated only as far as validation paid for it.

---

## Slide 4 — Validation and results

**Title:** Measured properly, reported honestly

**Rolling-origin backtest**, 5 expanding folds, 14-day horizon, covering the last
70 days. A fresh model is fitted inside each fold.

**Why not a random split** (one line each):
1. Rolling features leak across a shuffled boundary
2. It scores interpolation, not forecasting
3. Training on June to predict February hides drift

**Results — 1,750 forecasts, pooled WAPE:**

| Model | Role | WAPE |
|---|---|---|
| `naive_last_value` | baseline | 0.2736 |
| `seasonal_naive_weekly` | baseline | 0.2393 |
| `moving_average_28` | baseline | **0.1962** |
| `ridge_pooled_ratio` | candidate | 0.1745 |
| **`hist_gradient_boosting_ratio`** | **selected** | **0.1721** |

**→ 12.3% relative improvement over the strongest baseline.**
MAE 51.7 units/day · Bias −1.48% · fold-to-fold spread ±0.0065

**Two things to say out loud:**
- Ridge scores 0.1745 against the tree's 0.1721 — a 1.4% margin. The tree won, but
  barely, and that is reported rather than hidden.
- **WAPE chosen over MAPE** (distorted by low-volume days, and asymmetric in the
  wrong direction for a stockout tool) **and over RMSE** (dominated by the 34
  demand spikes).

**Cold start:** the 3 new SKUs have 12 days each. A separate fold scores them at
7 days of history — where `moving_average_28` **beat** the main model. Production
routes them to the simpler model. 15 forecast points, so thin evidence, and the
routing errs toward the safer choice.

---

## Slide 5 — AI explanations and grounded Q&A

**Title:** The model never sees the data

**Explanations** — runtime Anthropic call, no templates:

```
RiskAssessment → build_evidence()  (3.3 KB of real numbers + ranked drivers)
              → system prompt (8 absolute rules)
              → Anthropic
              → verify_grounding()  every number traced back to the evidence
                   pass → served        fail → labelled fallback
```

**Grounded Q&A** — a retrieval layer, not a CSV dump:

```
question → classify (11 intents) → retrieve only what that intent needs
        → compact (1.6–5.9 KB)  → answer from that evidence alone
```

Retrieval returns *the same computed records the dashboard renders*, so an answer
can never disagree with the table on screen — asserted directly in the tests.

**Two bugs worth mentioning** — both found *by* this machinery, which is the
argument for building it:

1. The grounding check was parsing `"SKU-1010"` as the number **−1010**, silently
   rejecting every valid explanation. Fixed, with regression tests.
2. Live testing produced *"lead-time demand of 725 units — well above the reorder
   point of 872.4"*. Both figures real, so number-level grounding passed, but the
   comparison is wrong. **Grounding numbers does not ground relations.** The
   evidence now states which quantities are meaningfully comparable, and the
   prompt forbids unchecked comparisons.

**Degradation:** no API key → risk scores, charts and figures are unaffected;
explanations fall back to a direct read-out of the same numbers and the UI says so.

---

## Slide 6 — The application

**Title:** Screenshots / live demo

Capture from the running app (`npm run dev` + `uvicorn`):
1. **Dashboard** — KPI row, coverage-vs-lead-time scatter, risk distribution,
   category rollup
2. **Attention table** — badges, filters, the `New · 12d` cold-start marker
3. **SKU-1010 detail** — recommended action, AI explanation card, demand chart with
   the forecast continuing past "today"
4. **SKU-1006 inventory chart** — stock sawtoothing repeatedly *above* the
   order-up-to line: the overstock story in one picture
5. **Ask panel** — answer plus "Grounded in live dashboard data" badges
6. **How it works** page — metrics, validation design, and a candid list of what
   the tool cannot tell you

**Current risk distribution:** 4 Critical · 1 High · 4 Medium · 7 Low · 12 Healthy

**Talking point:** the first implementation flagged **13 of 28 SKUs Critical**,
because half the catalogue is mid-replenishment-cycle at any moment. Modelling
inventory *position* rather than stock on hand — and aligning the supply window to
whole delivery cycles — produced a list a planner can actually work through.

---

## Slide 7 — Limitations and next steps

**Title:** What it cannot tell you, and what comes next

**Limitations (lead with these — they are the credibility):**
- **No open purchase orders.** Inbound is *inferred* from delivery cadence and
  labelled as an estimate throughout; the conservative "if nothing is on order"
  figure is published alongside.
- **Six months, one seasonal cycle.** Weekly patterns are supported; annual
  seasonality and promotions are not.
- **Demand is recorded, not true, demand** — censored on 277 zero-stock days.
- **Cold-start metrics rest on 15 forecast points.**
- **No cost data**, so risk is not yet ranked by money.

**Next steps, highest value first:**
1. Ingest open purchase orders — the single biggest accuracy gain available
2. Add cost and margin → rank the attention list by money at risk
3. Model lead-time variability → turn safety stock into a real service guarantee
4. Censored-demand correction so short SKUs stop being under-forecast
5. Scheduled retraining with drift monitoring

**Closing line:** the tool does not just say a SKU is red. It says *how many days
of cover it has, against what lead time, why the stock is draining, and how many
units to order* — and every one of those numbers is reproducible from the dataset.

---

### Notes for the presenter

- **Do not fabricate screenshots.** Capture them from the running application.
- Deployment URLs: the app is configured for Render and Vercel but has **not been
  deployed**. Say so if asked; do not claim a live URL.
- The live Anthropic API **has** been exercised: 4/4 explanations and 9/9 Q&A
  answers generated by `claude-sonnet-5`, all passing grounding verification,
  including correct refusals for an off-topic question and an unknown SKU.
  Reproduce with `python scripts/verify_live_llm.py`.
- Docker was not installed in the build environment, so the image build is
  unverified; the Render native build path was run successfully.
- Deepest technical question to be ready for: *"How do you know there's no
  leakage?"* → three independent proofs, including truncate-and-recompute across
  every feature, plus rolling windows rebuilt inside each fold.
- Best business question to be ready for: *"Why should I trust the inbound
  estimate?"* → receipt-quantity CV is 0.11 across 475 deliveries; the estimate is
  never allowed to remove a flag on its own, and the no-inbound figure is always
  shown.
