"""
Runtime, LLM-generated explanations for a flagged SKU.

Grounding contract
------------------
The model is never handed the dataset. It receives one compact JSON *evidence*
object built from the SKU's own computed risk assessment — real numbers, already
labelled with their units and meaning — and is instructed to write from those
numbers alone. Concretely:

* Every figure in the evidence block comes from `RiskAssessment`, which is derived
  from the cleaned panel and the trained forecast. Nothing is synthesised for the
  prompt.
* The system prompt forbids inventing numbers, forbids business facts not present
  in the evidence, and requires observed values and forecast values to be
  described differently.
* `verify_grounding()` re-reads the generated text and checks that every number it
  contains can be traced to the evidence. Ungrounded output is rejected and the
  deterministic fallback is served instead, labelled `source="fallback"`.

Caching
-------
Keyed by SKU *and* a hash of the evidence, so a cached explanation is only ever
reused while the underlying numbers are unchanged. A refresh of the model or any
movement in the risk state produces a new key and therefore a genuine new LLM
call. `force=True` bypasses the cache entirely.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import OrderedDict
from threading import Lock

from app.config import get_settings
from app.services.data_service import DataService, now_iso
from app.services.llm_client import LlmClient, get_llm

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a supply-chain analyst writing for a non-technical \
planner at a food manufacturing company. You explain why a specific SKU has been \
flagged by an inventory risk model.

RULES — these are absolute:
1. Use ONLY the numbers in the EVIDENCE block. Never introduce a figure that is \
not there, and never round so aggressively that the meaning changes.
2. Never invent business facts. You do not know about promotions, suppliers, \
seasonality, customers, contracts or events unless the evidence states them.
3. Distinguish what is observed from what is predicted. Stock on hand, units \
received and past demand are facts. Daily demand forecasts, projected stockout \
days and probabilities are model estimates — say so with words like "forecast", \
"projected" or "estimated".
4. Lead with the single most decisive driver. The drivers are supplied in order \
of importance; the first one is the reason this SKU is flagged.
5. If `is_cold_start` is true, state plainly that the SKU has only \
`days_of_history` days of demand history and that the estimate is less certain \
than for established products. Do not invent a confidence percentage.
6. If `expected_inbound_within_lead_time` is above zero, make clear it is \
inferred from the SKU's past delivery pattern, not a confirmed purchase order.
7. Be careful with comparisons. Before writing that one figure is above, below \
or bigger than another, check the arithmetic. The meaningful comparisons are \
listed in `_how_to_read` — do not invent others. If you are unsure a comparison \
holds, state the two figures and let the reader draw the conclusion.
8. Recommend one practical action, using the numbers provided.
9. No preamble, no headings, no bullet points, no markdown. Two short paragraphs \
of plain prose, 60-110 words in total.

Write in plain business English. A planner should be able to act on it without \
asking what anything means."""

_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_LOCK = Lock()

# Fields that carry the numbers the LLM is allowed to use.
_EVIDENCE_FIELDS = [
    "sku_id", "category", "as_of", "risk_level", "risk_type", "risk_score",
    "stockout_probability", "stockout_probability_no_inbound", "overstock_score",
    "current_stock", "forecast_daily_demand", "lead_time_days", "lead_time_demand",
    "inventory_coverage_days", "days_to_projected_stockout", "safety_stock_units",
    "reorder_point_units", "order_up_to_units", "suggested_order_qty",
    "excess_units", "excess_ratio", "demand_cv", "recent_7d_avg_demand",
    "previous_7d_avg_demand", "demand_change_pct", "replenishment_rate_per_day",
    "expected_inbound_within_lead_time", "supply_coverage_ratio",
    "is_structurally_undersupplied", "units_received_56d", "days_since_last_receipt",
    "avg_replenishment_interval_days", "avg_receipt_qty",
    "observed_stockout_days_28d", "observed_stockout_rate_all_time",
    "days_of_history", "is_cold_start", "confidence",
]


def build_evidence(risk: dict) -> dict:
    """
    The exact, complete set of facts the LLM may use.

    Built from the SKU's computed risk record — every value is a number this
    application calculated from the dataset, not a value written for the prompt.
    """
    ev = {k: risk.get(k) for k in _EVIDENCE_FIELDS if risk.get(k) is not None}
    ev["drivers"] = [
        {"name": d["name"], "label": d["label"], "value": d["value"],
         "unit": d["unit"], "detail": d["detail"]}
        for d in (risk.get("drivers") or [])
    ]
    ev["_units_note"] = (
        "All unit figures are units of product. All *_days figures are days. "
        "Probabilities are between 0 and 1."
    )
    # Which quantities are meaningfully comparable, and against what. Without this
    # a model will pair numbers that share a unit but not a meaning — an observed
    # failure was "lead_time_demand is well above reorder_point_units", which is
    # both arithmetically wrong and not a comparison that means anything.
    ev["_how_to_read"] = [
        "current_stock vs reorder_point_units: below the reorder point means an "
        "order should be raised now.",
        "inventory_coverage_days vs lead_time_days: less cover than lead time "
        "means an order placed today arrives after stock runs out.",
        "current_stock vs order_up_to_units: above it is excess stock; "
        "excess_units is that difference.",
        "reorder_point_units equals lead_time_demand plus safety_stock_units, so "
        "it is always the larger of those two. Never compare them as if one "
        "could exceed the other.",
        "days_to_projected_stockout vs lead_time_days: running out sooner than "
        "the lead time means the gap cannot be closed by ordering today.",
        "supply_coverage_ratio below 1.0 means fewer units are being received "
        "than sold.",
    ]
    return ev


def evidence_hash(evidence: dict) -> str:
    payload = json.dumps(evidence, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Identifiers and dates are stripped BEFORE numbers are extracted. Without this,
# "SKU-1010" yields the number -1010 (the hyphen reads as a minus sign) and every
# explanation that names its own SKU is rejected as ungrounded.
_IDENT = re.compile(r"\b[A-Za-z]{1,12}[-_]?\d[\w-]*\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# A leading minus counts only when it is not glued to a preceding word character,
# dot or hyphen — so "12-14 days" is two numbers, not 12 and -14.
_NUM = re.compile(r"(?<![\w.\-])-?\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> list[float]:
    cleaned = _ISO_DATE.sub(" ", _IDENT.sub(" ", text))
    out = []
    for m in _NUM.finditer(cleaned):
        try:
            out.append(float(m.group().replace(",", "")))
        except ValueError:
            continue
    return out


def _allowed_numbers(evidence: dict) -> set[float]:
    """
    Every number the model may legitimately state, plus the obvious derivations a
    human writer would make (percentages, rounding, simple differences).
    """
    vals: set[float] = set()

    def add(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        vals.add(f)
        vals.add(round(f))
        vals.add(round(f, 1))
        vals.add(round(f, 2))
        vals.add(abs(f))
        vals.add(round(abs(f)))
        vals.add(round(abs(f), 1))
        if 0.0 <= abs(f) <= 1.0:          # probability stated as a percentage
            vals.add(round(f * 100))
            vals.add(round(f * 100, 1))
        vals.add(round(f / 100, 3))       # percentage stated as a ratio

    for k, v in evidence.items():
        if k == "drivers":
            for d in v:
                add(d.get("value"))
                vals.update(_numbers_in(str(d.get("detail", ""))))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            add(v)
    # Derived quantities a careful writer may compute from the evidence.
    stock = evidence.get("current_stock")
    rp = evidence.get("reorder_point_units")
    out = evidence.get("order_up_to_units")
    for a, b in ((rp, stock), (out, stock)):
        if a is not None and b is not None:
            add(a - b)
    expanded = set()
    for v in vals:
        expanded.update({v, round(v), round(v, 1), round(v, 2)})
    return expanded


def verify_grounding(text: str, evidence: dict, tolerance: float = 0.02) -> tuple[bool, list[float]]:
    """
    Check that every number in the generated text traces back to the evidence.

    Small integers (0-31) are exempt: they are almost always ordinary prose —
    "two paragraphs", "7 days", a date. Everything else must match an allowed
    value within `tolerance` relative error.
    """
    allowed = _allowed_numbers(evidence)
    ungrounded = []
    for n in _numbers_in(text):
        if abs(n) <= 31 and float(n).is_integer():
            continue
        if any(abs(n - a) <= max(tolerance * max(abs(a), 1.0), 0.05) for a in allowed):
            continue
        ungrounded.append(n)
    return (not ungrounded), ungrounded


def _user_prompt(evidence: dict) -> str:
    return (
        "Explain why this SKU has been flagged, and what the planner should do.\n\n"
        "EVIDENCE (the only facts you may use):\n"
        f"{json.dumps(evidence, indent=2, default=str)}"
    )


def fallback_explanation(risk: dict) -> str:
    """
    Deterministic text used when the LLM is unavailable or ungrounded.

    Assembled from the same computed numbers, so it is truthful — but it is
    plainly a template, and the API labels it `source="fallback"` so the UI can
    say the generated explanation is temporarily unavailable rather than passing
    this off as model output.
    """
    parts = [f"{risk['headline']}."]
    for d in (risk.get("drivers") or [])[:3]:
        val = d.get("value")
        if val is None:
            continue
        parts.append(f"{d['label']}: {val:g} {d['unit']}. {d['detail']}")
    parts.append(risk["recommended_action"])
    if risk.get("is_cold_start"):
        parts.append(
            f"Limited history — this SKU has {risk['days_of_history']} days of "
            f"observed demand, so this estimate is less certain than for "
            f"established SKUs."
        )
    return " ".join(parts)


# ---------------------------------------------------------------------------
def generate_explanation(
    svc: DataService,
    sku_id: str,
    *,
    force: bool = False,
    llm: LlmClient | None = None,
) -> dict:
    """Produce (or serve from cache) the explanation for one SKU."""
    risk = svc.risk(sku_id)
    if risk is None:
        raise KeyError(sku_id)

    evidence = build_evidence(risk)
    key = f"{sku_id}:{evidence_hash(evidence)}"

    if not force:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit:
                _CACHE.move_to_end(key)
                return {**hit, "cached": True}

    client = llm or get_llm()
    result = client.complete(system=SYSTEM_PROMPT, user=_user_prompt(evidence))

    if result.ok:
        grounded, bad = verify_grounding(result.text, evidence)
        if grounded:
            payload = {
                "sku_id": sku_id, "explanation": result.text.strip(), "source": "llm",
                "model": result.model, "cached": False, "generated_at": now_iso(),
                "evidence": evidence, "error": None,
            }
            with _CACHE_LOCK:
                _CACHE[key] = payload
                while len(_CACHE) > get_settings().llm_cache_size:
                    _CACHE.popitem(last=False)
            return payload
        log.warning("explanation for %s rejected: ungrounded numbers %s", sku_id, bad)
        err = "ungrounded_response"
    else:
        err = result.error

    return {
        "sku_id": sku_id, "explanation": fallback_explanation(risk),
        "source": "fallback", "model": None, "cached": False,
        "generated_at": now_iso(), "evidence": evidence, "error": err,
    }


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def cache_size() -> int:
    return len(_CACHE)
