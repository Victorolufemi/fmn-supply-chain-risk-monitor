"""Pydantic response/request models. These define the contract the frontend types mirror."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

RiskLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "HEALTHY"]
RiskType = Literal["STOCKOUT", "OVERSTOCK", "NONE"]
Confidence = Literal["HIGH", "MEDIUM", "LOW"]


class Driver(BaseModel):
    name: str
    label: str
    value: float | None
    unit: str
    detail: str


class SkuSummary(BaseModel):
    """Row shape for the dashboard attention table."""

    sku_id: str
    category: str
    risk_level: RiskLevel
    risk_type: RiskType
    risk_score: float
    current_stock: float | None
    forecast_daily_demand: float | None
    inventory_coverage_days: float | None
    days_to_projected_stockout: float | None
    lead_time_days: float
    excess_units: float | None
    is_cold_start: bool
    days_of_history: int
    confidence: Confidence
    is_structurally_undersupplied: bool
    headline: str


class HistoryPoint(BaseModel):
    date: str
    units_sold: float | None
    units_received: float | None
    closing_stock: float | None
    is_stockout_day: int


class ForecastPoint(BaseModel):
    date: str
    horizon: int
    forecast_units: float


class SkuDetail(BaseModel):
    """Everything the SKU drill-down page renders."""

    sku_id: str
    category: str
    as_of: str

    risk_level: RiskLevel
    risk_type: RiskType
    risk_score: float
    stockout_probability: float
    stockout_probability_no_inbound: float
    overstock_score: float

    current_stock: float | None
    forecast_daily_demand: float | None
    lead_time_days: float
    lead_time_demand: float | None
    inventory_coverage_days: float | None
    days_to_projected_stockout: float | None
    safety_stock_units: float | None
    reorder_point_units: float | None
    order_up_to_units: float | None
    suggested_order_qty: float | None
    excess_units: float | None
    excess_ratio: float | None

    demand_sigma_daily: float | None
    demand_cv: float | None
    recent_7d_avg_demand: float | None
    previous_7d_avg_demand: float | None
    demand_change_pct: float | None

    replenishment_rate_per_day: float | None
    expected_inbound_within_lead_time: float | None
    supply_coverage_ratio: float | None
    is_structurally_undersupplied: bool
    units_received_in_window: float | None
    supply_window_days: int
    days_since_last_receipt: float | None
    avg_replenishment_interval_days: float | None
    avg_receipt_qty: float | None
    observed_stockout_days_28d: int
    observed_stockout_rate_all_time: float

    days_of_history: int
    is_cold_start: bool
    confidence: Confidence

    headline: str
    recommended_action: str
    drivers: list[Driver]

    history: list[HistoryPoint]
    forecast: list[ForecastPoint]


class RiskCount(BaseModel):
    level: RiskLevel
    count: int


class CategoryRisk(BaseModel):
    category: str
    total: int
    critical_high: int
    stockout: int
    overstock: int
    avg_coverage_days: float | None


class DashboardKpis(BaseModel):
    total_skus: int
    high_risk_count: int          # CRITICAL + HIGH
    critical_count: int
    stockout_risk_count: int
    overstock_risk_count: int
    healthy_count: int
    newly_launched_count: int
    out_of_stock_now: int
    structurally_undersupplied: int
    total_excess_units: float


class DashboardResponse(BaseModel):
    as_of: str
    generated_at: str
    kpis: DashboardKpis
    risk_distribution: list[RiskCount]
    category_risk: list[CategoryRisk]
    attention_list: list[SkuSummary]
    model_name: str
    llm_available: bool


class ExplanationResponse(BaseModel):
    sku_id: str
    explanation: str
    source: Literal["llm", "fallback"]
    model: str | None = None
    cached: bool = False
    generated_at: str
    evidence: dict
    error: str | None = None


class QaRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)

    @field_validator("question")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v


class QaSource(BaseModel):
    kind: str
    label: str
    sku_ids: list[str] = []


class QaResponse(BaseModel):
    question: str
    answer: str
    source: Literal["llm", "fallback"]
    model: str | None = None
    intent: str
    grounded_on: list[QaSource]
    evidence: dict
    generated_at: str
    error: str | None = None


class ModelInfo(BaseModel):
    selected_model: str
    serving_model: str
    cold_start_model: str
    model_description: str
    trained_at: str
    as_of_date: str
    forecast_horizon_days: int
    primary_metric: str
    metrics: dict
    baselines: list[dict]
    validation: dict
    cold_start: dict
    versions: dict


class MetadataResponse(BaseModel):
    as_of: str
    date_range: dict
    row_count: int
    sku_count: int
    categories: list[str]
    cold_start_skus: list[str]
    established_skus: list[str]
    cleaning_report: dict
    risk_config: dict
    llm_available: bool
    llm_model: str | None


class HealthResponse(BaseModel):
    status: str
    version: str
    artifacts_loaded: bool
    llm_configured: bool
    as_of: str | None
