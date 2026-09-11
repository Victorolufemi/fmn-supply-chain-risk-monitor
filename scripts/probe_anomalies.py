"""Deep-dive into the anomalies surfaced by profile_data.py, before deciding the cleaning rules."""
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_csv(ROOT / "data" / "project1_supply_chain_demand.csv")
df["date"] = pd.to_datetime(df["date"])

print("=" * 70)
print("A. DUPLICATE ROWS")
dups = df[df.duplicated(["sku_id", "date"], keep=False)].sort_values(["sku_id", "date"])
print(dups.to_string())
print("\nexact-dup groups (all 7 cols identical)?",
      df.duplicated().sum(), "of", df.duplicated(['sku_id','date']).sum())

print("\n" + "=" * 70)
print("B. CATEGORY CASE VARIANTS")
print(df["category"].value_counts().to_string())
print("\nSKUs whose category is not constant after upper():")
g = df.groupby("sku_id")["category"].apply(lambda s: s.str.upper().nunique())
print(g[g > 1].to_string() if (g > 1).any() else "  none — case is the only inconsistency")
print("\nraw category variants per sku (only those with >1 raw variant):")
g2 = df.groupby("sku_id")["category"].nunique()
for s in g2[g2 > 1].index:
    print(" ", s, df.loc[df.sku_id == s, "category"].value_counts().to_dict())

print("\n" + "=" * 70)
print("C. LEAD TIME NON-CONSTANT SKUS")
lt = df.groupby("sku_id")["lead_time_days"].nunique()
for s in lt[lt > 1].index:
    print(" ", s, df.loc[df.sku_id == s, "lead_time_days"].value_counts().to_dict())

print("\n" + "=" * 70)
print("D. MISSINGNESS PATTERN")
print("rows with missing units_sold AND missing closing_stock:",
      int((df.units_sold.isna() & df.closing_stock.isna()).sum()))
print("missing units_sold by sku (new SKUs?):")
m = df.groupby("sku_id")[["units_sold", "closing_stock"]].apply(lambda d: d.isna().sum())
print(m[m.sum(axis=1) > 0].to_string())
print("\nis missingness clustered in time? by month:")
print(df.assign(m=df.date.dt.to_period("M")).groupby("m")[["units_sold","closing_stock"]]
        .apply(lambda d: d.isna().sum()).to_string())

print("\n" + "=" * 70)
print("E. BALANCE VIOLATIONS vs STOCKOUT FLOOR")
d = df.drop_duplicates(["sku_id", "date"]).sort_values(["sku_id", "date"]).copy()
d["prev"] = d.groupby("sku_id")["closing_stock"].shift(1)
d["expected"] = d["prev"] + d["units_received"] - d["units_sold"]
d["resid"] = d["closing_stock"] - d["expected"]
chk = d.dropna(subset=["resid"])
viol = chk[chk.resid.abs() > 1]
print("total violations:", len(viol), "of", len(chk))
print("  ... of which expected<0 (censored at zero):", int((viol.expected < 0).sum()))
print("  ... of which closing_stock==0:", int((viol.closing_stock == 0).sum()))
print("  ... of which expected<0 AND closing==0:",
      int(((viol.expected < 0) & (viol.closing_stock == 0)).sum()))
rest = viol[(viol.expected >= 0)]
print("\nviolations NOT explained by the zero floor:", len(rest))
print(rest[["sku_id","date","units_sold","units_received","prev","closing_stock","expected","resid"]]
      .head(20).to_string())
print("\nresid distribution for unexplained:", rest.resid.describe().round(2).to_dict())

print("\n" + "=" * 70)
print("F. CENSORED DEMAND (potential lost sales)")
z = d[d.closing_stock == 0]
print("zero-stock days:", len(z), "across", z.sku_id.nunique(), "SKUs")
print(z.groupby("sku_id").size().sort_values(ascending=False).head(10).to_string())

print("\n" + "=" * 70)
print("G. NEW SKUS DETAIL")
for s in ["SKU-2000", "SKU-2001", "SKU-2002"]:
    sub = d[d.sku_id == s]
    print(f"\n--- {s} | cat={sub.category.iloc[0]} | lt={sub.lead_time_days.iloc[0]} "
          f"| n={len(sub)} | {sub.date.min().date()}..{sub.date.max().date()}")
    print(sub[["date","units_sold","units_received","closing_stock","lead_time_days"]].to_string(index=False))

print("\n" + "=" * 70)
print("H. LAST-DAY SNAPSHOT (what the dashboard will show)")
last = d.sort_values("date").groupby("sku_id").tail(1)
last = last.assign(cov=last.closing_stock / d.groupby("sku_id")["units_sold"].mean().reindex(last.sku_id).values)
print(last[["sku_id","date","category","closing_stock","units_sold","lead_time_days","cov"]]
      .sort_values("cov").round(2).to_string(index=False))

print("\n" + "=" * 70)
print("I. DAY-OF-WEEK PER SKU (is the weekly pattern universal?)")
dw = d.assign(dow=d.date.dt.dayofweek)
piv = dw.pivot_table(index="sku_id", columns="dow", values="units_sold", aggfunc="mean")
ratio = (piv.max(axis=1) / piv.min(axis=1)).round(2)
print(ratio.sort_values(ascending=False).to_string())

print("\n" + "=" * 70)
print("J. AUTOCORRELATION / TREND CHECK on a few SKUs")
for s in ["SKU-1004", "SKU-1012", "SKU-1019", "SKU-1008"]:
    y = d.loc[d.sku_id == s].set_index("date")["units_sold"].asfreq("D")
    yi = y.interpolate()
    print(f"{s}: lag1={yi.autocorr(1):.3f} lag7={yi.autocorr(7):.3f} "
          f"first30={yi.head(30).mean():.1f} last30={yi.tail(30).mean():.1f}")

print("\n" + "=" * 70)
print("K. OUTLIERS — demand spikes")
sd = d.groupby("sku_id")["units_sold"].transform(lambda s: (s - s.mean()) / s.std())
print("rows with |z|>4:", int((sd.abs() > 4).sum()))
print(d.loc[sd.abs() > 4, ["sku_id","date","units_sold"]].to_string(index=False))
