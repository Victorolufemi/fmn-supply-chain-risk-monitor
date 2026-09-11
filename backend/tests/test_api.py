"""API contract tests, exercised through the real app with the real artifacts."""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.ml.training import ARTIFACT_NAME


@pytest.fixture(scope="module", autouse=True)
def _offline_llm():
    """
    Keep the API suite offline.

    These tests assert the HTTP contract, not the model. Letting them reach
    Anthropic would make the suite slow, non-deterministic, dependent on network
    access, and would spend credits on every run. The endpoints are asserted to
    behave correctly for *either* source, so the deterministic fallback exercises
    the same paths. Live-model behaviour is covered by `test_llm.py` with explicit
    mocks, and by `scripts/verify_live_llm.py` against the real API.
    """
    from app.services import llm_client
    from app.services.explanation_service import clear_cache

    class Offline:
        available = False
        model = None

        def complete(self, *, system, user, max_tokens=None):
            return llm_client.LlmResult(False, "", error="llm_disabled_for_tests")

    llm_client.reset_for_tests(Offline())
    clear_cache()
    yield
    llm_client.reset_for_tests(None)
    clear_cache()


@pytest.fixture(scope="module")
def client():
    if not (get_settings().artifact_dir / ARTIFACT_NAME).exists():
        pytest.skip("artifact bundle not built")
    from app.main import app

    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        b = r.json()
        assert b["status"] == "ok"
        assert b["artifacts_loaded"] is True
        assert b["as_of"] == "2026-06-29"
        assert isinstance(b["llm_configured"], bool)

    def test_root(self, client):
        assert client.get("/").status_code == 200


class TestDashboard:
    def test_shape(self, client):
        b = client.get("/api/dashboard").json()
        assert b["as_of"] == "2026-06-29"
        assert len(b["attention_list"]) == 28
        assert len(b["risk_distribution"]) == 5
        assert len(b["category_risk"]) == 5
        assert b["model_name"]

    def test_kpis_are_internally_consistent(self, client):
        b = client.get("/api/dashboard").json()
        k, rows = b["kpis"], b["attention_list"]
        assert k["total_skus"] == len(rows)
        assert k["critical_count"] == sum(r["risk_level"] == "CRITICAL" for r in rows)
        assert k["high_risk_count"] == sum(
            r["risk_level"] in ("CRITICAL", "HIGH") for r in rows
        )
        assert k["stockout_risk_count"] == sum(r["risk_type"] == "STOCKOUT" for r in rows)
        assert k["overstock_risk_count"] == sum(r["risk_type"] == "OVERSTOCK" for r in rows)
        assert k["healthy_count"] == sum(r["risk_level"] == "HEALTHY" for r in rows)
        assert k["newly_launched_count"] == 3
        assert sum(d["count"] for d in b["risk_distribution"]) == k["total_skus"]

    def test_attention_list_is_ranked(self, client):
        rows = client.get("/api/dashboard").json()["attention_list"]
        rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "HEALTHY": 4}
        seq = [rank[r["risk_level"]] for r in rows]
        assert seq == sorted(seq)

    def test_no_nan_in_payload(self, client):
        """NaN is not valid JSON; the service must never emit it."""
        import json

        raw = client.get("/api/dashboard").text
        assert "NaN" not in raw and "Infinity" not in raw
        json.loads(raw)


class TestSkuList:
    def test_default_returns_all(self, client):
        assert len(client.get("/api/skus").json()) == 28

    @pytest.mark.parametrize("level", ["CRITICAL", "HIGH", "MEDIUM", "LOW", "HEALTHY"])
    def test_filter_by_risk_level(self, client, level):
        rows = client.get(f"/api/skus?risk_level={level}").json()
        assert all(r["risk_level"] == level for r in rows)

    def test_filter_accepts_multiple_levels(self, client):
        rows = client.get("/api/skus?risk_level=CRITICAL,HIGH").json()
        assert all(r["risk_level"] in ("CRITICAL", "HIGH") for r in rows)

    def test_filter_by_type_and_category(self, client):
        rows = client.get("/api/skus?risk_type=OVERSTOCK").json()
        assert all(r["risk_type"] == "OVERSTOCK" for r in rows)
        rows = client.get("/api/skus?category=Snacks").json()
        assert rows and all(r["category"] == "Snacks" for r in rows)

    def test_filter_cold_start(self, client):
        cold = client.get("/api/skus?cold_start=true").json()
        assert len(cold) == 3
        assert all(r["is_cold_start"] and r["days_of_history"] == 12 for r in cold)
        warm = client.get("/api/skus?cold_start=false").json()
        assert len(warm) == 25

    def test_search(self, client):
        assert len(client.get("/api/skus?search=SKU-1004").json()) == 1
        assert client.get("/api/skus?search=zzzz").json() == []

    def test_unknown_filter_value_returns_empty_not_error(self, client):
        r = client.get("/api/skus?risk_level=NONSENSE")
        assert r.status_code == 200
        assert r.json() == []


class TestSkuDetail:
    def test_detail_shape(self, client):
        b = client.get("/api/skus/SKU-1000").json()
        assert b["sku_id"] == "SKU-1000"
        assert b["history"] and b["forecast"]
        assert len(b["forecast"]) == 28
        assert b["drivers"]
        assert set(b["drivers"][0]) == {"name", "label", "value", "unit", "detail"}

    def test_history_is_chronological_and_dated(self, client):
        h = client.get("/api/skus/SKU-1000?history_days=30").json()["history"]
        assert len(h) == 30
        dates = [p["date"] for p in h]
        assert dates == sorted(dates)
        assert dates[-1] == "2026-06-29"

    def test_forecast_starts_the_day_after_the_snapshot(self, client):
        f = client.get("/api/skus/SKU-1000").json()["forecast"]
        assert f[0]["horizon"] == 1
        assert f[0]["date"] == "2026-06-30"
        assert [p["horizon"] for p in f] == list(range(1, 29))
        assert all(p["forecast_units"] >= 0 for p in f)

    def test_case_insensitive_lookup(self, client):
        assert client.get("/api/skus/sku-1004").json()["sku_id"] == "SKU-1004"

    def test_invalid_sku_returns_404(self, client):
        r = client.get("/api/skus/NOPE-9999")
        assert r.status_code == 404
        assert "NOPE-9999" in r.json()["detail"]

    def test_history_days_is_validated(self, client):
        assert client.get("/api/skus/SKU-1000?history_days=0").status_code == 422
        assert client.get("/api/skus/SKU-1000?history_days=9999").status_code == 422

    def test_cold_start_sku_is_marked(self, client):
        b = client.get("/api/skus/SKU-2000").json()
        assert b["is_cold_start"] is True
        assert b["confidence"] == "LOW"
        assert b["days_of_history"] == 12
        assert len(b["history"]) == 12

    def test_numbers_are_finite(self, client):
        b = client.get("/api/skus/SKU-1012").json()
        for k, v in b.items():
            if isinstance(v, float):
                assert math.isfinite(v), k


class TestExplanation:
    def test_returns_evidence_and_a_source_label(self, client):
        b = client.get("/api/skus/SKU-1000/explanation").json()
        assert b["sku_id"] == "SKU-1000"
        assert b["source"] in ("llm", "fallback")
        assert b["explanation"]
        assert b["evidence"]["sku_id"] == "SKU-1000"
        assert "drivers" in b["evidence"]

    def test_degrades_to_a_labelled_fallback_when_the_llm_is_down(self, client):
        """With the LLM unavailable the endpoint must still answer, and say so."""
        b = client.get("/api/skus/SKU-1000/explanation").json()
        assert b["source"] == "fallback"
        assert b["error"] == "llm_disabled_for_tests"
        assert b["model"] is None
        assert len(b["explanation"]) > 40, "fallback must still be informative"

    def test_invalid_sku_returns_404(self, client):
        assert client.get("/api/skus/NOPE/explanation").status_code == 404


class TestQa:
    def test_answer_shape(self, client):
        b = client.post("/api/qa", json={"question": "Which SKUs need attention?"}).json()
        assert b["answer"]
        assert b["intent"] == "attention_list"
        assert b["grounded_on"]
        assert b["source"] in ("llm", "fallback")

    @pytest.mark.parametrize("q", ["", "  ", "a", "x" * 501])
    def test_invalid_questions_rejected(self, client, q):
        assert client.post("/api/qa", json={"question": q}).status_code == 422

    def test_missing_field_rejected(self, client):
        assert client.post("/api/qa", json={}).status_code == 422

    def test_suggestions_reference_a_real_sku(self, client):
        s = client.get("/api/qa/suggestions").json()
        assert len(s) >= 6
        known = {r["sku_id"] for r in client.get("/api/skus").json()}
        referenced = [x for x in s if "SKU-" in x]
        for text in referenced:
            assert any(k in text for k in known)


class TestMeta:
    def test_metadata(self, client):
        b = client.get("/api/metadata").json()
        assert b["sku_count"] == 28
        assert b["row_count"] == 4536
        assert b["date_range"] == {"start": "2026-01-01", "end": "2026-06-29"}
        assert len(b["categories"]) == 5
        assert len(b["cold_start_skus"]) == 3
        assert b["cleaning_report"]["exact_duplicates_dropped"] == 15

    def test_model_info_reports_real_metrics(self, client):
        b = client.get("/api/model-info").json()
        assert b["primary_metric"] == "WAPE"
        assert 0 < b["metrics"]["wape_pooled"] < 1
        assert b["metrics"]["forecast_points"] > 1000
        assert b["validation"]["random_split_used"] is False
        assert b["validation"]["folds"] == 5
        # The selected model must actually be the best scoring one.
        scored = [x for x in b["baselines"] if x["wape"] is not None]
        assert min(scored, key=lambda x: x["wape"])["model"] == b["selected_model"]
        # And it must beat every baseline.
        best_baseline = min(
            (x for x in scored if x["is_baseline"]), key=lambda x: x["wape"]
        )
        assert b["metrics"]["wape_pooled"] < best_baseline["wape"]

    def test_categories(self, client):
        b = client.get("/api/categories").json()
        assert len(b) == 5
        assert sum(c["total"] for c in b) == 28


class TestCors:
    def test_preflight_allows_localhost(self, client):
        r = client.options(
            "/api/dashboard",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.status_code in (200, 204)
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_wildcard_is_not_used(self, client):
        r = client.get("/api/dashboard", headers={"Origin": "http://localhost:3000"})
        assert r.headers.get("access-control-allow-origin") != "*"
