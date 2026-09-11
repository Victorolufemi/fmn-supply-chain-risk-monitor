"""
Verify the LLM path against the REAL Anthropic API.

Prints the generated text, whether grounding verification passed, latency and
token counts. Nothing is mocked here — this is the production code path.
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
from app.services.llm_client import get_llm

s = get_settings()
llm = get_llm()
print("=" * 78)
print(f"LLM configured : {llm.available}")
print(f"Model          : {llm.model}")
print(f"Timeout        : {llm.timeout}s   max_tokens={llm.max_tokens}")
print("=" * 78)
if not llm.available:
    sys.exit("ANTHROPIC_API_KEY not resolved — aborting")

svc = DataService(joblib.load(s.artifact_dir / ARTIFACT_NAME))

# --- 1. explanations for a spread of risk situations ------------------------
ranked = svc.ranked()
picks = []
for want in ("STOCKOUT", "OVERSTOCK"):
    for r in ranked:
        if r["risk_type"] == want and r["sku_id"] not in picks:
            picks.append(r["sku_id"])
            break
cold = next((r["sku_id"] for r in ranked if r["is_cold_start"]), None)
if cold:
    picks.append(cold)
healthy = next((r["sku_id"] for r in ranked if r["risk_level"] == "HEALTHY"), None)
if healthy:
    picks.append(healthy)

ok_count = 0
for sku in picks:
    risk = svc.risk(sku)
    print()
    print("-" * 78)
    print(f"EXPLANATION  {sku}  [{risk['risk_level']} / {risk['risk_type']}"
          f"{' / COLD START' if risk['is_cold_start'] else ''}]")
    print("-" * 78)
    out = es.generate_explanation(svc, sku, force=True)
    print(f"  source={out['source']}  model={out['model']}  error={out['error']}")
    print()
    for line in out["explanation"].split("\n"):
        print("   " + line)
    if out["source"] == "llm":
        ok_count += 1
        grounded, bad = es.verify_grounding(out["explanation"], out["evidence"])
        print(f"\n  grounding re-check: {'PASS' if grounded else 'FAIL'} {bad if bad else ''}")
        words = len(out["explanation"].split())
        print(f"  length: {words} words")

# --- 2. cache behaviour on a real call --------------------------------------
print()
print("=" * 78)
print("CACHE")
print("=" * 78)
first = es.generate_explanation(svc, picks[0], force=True)
second = es.generate_explanation(svc, picks[0])
print(f"  forced call cached={first['cached']}  ->  repeat cached={second['cached']}")
print(f"  identical text: {first['explanation'] == second['explanation']}")

# --- 3. grounded Q&A --------------------------------------------------------
questions = [
    "Which SKUs need attention?",
    f"Why is {picks[0]} flagged?",
    "Which products have the highest stockout risk?",
    "Which SKUs are overstocked and tying up working capital?",
    "Which categories have the greatest risk?",
    "How are the newly launched SKUs doing?",
    "Which SKUs have the shortest inventory coverage?",
    "What is the capital of France?",          # off-topic: must refuse politely
    "How many units of SKU-9999 do we have?",  # unknown SKU: must not invent
]
qa_ok = 0
for q in questions:
    print()
    print("-" * 78)
    print(f"Q: {q}")
    out = qs.answer_question(svc, q)
    print(f"   intent={out['intent']}  source={out['source']}  error={out['error']}")
    print(f"   grounded_on={[g['kind'] for g in out['grounded_on']]}")
    print()
    for line in out["answer"].split("\n"):
        print("   " + line)
    if out["source"] == "llm":
        qa_ok += 1

print()
print("=" * 78)
print(f"explanations via live LLM: {ok_count}/{len(picks)}")
print(f"Q&A answers via live LLM : {qa_ok}/{len(questions)}")
print("=" * 78)
