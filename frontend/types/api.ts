/**
 * Types mirroring the FastAPI response models in `backend/app/schemas/models.py`.
 *
 * The frontend holds NO business logic: no risk arithmetic, no thresholds, no
 * forecasting, no LLM calls. Everything below is a shape the backend computed.
 */

export type RiskLevel = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "HEALTHY";
export type RiskType = "STOCKOUT" | "OVERSTOCK" | "NONE";
export type Confidence = "HIGH" | "MEDIUM" | "LOW";

export interface Driver {
  name: string;
  label: string;
  value: number | null;
  unit: string;
  detail: string;
}

export interface SkuSummary {
  sku_id: string;
  category: string;
  risk_level: RiskLevel;
  risk_type: RiskType;
  risk_score: number;
  current_stock: number | null;
  forecast_daily_demand: number | null;
  inventory_coverage_days: number | null;
  days_to_projected_stockout: number | null;
  lead_time_days: number;
  excess_units: number | null;
  is_cold_start: boolean;
  days_of_history: number;
  confidence: Confidence;
  is_structurally_undersupplied: boolean;
  headline: string;
}

export interface HistoryPoint {
  date: string;
  units_sold: number | null;
  units_received: number | null;
  closing_stock: number | null;
  is_stockout_day: number;
}

export interface ForecastPoint {
  date: string;
  horizon: number;
  forecast_units: number;
}

export interface SkuDetail extends SkuSummary {
  as_of: string;
  stockout_probability: number;
  stockout_probability_no_inbound: number;
  overstock_score: number;
  lead_time_demand: number | null;
  safety_stock_units: number | null;
  reorder_point_units: number | null;
  order_up_to_units: number | null;
  suggested_order_qty: number | null;
  excess_ratio: number | null;
  demand_sigma_daily: number | null;
  demand_cv: number | null;
  recent_7d_avg_demand: number | null;
  previous_7d_avg_demand: number | null;
  demand_change_pct: number | null;
  replenishment_rate_per_day: number | null;
  expected_inbound_within_lead_time: number | null;
  supply_coverage_ratio: number | null;
  units_received_in_window: number | null;
  supply_window_days: number;
  days_since_last_receipt: number | null;
  avg_replenishment_interval_days: number | null;
  avg_receipt_qty: number | null;
  observed_stockout_days_28d: number;
  observed_stockout_rate_all_time: number;
  recommended_action: string;
  drivers: Driver[];
  history: HistoryPoint[];
  forecast: ForecastPoint[];
}

export interface DashboardKpis {
  total_skus: number;
  high_risk_count: number;
  critical_count: number;
  stockout_risk_count: number;
  overstock_risk_count: number;
  healthy_count: number;
  newly_launched_count: number;
  out_of_stock_now: number;
  structurally_undersupplied: number;
  total_excess_units: number;
}

export interface RiskCount {
  level: RiskLevel;
  count: number;
}

export interface CategoryRisk {
  category: string;
  total: number;
  critical_high: number;
  stockout: number;
  overstock: number;
  avg_coverage_days: number | null;
}

export interface DashboardResponse {
  as_of: string;
  generated_at: string;
  kpis: DashboardKpis;
  risk_distribution: RiskCount[];
  category_risk: CategoryRisk[];
  attention_list: SkuSummary[];
  model_name: string;
  llm_available: boolean;
}

export interface ExplanationResponse {
  sku_id: string;
  explanation: string;
  source: "llm" | "fallback";
  model: string | null;
  cached: boolean;
  generated_at: string;
  evidence: Record<string, unknown>;
  error: string | null;
}

export interface QaSource {
  kind: string;
  label: string;
  sku_ids: string[];
}

export interface QaResponse {
  question: string;
  answer: string;
  source: "llm" | "fallback";
  model: string | null;
  intent: string;
  grounded_on: QaSource[];
  evidence: Record<string, unknown>;
  generated_at: string;
  error: string | null;
}

export interface ModelInfo {
  selected_model: string;
  serving_model: string;
  cold_start_model: string;
  model_description: string;
  trained_at: string;
  as_of_date: string;
  forecast_horizon_days: number;
  primary_metric: string;
  metrics: {
    wape_pooled: number | null;
    wape_mean_of_folds: number | null;
    wape_sd_across_folds: number | null;
    mae_units: number | null;
    rmse_units: number | null;
    bias_pct: number | null;
    forecast_points: number;
  };
  baselines: {
    model: string;
    wape: number | null;
    mae: number | null;
    is_baseline: boolean;
  }[];
  validation: Record<string, unknown>;
  cold_start: Record<string, unknown>;
  versions: Record<string, string>;
}

export interface MetadataResponse {
  as_of: string;
  date_range: { start: string; end: string };
  row_count: number;
  sku_count: number;
  categories: string[];
  cold_start_skus: string[];
  established_skus: string[];
  cleaning_report: Record<string, unknown>;
  risk_config: Record<string, unknown>;
  llm_available: boolean;
  llm_model: string | null;
}
