"""
Grounded natural-language Q&A over the current risk state.

Why there is a retrieval layer at all
-------------------------------------
The naive approach — paste the CSV into the prompt — fails on three counts: 4,536
rows of raw daily movements do not fit a sensible prompt budget, the model would
have to re-derive risk arithmetic it is bad at, and its answers could not be
reconciled with what the dashboard shows. So the LLM never sees the dataset.

Instead:

1. **Classify** the question into one of a small set of intents, and extract any
   entities it names (SKU ids, categories, risk levels, risk types).
2. **Retrieve** only the structured records that intent needs — the same computed
   `RiskAssessment` objects the dashboard renders, so an answer can never disagree
   with the table on screen.
3. **Compact** the retrieval into a small evidence object, dropping fields the
   intent does not need and capping list lengths.
4. **Answer** from that evidence alone, under a system prompt that forbids
   inventing numbers or business facts.

The response reports which records the answer was grounded on, so the UI can show
the user exactly what the model was looking at.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from app.services.data_service import DataService, now_iso
from app.services.llm_client import LlmClient, get_llm

log = logging.getLogger(__name__)

MAX_SKUS_IN_EVIDENCE = 12
MAX_QUESTION_CHARS = 500

SYSTEM_PROMPT = """You are the analyst behind an inventory risk dashboard at a \
food manufacturing company. You answer a planner's questions about the CURRENT \
state of their SKUs.

RULES — these are absolute:
1. Answer ONLY from the EVIDENCE block. It is a snapshot of the live dashboard. \
If the evidence does not contain what was asked, say so plainly and describe what \
you can see instead. Never guess.
2. Never invent numbers, SKUs, categories, suppliers, promotions or events. If a \
SKU is not in the evidence, you do not know about it.
3. Distinguish observed facts (stock on hand, units received, past demand) from \
model estimates (demand forecasts, projected stockout days, probabilities). Use \
words like "forecast", "projected" or "estimated" for the latter.
4. Quote the specific numbers that support your answer — a planner needs the \
figures, not adjectives.
5. When a SKU has `is_cold_start` true, mention it has only `days_of_history` \
days of history and is therefore less certain. Do not invent a confidence figure.
6. Be concise and concrete: at most 130 words unless a list is genuinely needed, \
in which case use short plain-text lines. No markdown headings.

Write for a busy non-technical planner."""

RISK_WORDS = {
    "CRITICAL": ["critical", "urgent", "severe"],
    "HIGH": ["high risk", "high-risk", "high"],
    "MEDIUM": ["medium", "moderate"],
    "LOW": ["low risk", "low-risk"],
    "HEALTHY": ["healthy", "fine", "ok", "no risk", "safe"],
}


@dataclass
class Retrieval:
    intent: str
    evidence: dict
    sources: list[dict] = field(default_factory=list)
    fallback_answer: str = ""


# ---------------------------------------------------------------------------
# 1. Intent + entity extraction
# ---------------------------------------------------------------------------
def extract_skus(question: str, known: list[str]) -> list[str]:
    """Find SKU ids in free text, tolerating case and missing punctuation."""
    found: list[str] = []
    upper = question.upper()
    for token in re.findall(r"\b[A-Z]{2,6}[-_ ]?\d{2,6}\b", upper):
        norm = re.sub(r"[-_ ]", "", token)
        for sku in known:
            if re.sub(r"[-_ ]", "", sku.upper()) == norm and sku not in found:
                found.append(sku)
    return found


def extract_categories(question: str, known: list[str]) -> list[str]:
    q = question.lower()
    return [c for c in known if c.lower() in q]


def extract_risk_levels(question: str) -> list[str]:
    q = question.lower()
    return [lvl for lvl, words in RISK_WORDS.items() if any(w in q for w in words)]


def classify(question: str, skus: list[str], categories: list[str]) -> str:
    q = question.lower()
    if skus and any(w in q for w in ("why", "explain", "reason", "what's wrong",
                                     "whats wrong", "how come")):
        return "sku_explanation"
    if skus:
        return "sku_detail"
    if any(w in q for w in ("category", "categories")) or categories:
        return "category_risk"
    if any(w in q for w in ("overstock", "excess", "too much", "tied up",
                            "working capital", "slow moving", "slow-moving")):
        return "overstock_list"
    # Coverage is checked before stockout: "which SKUs have short inventory
    # coverage?" is a request to rank by cover, and "short" would otherwise be
    # swallowed by the stockout keywords.
    if any(w in q for w in ("coverage", "days of cover", "days of stock", "lead time")):
        return "coverage_list"
    if any(w in q for w in ("stockout", "stock out", "run out", "running out",
                            "shortage", "out of stock", "short of")):
        return "stockout_list"
    if any(w in q for w in ("new", "newly launched", "launch", "cold start",
                            "limited history")):
        return "new_skus"
    if "cover" in q:
        return "coverage_list"
    if any(w in q for w in ("how many", "count", "summary", "overview", "total",
                            "how is", "how are things", "status")):
        return "summary"
    if any(w in q for w in ("attention", "need", "worry", "worried", "focus",
                            "priorit", "action", "which sku", "what should")):
        return "attention_list"
    if any(w in q for w in ("model", "accurate", "accuracy", "forecast method",
                            "how does", "wape", "trained")):
        return "model_info"
    return "attention_list"


# ---------------------------------------------------------------------------
# 2-3. Retrieval + compaction
# ---------------------------------------------------------------------------
_SUMMARY_FIELDS = [
    "sku_id", "category", "risk_level", "risk_type", "risk_score",
    "current_stock", "forecast_daily_demand", "inventory_coverage_days",
    "days_to_projected_stockout", "lead_time_days", "excess_units",
    "supply_coverage_ratio", "is_structurally_undersupplied",
    "is_cold_start", "days_of_history", "headline",
]
_DETAIL_FIELDS = _SUMMARY_FIELDS + [
    "stockout_probability", "stockout_probability_no_inbound", "overstock_score",
    "lead_time_demand", "reorder_point_units", "order_up_to_units",
    "suggested_order_qty", "recent_7d_avg_demand", "previous_7d_avg_demand",
    "demand_change_pct", "demand_cv", "replenishment_rate_per_day",
    "expected_inbound_within_lead_time", "units_received_in_window",
    "supply_window_days",
    "days_since_last_receipt", "avg_replenishment_interval_days",
    "observed_stockout_days_28d", "observed_stockout_rate_all_time",
    "confidence", "recommended_action",
]


def _compact(rec: dict, fields: list[str]) -> dict:
    return {k: rec.get(k) for k in fields if rec.get(k) is not None}


def _with_drivers(rec: dict, n: int = 4) -> dict:
    d = _compact(rec, _DETAIL_FIELDS)
    d["drivers"] = [
        {"label": x["label"], "value": x["value"], "unit": x["unit"], "detail": x["detail"]}
        for x in (rec.get("drivers") or [])[:n]
    ]
    return d


def _kpis(records: list[dict]) -> dict:
    return {
        "total_skus": len(records),
        "critical": sum(r["risk_level"] == "CRITICAL" for r in records),
        "high": sum(r["risk_level"] == "HIGH" for r in records),
        "medium": sum(r["risk_level"] == "MEDIUM" for r in records),
        "low": sum(r["risk_level"] == "LOW" for r in records),
        "healthy": sum(r["risk_level"] == "HEALTHY" for r in records),
        "stockout_risk": sum(r["risk_type"] == "STOCKOUT" for r in records),
        "overstock_risk": sum(r["risk_type"] == "OVERSTOCK" for r in records),
        "out_of_stock_now": sum((r.get("current_stock") or 0) <= 0 for r in records),
        "newly_launched": sum(bool(r.get("is_cold_start")) for r in records),
        "structurally_undersupplied":
            sum(bool(r.get("is_structurally_undersupplied")) for r in records),
    }


def retrieve(svc: DataService, question: str) -> Retrieval:
    """Select the structured records relevant to the question. No LLM involved."""
    known_skus = svc.sku_ids
    known_cats = svc.categories
    skus = extract_skus(question, known_skus)
    cats = extract_categories(question, known_cats)
    levels = extract_risk_levels(question)
    intent = classify(question, skus, cats)

    all_recs = svc.risk_records()
    ranked = svc.ranked()
    as_of = svc.as_of
    base = {"as_of": as_of, "question_intent": intent,
            "_note": "This is the live dashboard state. Nothing outside it is known."}
    sources: list[dict] = []
    fallback = ""

    if intent in ("sku_explanation", "sku_detail") and skus:
        picked = [svc.risk(s) for s in skus[:3] if svc.risk(s)]
        base["skus"] = [_with_drivers(r) for r in picked]
        sources.append({"kind": "sku_detail",
                        "label": f"Risk assessment for {', '.join(s['sku_id'] for s in picked)}",
                        "sku_ids": [s["sku_id"] for s in picked]})
        if picked:
            fallback = " ".join(f"{r['sku_id']} is {r['risk_level']} "
                                f"({r['risk_type'].lower()}): {r['headline']}. "
                                f"{r['recommended_action']}" for r in picked)

    elif intent == "stockout_list":
        sel = [r for r in ranked if r["risk_type"] == "STOCKOUT"][:MAX_SKUS_IN_EVIDENCE]
        base["stockout_risk_skus"] = [_compact(r, _SUMMARY_FIELDS) for r in sel]
        base["kpis"] = _kpis(all_recs)
        sources.append({"kind": "ranked_list", "label": "SKUs ranked by stockout risk",
                        "sku_ids": [r["sku_id"] for r in sel]})
        fallback = _list_fallback("at risk of stockout", sel)

    elif intent == "overstock_list":
        sel = [r for r in ranked if r["risk_type"] == "OVERSTOCK"][:MAX_SKUS_IN_EVIDENCE]
        base["overstock_skus"] = [_compact(r, _SUMMARY_FIELDS) for r in sel]
        base["total_excess_units"] = round(
            sum(float(r.get("excess_units") or 0) for r in all_recs), 1)
        base["kpis"] = _kpis(all_recs)
        sources.append({"kind": "ranked_list", "label": "SKUs carrying excess stock",
                        "sku_ids": [r["sku_id"] for r in sel]})
        fallback = _list_fallback("carrying excess stock", sel)

    elif intent == "category_risk":
        target = cats or known_cats
        rows = []
        for c in target:
            recs = [r for r in all_recs if r["category"] == c]
            if not recs:
                continue
            covs = [r["inventory_coverage_days"] for r in recs
                    if r.get("inventory_coverage_days") is not None]
            rows.append({
                "category": c, **_kpis(recs),
                "avg_coverage_days": round(sum(covs) / len(covs), 2) if covs else None,
                "worst_skus": [r["sku_id"] for r in svc.ranked(recs)[:3]],
            })
        rows.sort(key=lambda r: (-(r["critical"] + r["high"]), r["category"]))
        base["categories"] = rows
        sources.append({"kind": "category_rollup",
                        "label": f"Risk rolled up across {len(rows)} categories"})
        fallback = "; ".join(
            f"{r['category']}: {r['critical'] + r['high']} of {r['total_skus']} "
            f"SKUs at high or critical risk" for r in rows[:6])

    elif intent == "new_skus":
        sel = [r for r in ranked if r.get("is_cold_start")]
        base["newly_launched_skus"] = [_with_drivers(r) for r in sel]
        base["cold_start_note"] = (
            "These SKUs have far less history than the rest. Their risk estimates "
            "are less certain and the model serves them from a simpler, more "
            "robust forecast."
        )
        sources.append({"kind": "cold_start", "label": "Newly launched SKUs",
                        "sku_ids": [r["sku_id"] for r in sel]})
        fallback = _list_fallback("newly launched", sel)

    elif intent == "coverage_list":
        sel = sorted(
            [r for r in all_recs if r.get("inventory_coverage_days") is not None],
            key=lambda r: r["inventory_coverage_days"],
        )[:MAX_SKUS_IN_EVIDENCE]
        base["lowest_coverage_skus"] = [_compact(r, _SUMMARY_FIELDS) for r in sel]
        sources.append({"kind": "ranked_list", "label": "SKUs with the least inventory cover",
                        "sku_ids": [r["sku_id"] for r in sel]})
        fallback = "; ".join(
            f"{r['sku_id']}: {r['inventory_coverage_days']:.1f} days cover vs "
            f"{r['lead_time_days']:.0f}-day lead time" for r in sel[:6])

    elif intent == "summary":
        base["kpis"] = _kpis(all_recs)
        base["top_priorities"] = [_compact(r, _SUMMARY_FIELDS) for r in ranked[:6]]
        sources.append({"kind": "kpis", "label": "Portfolio summary across all SKUs"})
        k = base["kpis"]
        fallback = (f"{k['total_skus']} SKUs monitored: {k['critical']} critical, "
                    f"{k['high']} high, {k['medium']} medium, {k['low']} low, "
                    f"{k['healthy']} healthy. {k['out_of_stock_now']} are out of "
                    f"stock right now.")

    elif intent == "model_info":
        b = svc.bundle
        ev = b.get("evaluation", {})
        base["model"] = {
            "serving_model": b.get("serving_model"),
            "selected_model": b.get("selected_model"),
            "cold_start_model": b.get("cold_start_model"),
            "trained_at": b.get("trained_at"),
            "as_of_date": b.get("as_of_date"),
            "primary_metric": "WAPE",
            "pooled_wape_by_model": {k: round(float(v), 4)
                                     for k, v in (ev.get("pooled_wape") or {}).items()},
            "validation": "5 expanding-window folds, 14-day horizon, chronological",
            "forecast_horizon_days": b.get("horizons", [None])[-1],
        }
        sources.append({"kind": "model_card", "label": "Model card and validation results"})
        w = base["model"]["pooled_wape_by_model"].get(b.get("selected_model"))
        fallback = (f"Forecasts come from {b.get('serving_model')}, validated with "
                    f"5 chronological folds. WAPE {w}.")

    else:  # attention_list
        sel = [r for r in ranked if r["risk_level"] != "HEALTHY"][:MAX_SKUS_IN_EVIDENCE]
        if levels:
            filtered = [r for r in ranked if r["risk_level"] in levels]
            if filtered:
                sel = filtered[:MAX_SKUS_IN_EVIDENCE]
        if cats:
            sel = [r for r in sel if r["category"] in cats] or sel
        base["skus_needing_attention"] = [_compact(r, _SUMMARY_FIELDS) for r in sel]
        base["kpis"] = _kpis(all_recs)
        sources.append({"kind": "ranked_list",
                        "label": "Attention list, ranked by severity then urgency",
                        "sku_ids": [r["sku_id"] for r in sel]})
        fallback = _list_fallback("needing attention", sel)

    return Retrieval(intent=intent, evidence=base, sources=sources,
                     fallback_answer=fallback or "No matching SKUs in the current data.")


def _list_fallback(label: str, recs: list[dict], n: int = 5) -> str:
    if not recs:
        return f"No SKUs are currently {label}."
    head = ", ".join(f"{r['sku_id']} ({r['risk_level'].lower()})" for r in recs[:n])
    more = f" and {len(recs) - n} more" if len(recs) > n else ""
    return f"{len(recs)} SKUs are {label}: {head}{more}."


# ---------------------------------------------------------------------------
# 4. Answer
# ---------------------------------------------------------------------------
def answer_question(
    svc: DataService, question: str, *, llm: LlmClient | None = None
) -> dict:
    question = question.strip()[:MAX_QUESTION_CHARS]
    r = retrieve(svc, question)

    client = llm or get_llm()
    user = (
        f"PLANNER'S QUESTION:\n{question}\n\n"
        f"EVIDENCE (a snapshot of the live dashboard — the only facts you may use):\n"
        f"{json.dumps(r.evidence, indent=2, default=str)}"
    )
    result = client.complete(system=SYSTEM_PROMPT, user=user)

    if result.ok:
        return {
            "question": question, "answer": result.text.strip(), "source": "llm",
            "model": result.model, "intent": r.intent, "grounded_on": r.sources,
            "evidence": r.evidence, "generated_at": now_iso(), "error": None,
        }
    log.warning("QA fell back for intent=%s: %s", r.intent, result.error)
    return {
        "question": question, "answer": r.fallback_answer, "source": "fallback",
        "model": None, "intent": r.intent, "grounded_on": r.sources,
        "evidence": r.evidence, "generated_at": now_iso(), "error": result.error,
    }
