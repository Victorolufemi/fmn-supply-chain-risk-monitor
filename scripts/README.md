# Scripts

Diagnostic and verification scripts. Run from the repository root with the backend
virtualenv, e.g. `backend/.venv/Scripts/python.exe scripts/final_check.py`.

None of these are part of the running application — the API depends only on
`backend/app/`.

| Script | Purpose |
|---|---|
| `profile_data.py` | Phase-2 data profiling. Regenerates `backend/reports/data_profile.md` and `data_profile.json` from the raw CSV. Detects the date and SKU columns rather than assuming them. |
| `probe_anomalies.py` | Deep dive into the issues profiling surfaced: duplicate rows, category case variants, non-constant lead times, missingness patterns, inventory-balance violations vs the zero floor, the new SKUs' full history, day-of-week strength per SKU, autocorrelation and demand spikes. |
| `probe_replenishment.py` | Delivery cadence per SKU — inter-arrival gaps, receipt-size variability, and total supply against total demand. This is the analysis that established replenishment is regular enough to model, and that several SKUs are structurally under-supplied. |
| `inspect_results.py` | Prints the backtest results: per-fold WAPE, pooled metrics, per-horizon and per-SKU breakdowns. |
| `inspect_risk.py` | Prints the full risk table from the trained artifact, plus coverage-vs-lead-time and a forecast sanity check against recent actuals. |
| `smoke_api.py` | End-to-end API check through FastAPI's `TestClient` — no server needed. Hits every endpoint and asserts the contract. |
| `demo_llm_path.py` | Walks the whole LLM path with a mocked Anthropic client: evidence construction, the prompt sent, a grounded response accepted, a hallucinated number rejected, caching, Q&A retrieval per intent, and the labelled fallback when the service is down. |
| `final_check.py` | Quality gate: no committed secrets, no secret-bearing `NEXT_PUBLIC_` variables, no hardcoded business data or thresholds in the frontend, required files present, clean text encoding, and — importantly — that the metrics quoted in the README match the trained artifact. |
