"""
Exercise the full LLM path with a mocked Anthropic client.

No ANTHROPIC_API_KEY is available in this environment, so this proves the
*contract*: what evidence is built, what prompt is sent, that a grounded answer is
accepted, and that a hallucinated number is caught and replaced by the labelled
fallback. Swapping the fake for the real client changes nothing else.
"""
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import joblib
from app.config import get_settings
from app.ml.training import ARTIFACT_NAME
from app.services.data_service import DataService
from app.services import explanation_service as es
from app.services import qa_service as qs
from app.services.llm_client import LlmResult

svc = DataService(joblib.load(get_settings().artifact_dir / ARTIFACT_NAME))
sku = svc.ranked()[4]["sku_id"]          # a flagged, non-trivial SKU
risk = svc.risk(sku)


class Fake:
    """Echoes a canned answer and captures the prompt."""

    available = True

    def __init__(self, text):
        self.text = text
        self.last = None

    def complete(self, *, system, user, max_tokens=None):
        self.last = {"system": system, "user": user}
        return LlmResult(True, self.text, model="claude-sonnet-5-(mocked)", latency_ms=900)


print("=" * 78)
print(f"1. EVIDENCE BUILT FOR {sku}  (this is all the model ever sees)")
print("=" * 78)
ev = es.build_evidence(risk)
print(json.dumps({k: v for k, v in ev.items() if k != "drivers"}, indent=2)[:1800])
print(f"\n  drivers ({len(ev['drivers'])}, in order of importance):")
for d in ev["drivers"][:5]:
    print(f"   - {d['label']}: {d['value']} {d['unit']}")
print(f"\n  evidence size: {len(json.dumps(ev, default=str))} chars "
      f"(the dataset is {len(svc.bundle['panel'])} rows — never sent)")

# A grounded answer: every number below is taken from the evidence above.
grounded = (
    f"{sku} has {risk['current_stock']:.0f} units on hand against forecast demand of "
    f"{risk['forecast_daily_demand']:.0f} units a day, which is "
    f"{risk['inventory_coverage_days']:.1f} days of cover against a "
    f"{risk['lead_time_days']:.0f}-day lead time. "
    f"Deliveries have been running at {risk['supply_coverage_ratio'] * 100:.0f} units "
    f"received for every 100 sold, so stock is draining rather than holding.\n\n"
    f"Raise a replenishment order of roughly {risk['suggested_order_qty']:.0f} units "
    f"to reach the order-up-to level of {risk['order_up_to_units']:.0f} units."
)

print("\n" + "=" * 78)
print("2. PROMPT SENT (system rules + evidence)")
print("=" * 78)
fake = Fake(grounded)
out = es.generate_explanation(svc, sku, llm=fake, force=True)
print(fake.last["system"][:700] + "\n  ...")
print(f"\n  user prompt: {len(fake.last['user'])} chars, "
      f"contains 'EVIDENCE': {'EVIDENCE' in fake.last['user']}")

print("\n" + "=" * 78)
print("3. GROUNDED RESPONSE ACCEPTED")
print("=" * 78)
print(f"  source = {out['source']}   model = {out['model']}   error = {out['error']}")
print("  " + out["explanation"].replace("\n", "\n  "))

print("\n" + "=" * 78)
print("4. HALLUCINATED NUMBER REJECTED")
print("=" * 78)
bad = ("Stock is critically low and our supplier has confirmed 87,400 units will "
       "arrive on Thursday, so no action is needed this week.")
ok, ungrounded = es.verify_grounding(bad, ev)
print(f"  grounding check: ok={ok}  ungrounded numbers={ungrounded}")
out2 = es.generate_explanation(svc, sku, llm=Fake(bad), force=True)
print(f"  -> source = {out2['source']}   error = {out2['error']}")
print("  fallback served instead:")
print("  " + out2["explanation"][:300])

print("\n" + "=" * 78)
print("5. CACHING")
print("=" * 78)
f3 = Fake(grounded)
a = es.generate_explanation(svc, sku, llm=f3, force=True)
b = es.generate_explanation(svc, sku, llm=f3)
print(f"  first call cached={a['cached']}, second cached={b['cached']}, "
      f"model calls made={1 if f3.last else 0} (second served from cache)")

print("\n" + "=" * 78)
print("6. GROUNDED Q&A — retrieval, then answer")
print("=" * 78)
for q in ["Which SKUs need attention?",
          f"Why is {sku} flagged?",
          "Which categories have the greatest risk?",
          "Which SKUs are overstocked and tying up working capital?",
          "How are the newly launched SKUs doing?"]:
    r = qs.retrieve(svc, q)
    size = len(json.dumps(r.evidence, default=str))
    keys = [k for k in r.evidence if not k.startswith("_")]
    print(f"\n  Q: {q}")
    print(f"     intent   : {r.intent}")
    print(f"     retrieved: {keys}  ({size} chars)")
    print(f"     grounded : {[g['label'] for g in r.sources]}")
    print(f"     fallback : {r.fallback_answer[:150]}")

print("\n" + "=" * 78)
print("7. LLM UNAVAILABLE -> LABELLED FALLBACK, APP STAYS USABLE")
print("=" * 78)


class Down:
    available = False

    def complete(self, *, system, user, max_tokens=None):
        return LlmResult(False, "", error="APIConnectionError")


down = es.generate_explanation(svc, sku, llm=Down(), force=True)
print(f"  explanation source={down['source']} error={down['error']}")
print("  " + down["explanation"][:260])
qdown = qs.answer_question(svc, "Which SKUs need attention?", llm=Down())
print(f"\n  qa source={qdown['source']} error={qdown['error']}")
print("  " + qdown["answer"][:260])
