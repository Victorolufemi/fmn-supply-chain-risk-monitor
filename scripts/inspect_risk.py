import warnings; warnings.filterwarnings("ignore")
import sys
import joblib, pandas as pd, numpy as np
from pathlib import Path
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))   # the bundle pickles app.ml classes
b = joblib.load(ROOT / "models/supply_chain/supply_chain_bundle.joblib")
r = b["risk"]
cols = ["sku_id", "category", "risk_level", "risk_type", "risk_score",
        "stockout_probability", "stockout_probability_no_inbound", "overstock_score",
        "current_stock", "forecast_daily_demand", "inventory_coverage_days",
        "days_to_projected_stockout", "lead_time_days", "lead_time_demand",
        "replenishment_rate_per_day", "expected_inbound_within_lead_time",
        "supply_coverage_ratio", "supply_window_days", "is_structurally_undersupplied",
        "order_up_to_units", "excess_units", "suggested_order_qty",
        "demand_change_pct", "observed_stockout_rate_all_time",
        "days_of_history", "is_cold_start", "confidence"]
print(r[cols].sort_values("risk_score", ascending=False).to_string(index=False))
print("\n=== level counts ===")
print(r.risk_level.value_counts().to_string())
print("\n=== type counts ===")
print(r.risk_type.value_counts().to_string())
print("\n=== coverage vs lead time ===")
print(r[["sku_id","inventory_coverage_days","lead_time_days","stockout_probability"]]
      .assign(cov_minus_lt=lambda d: d.inventory_coverage_days-d.lead_time_days)
      .sort_values("cov_minus_lt").to_string(index=False))
print("\n=== forecast sanity: model vs recent actual ===")
f = b["forecast"]; panel = b["panel"]
last7 = panel.groupby("sku_id")["units_sold"].apply(lambda s: s.tail(7).mean())
fc7 = f[f.horizon <= 7].groupby("sku_id")["y_pred"].mean()
cmp = pd.DataFrame({"actual_last7": last7, "forecast_next7": fc7})
cmp["ratio"] = cmp.forecast_next7 / cmp.actual_last7
print(cmp.round(1).sort_values("ratio").to_string())
