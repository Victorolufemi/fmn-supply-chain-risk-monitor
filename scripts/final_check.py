"""Final quality gate: secrets, hardcoded data, encoding, and structural checks."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAIL = []
WARN = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -> ' + detail) if detail else ''}")
    if not ok:
        FAIL.append(f"{name}: {detail}")


SKIP_DIRS = {"node_modules", ".next", ".venv", "__pycache__", ".git", "out", ".vercel"}


def walk(exts):
    for p in ROOT.rglob("*"):
        if p.is_dir() or any(d in p.parts for d in SKIP_DIRS):
            continue
        if p.suffix in exts:
            yield p


print("=" * 72)
print("1. SECRETS")
print("=" * 72)

# A real Anthropic key literal anywhere in the tree.
key_pat = re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")
hits = []
for p in walk({".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".yaml", ".yml", ".env", ".example"}):
    try:
        t = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    if key_pat.search(t):
        hits.append(str(p.relative_to(ROOT)))
check("no Anthropic key literal committed", not hits, ", ".join(hits))

# NEXT_PUBLIC_ must never carry a secret.
bad_public = []
for p in walk({".ts", ".tsx", ".js", ".mjs", ".env", ".example", ".local", ".md"}):
    t = p.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"NEXT_PUBLIC_\w+", t):
        name = m.group()
        if any(w in name.upper() for w in ("KEY", "SECRET", "TOKEN", "PASSWORD", "ANTHROPIC")):
            # The README warns against it by name; that mention is fine.
            line = t[max(0, m.start() - 120):m.start() + 60]
            if "Never" in line or "never" in line or "Do NOT" in line or "do not" in line:
                continue
            bad_public.append(f"{p.relative_to(ROOT)}::{name}")
check("no secret-bearing NEXT_PUBLIC_ variable", not bad_public, ", ".join(bad_public))

# The frontend must never reference the Anthropic SDK or key.
fe_bad = []
for p in walk({".ts", ".tsx"}):
    if "frontend" not in p.parts:
        continue
    t = p.read_text(encoding="utf-8", errors="ignore")
    if "ANTHROPIC_API_KEY" in t or "@anthropic-ai" in t or "api.anthropic.com" in t:
        fe_bad.append(str(p.relative_to(ROOT)))
check("frontend never references Anthropic", not fe_bad, ", ".join(fe_bad))

# .env files must not be committed (they must be gitignored).
gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
check(".gitignore covers .env", ".env" in gi and "!.env.example" in gi)
check(".gitignore covers node_modules", "node_modules/" in gi)
check(".gitignore covers python caches", "__pycache__/" in gi and ".venv/" in gi)
check(".gitignore covers model artifacts", "*.joblib" in gi)
check(".env.example exists", (ROOT / ".env.example").exists())
env_ex = (ROOT / ".env.example").read_text(encoding="utf-8")
for var in ("ANTHROPIC_API_KEY", "MODEL_NAME", "FRONTEND_URL", "NEXT_PUBLIC_API_URL"):
    check(f".env.example documents {var}", var in env_ex)

print()
print("=" * 72)
print("2. NO HARDCODED BUSINESS DATA IN THE FRONTEND")
print("=" * 72)

fe_files = [p for p in walk({".ts", ".tsx"}) if "frontend" in p.parts]
# A SKU id hardcoded outside of a doc comment would mean baked-in data.
sku_hits = []
for p in fe_files:
    t = p.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"SKU-\d{4}", t):
        line_start = t.rfind("\n", 0, m.start()) + 1
        line = t[line_start:t.find("\n", m.start())]
        if line.strip().startswith(("*", "//", "/*")):
            continue
        sku_hits.append(f"{p.relative_to(ROOT)}: {line.strip()[:70]}")
check("no hardcoded SKU ids in frontend code", not sku_hits, "; ".join(sku_hits))

# Risk thresholds must live in the backend only.
thresh_hits = []
for p in fe_files:
    t = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"(stockout_probability|risk_score)\s*[<>]=?\s*0\.\d", t):
        thresh_hits.append(str(p.relative_to(ROOT)))
check("no risk thresholds computed in frontend", not thresh_hits, ", ".join(thresh_hits))

# localhost must not be hardcoded outside the single documented default.
lh = []
for p in fe_files:
    t = p.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"https?://localhost", t):
        line_start = t.rfind("\n", 0, m.start()) + 1
        line = t[line_start:t.find("\n", m.start())].strip()
        # A formatter may wrap the expression, putting the env var and its
        # fallback on different lines, so look at the surrounding statement
        # rather than the single line the literal happens to land on.
        context = t[max(0, m.start() - 200):m.start() + 80]
        if "NEXT_PUBLIC_API_URL" in context or line.startswith(("*", "//")):
            continue
        lh.append(f"{p.relative_to(ROOT)}: {line[:70]}")
check("localhost only as the documented env fallback", not lh, "; ".join(lh))

print()
print("=" * 72)
print("3. STRUCTURE AND DELIVERABLES")
print("=" * 72)

required = [
    "README.md", ".env.example", ".gitignore",
    "data/project1_supply_chain_demand.csv",
    "backend/requirements.txt", "backend/Dockerfile", "backend/render.yaml",
    "backend/app/main.py", "backend/app/config.py",
    "backend/app/api/dashboard.py", "backend/app/api/skus.py", "backend/app/api/qa.py",
    "backend/app/ml/data.py", "backend/app/ml/features.py",
    "backend/app/ml/forecasting.py", "backend/app/ml/evaluation.py",
    "backend/app/ml/risk.py", "backend/app/ml/training.py",
    "backend/app/services/data_service.py", "backend/app/services/llm_client.py",
    "backend/app/services/explanation_service.py", "backend/app/services/qa_service.py",
    "backend/app/schemas/models.py",
    "backend/reports/data_profile.md", "backend/reports/model_evaluation.md",
    "backend/reports/model_summary.md",
    "frontend/package.json", "frontend/types/api.ts", "frontend/lib/api.ts",
    "frontend/app/supply-chain/page.tsx",
    "frontend/app/supply-chain/sku/[skuId]/page.tsx",
    "presentation/project1_outline.md",
]
missing = [f for f in required if not (ROOT / f).exists()]
check("all required files present", not missing, ", ".join(missing))

print()
print("=" * 72)
print("4. TEXT ENCODING")
print("=" * 72)
# Built from escapes so this file does not match its own detector.
NEEDLES = ("\u00e2\u20ac", "\u00c3\u00a2", "\ufffd")
mojibake = []
for p in walk({".py", ".ts", ".tsx", ".md", ".json", ".yaml", ".yml", ".css"}):
    t = p.read_text(encoding="utf-8", errors="ignore")
    if any(m in t for m in NEEDLES):
        mojibake.append(str(p.relative_to(ROOT)))
check("no mojibake in source or docs", not mojibake, ", ".join(mojibake))

bom = [str(p.relative_to(ROOT)) for p in walk({".py", ".ts", ".tsx", ".md", ".json", ".yaml"})
       if p.read_bytes().startswith(b"\xef\xbb\xbf")]
check("no UTF-8 BOMs", not bom, ", ".join(bom))

print()
print("=" * 72)
print("5. REPORTED METRICS MATCH THE ARTIFACT")
print("=" * 72)
sys.path.insert(0, str(ROOT / "backend"))
import warnings
warnings.filterwarnings("ignore")
import joblib

bundle = joblib.load(ROOT / "models" / "supply_chain" / "supply_chain_bundle.joblib")
pooled = bundle["evaluation"]["pooled_wape"]
selected = bundle["selected_model"]
best = min(pooled, key=pooled.get)
check("selected model is the best scoring", selected == best, f"{selected} vs {best}")

readme = (ROOT / "README.md").read_text(encoding="utf-8")
wape = f"{pooled[selected]:.4f}"
check(f"README quotes the real WAPE ({wape})", wape in readme)
baselines = {k: v for k, v in pooled.items()
             if k in ("naive_last_value", "seasonal_naive_weekly", "moving_average_28")}
best_base = min(baselines, key=baselines.get)
lift = (baselines[best_base] - pooled[selected]) / baselines[best_base] * 100
check(f"README quotes the real improvement ({lift:.1f}%)", f"{lift:.1f}%" in readme)
for name, v in pooled.items():
    check(f"README quotes {name} WAPE {v:.4f}", f"{v:.4f}" in readme)

risk = bundle["risk"]
counts = risk["risk_level"].value_counts().to_dict()
print(f"      risk distribution: {counts}")
check("distribution is graded (>=3 bands used)", risk["risk_level"].nunique() >= 3)
check("not everything is critical", counts.get("CRITICAL", 0) < len(risk) * 0.35)
check("something is flagged", counts.get("HEALTHY", 0) < len(risk) * 0.9)

print()
print("=" * 72)
print("6. NO FABRICATED EXPLANATIONS IN DATA OR CODE")
print("=" * 72)
csv_head = (ROOT / "data" / "project1_supply_chain_demand.csv").read_text(
    encoding="utf-8", errors="ignore")[:300]
check("dataset contains no pre-generated explanation column",
      "explanation" not in csv_head.lower())
expl = (ROOT / "backend/app/services/explanation_service.py").read_text(encoding="utf-8")
check("explanation service calls the LLM at runtime", "client.complete(" in expl)
check("explanation service verifies grounding", "verify_grounding" in expl)
check("fallback is explicitly labelled", '"source": "fallback"' in expl)

print()
print("=" * 72)
if FAIL:
    print(f"{len(FAIL)} CHECK(S) FAILED")
    for f in FAIL:
        print("  -", f)
    sys.exit(1)
print("ALL FINAL CHECKS PASSED")
