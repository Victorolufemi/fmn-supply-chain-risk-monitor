import sys, warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
pd.set_option("display.width", 220)
from app.ml.data import load_clean_panel
from app.config import get_settings

panel, _, _ = load_clean_panel(get_settings().data_csv)
rows = []
for sku, g in panel.groupby("sku_id"):
    g = g.sort_values("date")
    rec = g[g.units_received > 0]
    gaps = rec.date.diff().dt.days.dropna()
    d = g.units_sold.mean()
    rows.append({
        "sku": sku, "n_days": len(g), "n_receipts": len(rec),
        "gap_mean": gaps.mean(), "gap_std": gaps.std(), "gap_min": gaps.min(),
        "gap_max": gaps.max(), "gap_cv": gaps.std() / gaps.mean() if len(gaps) > 1 else np.nan,
        "qty_mean": rec.units_received.mean(), "qty_std": rec.units_received.std(),
        "qty_cv": rec.units_received.std() / rec.units_received.mean() if len(rec) > 1 else np.nan,
        "daily_demand": d,
        "qty_in_days": rec.units_received.mean() / d if d else np.nan,
        "supply_vs_demand": rec.units_received.sum() / g.units_sold.sum(),
        "days_since_last": (g.date.max() - rec.date.max()).days if len(rec) else None,
        "zero_stock_days": int(g.is_stockout_day.sum()),
    })
df = pd.DataFrame(rows).set_index("sku")
print(df.round(2).to_string())
print("\n--- summary ---")
print(f"median inter-receipt gap CV: {df.gap_cv.median():.2f}")
print(f"median receipt qty CV      : {df.qty_cv.median():.2f}")
print(f"median receipts per SKU    : {df.n_receipts.median():.0f}")
print(f"total supply / total demand: {df.supply_vs_demand.median():.3f}")
print("\n--- gap distribution pooled (established SKUs) ---")
allgaps = []
for sku, g in panel.groupby("sku_id"):
    if len(g) < 30:
        continue
    rec = g.sort_values("date")
    rec = rec[rec.units_received > 0]
    allgaps += rec.date.diff().dt.days.dropna().tolist()
s = pd.Series(allgaps)
print(s.describe().round(2).to_string())
print("\nquantiles:", {q: round(float(s.quantile(q)), 1) for q in (.1, .25, .5, .75, .9)})
