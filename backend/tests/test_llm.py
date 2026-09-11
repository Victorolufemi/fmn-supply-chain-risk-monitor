"""
Explanation and Q&A services.

The Anthropic client is mocked throughout: these tests are about the contract we
build around the model — what evidence it is given, what it is forbidden to do,
and what happens when it misbehaves — not about the vendor's API.
"""
from __future__ import annotations

import json

import pytest

from app.services import explanation_service as es
from app.services import qa_service as qs
from app.services.llm_client import LlmResult, _validate


# ---------------------------------------------------------------------------
class FakeLlm:
    """Stands in for LlmClient. Records what it was asked."""

    def __init__(self, text="", ok=True, error=None, available=True):
        self._text, self._ok, self._error = text, ok, error
        self.available = available
        self.calls: list[dict] = []

    def complete(self, *, system: str, user: str, max_tokens=None) -> LlmResult:
        self.calls.append({"system": system, "user": user})
        if not self._ok:
            return LlmResult(False, "", error=self._error or "boom")
        return LlmResult(True, self._text, model="fake-model", latency_ms=12)


@pytest.fixture
def svc():
    import joblib
    from app.config import get_settings
    from app.ml.training import ARTIFACT_NAME
    from app.services.data_service import DataService

    path = get_settings().artifact_dir / ARTIFACT_NAME
    if not path.exists():
        pytest.skip("artifact bundle not built")
    return DataService(joblib.load(path))


@pytest.fixture(autouse=True)
def _clear_cache():
    es.clear_cache()
    yield
    es.clear_cache()


# ---------------------------------------------------------------------------
class TestEvidenceConstruction:
    def test_evidence_carries_real_computed_numbers(self, svc):
        sku = svc.ranked()[0]["sku_id"]
        risk = svc.risk(sku)
        ev = es.build_evidence(risk)

        assert ev["sku_id"] == sku
        assert ev["risk_level"] == risk["risk_level"]
        # Every numeric field must match the risk record exactly — nothing is
        # rewritten or rounded on the way into the prompt.
        for key in ("current_stock", "forecast_daily_demand", "lead_time_days",
                    "inventory_coverage_days", "days_of_history"):
            if key in ev:
                assert ev[key] == risk[key]
        assert ev["drivers"], "drivers must be included as ordered evidence"
        assert all({"name", "label", "value", "unit", "detail"} <= set(d) for d in ev["drivers"])

    def test_evidence_excludes_none_values(self, svc):
        ev = es.build_evidence(svc.risk(svc.sku_ids[0]))
        assert all(v is not None for k, v in ev.items() if k != "drivers")

    def test_evidence_states_which_comparisons_are_meaningful(self, svc):
        """
        Grounding verification checks numbers, not relations. A live run produced
        "lead_time_demand is well above reorder_point_units" — both figures real,
        the comparison arithmetically wrong and meaningless. The evidence now
        names the valid comparisons so the model is not left to pair figures that
        merely share a unit.
        """
        ev = es.build_evidence(svc.risk(svc.sku_ids[0]))
        guidance = " ".join(ev["_how_to_read"])
        assert "current_stock vs reorder_point_units" in guidance
        assert "inventory_coverage_days vs lead_time_days" in guidance
        assert "reorder_point_units equals lead_time_demand plus" in guidance

    def test_prompt_warns_against_unchecked_comparisons(self, svc):
        llm = FakeLlm(text="Stock is at zero, so an order is needed immediately.")
        es.generate_explanation(svc, svc.sku_ids[0], llm=llm, force=True)
        system = llm.calls[0]["system"]
        assert "Be careful with comparisons" in system
        assert "_how_to_read" in system
        assert "_how_to_read" in llm.calls[0]["user"]

    def test_evidence_hash_tracks_the_numbers(self, svc):
        ev = es.build_evidence(svc.risk(svc.sku_ids[0]))
        h1 = es.evidence_hash(ev)
        assert h1 == es.evidence_hash(dict(ev))
        changed = {**ev, "current_stock": (ev.get("current_stock") or 0) + 1}
        assert es.evidence_hash(changed) != h1


class TestPromptGrounding:
    def test_prompt_contains_the_evidence_and_the_rules(self, svc):
        sku = svc.ranked()[0]["sku_id"]
        llm = FakeLlm(text="Stock is at zero and demand continues, so this needs an order today.")
        es.generate_explanation(svc, sku, llm=llm)

        system = llm.calls[0]["system"]
        user = llm.calls[0]["user"]
        assert "ONLY the numbers in the EVIDENCE block" in system
        assert "Never invent business facts" in system
        assert "Distinguish what is observed from what is predicted" in system
        assert "EVIDENCE" in user and sku in user
        # The dataset itself must never be in the prompt.
        assert "units_received" not in user or len(user) < 20000
        assert len(user) < 20000, "prompt should be a compact evidence object, not a data dump"

    def test_dataset_is_never_sent(self, svc):
        llm = FakeLlm(text="A grounded sentence about this SKU and its stock position.")
        es.generate_explanation(svc, svc.sku_ids[0], llm=llm)
        user = llm.calls[0]["user"]
        # A daily panel would contain many ISO dates; the evidence has at most one.
        assert user.count("2026-0") <= 3


class TestGroundingVerification:
    def test_accepts_numbers_present_in_the_evidence(self):
        ev = {"current_stock": 42.0, "forecast_daily_demand": 15.2,
              "inventory_coverage_days": 2.76, "lead_time_days": 7, "drivers": []}
        ok, bad = es.verify_grounding(
            "Stock is 42 units against forecast demand of 15.2 units a day, "
            "leaving 2.76 days of cover against a 7 day lead time.", ev,
        )
        assert ok, bad

    def test_rejects_an_invented_number(self):
        ev = {"current_stock": 42.0, "forecast_daily_demand": 15.2, "drivers": []}
        ok, bad = es.verify_grounding(
            "Stock is 42 units and the supplier will deliver 8500 units next week.", ev,
        )
        assert not ok
        assert 8500 in bad

    def test_accepts_a_probability_stated_as_a_percentage(self):
        ev = {"stockout_probability": 0.87, "drivers": []}
        ok, bad = es.verify_grounding("There is an 87% chance of running out.", ev)
        assert ok, bad

    def test_small_integers_are_exempt(self):
        ev = {"current_stock": 1000.0, "drivers": []}
        ok, _ = es.verify_grounding("Stock is 1000 units. Two actions are needed.", ev)
        assert ok

    def test_sku_identifiers_are_not_read_as_numbers(self):
        """
        Regression: "SKU-1010" parsed as -1010, so any explanation that named its
        own SKU was rejected and the LLM path silently fell back every time.
        """
        assert es._numbers_in("SKU-1010 has 112 units") == [112.0]
        ev = {"current_stock": 112.0, "drivers": []}
        ok, bad = es.verify_grounding("SKU-1010 has 112 units on hand.", ev)
        assert ok, bad

    def test_iso_dates_are_not_read_as_numbers(self):
        assert es._numbers_in("As of 2026-06-29 stock is 500 units") == [500.0]
        ev = {"current_stock": 500.0, "as_of": "2026-06-29", "drivers": []}
        ok, bad = es.verify_grounding("As of 2026-06-29 stock is 500 units.", ev)
        assert ok, bad

    def test_ranges_are_read_as_two_positive_numbers(self):
        assert es._numbers_in("between 1200 and 1400 units") == [1200.0, 1400.0]
        assert es._numbers_in("a drop of -15.5 percent") == [-15.5]

    def test_a_realistic_grounded_explanation_is_accepted(self, svc):
        """
        End-to-end: compose an explanation the way the model is asked to, using
        only evidence values, and confirm the verifier lets it through.
        """
        risk = next(r for r in svc.ranked() if r["risk_type"] == "STOCKOUT"
                    and r.get("supply_coverage_ratio"))
        ev = es.build_evidence(risk)
        text = (
            f"{risk['sku_id']} has {risk['current_stock']:.0f} units on hand against "
            f"forecast demand of {risk['forecast_daily_demand']:.0f} units a day — "
            f"{risk['inventory_coverage_days']:.1f} days of cover against a "
            f"{risk['lead_time_days']:.0f}-day lead time. Raise an order of about "
            f"{risk['suggested_order_qty']:.0f} units to reach the order-up-to level "
            f"of {risk['order_up_to_units']:.0f} units."
        )
        ok, bad = es.verify_grounding(text, ev)
        assert ok, f"grounded text wrongly rejected; offending numbers: {bad}"

    def test_ungrounded_response_falls_back(self, svc):
        sku = svc.ranked()[0]["sku_id"]
        llm = FakeLlm(text="Our supplier confirmed 99999 units arriving on Tuesday.")
        out = es.generate_explanation(svc, sku, llm=llm)
        assert out["source"] == "fallback"
        assert out["error"] == "ungrounded_response"
        assert out["explanation"], "fallback text must still be produced"


class TestFailureHandling:
    def test_llm_error_produces_a_labelled_fallback(self, svc):
        sku = svc.ranked()[0]["sku_id"]
        out = es.generate_explanation(svc, sku, llm=FakeLlm(ok=False, error="APITimeoutError"))
        assert out["source"] == "fallback"
        assert out["error"] == "APITimeoutError"
        assert out["model"] is None
        assert len(out["explanation"]) > 30

    def test_fallback_uses_real_numbers(self, svc):
        risk = svc.ranked()[0]
        text = es.fallback_explanation(risk)
        assert risk["headline"] in text
        assert risk["recommended_action"] in text

    def test_fallback_mentions_limited_history_for_new_skus(self, svc):
        cold = [r for r in svc.risk_records() if r["is_cold_start"]]
        if not cold:
            pytest.skip("no cold-start SKUs")
        text = es.fallback_explanation(cold[0])
        assert "Limited history" in text
        assert str(cold[0]["days_of_history"]) in text

    def test_unknown_sku_raises(self, svc):
        with pytest.raises(KeyError):
            es.generate_explanation(svc, "NOPE-1", llm=FakeLlm(text="x y z w"))

    @pytest.mark.parametrize(
        "text,valid",
        [
            ("A perfectly reasonable explanation of the risk.", True),
            ("", False),
            ("   ", False),
            ("too short", False),
            ('{"sku_id": "SKU-1", "risk": 1}', False),   # echoed the evidence back
            ("x" * 5000, False),                          # runaway output
        ],
    )
    def test_response_validation(self, text, valid):
        ok, _ = _validate(text)
        assert ok is valid


class TestCaching:
    def test_second_call_is_served_from_cache(self, svc):
        sku = svc.ranked()[0]["sku_id"]
        llm = FakeLlm(text="Stock is low relative to the lead time, so order now.")
        first = es.generate_explanation(svc, sku, llm=llm)
        second = es.generate_explanation(svc, sku, llm=llm)
        assert first["cached"] is False
        assert second["cached"] is True
        assert len(llm.calls) == 1, "cache hit must not call the model again"

    def test_force_bypasses_the_cache(self, svc):
        sku = svc.ranked()[0]["sku_id"]
        llm = FakeLlm(text="Stock is low relative to the lead time, so order now.")
        es.generate_explanation(svc, sku, llm=llm)
        out = es.generate_explanation(svc, sku, force=True, llm=llm)
        assert len(llm.calls) == 2
        assert out["cached"] is False

    def test_failures_are_not_cached(self, svc):
        sku = svc.ranked()[0]["sku_id"]
        bad = FakeLlm(ok=False)
        es.generate_explanation(svc, sku, llm=bad)
        good = FakeLlm(text="A grounded explanation of why this SKU is flagged today.")
        out = es.generate_explanation(svc, sku, llm=good)
        assert out["source"] == "llm", "a failed call must not poison the cache"


# ---------------------------------------------------------------------------
class TestQaRetrieval:
    @pytest.mark.parametrize(
        "question,intent",
        [
            ("Why is SKU-1004 flagged?", "sku_explanation"),
            ("Tell me about SKU-1012", "sku_detail"),
            ("Which SKUs need attention?", "attention_list"),
            ("Which products have the highest stockout risk?", "stockout_list"),
            ("Why is SKU-1012 considered overstocked?", "sku_explanation"),
            ("Which SKUs are overstocked?", "overstock_list"),
            ("Which categories have the greatest risk?", "category_risk"),
            ("How are the newly launched SKUs doing?", "new_skus"),
            ("Which high-risk SKUs have short inventory coverage?", "coverage_list"),
            ("How many SKUs are there in total?", "summary"),
            ("How accurate is the model?", "model_info"),
        ],
    )
    def test_intent_classification(self, svc, question, intent):
        r = qs.retrieve(svc, question)
        assert r.intent == intent, f"{question!r} -> {r.intent}"

    def test_sku_extraction_is_case_insensitive(self, svc):
        for q in ("Why is SKU-1004 flagged?", "why is sku-1004 flagged?",
                  "Why is sku 1004 flagged?"):
            assert "SKU-1004" in qs.extract_skus(q, svc.sku_ids), q

    def test_retrieval_returns_only_relevant_records(self, svc):
        r = qs.retrieve(svc, "Why is SKU-1004 flagged?")
        assert "skus" in r.evidence
        assert [s["sku_id"] for s in r.evidence["skus"]] == ["SKU-1004"]
        # Not the whole catalogue.
        assert "skus_needing_attention" not in r.evidence

    def test_retrieval_is_bounded(self, svc):
        r = qs.retrieve(svc, "Which SKUs need attention?")
        assert len(r.evidence["skus_needing_attention"]) <= qs.MAX_SKUS_IN_EVIDENCE
        payload = json.dumps(r.evidence, default=str)
        assert len(payload) < 30_000, "evidence should be compact, not a data dump"

    def test_evidence_matches_the_dashboard(self, svc):
        """An answer must never disagree with the table on screen."""
        r = qs.retrieve(svc, "Which SKUs need attention?")
        for row in r.evidence["skus_needing_attention"]:
            live = svc.risk(row["sku_id"])
            assert row["risk_level"] == live["risk_level"]
            assert row["risk_score"] == live["risk_score"]

    def test_unknown_sku_falls_back_to_a_list_intent(self, svc):
        r = qs.retrieve(svc, "Why is SKU-9999 flagged?")
        assert r.intent == "attention_list"
        assert r.evidence.get("skus_needing_attention") is not None


class TestQaAnswering:
    def test_answer_is_grounded_and_labelled(self, svc):
        llm = FakeLlm(text="SKU-1004 is healthy with ample cover for its lead time.")
        out = qs.answer_question(svc, "Why is SKU-1004 flagged?", llm=llm)
        assert out["source"] == "llm"
        assert out["intent"] == "sku_explanation"
        assert out["grounded_on"][0]["kind"] == "sku_detail"
        assert "SKU-1004" in out["grounded_on"][0]["sku_ids"]

    def test_system_prompt_forbids_invention(self, svc):
        llm = FakeLlm(text="Some grounded answer about the current inventory position.")
        qs.answer_question(svc, "Which SKUs need attention?", llm=llm)
        system = llm.calls[0]["system"]
        assert "Answer ONLY from the EVIDENCE block" in system
        assert "Never invent numbers" in system

    def test_fallback_answer_is_useful(self, svc):
        out = qs.answer_question(svc, "Which SKUs need attention?",
                                 llm=FakeLlm(ok=False, error="rate_limit"))
        assert out["source"] == "fallback"
        assert out["error"] == "rate_limit"
        assert "SKU-" in out["answer"]
        assert out["grounded_on"], "grounding must still be reported on fallback"

    def test_long_question_is_truncated(self, svc):
        llm = FakeLlm(text="A perfectly ordinary answer about the inventory.")
        out = qs.answer_question(svc, "x" * 5000, llm=llm)
        assert len(out["question"]) <= qs.MAX_QUESTION_CHARS
