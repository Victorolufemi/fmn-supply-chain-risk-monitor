"""Metadata, model card and category endpoints — the transparency surface."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import get_settings
from app.schemas.models import CategoryRisk, MetadataResponse, ModelInfo
from app.services.data_service import DataService, get_service
from app.services.llm_client import get_llm

router = APIRouter(tags=["meta"])


@router.get("/metadata", response_model=MetadataResponse)
def metadata(svc: DataService = Depends(get_service)) -> MetadataResponse:
    b = svc.bundle
    panel = b["panel"]
    s = get_settings()
    llm = get_llm()
    return MetadataResponse(
        as_of=svc.as_of,
        date_range={"start": str(panel["date"].min().date()),
                    "end": str(panel["date"].max().date())},
        row_count=int(len(panel)),
        sku_count=len(svc.sku_ids),
        categories=svc.categories,
        cold_start_skus=b.get("cold_start_skus", []),
        established_skus=b.get("established_skus", []),
        cleaning_report=b.get("cleaning_report", {}),
        risk_config=_jsonable(b.get("config", {})),
        llm_available=llm.available,
        llm_model=llm.model if llm.available else None,
    )


@router.get("/model-info", response_model=ModelInfo)
def model_info(svc: DataService = Depends(get_service)) -> ModelInfo:
    b = svc.bundle
    ev = b.get("evaluation", {})
    pooled = {k: round(float(v), 4) for k, v in (ev.get("pooled_wape") or {}).items()}
    agg = {row["model"]: row for row in (ev.get("aggregate") or [])}
    selected = b.get("selected_model", "")
    sel_agg = agg.get(selected, {})

    baselines = [
        {"model": m, "wape": pooled.get(m),
         "mae": round(float(agg[m]["mae"]), 1) if m in agg else None,
         "is_baseline": bool(agg.get(m, {}).get("is_baseline"))}
        for m in pooled
    ]
    cold_fold_rows = [r for r in (ev.get("fold_results") or [])
                      if r.get("fold") == ev.get("cold_fold")]

    return ModelInfo(
        selected_model=selected,
        serving_model=b.get("serving_model", selected),
        cold_start_model=b.get("cold_start_model", selected),
        model_description=getattr(b.get("model"), "description", ""),
        trained_at=b.get("trained_at", ""),
        as_of_date=b.get("as_of_date", ""),
        forecast_horizon_days=int(b.get("horizons", [28])[-1]),
        primary_metric="WAPE",
        metrics={
            "wape_pooled": pooled.get(selected),
            "wape_mean_of_folds": _round(sel_agg.get("wape_mean_of_folds")),
            "wape_sd_across_folds": _round(sel_agg.get("wape_std_of_folds")),
            "mae_units": _round(sel_agg.get("mae"), 1),
            "rmse_units": _round(sel_agg.get("rmse"), 1),
            "bias_pct": _round(sel_agg.get("bias_pct"), 2),
            "forecast_points": int(sel_agg.get("n_points") or 0),
        },
        baselines=sorted(baselines, key=lambda r: (r["wape"] is None, r["wape"])),
        validation={
            "strategy": "rolling-origin expanding window",
            "folds": len(ev.get("main_folds") or []),
            "horizon_days": 14,
            "random_split_used": False,
            "why_not_random": (
                "Rolling features would leak across a shuffled boundary, and a "
                "random split scores interpolation rather than forecasting."
            ),
            "fold_results": [r for r in (ev.get("fold_results") or [])
                             if r.get("fold") in (ev.get("main_folds") or [])],
        },
        cold_start={
            "threshold_days": int(b.get("config", {}).get("cold_start_max_days", 30)),
            "skus": b.get("cold_start_skus", []),
            "history_lengths": {k: int(v) for k, v in (b.get("history_lengths") or {}).items()
                                if k in b.get("cold_start_skus", [])},
            "serving_model": b.get("cold_start_model", selected),
            "fold_results": cold_fold_rows,
        },
        versions=b.get("versions", {}),
    )


@router.get("/categories", response_model=list[CategoryRisk])
def categories(svc: DataService = Depends(get_service)) -> list[CategoryRisk]:
    records = svc.risk_records()
    out: list[CategoryRisk] = []
    for cat in svc.categories:
        sub = [r for r in records if r["category"] == cat]
        if not sub:
            continue
        covs = [r["inventory_coverage_days"] for r in sub
                if r.get("inventory_coverage_days") is not None]
        out.append(CategoryRisk(
            category=cat, total=len(sub),
            critical_high=sum(r["risk_level"] in ("CRITICAL", "HIGH") for r in sub),
            stockout=sum(r["risk_type"] == "STOCKOUT" for r in sub),
            overstock=sum(r["risk_type"] == "OVERSTOCK" for r in sub),
            avg_coverage_days=round(sum(covs) / len(covs), 2) if covs else None,
        ))
    out.sort(key=lambda c: (-c.critical_high, c.category))
    return out


def _round(v, nd: int = 4):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _jsonable(obj):
    """Risk bands are tuples; JSON wants lists."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj
