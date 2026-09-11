/**
 * Supply Chain Risk Monitor — presentation deck generator.
 *
 * Palette and motif are taken from the product itself (indigo→sky brand, the
 * five risk colours), so the deck reads as the same system as the app.
 * Motif: rounded cards with a small solid colour-coded circle badge. No accent
 * stripes, no underlines.
 *
 * Every figure is computed from the supplied dataset and reproduced by
 * `python -m app.ml.training`. Nothing here is illustrative.
 */
const PptxGenJS = require("pptxgenjs");

// ── palette ──────────────────────────────────────────────────────────────────
const NAVY = "10162F"; // dark slides
const NAVY_SOFT = "1C2547";
const INDIGO = "4F46E5"; // brand primary
const SKY = "0EA5E9"; // brand secondary
const AMBER = "F59E0B"; // attention
const ROSE = "E11D48"; // critical
const EMERALD = "10B981"; // healthy
const INK = "1E293B";
const MUTED = "64748B";
const FAINT = "94A3B8";
const LIGHT = "F7F9FC";
const CARD = "FFFFFF";
const TINT = "EEF2FF"; // indigo-50
const LINE = "E2E8F0";
const ICE = "CBD5E1";

const HEAD = "Cambria";
const BODY = "Calibri";

// ── geometry ─────────────────────────────────────────────────────────────────
const W = 13.3;
const H = 7.5;
const M = 0.65; // side margin
const CW = W - M * 2; // content width = 12.0
const TITLE_Y = 0.84;   // kicker sits at TITLE_Y-0.34 = 0.50 → clears the 0.5in margin
const BODY_Y = 1.72;

const pres = new PptxGenJS();
pres.layout = "LAYOUT_WIDE"; // must precede addSlide
pres.author = "Olufemi Victor";
pres.title = "Supply Chain Risk Monitor";

// fresh object every call — pptxgenjs mutates options in place
const shadow = (blur = 8, op = 0.07, offset = 2) => ({
  type: "outer",
  angle: 90,
  blur,
  offset,
  color: "0F172A",
  opacity: op,
});

function slideLight() {
  const s = pres.addSlide();
  s.background = { color: LIGHT };
  return s;
}

function slideDark() {
  const s = pres.addSlide();
  s.background = { color: NAVY };
  return s;
}

/** Slide title + optional kicker line above it. */
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
    fontSize: 34,
    bold: true,
    color: dark ? "FFFFFF" : INK,
    isTextBox: true,
    margin: 0,
  });
}

/** Rounded card. Returns nothing; caller places content inside. */
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

/** The repeated motif: a solid colour circle holding a short label. */
function badge(s, x, y, d, color, label, fontSize = 13) {
  s.addShape(pres.ShapeType.ellipse, {
    x,
    y,
    w: d,
    h: d,
    fill: { color },
    line: { color, width: 0 },
  });
  s.addText(label, {
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

/** Big number + caption, for stat callouts. */
function stat(s, x, y, w, value, label, color = INK, size = 34, labelColor = MUTED) {
  s.addText(value, {
    x,
    y,
    w,
    h: 0.56,
    fontFace: HEAD,
    fontSize: size,
    bold: true,
    color,
    isTextBox: true,
    margin: 0,
  });
  s.addText(label, {
    x,
    y: y + 0.58,
    w,
    h: 0.52,
    fontFace: BODY,
    fontSize: 11.5,
    color: labelColor,
    isTextBox: true,
    margin: 0,
  });
}

/* ═══════════════════════════════════════════════════════ 1 — TITLE ═════════ */
{
  const s = slideDark();

  // quiet geometric motif, top-right: the five risk bands as dots
  const bands = [ROSE, AMBER, "FBBF24", SKY, EMERALD];
  bands.forEach((c, i) => {
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
    y: 2.06,
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
    y: 2.46,
    w: 11.4,
    h: 1.0,
    fontFace: HEAD,
    fontSize: 52,
    bold: true,
    color: "FFFFFF",
    isTextBox: true,
    margin: 0,
  });

  s.addText(
    "Knowing which SKUs need attention — before inventory becomes a problem.",
    {
      x: M,
      y: 3.56,
      w: 10.2,
      h: 0.5,
      fontFace: BODY,
      fontSize: 19,
      color: ICE,
      isTextBox: true,
      margin: 0,
    },
  );

  const chips = [
    ["28", "SKUs scored every run"],
    ["12.3%", "better than the best baseline"],
    ["169", "tests, all passing"],
  ];
  chips.forEach(([v, l], i) => {
    const x = M + i * 4.0;
    card(s, x, 4.62, 3.7, 1.16, NAVY_SOFT, false);
    s.addText(v, {
      x: x + 0.3,
      y: 4.78,
      w: 3.1,
      h: 0.48,
      fontFace: HEAD,
      fontSize: 28,
      bold: true,
      color: i === 1 ? SKY : "FFFFFF",
      isTextBox: true,
      margin: 0,
    });
    s.addText(l, {
      x: x + 0.3,
      y: 5.28,
      w: 3.1,
      h: 0.34,
      fontFace: BODY,
      fontSize: 11.5,
      color: ICE,
      isTextBox: true,
      margin: 0,
    });
  });

  s.addText("Olufemi Victor", {
    x: M,
    y: 6.42,
    w: 6,
    h: 0.3,
    fontFace: BODY,
    fontSize: 12.5,
    color: FAINT,
    isTextBox: true,
    margin: 0,
  });

  s.addNotes(
    "Opening frame. The tool turns six months of daily SKU movements into a ranked list of products that need a decision today. Three numbers to anchor: 28 SKUs, 12.3% better forecast than the strongest baseline, 169 tests. Every figure in this deck is computed from the supplied dataset — nothing is illustrative.",
  );
}

/* ═══════════════════════════════════════════════════ 2 — THE PROBLEM ═══════ */
{
  const s = slideLight();
  title(s, "The sponsor was flying blind", "The problem");

  // quote card
  card(s, M, BODY_Y, 6.9, 4.0, "FFFFFF");
  s.addShape(pres.ShapeType.roundRect, {
    x: M,
    y: BODY_Y,
    w: 6.9,
    h: 4.0,
    rectRadius: 0.1,
    fill: { color: TINT },
    line: { color: TINT, width: 1 },
  });
  s.addText(
    "“We keep getting caught off guard — some SKUs run out and delay production, others sit overstocked and tie up working capital. I don't have anything today that tells me, ahead of time, which SKUs need attention and why.”",
    {
      x: M + 0.5,
      y: BODY_Y + 0.6,
      w: 5.9,
      h: 2.4,
      fontFace: HEAD,
      fontSize: 17,
      italic: true,
      color: INK,
      lineSpacingMultiple: 1.28,
      isTextBox: true,
      margin: 0,
    },
  );
  s.addText("FMN Supply Chain sponsor", {
    x: M + 0.5,
    y: BODY_Y + 3.3,
    w: 5.9,
    h: 0.3,
    fontFace: BODY,
    fontSize: 11.5,
    color: MUTED,
    isTextBox: true,
    margin: 0,
  });

  // three asks
  const asks = [
    [
      "Advance warning",
      "Not a rear-view report. A signal before the stockout.",
      ROSE,
    ],
    [
      "Prioritisation",
      "28 SKUs, one planner. Which three matter this morning?",
      AMBER,
    ],
    [
      "A reason you can act on",
      "Not a red dot. The numbers, in plain English.",
      INDIGO,
    ],
  ];
  asks.forEach(([h, d, c], i) => {
    const y = BODY_Y + 0.2 + i * 1.4;
    badge(s, 7.95, y + 0.08, 0.5, c, String(i + 1), 15);
    s.addText(h, {
      x: 8.62,
      y: y + 0.04,
      w: 4.1,
      h: 0.34,
      fontFace: BODY,
      fontSize: 17,
      bold: true,
      color: INK,
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: 8.62,
      y: y + 0.42,
      w: 4.1,
      h: 0.6,
      fontFace: BODY,
      fontSize: 13,
      color: MUTED,
      lineSpacingMultiple: 1.18,
      isTextBox: true,
      margin: 0,
    });
  });

  s.addText(
    "Three things are being asked for — and only the third is really about AI.",
    {
      x: M,
      y: 6.05,
      w: CW,
      h: 0.36,
      fontFace: BODY,
      fontSize: 14,
      italic: true,
      color: MUTED,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Read the quote, then land the three asks. Point out that advance warning and prioritisation are ordinary inventory maths — it's the third, the plain-English reason, where the LLM earns its place. That framing sets up the rest of the deck.",
  );
}

/* ══════════════════════════════════════════ 3 — TRANSLATION ════════════════ */
{
  const s = slideLight();
  title(s, "A triage problem that happens to need a forecast", "Framing");

  card(s, M, BODY_Y, CW, 1.34, NAVY, false);
  s.addText("THE MEASURABLE QUESTION", {
    x: M + 0.42,
    y: BODY_Y + 0.2,
    w: 11,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: AMBER,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "For each SKU, what is the probability that demand over the lead time exceeds what will be available — and how far is stock above the maximum the policy justifies?",
    {
      x: M + 0.42,
      y: BODY_Y + 0.52,
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

  const map = [
    ['"which SKUs need attention"', "A ranked list — severity, then urgency", INDIGO],
    ['"some SKUs run out"', "Probability of running dry inside the lead time", ROSE],
    ['"others sit overstocked"', "Units above the order-up-to level", SKY],
    ['"and why"', "Quantified drivers + an AI explanation", AMBER],
  ];
  map.forEach(([q, a, c], i) => {
    const x = M + i * 3.05;
    card(s, x, 3.28, 2.8, 1.86);
    s.addShape(pres.ShapeType.ellipse, {
      x: x + 0.26,
      y: 3.52,
      w: 0.2,
      h: 0.2,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    s.addText(q, {
      x: x + 0.26,
      y: 3.82,
      w: 2.3,
      h: 0.52,
      fontFace: HEAD,
      fontSize: 13,
      italic: true,
      color: INK,
      lineSpacingMultiple: 1.1,
      isTextBox: true,
      margin: 0,
    });
    s.addText(a, {
      x: x + 0.26,
      y: 4.36,
      w: 2.3,
      h: 0.68,
      fontFace: BODY,
      fontSize: 12,
      color: MUTED,
      lineSpacingMultiple: 1.16,
      isTextBox: true,
      margin: 0,
    });
  });

  s.addText(
    "The forecast is a means, not the deliverable. Nobody acts on “179 units a day” — they act on “0.6 days of cover against a 3-day lead time, and you're receiving 76 units for every 100 you sell.”",
    {
      x: M,
      y: 5.52,
      w: CW,
      h: 0.7,
      fontFace: BODY,
      fontSize: 14,
      italic: true,
      color: MUTED,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "This is the slide that shows the vague brief was actually translated. Each phrase in the sponsor's words maps to something computed. Close on the italic line — it is the single best summary of the product's point of view.",
  );
}

/* ═══════════════════════════════════════ 4 — WORKFLOW ══════════════════════ */
{
  const s = slideLight();
  title(s, "What the planner actually does", "Solution");

  const steps = [
    ["Scan", "Four KPIs and a ranked table. Worst first.", INDIGO],
    ["Spot", "Coverage vs lead time — below the line is too late.", SKY],
    ["Open", "One SKU: risk, policy, demand and stock trends.", "6366F1"],
    ["Understand", "AI explanation written from that SKU's own figures.", AMBER],
    ["Act", "A suggested order quantity, in units.", EMERALD],
  ];
  steps.forEach(([h, d, c], i) => {
    const x = M + i * 2.44;
    card(s, x, BODY_Y, 2.2, 2.42);
    badge(s, x + 0.24, BODY_Y + 0.26, 0.52, c, String(i + 1), 15);
    s.addText(h, {
      x: x + 0.24,
      y: BODY_Y + 0.92,
      w: 1.75,
      h: 0.32,
      fontFace: BODY,
      fontSize: 16,
      bold: true,
      color: INK,
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: x + 0.24,
      y: BODY_Y + 1.28,
      w: 1.75,
      h: 0.96,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.18,
      isTextBox: true,
      margin: 0,
    });
  });

  const screens = [
    ["Dashboard", "KPIs, three charts, filterable attention table, Ask box"],
    ["SKU drill-down", "Risk drivers, replenishment policy, demand & stock charts"],
    ["How it works", "Metrics, validation design, and what the tool cannot tell you"],
  ];
  s.addText("THREE SCREENS", {
    x: M,
    y: 4.42,
    w: 4,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: INDIGO,
    isTextBox: true,
    margin: 0,
  });
  screens.forEach(([h, d], i) => {
    const x = M + i * 4.04;
    card(s, x, 4.78, 3.76, 1.12, TINT, false);
    s.addText(h, {
      x: x + 0.26,
      y: 4.94,
      w: 3.3,
      h: 0.3,
      fontFace: BODY,
      fontSize: 14.5,
      bold: true,
      color: INK,
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: x + 0.26,
      y: 5.26,
      w: 3.3,
      h: 0.56,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.16,
      isTextBox: true,
      margin: 0,
    });
  });

  s.addText(
    "Next.js + TypeScript + Tailwind on Vercel · FastAPI + scikit-learn on Render · the browser holds no ML logic, no thresholds and no keys",
    {
      x: M,
      y: 6.22,
      w: CW,
      h: 0.34,
      fontFace: BODY,
      fontSize: 12,
      color: FAINT,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Walk the five steps as a story, then show the live app if time allows. The bottom line matters for the code-quality mark: the frontend renders what the API computed and nothing else — that separation is enforced by an automated check, not just convention.",
  );
}

/* ═══════════════════════════════════════ 5 — DATA ══════════════════════════ */
{
  const s = slideLight();
  title(s, "The data told us what to build", "Profiling");

  card(s, M, BODY_Y, 4.5, 4.05, "FFFFFF");
  s.addText("THE DATASET", {
    x: M + 0.32,
    y: BODY_Y + 0.26,
    w: 3.8,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: INDIGO,
    isTextBox: true,
    margin: 0,
  });
  const ds = [
    ["4,551", "raw rows"],
    ["28", "SKUs"],
    ["180", "days of history"],
    ["3", "newly launched, 12 days each"],
  ];
  ds.forEach(([v, l], i) => {
    const x = M + 0.32 + (i % 2) * 2.05;
    const y = BODY_Y + 0.78 + Math.floor(i / 2) * 1.75;
    stat(s, x, y, 1.9, v, l, i === 3 ? AMBER : INK, 27);
  });

  s.addText("The four that reshaped the model", {
    x: 5.52,
    y: BODY_Y + 0.02,
    w: 7.1,
    h: 0.34,
    fontFace: BODY,
    fontSize: 15.5,
    bold: true,
    color: INK,
    isTextBox: true,
    margin: 0,
  });

  const finds = [
    ["Stock is censored at zero", "268 balance violations — 100% explained by the zero floor. 277 days flagged as real stockouts.", ROSE],
    ["Weekly cycle, no trend", "Day-of-week ratio 1.39; monthly mean varies under 2% across six months.", INDIGO],
    ["Lead time is noise for new SKUs", "4–5 different values in 12 rows. Replaced with the category median.", AMBER],
    ["Demand spans 6×", "85 to 536 units/day — so the model predicts a ratio, not raw units.", SKY],
  ];
  finds.forEach(([h, d, c], i) => {
    const y = BODY_Y + 0.52 + i * 1.0;
    s.addShape(pres.ShapeType.ellipse, {
      x: 5.52,
      y: y + 0.1,
      w: 0.18,
      h: 0.18,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    s.addText(h, {
      x: 5.86,
      y: y,
      w: 6.7,
      h: 0.3,
      fontFace: BODY,
      fontSize: 14,
      bold: true,
      color: INK,
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: 5.86,
      y: y + 0.3,
      w: 6.7,
      h: 0.48,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.14,
      isTextBox: true,
      margin: 0,
    });
  });

  s.addText(
    "Also cleaned: 15 duplicate rows dropped · 20 mis-cased category labels · 90 missing demand values imputed causally, proven by truncate-and-recompute",
    {
      x: M,
      y: 6.22,
      w: CW,
      h: 0.6,
      fontFace: BODY,
      fontSize: 12.5,
      color: MUTED,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Lead with the censoring finding — it is the most interesting. Every one of the 268 inventory-balance violations sits on a day where stock would have gone negative and was recorded as zero. That is not noise, it is a stockout signal, so those days became a risk driver rather than being 'corrected' away.",
  );
}

/* ══════════════════════════════════ 6 — MODELLING ══════════════════════════ */
{
  const s = slideLight();
  title(s, "Modelling: only as complex as validation paid for", "Approach");

  card(s, M, BODY_Y, 5.85, 3.85);
  s.addText("WHAT IS PREDICTED", {
    x: M + 0.34,
    y: BODY_Y + 0.26,
    w: 5,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: INDIGO,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    [
      { text: "Units sold per SKU per day, 28 days ahead", options: { bullet: true, breakLine: true } },
      { text: "Target is a ratio to each SKU's own trailing mean — so one pooled model works across a 6× scale range", options: { bullet: true, breakLine: true } },
      { text: "Horizon is a feature, so one model serves h = 1…28 without compounding error", options: { bullet: true, breakLine: true } },
      { text: "23 features: lags, rolling level and spread, trend, a shrunk weekday index, inventory context", options: { bullet: true } },
    ],
    {
      x: M + 0.34,
      y: BODY_Y + 0.72,
      w: 5.2,
      h: 2.9,
      fontFace: BODY,
      fontSize: 13,
      color: INK,
      lineSpacingMultiple: 1.16,
      paraSpaceAfter: 8,
      isTextBox: true,
      margin: 0,
    },
  );

  card(s, 6.95, BODY_Y, 5.7, 3.85);
  s.addText("WHY NOT DEEP LEARNING", {
    x: 7.29,
    y: BODY_Y + 0.26,
    w: 5,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: ROSE,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "~4,500 observations across 28 short series, no trend, one seasonal cycle. A sequence model has nowhere near the data to justify its parameters — and would give up the native handling of missing lags and categoricals that a gradient-boosting tree provides for free.",
    {
      x: 7.29,
      y: BODY_Y + 0.72,
      w: 5.05,
      h: 1.35,
      fontFace: BODY,
      fontSize: 13,
      color: INK,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );
  s.addShape(pres.ShapeType.roundRect, {
    x: 7.29,
    y: BODY_Y + 2.35,
    w: 5.05,
    h: 1.2,
    rectRadius: 0.08,
    fill: { color: TINT },
    line: { color: TINT, width: 1 },
  });
  s.addText("No leakage — proven three ways", {
    x: 7.53,
    y: BODY_Y + 2.5,
    w: 4.6,
    h: 0.28,
    fontFace: BODY,
    fontSize: 13,
    bold: true,
    color: INK,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "Re-derived from the raw panel · truncate-and-recompute across every feature · rolling windows rebuilt inside each fold",
    {
      x: 7.53,
      y: BODY_Y + 2.82,
      w: 4.6,
      h: 0.54,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.14,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addText(
    "Every feature at day t uses only days ≤ t. The single forward-looking input is the target day's calendar weekday — genuinely known in advance.",
    {
      x: M,
      y: 5.85,
      w: CW,
      h: 0.6,
      fontFace: BODY,
      fontSize: 13.5,
      italic: true,
      color: MUTED,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "The examiner is looking for justified model choice. Say plainly: complexity was escalated only as far as the numbers paid for it. Be ready for the leakage question — there are three independent guards, and the strongest is truncate-and-recompute: chop the panel, rebuild every feature, and assert nothing changed for the days that remain.",
  );
}

/* ═════════════════════════════════ 7 — VALIDATION ══════════════════════════ */
{
  const s = slideLight();
  title(s, "Validated the only way that is honest", "Results");

  card(s, M, BODY_Y, 7.1, 4.12);
  s.addText("Forecast error by model — pooled WAPE, lower is better", {
    x: M + 0.34,
    y: BODY_Y + 0.24,
    w: 6.4,
    h: 0.3,
    fontFace: BODY,
    fontSize: 13,
    bold: true,
    color: INK,
    isTextBox: true,
    margin: 0,
  });

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
      y: BODY_Y + 0.62,
      w: 6.7,
      h: 3.3,
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

  const kpis = [
    ["12.3%", "better than the\nstrongest baseline", EMERALD],
    ["51.7", "MAE, units/day", INK],
    ["−1.48%", "bias — near neutral", INK],
    ["1,750", "forecasts scored", INK],
  ];
  kpis.forEach(([v, l, c], i) => {
    const y = BODY_Y + i * 1.03;
    s.addText(v, {
      x: 8.1,
      y,
      w: 2.0,
      h: 0.44,
      fontFace: HEAD,
      fontSize: 24,
      bold: true,
      color: c,
      isTextBox: true,
      margin: 0,
    });
    s.addText(l, {
      x: 10.15,
      y: y + 0.04,
      w: 2.5,
      h: 0.62,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.14,
      isTextBox: true,
      margin: 0,
    });
  });

  s.addText("WHY NOT A RANDOM SPLIT", {
    x: 8.1,
    y: 5.86,
    w: 4.55,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: ROSE,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "Rolling features leak across a shuffled boundary · it scores interpolation, not forecasting · training on June to predict February hides drift",
    {
      x: 8.1,
      y: 6.18,
      w: 4.55,
      h: 0.74,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.16,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addText(
    "Five expanding-window folds · 14-day horizon · a fresh model fitted inside every fold",
    {
      x: M,
      y: 5.94,
      w: 7.1,
      h: 0.34,
      fontFace: BODY,
      fontSize: 12.5,
      color: MUTED,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "The money slide. Two honest points to make out loud. First: the flat 28-day mean beats seasonal naive, which tells you the level matters more than the weekly shape alone. Second: ridge scores 17.4 against the tree's 17.2 — a 1.4% margin. The tree won, but barely, and that is reported rather than hidden.",
  );
}

/* ═════════════════════════════════ 8 — RISK ENGINE ═════════════════════════ */
{
  const s = slideLight();
  title(s, "Risk that a planner can argue with", "The engine");

  card(s, M, BODY_Y, 6.35, 2.5, NAVY, false);
  s.addText("STOCKOUT PROBABILITY", {
    x: M + 0.34,
    y: BODY_Y + 0.24,
    w: 5.6,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: AMBER,
    isTextBox: true,
    margin: 0,
  });
  s.addText("P( demand over lead time  −  expected inflow  >  stock on hand )", {
    x: M + 0.34,
    y: BODY_Y + 0.68,
    w: 5.75,
    h: 0.4,
    fontFace: "Consolas",
    fontSize: 11.5,
    color: "FFFFFF",
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "Demand and supply as independent Normals, every input measured from that SKU's own record. The score is the probability — 0.87 means an 87% chance of running dry, not an index.",
    {
      x: M + 0.34,
      y: BODY_Y + 1.28,
      w: 5.7,
      h: 1.0,
      fontFace: BODY,
      fontSize: 12,
      color: ICE,
      lineSpacingMultiple: 1.18,
      isTextBox: true,
      margin: 0,
    },
  );

  // before / after
  s.addText("A first version flagged 13 of 28 SKUs Critical", {
    x: M,
    y: 4.52,
    w: 6.35,
    h: 0.32,
    fontFace: BODY,
    fontSize: 14.5,
    bold: true,
    color: INK,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "Half the catalogue is simply mid-replenishment-cycle at any moment. Modelling inventory position — and measuring supply over whole delivery cycles — turned a red wall into a list you can work through.",
    {
      x: M,
      y: 4.9,
      w: 6.35,
      h: 0.94,
      fontFace: BODY,
      fontSize: 12.5,
      color: MUTED,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  // distribution chips
  s.addText("TODAY'S DISTRIBUTION", {
    x: 7.35,
    y: BODY_Y + 0.02,
    w: 5.3,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: INDIGO,
    isTextBox: true,
    margin: 0,
  });
  const dist = [
    ["Critical", 4, ROSE],
    ["High", 1, "EA580C"],
    ["Medium", 4, AMBER],
    ["Low", 7, SKY],
    ["Healthy", 12, EMERALD],
  ];
  dist.forEach(([l, n, c], i) => {
    const y = BODY_Y + 0.46 + i * 0.68;
    s.addShape(pres.ShapeType.roundRect, {
      x: 7.35,
      y,
      w: 5.3,
      h: 0.56,
      rectRadius: 0.07,
      fill: { color: CARD },
      line: { color: LINE, width: 1 },
    });
    s.addShape(pres.ShapeType.ellipse, {
      x: 7.58,
      y: y + 0.19,
      w: 0.18,
      h: 0.18,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    s.addText(l, {
      x: 7.92,
      y: y + 0.12,
      w: 2.2,
      h: 0.32,
      fontFace: BODY,
      fontSize: 13,
      bold: true,
      color: INK,
      valign: "middle",
      isTextBox: true,
      margin: 0,
    });
    // proportional bar
    s.addShape(pres.ShapeType.roundRect, {
      x: 10.1,
      y: y + 0.21,
      w: (Number(n) / 12) * 1.7,
      h: 0.14,
      rectRadius: 0.05,
      fill: { color: c },
      line: { color: c, width: 0 },
    });
    s.addText(String(n), {
      x: 11.95,
      y: y + 0.12,
      w: 0.5,
      h: 0.32,
      fontFace: BODY,
      fontSize: 13,
      bold: true,
      color: INK,
      align: "right",
      valign: "middle",
      isTextBox: true,
      margin: 0,
    });
  });
  s.addText("Bands are absolute and documented — never percentiles of today's panel.", {
    x: 7.35,
    y: BODY_Y + 3.98,
    w: 5.3,
    h: 0.56,
    fontFace: BODY,
    fontSize: 11.5,
    italic: true,
    color: MUTED,
    lineSpacingMultiple: 1.16,
    isTextBox: true,
    margin: 0,
  });

  s.addNotes(
    "The strongest engineering story in the project. Percentile banding would guarantee something is always Critical even in a healthy month — so the bands are absolute. And the supply window is aligned to whole delivery cycles, because a fixed window clips a delivery and swings the ratio by a third, manufacturing shortfalls that do not exist.",
  );
}

/* ════════════════════════════ 9 — AI EXPLANATIONS + Q&A ════════════════════ */
{
  const s = slideLight();
  title(s, "The model never sees the dataset", "Explainability & Q&A");

  // pipeline
  const stages = [
    ["Evidence", "~38 computed numbers + ranked drivers", INDIGO],
    ["Prompt", "9 absolute rules — no invented figures", "7C3AED"],
    ["Anthropic", "claude-sonnet-5 at request time", SKY],
    ["Verify", "Every number traced back to the evidence", EMERALD],
  ];
  stages.forEach(([h, d, c], i) => {
    const x = M + i * 3.06;
    card(s, x, BODY_Y, 2.8, 1.66);
    badge(s, x + 0.24, BODY_Y + 0.24, 0.44, c, String(i + 1), 13);
    s.addText(h, {
      x: x + 0.78,
      y: BODY_Y + 0.28,
      w: 1.9,
      h: 0.32,
      fontFace: BODY,
      fontSize: 15,
      bold: true,
      color: INK,
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: x + 0.24,
      y: BODY_Y + 0.82,
      w: 2.32,
      h: 0.66,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.16,
      isTextBox: true,
      margin: 0,
    });
  });

  // scale contrast
  card(s, M, 3.66, 5.85, 1.5, TINT, false);
  s.addText("3.3 KB", {
    x: M + 0.34,
    y: 3.84,
    w: 1.9,
    h: 0.52,
    fontFace: HEAD,
    fontSize: 30,
    bold: true,
    color: INDIGO,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "of evidence sent — against a 4,536-row panel. Retrieval selects the records; the dataset itself is never in the prompt.",
    {
      x: M + 2.34,
      y: 3.86,
      w: 3.3,
      h: 1.1,
      fontFace: BODY,
      fontSize: 12,
      color: INK,
      lineSpacingMultiple: 1.2,
      isTextBox: true,
      margin: 0,
    },
  );

  card(s, 6.8, 3.66, 5.85, 1.5, "FFFFFF");
  s.addText("Grounded Q&A", {
    x: 7.14,
    y: 3.84,
    w: 5.2,
    h: 0.3,
    fontFace: BODY,
    fontSize: 14.5,
    bold: true,
    color: INK,
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "Question → 10 intents → retrieve only what that intent needs → answer from that evidence alone. Answers cannot contradict the dashboard: they read the same records it renders.",
    {
      x: 7.14,
      y: 4.18,
      w: 5.2,
      h: 0.86,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTED,
      lineSpacingMultiple: 1.18,
      isTextBox: true,
      margin: 0,
    },
  );

  // the bug
  card(s, M, 5.36, CW, 1.28, NAVY, false);
  badge(s, M + 0.32, 5.66, 0.5, AMBER, "!", 17);
  s.addText("Grounding numbers is not grounding relations", {
    x: M + 1.0,
    y: 5.58,
    w: 10.6,
    h: 0.3,
    fontFace: BODY,
    fontSize: 14,
    bold: true,
    color: "FFFFFF",
    isTextBox: true,
    margin: 0,
  });
  s.addText(
    "Live testing produced “lead-time demand of 725 units — well above the reorder point of 872.4”. Both figures real, so number-level checks passed; the comparison is false. The evidence now states which quantities are comparable. The verifier found it — that is the argument for building one.",
    {
      x: M + 1.0,
      y: 5.9,
      w: 10.9,
      h: 0.62,
      fontFace: BODY,
      fontSize: 11.5,
      color: ICE,
      lineSpacingMultiple: 1.16,
      isTextBox: true,
      margin: 0,
    },
  );

  s.addNotes(
    "Verified against the live API: 4 of 4 explanations and 9 of 9 Q&A answers, every one passing grounding verification. An off-topic question and a question about a non-existent SKU were both declined without inventing figures. If the LLM is unavailable the app stays usable and labels the fallback — it never passes a template off as model output.",
  );
}

/* ══════════════════════════ 10 — LIMITATIONS & NEXT ════════════════════════ */
{
  const s = slideDark();
  title(s, "What it cannot tell you — and what comes next", "Honesty", true);

  s.addText("LIMITATIONS", {
    x: M,
    y: BODY_Y,
    w: 5.85,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: ROSE,
    isTextBox: true,
    margin: 0,
  });
  const lims = [
    ["No open purchase orders", "Inbound is inferred from delivery cadence and labelled as an estimate."],
    ["Six months, one cycle", "Weekly patterns hold. Annual seasonality cannot be validated."],
    ["Demand is recorded, not true", "Censored on 277 zero-stock days."],
    ["No cost data", "Risk is ranked by likelihood, not by money."],
  ];
  lims.forEach(([h, d], i) => {
    const y = BODY_Y + 0.42 + i * 1.0;
    card(s, M, y, 5.85, 0.92, NAVY_SOFT, false);
    s.addText(h, {
      x: M + 0.3,
      y: y + 0.12,
      w: 5.25,
      h: 0.28,
      fontFace: BODY,
      fontSize: 13.5,
      bold: true,
      color: "FFFFFF",
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: M + 0.3,
      y: y + 0.42,
      w: 5.25,
      h: 0.42,
      fontFace: BODY,
      fontSize: 11.5,
      color: ICE,
      lineSpacingMultiple: 1.14,
      isTextBox: true,
      margin: 0,
    });
  });

  s.addText("NEXT, HIGHEST VALUE FIRST", {
    x: 6.95,
    y: BODY_Y,
    w: 5.7,
    h: 0.26,
    fontFace: BODY,
    fontSize: 10.5,
    bold: true,
    charSpacing: 2.2,
    color: EMERALD,
    isTextBox: true,
    margin: 0,
  });
  const nexts = [
    ["Ingest open purchase orders", "The single biggest accuracy gain available."],
    ["Add cost and margin", "Rank the list by money at risk, not probability."],
    ["Model lead-time variability", "Turn safety stock into a real service guarantee."],
    ["Censored-demand correction", "Stop under-forecasting chronically short SKUs."],
  ];
  nexts.forEach(([h, d], i) => {
    const y = BODY_Y + 0.42 + i * 1.0;
    badge(s, 6.95, y + 0.16, 0.46, i === 0 ? EMERALD : NAVY_SOFT, String(i + 1), 13);
    s.addText(h, {
      x: 7.58,
      y: y + 0.12,
      w: 5.05,
      h: 0.28,
      fontFace: BODY,
      fontSize: 13.5,
      bold: true,
      color: "FFFFFF",
      isTextBox: true,
      margin: 0,
    });
    s.addText(d, {
      x: 7.58,
      y: y + 0.42,
      w: 5.05,
      h: 0.42,
      fontFace: BODY,
      fontSize: 11.5,
      color: ICE,
      lineSpacingMultiple: 1.14,
      isTextBox: true,
      margin: 0,
    });
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
    "Close on honesty — the limitations are the credibility. Lead with open purchase orders as both the largest caveat and the highest-value next step. Then finish on the closing line: the point of the tool is the sentence a planner can act on, not the colour of a dot.",
  );
}

pres
  .writeFile({ fileName: "Supply-Chain-Risk-Monitor.pptx" })
  .then((f) => console.log("wrote", f));
