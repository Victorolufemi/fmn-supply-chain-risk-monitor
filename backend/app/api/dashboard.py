"""Dashboard endpoints: portfolio KPIs, risk distribution, ranked attention list."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.models import (CategoryRisk, DashboardKpis, DashboardResponse,
                                RiskCount, SkuSummary)
from app.services.data_service import DataService, get_service, now_iso
from app.services.llm_client import get_llm

router = APIRouter(tags=["dashboard"])

LEVELS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "HEALTHY"]


def to_summary(r: dict) -> SkuSummary:
    return SkuSummary(
        sku_id=r["sku_id"], category=r["category"],
        risk_level=r["risk_level"], risk_type=r["risk_type"],
        risk_score=r["risk_score"], current_stock=r.get("current_stock"),
        forecast_daily_demand=r.get("forecast_daily_demand"),
        inventory_coverage_days=r.get("inventory_coverage_days"),
        days_to_projected_stockout=r.get("days_to_projected_stockout"),
        lead_time_days=r["lead_time_days"], excess_units=r.get("excess_units"),
        is_cold_start=bool(r.get("is_cold_start")),
        days_of_history=int(r.get("days_of_history") or 0),
        confidence=r.get("confidence", "MEDIUM"),
        is_structurally_undersupplied=bool(r.get("is_structurally_undersupplied")),
        headline=r.get("headline", ""),
    )


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(svc: DataService = Depends(get_service)) -> DashboardResponse:
    records = svc.risk_records()
    ranked = svc.ranked()

    kpis = DashboardKpis(
        total_skus=len(records),
        high_risk_count=sum(r["risk_level"] in ("CRITICAL", "HIGH") for r in records),
        critical_count=sum(r["risk_level"] == "CRITICAL" for r in records),
        stockout_risk_count=sum(r["risk_type"] == "STOCKOUT" for r in records),
        overstock_risk_count=sum(r["risk_type"] == "OVERSTOCK" for r in records),
        healthy_count=sum(r["risk_level"] == "HEALTHY" for r in records),
        newly_launched_count=sum(bool(r.get("is_cold_start")) for r in records),
        out_of_stock_now=sum((r.get("current_stock") or 0) <= 0 for r in records),
        structurally_undersupplied=sum(
            bool(r.get("is_structurally_undersupplied")) for r in records),
        total_excess_units=round(
            sum(float(r.get("excess_units") or 0) for r in records), 1),
    )

    counts = {lvl: 0 for lvl in LEVELS}
    for r in records:
        counts[r["risk_level"]] = counts.get(r["risk_level"], 0) + 1

    cats: list[CategoryRisk] = []
    for cat in svc.categories:
        sub = [r for r in records if r["category"] == cat]
        if not sub:
            continue
        covs = [r["inventory_coverage_days"] for r in sub
                if r.get("inventory_coverage_days") is not None]
        cats.append(CategoryRisk(
            category=cat, total=len(sub),
            critical_high=sum(r["risk_level"] in ("CRITICAL", "HIGH") for r in sub),
            stockout=sum(r["risk_type"] == "STOCKOUT" for r in sub),
            overstock=sum(r["risk_type"] == "OVERSTOCK" for r in sub),
            avg_coverage_days=round(sum(covs) / len(covs), 2) if covs else None,
        ))
    cats.sort(key=lambda c: (-c.critical_high, c.category))

    b = svc.bundle
    return DashboardResponse(
        as_of=svc.as_of,
        generated_at=now_iso(),
        kpis=kpis,
        risk_distribution=[RiskCount(level=l, count=counts[l]) for l in LEVELS],
        category_risk=cats,
        attention_list=[to_summary(r) for r in ranked],
        model_name=b.get("serving_model") or b.get("selected_model", "unknown"),
        llm_available=get_llm().available,
    )
