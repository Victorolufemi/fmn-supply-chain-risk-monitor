"""SKU listing, drill-down detail, and the on-demand LLM explanation."""
from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dashboard import to_summary
from app.schemas.models import (Driver, ExplanationResponse, ForecastPoint,
                                HistoryPoint, SkuDetail, SkuSummary)
from app.services.data_service import DataService, get_service
from app.services.explanation_service import generate_explanation

router = APIRouter(tags=["skus"])


def _n(v):
    """None for anything non-finite, so the JSON never carries NaN."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


@router.get("/skus", response_model=list[SkuSummary])
def list_skus(
    risk_level: str | None = Query(None, description="CRITICAL|HIGH|MEDIUM|LOW|HEALTHY"),
    risk_type: str | None = Query(None, description="STOCKOUT|OVERSTOCK|NONE"),
    category: str | None = None,
    cold_start: bool | None = Query(None, description="true = newly launched only"),
    search: str | None = Query(None, description="Substring match on SKU id or category"),
    limit: int = Query(200, ge=1, le=1000),
    svc: DataService = Depends(get_service),
) -> list[SkuSummary]:
    recs = svc.ranked()
    if risk_level:
        wanted = {v.strip().upper() for v in risk_level.split(",") if v.strip()}
        recs = [r for r in recs if r["risk_level"] in wanted]
    if risk_type:
        wanted = {v.strip().upper() for v in risk_type.split(",") if v.strip()}
        recs = [r for r in recs if r["risk_type"] in wanted]
    if category:
        wanted = {v.strip().lower() for v in category.split(",") if v.strip()}
        recs = [r for r in recs if r["category"].lower() in wanted]
    if cold_start is not None:
        recs = [r for r in recs if bool(r.get("is_cold_start")) == cold_start]
    if search:
        q = search.strip().lower()
        recs = [r for r in recs
                if q in r["sku_id"].lower() or q in r["category"].lower()]
    return [to_summary(r) for r in recs[:limit]]


@router.get("/skus/{sku_id}", response_model=SkuDetail)
def get_sku(
    sku_id: str,
    history_days: int = Query(90, ge=7, le=400),
    svc: DataService = Depends(get_service),
) -> SkuDetail:
    resolved = svc.resolve_sku(sku_id)
    if resolved is None:
        raise HTTPException(404, detail=f"Unknown SKU '{sku_id}'")
    r = svc.risk(resolved)

    hist = svc.history(resolved, last_n=history_days)
    history = [
        HistoryPoint(
            date=pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
            units_sold=_n(row.get("units_sold")),
            units_received=_n(row.get("units_received")),
            closing_stock=_n(row.get("closing_stock")),
            is_stockout_day=int(row.get("is_stockout_day") or 0),
        )
        for row in hist.to_dict("records")
    ]
    fc = svc.forecast(resolved)
    forecast = [
        ForecastPoint(
            date=pd.Timestamp(row["target_date"]).strftime("%Y-%m-%d"),
            horizon=int(row["horizon"]),
            forecast_units=round(float(row["y_pred"]), 1),
        )
        for row in fc.to_dict("records")
    ]

    payload = {k: v for k, v in r.items() if k != "drivers"}
    for key in list(payload):
        if isinstance(payload[key], float) and not math.isfinite(payload[key]):
            payload[key] = None

    return SkuDetail(
        **payload,
        drivers=[Driver(**d) for d in (r.get("drivers") or [])],
        history=history,
        forecast=forecast,
    )


@router.get("/skus/{sku_id}/explanation", response_model=ExplanationResponse)
def get_explanation(
    sku_id: str,
    force: bool = Query(False, description="Bypass the cache and call the model again"),
    svc: DataService = Depends(get_service),
) -> ExplanationResponse:
    resolved = svc.resolve_sku(sku_id)
    if resolved is None:
        raise HTTPException(404, detail=f"Unknown SKU '{sku_id}'")
    return ExplanationResponse(**generate_explanation(svc, resolved, force=force))
