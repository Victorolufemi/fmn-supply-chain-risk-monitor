/**
 * Supply Chain Risk Monitor — build walkthrough deck.
 *
 * Structure: the problem I was given → how I framed it → what I built → how I
 * built it, phase by phase, with the decision and the evidence at each step.
 *
 * Palette and motif are taken from the product itself (indigo→sky brand, the
 * five risk colours). Motif: rounded cards with a small solid colour-coded
 * circle badge. No accent stripes, no underlines.
 *
 * Every figure is computed from the supplied dataset and reproduced by
 * `python -m app.ml.training`. Nothing here is illustrative.
 */
const PptxGenJS = require("pptxgenjs");

// ── palette ──────────────────────────────────────────────────────────────────
const NAVY = "10162F";
const NAVY_SOFT = "1C2547";
const INDIGO = "4F46E5";
const VIOLET = "7C3AED";
const SKY = "0EA5E9";
const AMBER = "F59E0B";
const ROSE = "E11D48";
const EMERALD = "10B981";
const INK = "1E293B";
const MUTED = "64748B";
const FAINT = "94A3B8";
const LIGHT = "F7F9FC";
const CARD = "FFFFFF";
const TINT = "EEF2FF";
const LINE = "E2E8F0";
const ICE = "CBD5E1";

const HEAD = "Cambria";
const BODY = "Calibri";
const MONO = "Consolas";

// ── geometry ─────────────────────────────────────────────────────────────────
const W = 13.3;
const M = 0.65;
const CW = W - M * 2; // 12.0
const TITLE_Y = 0.84; // kicker sits at 0.50 → clears the 0.5in margin
const BODY_Y = 1.72;

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE";
pres.author = "Olufemi Victor";
pres.title = "Supply Chain Risk Monitor — build walkthrough";

// fresh object every call — pptxgenjs mutates options in place
const shadow = () => ({
  type: "outer",
  angle: 90,
  blur: 8,
  offset: 2,
  color: "0F172A",
  opacity: 0.07,
});

const slideLight = () => {
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  return s;
};
const slideDark = () => {
  const s = pres.addSlide();
  s.background = { color: NAVY };
  return s;
};

function title(s, text, kicker, dark = false) {
  if (kicker) {
    s.addText(kicker.toUpperCase(), {
      x: M,
      y: TITLE_Y - 0.34,
      w: CW,
      h: 0.26,
      fontFace: BODY,
      fontSize: 11,
      bold: true,
      charSpacing: 2.2,
      color: dark ? AMBER : INDIGO,
      isTextBox: true,
      margin: 0,
    });
  }
  s.addText(text, {
    x: M,
    y: TITLE_Y,
    w: CW,
    h: 0.72,
    fontFace: HEAD,
    fontSize: 33,
    bold: true,
    color: dark ? "FFFFFF" : INK,
    isTextBox: true,
    margin: 0,
  });
}

function card(s, x, y, w, h, fill = CARD, withShadow = true) {
  s.addShape(pres.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    rectRadius: 0.1,
    fill: { color: fill },
    line: { color: fill === CARD ? LINE : fill, width: 1 },
    ...(withShadow ? { shadow: shadow() } : {}),
  });
}

function badge(s, x, y, d, color, text, fontSize = 13) {
  s.addShape(pres.ShapeType.ellipse, {
    x,
    y,
    w: d,
    h: d,
    fill: { color },
    line: { color, width: 0 },
  });
  s.addText(text, {
    x,
    y,
    w: d,
    h: d,
    fontFace: BODY,
    fontSize,
    bold: true,
    color: "FFFFFF",
    align: "center",
    valign: "middle",
    isTextBox: true,
    margin: 0,
  });
}

function label(s, x, y, text, color = INDIGO, w = 5) {
  s.addText(text.toUpperCase(), {
    x,
    y,
    w,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color,
    isTextBox: true,
    margin: 0,
  });
}

function body(s, x, y, w, h, text, size = 12, color = MUTED) {
  s.addText(text, {
    x,
    y,
    w,
    h,
    fontFace: BODY,
    fontSize: size,
    color,
    lineSpacingMultiple: 1.18,
    isTextBox: true,
    margin: 0,
  });
}

function heading(s, x, y, w, text, size = 14.5, color = INK) {
  s.addText(text, {
    x,
    y,
    w,
    h: 0.3,
    fontFace: BODY,
    fontSize: size,
    bold: true,
    color,
    isTextBox: true,
    margin: 0,
  });
}

/* ═════════════════════════════════════════════════════════ 1 — TITLE ═══════ */
{
  const s = slideDark();
  [ROSE, AMBER, "FBBF24", SKY, EMERALD].forEach((c, i) => {
    s.addShape(pres.ShapeType.ellipse, {
      x: 10.62 + i * 0.42,
      y: 0.72,
      w: 0.26,
      h: 0.26,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
  });

  s.addText("FMN AI ENGINEER INTERNSHIP  ·  PROJECT 1", {
    x: M,
    y: 2.0,
    w: CW,
    h: 0.3,
    fontFace: BODY,
    fontSize: 12,
    bold: true,
    charSpacing: 2.6,
    color: AMBER,
    isTextBox: true,
    margin: 0,
  });
  s.addText("Supply Chain Risk Monitor", {
    x: M,
    y: 2.4,
    w: 11.4,
    h: 1.0,
    fontFace: HEAD,
    fontSize: 50,
    bold: true,
    color: "FFFFFF",
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "The problem I was given, what I built, and how I built it — with the evidence for every claim.",
    {
      x: M,
      y: 3.48,
      w: 10.6,
      h: 0.5,
      fontFace: BODY,
      fontSize: 18,
      color: ICE,
      isTextBox: true,
      margin: 0,
    },
  );

  [
    ["A vague brief", "turned into a measurable prediction problem"],
    ["A working web app", "FastAPI + Next.js, not a notebook"],
    ["Evidence throughout", "169 tests, every figure reproducible"],
  ].forEach(([v, l], i) => {
    const x = M + i * 4.0;
    card(s, x, 4.56, 3.7, 1.3, NAVY_SOFT, false);
    s.addText(v, {
      x: x + 0.3,
      y: 4.74,
      w: 3.1,
      h: 0.36,
      fontFace: HEAD,
      fontSize: 18,
      bold: true,
      color: i === 1 ? SKY : "FFFFFF",
      isTextBox: true,
      margin: 0,
    });
    body(s, x + 0.3, 5.14, 3.1, 0.6, l, 11.5, ICE);
  });

  s.addText("Olufemi Victor", {
    x: M,
    y: 6.46,
    w: 6,
    h: 0.3,
    fontFace: BODY,
    fontSize: 12.5,
    color: FAINT,
    isTextBox: true,
    margin: 0,
  });

  s.addNotes(
    "Frame the talk in one line: I was handed a vague sponsor brief and six months of daily SKU data, and I turned it into a working decision tool. I will walk the problem, then the build, then how I validated every claim. Everything in this deck is computed from the dataset — nothing is illustrative.",
  );
}

/* ══════════════════════════════════════════ 2 — THE PROBLEM I WAS GIVEN ════ */
{
  const s = slideLight();
  title(s, "The problem I was given", "1 · The problem");

  card(s, M, BODY_Y, 6.9, 2.66, TINT, false);
  s.addText(
    "“We keep getting caught off guard — some SKUs run out and delay production, others sit overstocked and tie up working capital. I don't have anything today that tells me, ahead of time, which SKUs need attention and why.”",
    {
      x: M + 0.5,
      y: BODY_Y + 0.42,
      w: 5.9,
      h: 1.6,
      fontFace: HEAD,
      fontSize: 16,
      italic: true,
      color: INK,
      lineSpacingMultiple: 1.26,
      isTextBox: true,
      margin: 0,
    },
  );
  body(s, M + 0.5, BODY_Y + 2.12, 5.9, 0.3, "FMN Supply Chain sponsor", 11.5, MUTED);

  label(s, 8.0, BODY_Y + 0.04, "What was actually being asked", INDIGO, 4.7);
  [
    ["Advance warning", "A signal before the stockout, not a rear-view report.", ROSE],
    ["Prioritisation", "28 SKUs, one planner. Which three matter this morning?", AMBER],
    ["A reason to act on", "Not a red dot — the numbers, in plain English.", INDIGO],
  ].forEach(([h, d, c], i) => {
    const y = BODY_Y + 0.44 + i * 0.84;
    badge(s, 8.0, y + 0.04, 0.42, c, String(i + 1), 13);
    heading(s, 8.58, y, 4.1, h, 15);
    body(s, 8.58, y + 0.32, 4.1, 0.44, d, 11.5);
  });

  card(s, M, 4.72, CW, 1.62, NAVY, false);
  label(s, M + 0.4, 4.92, "The gap I had to close", AMBER, 6);
  s.addText(
    "The brief names no target, no metric and no threshold. Before writing any model code I had to decide what “needs attention” means in numbers — otherwise there is nothing to train, nothing to validate, and no way to tell whether the tool works.",
    {
      x: M + 0.4,
      y: 5.26,
      w: 11.2,
      h: 0.86,
      fontFace: BODY,
      fontSize: 13.5,
      color: ICE,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Read the quote, then land the three asks — and be explicit that only the third is really about AI. The dark band is the important part: the brief is unmeasurable as written. Everything that follows starts from having to define the target myself.",
  );
}

/* ═══════════════════════════════════════════════ 3 — HOW I FRAMED IT ═══════ */
{
  const s = slideLight();
  title(s, "How I turned it into a measurable problem", "2 · Framing");

  card(s, M, BODY_Y, CW, 1.36, NAVY, false);
  label(s, M + 0.42, BODY_Y + 0.2, "The question I chose to answer", AMBER, 8);
  s.addText(
    "For each SKU, what is the probability that demand over the lead time exceeds what will be available — and how far is stock above the maximum the replenishment policy justifies?",
    {
      x: M + 0.42,
      y: BODY_Y + 0.54,
      w: 11.2,
      h: 0.66,
      fontFace: HEAD,
      fontSize: 16.5,
      color: "FFFFFF",
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  [
    ['"which SKUs need attention"', "A ranked list — severity, then urgency", INDIGO],
    ['"some SKUs run out"', "Probability of running dry inside the lead time", ROSE],
    ['"others sit overstocked"', "Units above the order-up-to level", SKY],
    ['"and why"', "Quantified drivers + an AI explanation", AMBER],
  ].forEach(([q, a, c], i) => {
    const x = M + i * 3.05;
    card(s, x, 3.3, 2.8, 1.8);
    s.addShape(pres.ShapeType.ellipse, {
      x: x + 0.26,
      y: 3.54,
      w: 0.2,
      h: 0.2,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    s.addText(q, {
      x: x + 0.26,
      y: 3.84,
      w: 2.3,
      h: 0.5,
      fontFace: HEAD,
      fontSize: 13,
      italic: true,
      color: INK,
      lineSpacingMultiple: 1.1,
      isTextBox: true,
      margin: 0,
    });
    body(s, x + 0.26, 4.36, 2.3, 0.66, a, 12);
  });

  label(s, M, 5.44, "Two decisions this locked in", INDIGO, 6);
  [
    [
      "Forecast horizon = 28 days",
      "It must cover the longest lead time in the data (14 days) plus a review cycle, so lead-time demand is always inside the forecast.",
    ],
    [
      "The forecast is a means, not the deliverable",
      "Nobody acts on “179 units a day”. They act on “0.6 days of cover against a 3-day lead time”.",
    ],
  ].forEach(([h, d], i) => {
    const x = M + i * 6.12;
    card(s, x, 5.78, 5.88, 1.12, TINT, false);
    heading(s, x + 0.28, 5.94, 5.3, h, 13.5);
    body(s, x + 0.28, 6.26, 5.3, 0.5, d, 11.5);
  });

  s.addNotes(
    "This is the slide that proves the vague brief was actually translated. Each phrase maps to something computed. Then the two locked-in decisions: the horizon is not arbitrary — it is set by the longest lead time in the data — and the forecast is infrastructure, not the product.",
  );
}

/* ═══════════════════════════════════════════════ 4 — WHAT I BUILT ══════════ */
{
  const s = slideLight();
  title(s, "What I built", "3 · The deliverable");

  [
    [
      "Offline training pipeline",
      "Python · scikit-learn",
      "Detects the schema, cleans and audits, engineers leakage-safe features, backtests five models, scores every SKU, writes one 250 KB artifact bundle plus three generated reports.",
      INDIGO,
    ],
    [
      "REST API",
      "FastAPI",
      "Loads the bundle once at startup and serves slices of it. Ten endpoints. Owns all business rules, the Anthropic calls and the Q&A retrieval layer.",
      VIOLET,
    ],
    [
      "Web application",
      "Next.js · TypeScript · Tailwind · Recharts",
      "Dashboard, SKU drill-down and a model transparency page. Renders only — no ML logic, no thresholds, no model files, no keys.",
      SKY,
    ],
  ].forEach(([h, stack, d, c], i) => {
    const y = BODY_Y + i * 1.58;
    card(s, M, y, 7.55, 1.42);
    badge(s, M + 0.28, y + 0.26, 0.46, c, String(i + 1), 13);
    heading(s, M + 0.88, y + 0.22, 4.2, h, 15);
    s.addText(stack, {
      x: M + 0.88,
      y: y + 0.54,
      w: 6.3,
      h: 0.26,
      fontFace: MONO,
      fontSize: 10,
      color: c,
      isTextBox: true,
      margin: 0,
    });
    body(s, M + 0.88, y + 0.82, 6.3, 0.56, d, 11.5);
  });

  [1, 2].forEach((i) => {
    s.addText("▼", {
      x: M + 0.34,
      y: BODY_Y + i * 1.58 - 0.18,
      w: 0.34,
      h: 0.2,
      fontFace: BODY,
      fontSize: 11,
      color: FAINT,
      align: "center",
      isTextBox: true,
      margin: 0,
    });
  });

  card(s, 8.5, BODY_Y, 4.15, 4.58, TINT, false);
  label(s, 8.82, BODY_Y + 0.26, "What ships", INDIGO, 3.6);
  s.addText(
    [
      { text: "Working web app, deployable to Vercel + Render", options: { bullet: true, breakLine: true } },
      { text: "Trained model + risk scores for all 28 SKUs", options: { bullet: true, breakLine: true } },
      { text: "Runtime AI explanations, grounding-verified", options: { bullet: true, breakLine: true } },
      { text: "Grounded natural-language Q&A", options: { bullet: true, breakLine: true } },
      { text: "169 automated tests", options: { bullet: true, breakLine: true } },
      { text: "Data profile, model evaluation, model summary", options: { bullet: true, breakLine: true } },
      { text: "README + a full how-it-works reference", options: { bullet: true } },
    ],
    {
      x: 8.82,
      y: BODY_Y + 0.66,
      w: 3.55,
      h: 3.72,
      fontFace: BODY,
      fontSize: 12,
      color: INK,
      lineSpacingMultiple: 1.14,
      paraSpaceAfter: 7,
      isTextBox: true,
      margin: 0,
    },
  );

  body(
    s,
    M,
    6.6,
    CW,
    0.32,
    "Nothing is trained or recomputed per request — training is offline, the API only reads.",
    12.5,
    MUTED,
  );

  s.addNotes(
    "Three tiers, one rule: the browser renders what the API computed. That separation is enforced by an automated check, not convention — it scans the frontend for hardcoded SKU ids, risk thresholds and any Anthropic reference. Call out the artifact bundle: training runs once, the API loads 250 KB at startup and every request is a lookup.",
  );
}

/* ═══════════════════════════════════════════════ 5 — HOW I WORKED ══════════ */
{
  const s = slideLight();
  title(s, "How I worked — and the call I made at each step", "4 · Method");

  [
    ["Profile the data first", "Before any model code. Seven findings changed the build.", INDIGO],
    ["Engineer features causally", "Every input at day t uses days ≤ t. Proven three ways.", VIOLET],
    ["Baseline before candidate", "Three baselines, each answering a specific question.", SKY],
    ["Validate chronologically", "Rolling origin. A random split would have been invalid.", EMERALD],
    ["Turn forecast into decision", "Ordinary inventory maths a planner can argue with.", AMBER],
    ["Then engineer it properly", "Tests, security, performance, deployment.", ROSE],
  ].forEach(([h, d, c], i) => {
    const x = M + (i % 3) * 4.07;
    const y = BODY_Y + Math.floor(i / 3) * 2.3;
    card(s, x, y, 3.85, 2.06);
    badge(s, x + 0.28, y + 0.28, 0.5, c, String(i + 1), 15);
    s.addText(h, {
      x: x + 0.28,
      y: y + 0.92,
      w: 3.3,
      h: 0.56,
      fontFace: BODY,
      fontSize: 15.5,
      bold: true,
      color: INK,
      lineSpacingMultiple: 1.1,
      isTextBox: true,
      margin: 0,
    });
    body(s, x + 0.28, y + 1.5, 3.3, 0.46, d, 11.5);
  });

  body(
    s,
    M,
    6.46,
    CW,
    0.34,
    "The order mattered: profiling is what told me the weekly cycle dominates, that stock is censored at zero, and that lead time is noise for the new SKUs.",
    12.5,
    MUTED,
  );

  s.addNotes(
    "This is the spine of the talk — six phases, one decision each. If asked why I did not start modelling immediately: profiling is what revealed the weekly cycle dominates, that closing stock is censored at zero, and that the three new SKUs report a different lead time almost every row. All three changed what I built.",
  );
}

/* ═══════════════════════════════════════════ 6 — PHASE 1: THE DATA ═════════ */
{
  const s = slideLight();
  title(s, "Phase 1 — I started with the data, not the model", "5 · Data");

  card(s, M, BODY_Y, 3.5, 4.05);
  label(s, M + 0.3, BODY_Y + 0.26, "What I was given", INDIGO, 3);
  [
    ["4,551", "raw rows"],
    ["28", "SKUs"],
    ["180", "days"],
    ["3", "new SKUs, 12 days each"],
  ].forEach(([v, l], i) => {
    const y = BODY_Y + 0.74 + i * 0.8;
    s.addText(v, {
      x: M + 0.3,
      y,
      w: 1.2,
      h: 0.42,
      fontFace: HEAD,
      fontSize: 22,
      bold: true,
      color: i === 3 ? AMBER : INK,
      isTextBox: true,
      margin: 0,
    });
    body(s, M + 1.6, y + 0.08, 1.85, 0.5, l, 11.5);
  });

  heading(s, 4.5, BODY_Y + 0.02, 8.2, "What I found, and what I did about it", 15.5);
  [
    [
      "Stock is censored at zero",
      "268 balance violations, 100% on days the balance would have gone negative.",
      "Flagged 277 days as real stockouts and used them as a risk driver — did not “correct” them.",
      ROSE,
    ],
    [
      "Weekly cycle, no trend",
      "Day-of-week ratio 1.39; monthly mean varies under 2%.",
      "Modelled a per-SKU weekday index, shrunk toward its category. No trend terms.",
      INDIGO,
    ],
    [
      "Lead time is noise for new SKUs",
      "4–5 different values across 12 rows; all 25 established SKUs report one.",
      "Replaced with the category median from SKUs with a stable value.",
      AMBER,
    ],
    [
      "Demand spans 6×",
      "85 to 536 units/day across SKUs.",
      "Predict a ratio to each SKU's own trailing mean, so one pooled model is valid.",
      SKY,
    ],
  ].forEach(([h, found, did, c], i) => {
    const y = BODY_Y + 0.5 + i * 1.0;
    s.addShape(pres.ShapeType.ellipse, {
      x: 4.5,
      y: y + 0.1,
      w: 0.18,
      h: 0.18,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    heading(s, 4.84, y, 7.8, h, 13.5);
    body(s, 4.84, y + 0.3, 3.75, 0.66, found, 11);
    s.addText(did, {
      x: 8.78,
      y: y + 0.3,
      w: 3.87,
      h: 0.66,
      fontFace: BODY,
      fontSize: 11,
      color: INK,
      lineSpacingMultiple: 1.14,
      isTextBox: true,
      margin: 0,
    });
  });

  body(
    s,
    M,
    6.5,
    CW,
    0.3,
    "Also cleaned: 15 duplicate rows · 20 mis-cased category labels · 90 missing demand values imputed causally, proven by truncate-and-recompute.",
    12,
    MUTED,
  );

  s.addNotes(
    "Two columns on purpose: what I found, and what I did. The censoring finding is the most interesting — every one of the 268 violations sits on a day where stock would have gone negative and was recorded as zero. That is not dirty data, it is a stockout signal, so I kept it and used it.",
  );
}

/* ══════════════════════════════════ 7 — PHASE 2: FEATURES & LEAKAGE ════════ */
{
  const s = slideLight();
  title(s, "Phase 2 — Features, and proving nothing leaks", "6 · Feature engineering");

  card(s, M, BODY_Y, 6.25, 2.9);
  label(s, M + 0.32, BODY_Y + 0.26, "The 23 features I engineered", INDIGO, 5);
  [
    ["Lagged demand", "lag 1, 2, 3, 7, 14"],
    ["Rolling level & spread", "mean / median / std over 7, 14, 28 days"],
    ["Trend & velocity", "7-day against 28-day, 7 against 14"],
    ["Weekly shape", "per-SKU weekday index, shrunk to category"],
    ["Inventory context", "stock ratio, receipts, stockout rate"],
    ["Static & horizon", "lead time, category, days of history, h"],
  ].forEach(([h, d], i) => {
    const y = BODY_Y + 0.68 + i * 0.35;
    s.addText(h, {
      x: M + 0.32,
      y,
      w: 2.5,
      h: 0.3,
      fontFace: BODY,
      fontSize: 11.5,
      bold: true,
      color: INK,
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: M + 2.86,
      y,
      w: 3.3,
      h: 0.3,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      isTextBox: true,
      margin: 0,
    });
  });

  card(s, 7.35, BODY_Y, 5.3, 2.9, NAVY, false);
  label(s, 7.67, BODY_Y + 0.26, "How I proved no leakage", AMBER, 4.5);
  [
    "Re-derived lag_1 and roll_mean_28 from the raw panel; the build fails on mismatch",
    "Truncated the panel, recomputed every feature, asserted nothing changed for surviving days",
    "Rebuilt rolling windows inside each fold, so no window can span the origin",
  ].forEach((t, i) => {
    const y = BODY_Y + 0.7 + i * 0.72;
    badge(s, 7.67, y, 0.34, i === 1 ? EMERALD : NAVY_SOFT, String(i + 1), 11);
    s.addText(t, {
      x: 8.13,
      y: y - 0.04,
      w: 4.3,
      h: 0.62,
      fontFace: BODY,
      fontSize: 11.5,
      color: ICE,
      lineSpacingMultiple: 1.16,
      isTextBox: true,
      margin: 0,
    });
  });

  card(s, M, 4.88, CW, 1.76, TINT, false);
  heading(s, M + 0.36, 5.08, 11.3, "The decision that made one model work across 28 SKUs", 14.5);
  s.addText(
    "SKU demand spans 85 to 536 units/day. A model predicting raw units would spend its capacity learning scale, so I predict demand(t+h) ÷ trailing 28-day mean and multiply the level back at inference. One pooled model learns the shared shape; each SKU's own history supplies its level. Making the horizon a feature then lets a single model serve h = 1…28 without the compounding error of recursive forecasting — and it is what makes a 12-day-old SKU forecastable at all.",
    {
      x: M + 0.36,
      y: 5.42,
      w: 11.3,
      h: 1.04,
      fontFace: BODY,
      fontSize: 12.5,
      color: INK,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Leakage is the failure mode that would make every metric a lie, so I built three independent guards. The strongest is the middle one: chop the panel at a date, rebuild every feature from scratch, and assert the values for the surviving days are byte-identical. A feature that peeked forward would move. Be ready to be asked this.",
  );
}

/* ═══════════════════════════ 8 — PHASE 3: MODEL CHOICE & VALIDATION ════════ */
{
  const s = slideLight();
  title(s, "Phase 3 — Baselines first, then earn the complexity", "7 · Model & validation");

  card(s, M, BODY_Y, 7.1, 3.92);
  heading(s, M + 0.34, BODY_Y + 0.24, 6.4, "Forecast error by model — pooled WAPE, lower is better", 13);
  s.addChart(
    pres.ChartType.bar,
    [
      {
        name: "WAPE %",
        labels: [
          "Naive (last value)",
          "Seasonal naive",
          "Moving average 28d",
          "Ridge (pooled)",
          "Gradient boosting",
        ],
        values: [27.4, 23.9, 19.6, 17.4, 17.2],
      },
    ],
    {
      x: M + 0.2,
      y: BODY_Y + 0.6,
      w: 6.7,
      h: 3.12,
      barDir: "bar",
      chartColors: [FAINT, FAINT, MUTED, SKY, INDIGO],
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFormatCode: '0.0"%"',
      dataLabelFontSize: 11,
      dataLabelFontFace: BODY,
      dataLabelColor: INK,
      showLegend: false,
      showTitle: false,
      catAxisLabelFontSize: 11.5,
      catAxisLabelFontFace: BODY,
      catAxisLabelColor: INK,
      valAxisLabelFontSize: 10,
      valAxisLabelColor: FAINT,
      valAxisMinVal: 0,
      valAxisMaxVal: 32,
      valGridLine: { color: LINE, size: 1 },
      catGridLine: { style: "none" },
      barGapWidthPct: 45,
    },
  );

  label(s, 8.1, BODY_Y + 0.02, "How I validated", INDIGO, 4.55);
  body(
    s,
    8.1,
    BODY_Y + 0.34,
    4.55,
    0.9,
    "Five expanding-window folds. Each trains on everything up to its origin, then forecasts the next 14 days from that one origin — the act a planner actually performs. A fresh model is fitted inside every fold.",
    11.5,
    INK,
  );

  label(s, 8.1, BODY_Y + 1.36, "Why a random split would be invalid", ROSE, 4.55);
  [
    "Rolling features leak across a shuffled boundary",
    "It scores interpolation, not forecasting",
    "Training on June to predict February hides drift",
  ].forEach((t, i) => {
    body(s, 8.1, BODY_Y + 1.7 + i * 0.42, 4.55, 0.38, "·  " + t, 11.5, MUTED);
  });

  label(s, 8.1, BODY_Y + 3.08, "Result", EMERALD, 4.55);
  s.addText("12.3% better than the strongest baseline", {
    x: 8.1,
    y: BODY_Y + 3.38,
    w: 4.55,
    h: 0.32,
    fontFace: BODY,
    fontSize: 14,
    bold: true,
    color: INK,
    isTextBox: true,
    margin: 0,
  });
  body(
    s,
    8.1,
    BODY_Y + 3.72,
    4.55,
    0.36,
    "MAE 51.7 units/day · bias −1.48% · 1,750 forecasts",
    11.5,
    MUTED,
  );

  card(s, M, 5.9, CW, 0.98, TINT, false);
  s.addText(
    "Two things I report rather than hide: the flat 28-day mean beats seasonal naive, so the level matters more than the weekly shape alone — and ridge scores 17.4 against the tree's 17.2, a 1.4% margin. The tree won, but barely.",
    {
      x: M + 0.36,
      y: 6.1,
      w: 11.3,
      h: 0.6,
      fontFace: BODY,
      fontSize: 12.5,
      italic: true,
      color: INK,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "WAPE is the primary metric on purpose: MAPE divides by actual demand so one quiet day dominates, and RMSE is driven by the 34 demand spikes. WAPE is unit-free so 28 SKUs of very different size aggregate honestly. Say the honest caveat out loud — ridge is within 1.4% of the tree, so the complexity is justified but only just.",
  );
}

/* ═══════════════════════ 9 — PHASE 4: FORECAST INTO A DECISION ═════════════ */
{
  const s = slideLight();
  title(s, "Phase 4 — Turning a forecast into a decision", "8 · Risk engine");

  card(s, M, BODY_Y, 6.35, 2.34, NAVY, false);
  label(s, M + 0.34, BODY_Y + 0.24, "Stockout probability", AMBER, 5.6);
  s.addText("P( demand over lead time  −  expected inflow  >  stock on hand )", {
    x: M + 0.34,
    y: BODY_Y + 0.64,
    w: 5.75,
    h: 0.4,
    fontFace: MONO,
    fontSize: 11.5,
    color: "FFFFFF",
    isTextBox: true,
    margin: 0,
  });
  body(
    s,
    M + 0.34,
    BODY_Y + 1.16,
    5.7,
    1.0,
    "Demand and supply as independent Normals, every input measured from that SKU's own record. The score is the probability itself — 0.87 means an 87% chance of running dry, not an index. Safety stock at a 95% service level.",
    12,
    ICE,
  );

  label(s, 7.35, BODY_Y + 0.02, "Today's distribution", INDIGO, 5.3);
  [
    ["Critical", 4, ROSE],
    ["High", 1, "EA580C"],
    ["Medium", 4, AMBER],
    ["Low", 7, SKY],
    ["Healthy", 12, EMERALD],
  ].forEach(([l, n, c], i) => {
    const y = BODY_Y + 0.36 + i * 0.54;
    s.addShape(pres.ShapeType.roundRect, {
      x: 7.35,
      y,
      w: 5.3,
      h: 0.46,
      rectRadius: 0.07,
      fill: { color: CARD },
      line: { color: LINE, width: 1 },
    });
    s.addShape(pres.ShapeType.ellipse, {
      x: 7.58,
      y: y + 0.14,
      w: 0.18,
      h: 0.18,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    s.addText(l, {
      x: 7.92,
      y: y + 0.07,
      w: 2.2,
      h: 0.32,
      fontFace: BODY,
      fontSize: 12.5,
      bold: true,
      color: INK,
      valign: "middle",
      isTextBox: true,
      margin: 0,
    });
    s.addShape(pres.ShapeType.roundRect, {
      x: 10.1,
      y: y + 0.16,
      w: (Number(n) / 12) * 1.7,
      h: 0.14,
      rectRadius: 0.05,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    s.addText(String(n), {
      x: 11.95,
      y: y + 0.07,
      w: 0.5,
      h: 0.32,
      fontFace: BODY,
      fontSize: 12.5,
      bold: true,
      color: INK,
      align: "right",
      valign: "middle",
      isTextBox: true,
      margin: 0,
    });
  });

  card(s, M, 4.92, CW, 2.0, TINT, false);
  badge(s, M + 0.34, 5.18, 0.46, ROSE, "!", 15);
  heading(s, M + 0.94, 5.16, 11.0, "The iteration that mattered most", 14.5);
  s.addText(
    "My first version scored risk on stock on hand alone. It flagged 13 of 28 SKUs Critical — because roughly half the catalogue is simply mid-replenishment-cycle at any moment. That is a red wall, not a decision tool.",
    {
      x: M + 0.94,
      y: 5.5,
      w: 11.0,
      h: 0.56,
      fontFace: BODY,
      fontSize: 12.5,
      color: INK,
      lineSpacingMultiple: 1.18,
      isTextBox: true,
      margin: 0,
    },
  );
  s.addText(
    "I modelled inventory position instead — crediting each SKU's observed delivery rate — and measured supply over whole delivery cycles rather than a fixed window, because a fixed window clips a delivery and swings the ratio by a third. Result: 4 Critical, and the under-supply signal now tracks the SKUs that genuinely sit at zero stock a fifth of the time.",
    {
      x: M + 0.94,
      y: 6.08,
      w: 11.0,
      h: 0.76,
      fontFace: BODY,
      fontSize: 12.5,
      color: INK,
      lineSpacingMultiple: 1.18,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "This is the best engineering story in the project — an iteration driven by looking at the output and rejecting it. Also worth saying: the bands are absolute and documented, never percentiles of the current panel, because percentile banding guarantees something is always Critical even in a perfectly healthy month.",
  );
}

/* ════════════════════════════════ 10 — PHASE 5: GROUNDED AI ════════════════ */
{
  const s = slideLight();
  title(s, "Phase 5 — Making the AI answer from evidence", "9 · Explainability");

  [
    ["Build evidence", "~38 computed numbers + ranked drivers for that SKU", INDIGO],
    ["Constrain", "9 absolute prompt rules — no invented figures or facts", VIOLET],
    ["Call at runtime", "claude-sonnet-5, per request, never pre-generated", SKY],
    ["Verify", "Every number traced back to the evidence, or reject", EMERALD],
  ].forEach(([h, d, c], i) => {
    const x = M + i * 3.06;
    card(s, x, BODY_Y, 2.8, 1.64);
    badge(s, x + 0.24, BODY_Y + 0.24, 0.44, c, String(i + 1), 13);
    heading(s, x + 0.78, BODY_Y + 0.28, 1.9, h, 14);
    body(s, x + 0.24, BODY_Y + 0.8, 2.32, 0.72, d, 11.5);
  });

  card(s, M, 3.64, 5.85, 1.5, TINT, false);
  s.addText("3.3 KB", {
    x: M + 0.34,
    y: 3.82,
    w: 1.9,
    h: 0.5,
    fontFace: HEAD,
    fontSize: 28,
    bold: true,
    color: INDIGO,
    isTextBox: true,
    margin: 0,
  });
  body(
    s,
    M + 2.34,
    3.84,
    3.3,
    1.1,
    "of evidence sent — against a 4,536-row panel. The model never sees the dataset; a retrieval layer selects the records.",
    12,
    INK,
  );

  card(s, 6.8, 3.64, 5.85, 1.5);
  heading(s, 7.14, 3.82, 5.2, "Grounded Q&A", 14.5);
  body(
    s,
    7.14,
    4.16,
    5.2,
    0.9,
    "Question → 10 intents → retrieve only what that intent needs → answer from that evidence alone. Answers cannot contradict the dashboard: they read the same records it renders.",
    11.5,
  );

  card(s, M, 5.36, CW, 1.32, NAVY, false);
  badge(s, M + 0.32, 5.66, 0.5, AMBER, "!", 17);
  heading(s, M + 1.0, 5.58, 10.6, "What the verifier caught that I would otherwise have shipped", 14, "FFFFFF");
  s.addText(
    "First, “SKU-1010” was being parsed as the number −1010, so every explanation naming its own SKU was silently rejected. Second, live testing produced “lead-time demand of 725 units — well above the reorder point of 872.4”: both figures real, so number checks passed, but the comparison is false. Grounding numbers is not grounding relations. The evidence now states which quantities are comparable.",
    {
      x: M + 1.0,
      y: 5.9,
      w: 10.9,
      h: 0.68,
      fontFace: BODY,
      fontSize: 11.5,
      color: ICE,
      lineSpacingMultiple: 1.16,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Verified against the live API: 4 of 4 explanations and 9 of 9 Q&A answers, all passing grounding verification. An off-topic question and a question about a non-existent SKU were both declined without inventing figures. If the key is absent the app stays fully usable and labels the fallback — it never passes a template off as model output.",
  );
}

/* ═════════════════════════ 11 — PHASE 6: ENGINEERING QUALITY ═══════════════ */
{
  const s = slideLight();
  title(s, "Phase 6 — Then I engineered it properly", "10 · Production quality");

  [
    [
      "Testing",
      "169",
      "tests, all passing offline",
      "Leakage proofs, the brief's worked example, band monotonicity, KPI self-consistency, and a check that the reported model really is the best-scoring one.",
      INDIGO,
    ],
    [
      "Security",
      "0",
      "secrets in the repo",
      "Key is server-side only; there is no NEXT_PUBLIC equivalent. CORS is an explicit allowlist, never a wildcard. An automated gate scans for all of it.",
      ROSE,
    ],
    [
      "Performance",
      "250 KB",
      "loaded once at startup",
      "No request trains a model or re-reads the CSV. Per-SKU history and forecasts are pre-sliced; LLM explanations cached by SKU and evidence hash.",
      SKY,
    ],
    [
      "Deployment",
      "2",
      "platforms configured",
      "render.yaml trains the model during the build so the first request is warm; a Dockerfile is provided as an alternative. Frontend configured for Vercel.",
      EMERALD,
    ],
  ].forEach(([h, big, sub, d, c], i) => {
    const x = M + i * 3.06;
    card(s, x, BODY_Y, 2.8, 3.9);
    badge(s, x + 0.28, BODY_Y + 0.28, 0.46, c, String(i + 1), 13);
    heading(s, x + 0.86, BODY_Y + 0.32, 1.8, h, 15);
    s.addText(big, {
      x: x + 0.28,
      y: BODY_Y + 0.94,
      w: 2.3,
      h: 0.54,
      fontFace: HEAD,
      fontSize: 26,
      bold: true,
      color: c,
      isTextBox: true,
      margin: 0,
    });
    body(s, x + 0.28, BODY_Y + 1.5, 2.3, 0.36, sub, 11);
    body(s, x + 0.28, BODY_Y + 1.94, 2.3, 1.82, d, 11.5);
  });

  card(s, M, 5.92, CW, 0.98, TINT, false);
  s.addText(
    "Documentation is part of the deliverable: a generated data profile, model evaluation and model summary — all rebuilt by the training run, so the numbers in the docs can never drift from the model.",
    {
      x: M + 0.36,
      y: 6.12,
      w: 11.3,
      h: 0.6,
      fontFace: BODY,
      fontSize: 12.5,
      color: INK,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "The point of this slide is that it is a product, not a prototype. Worth naming the automated quality gate: it verifies no committed key, no secret-bearing NEXT_PUBLIC variable, no hardcoded SKU ids or thresholds in the frontend — and that the metrics quoted in the README match the trained artifact.",
  );
}

/* ══════════════════════════ 12 — LIMITATIONS & NEXT ════════════════════════ */
{
  const s = slideDark();
  title(s, "What it cannot tell you — and what I would do next", "11 · Honesty", true);

  label(s, M, BODY_Y, "Limitations", ROSE, 5.85);
  [
    ["No open purchase orders", "Inbound is inferred from delivery cadence and labelled as an estimate."],
    ["Six months, one cycle", "Weekly patterns hold. Annual seasonality cannot be validated."],
    ["Demand is recorded, not true", "Censored on 277 zero-stock days."],
    ["No cost data", "Risk is ranked by likelihood, not by money."],
  ].forEach(([h, d], i) => {
    const y = BODY_Y + 0.42 + i * 1.0;
    card(s, M, y, 5.85, 0.92, NAVY_SOFT, false);
    heading(s, M + 0.3, y + 0.12, 5.25, h, 13.5, "FFFFFF");
    body(s, M + 0.3, y + 0.42, 5.25, 0.42, d, 11.5, ICE);
  });

  label(s, 6.95, BODY_Y, "What I would do next", EMERALD, 5.7);
  [
    ["Ingest open purchase orders", "The single biggest accuracy gain available."],
    ["Add cost and margin", "Rank the list by money at risk, not probability."],
    ["Model lead-time variability", "Turn safety stock into a real service guarantee."],
    ["Censored-demand correction", "Stop under-forecasting chronically short SKUs."],
  ].forEach(([h, d], i) => {
    const y = BODY_Y + 0.42 + i * 1.0;
    badge(s, 6.95, y + 0.16, 0.46, i === 0 ? EMERALD : NAVY_SOFT, String(i + 1), 13);
    heading(s, 7.58, y + 0.12, 5.05, h, 13.5, "FFFFFF");
    body(s, 7.58, y + 0.42, 5.05, 0.42, d, 11.5, ICE);
  });

  s.addText(
    "The tool does not just say a SKU is red. It says how many days of cover it has, against what lead time, why stock is draining, and how many units to order — and every number is reproducible from the dataset.",
    {
      x: M,
      y: 6.38,
      w: CW,
      h: 0.62,
      fontFace: HEAD,
      fontSize: 14,
      italic: true,
      color: ICE,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Close on honesty — the limitations are the credibility. Lead with open purchase orders: it is both the largest caveat and the highest-value next step. Then finish on the closing line, which is the whole thesis of the build in one sentence.",
  );
}

pres
  .writeFile({ fileName: "Supply-Chain-Risk-Monitor.pptx" })
  .then((f) => console.log("wrote", f));
