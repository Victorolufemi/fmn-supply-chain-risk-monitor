"""End-to-end API smoke test using FastAPI's TestClient (no server needed)."""
import json, sys, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from app.main import app

ok = True


def check(name, cond, extra=""):
    global ok
    ok = ok and bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  ' + str(extra)) if extra else ''}")


with TestClient(app) as c:
    r = c.get("/health")
    check("GET /health", r.status_code == 200 and r.json()["artifacts_loaded"], r.json())

    r = c.get("/api/dashboard")
    d = r.json()
    check("GET /api/dashboard", r.status_code == 200)
    print("   kpis:", json.dumps(d["kpis"]))
    print("   model:", d["model_name"], "| llm_available:", d["llm_available"])
    print("   risk_distribution:", {x["level"]: x["count"] for x in d["risk_distribution"]})
    print("   top 5 attention:")
    for s in d["attention_list"][:5]:
        print(f"     {s['sku_id']:10} {s['risk_level']:9} {s['risk_type']:9} "
              f"cov={s['inventory_coverage_days']} lt={s['lead_time_days']} "
              f"dts={s['days_to_projected_stockout']} | {s['headline']}")
    check("attention_list non-empty", len(d["attention_list"]) == 28)
    check("category_risk present", len(d["category_risk"]) >= 5)

    r = c.get("/api/skus?risk_level=CRITICAL,HIGH")
    check("GET /api/skus filtered", r.status_code == 200, f"{len(r.json())} rows")
    r = c.get("/api/skus?cold_start=true")
    check("GET /api/skus cold_start", r.status_code == 200 and len(r.json()) == 3)
    r = c.get("/api/skus?search=1004")
    check("GET /api/skus search", r.status_code == 200 and len(r.json()) == 1)

    sku = d["attention_list"][0]["sku_id"]
    r = c.get(f"/api/skus/{sku}")
    det = r.json()
    check(f"GET /api/skus/{sku}", r.status_code == 200)
    print(f"   history pts={len(det['history'])} forecast pts={len(det['forecast'])} "
          f"drivers={len(det['drivers'])}")
    print("   drivers:")
    for dr in det["drivers"][:4]:
        print(f"     - {dr['label']}: {dr['value']} {dr['unit']}")
    check("history populated", len(det["history"]) > 0)
    check("forecast populated", len(det["forecast"]) == 28)
    check("drivers populated", len(det["drivers"]) >= 3)

    r = c.get("/api/skus/sku-1004")     # case-insensitive resolve
    check("GET /api/skus case-insensitive", r.status_code == 200)
    r = c.get("/api/skus/NOPE-9999")
    check("GET /api/skus invalid -> 404", r.status_code == 404, r.json())

    r = c.get(f"/api/skus/{sku}/explanation")
    e = r.json()
    check("GET explanation", r.status_code == 200)
    print(f"   source={e['source']} model={e['model']} error={e['error']}")
    print(f"   text: {e['explanation'][:220]}")
    check("evidence attached", len(e["evidence"]) > 10, f"{len(e['evidence'])} fields")

    r = c.post("/api/qa", json={"question": f"Why is {sku} flagged?"})
    q = r.json()
    check("POST /api/qa", r.status_code == 200)
    print(f"   intent={q['intent']} source={q['source']} grounded_on={[g['kind'] for g in q['grounded_on']]}")
    print(f"   answer: {q['answer'][:220]}")

    for question in ["Which SKUs need attention?",
                     "Which products have the highest stockout risk?",
                     "Which categories have the greatest risk?",
                     "How are the newly launched SKUs doing?",
                     "Which SKUs are overstocked?"]:
        rr = c.post("/api/qa", json={"question": question}).json()
        print(f"   [{rr['intent']:18}] {question}")
    check("POST /api/qa blank -> 422", c.post("/api/qa", json={"question": "  "}).status_code == 422)
    check("POST /api/qa short -> 422", c.post("/api/qa", json={"question": "a"}).status_code == 422)

    r = c.get("/api/qa/suggestions")
    check("GET /api/qa/suggestions", r.status_code == 200 and len(r.json()) >= 6)

    r = c.get("/api/metadata")
    check("GET /api/metadata", r.status_code == 200)
    print("   cleaning:", json.dumps(r.json()["cleaning_report"]))

    r = c.get("/api/model-info")
    mi = r.json()
    check("GET /api/model-info", r.status_code == 200)
    print("   serving:", mi["serving_model"], "| cold-start:", mi["cold_start_model"])
    print("   metrics:", json.dumps(mi["metrics"]))
    print("   baselines:", json.dumps(mi["baselines"]))

    r = c.get("/api/categories")
    check("GET /api/categories", r.status_code == 200 and len(r.json()) >= 5)

print("\n" + ("ALL SMOKE CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
sys.exit(0 if ok else 1)
