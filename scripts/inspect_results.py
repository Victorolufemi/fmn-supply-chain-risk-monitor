import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from pathlib import Path
pd.set_option("display.width", 220)
ROOT = Path(__file__).resolve().parents[1]

r = pd.read_csv(ROOT / "backend/reports/fold_results.csv")
p = pd.read_csv(ROOT / "backend/reports/backtest_predictions.csv")
main = [f"fold_{i}" for i in range(1, 6)]

def w(d):
    return np.abs(d.y_true - d.y_pred).sum() / d.y_true.sum()

print("=== per-fold WAPE ===")
print(r[r.fold.isin(main)].pivot(index="model", columns="fold", values="wape").round(4).to_string())
print("\n=== pooled WAPE (main folds) ===")
sub = p[p.fold.isin(main)]
print(sub.groupby("model").apply(w, include_groups=False).sort_values().round(4).to_string())
print("\n=== MAE / RMSE / bias pooled ===")
agg = sub.groupby("model").apply(lambda d: pd.Series({
    "wape": w(d),
    "mae": np.abs(d.y_true - d.y_pred).mean(),
    "rmse": np.sqrt(((d.y_true - d.y_pred) ** 2).mean()),
    "bias%": (d.y_pred - d.y_true).sum() / d.y_true.sum() * 100,
}), include_groups=False).sort_values("wape")
print(agg.round(3).to_string())
print("\n=== cold start fold ===")
print(r[r.fold == "cold_start"][["model", "wape", "mae", "rmse", "n"]].sort_values("wape").round(4).to_string(index=False))
print("\n=== WAPE by horizon (main folds) ===")
print(sub.groupby(["model", "horizon"]).apply(w, include_groups=False).unstack(0).round(4).to_string())
print("\n=== WAPE by SKU, top/bottom for best 3 models ===")
best3 = agg.index[:3].tolist()
bysku = sub[sub.model.isin(best3)].groupby(["model", "sku_id"]).apply(w, include_groups=False).unstack(0)
print(bysku.round(3).sort_values(bysku.columns[0]).to_string())
