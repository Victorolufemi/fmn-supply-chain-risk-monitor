"""Grounded natural-language Q&A endpoint."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.schemas.models import QaRequest, QaResponse, QaSource
from app.services.data_service import DataService, get_service
from app.services.qa_service import answer_question

log = logging.getLogger(__name__)
router = APIRouter(tags=["qa"])

SUGGESTIONS = [
    "Which SKUs need attention?",
    "Which products have the highest stockout risk?",
    "Which SKUs are overstocked and tying up working capital?",
    "Which categories carry the most risk?",
    "How are the newly launched SKUs doing?",
    "Which SKUs have the least inventory coverage?",
]


@router.post("/qa", response_model=QaResponse)
def ask(req: QaRequest, svc: DataService = Depends(get_service)) -> QaResponse:
    # Log the question but never the evidence payload, which mirrors business data.
    log.info("QA question (%d chars)", len(req.question))
    result = answer_question(svc, req.question)
    return QaResponse(
        **{**result, "grounded_on": [QaSource(**s) for s in result["grounded_on"]]}
    )


@router.get("/qa/suggestions", response_model=list[str])
def suggestions(svc: DataService = Depends(get_service)) -> list[str]:
    """Starter questions, with one pointing at a SKU that is actually flagged."""
    out = list(SUGGESTIONS)
    ranked = [r for r in svc.ranked() if r["risk_level"] != "HEALTHY"]
    if ranked:
        out.insert(1, f"Why is {ranked[0]['sku_id']} flagged?")
    return out
