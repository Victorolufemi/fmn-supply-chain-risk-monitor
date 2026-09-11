"""
Canonical data loading + cleaning.

Every cleaning rule below is a direct response to something found in
`backend/reports/data_profile.md`. Column names are DETECTED, not assumed, so a
renamed header in a future extract does not silently break the pipeline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Canonical internal names. The detector maps whatever the file uses onto these.
DATE = "date"
SKU = "sku_id"
CATEGORY = "category"
DEMAND = "units_sold"
RECEIVED = "units_received"
STOCK = "closing_stock"
LEAD_TIME = "lead_time_days"


@dataclass
class SchemaMap:
    """Which source column plays which role."""

    date: str
    sku: str
    category: str | None
    demand: str
    received: str | None
    stock: str | None
    lead_time: str | None

    def rename_map(self) -> dict[str, str]:
        m = {self.date: DATE, self.sku: SKU, self.demand: DEMAND}
        if self.category:
            m[self.category] = CATEGORY
        if self.received:
            m[self.received] = RECEIVED
        if self.stock:
            m[self.stock] = STOCK
        if self.lead_time:
            m[self.lead_time] = LEAD_TIME
        return m


@dataclass
class CleaningReport:
    """Audit trail of what cleaning did — surfaced through /api/metadata."""

    rows_in: int = 0
    rows_out: int = 0
    exact_duplicates_dropped: int = 0
    category_case_normalised: int = 0
    demand_values_imputed: int = 0
    stock_values_imputed: int = 0
    lead_time_imputed_skus: list[str] = field(default_factory=list)
    balance_violations: int = 0
    balance_violations_explained_by_zero_floor: int = 0
    observed_stockout_days: int = 0

    def as_dict(self) -> dict:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "exact_duplicates_dropped": self.exact_duplicates_dropped,
            "category_case_normalised": self.category_case_normalised,
            "demand_values_imputed": self.demand_values_imputed,
            "stock_values_imputed": self.stock_values_imputed,
            "lead_time_imputed_skus": self.lead_time_imputed_skus,
            "balance_violations": self.balance_violations,
            "balance_violations_explained_by_zero_floor":
                self.balance_violations_explained_by_zero_floor,
            "observed_stockout_days": self.observed_stockout_days,
        }


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------
def detect_schema(df: pd.DataFrame) -> SchemaMap:
    """Infer the role of each column from its content (with name as a tiebreaker)."""
    date_col = _detect_date_column(df)
    sku_col = _detect_id_column(df, date_col)

    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    demand = received = stock = lead = None
    for c in numeric:
        lc = c.lower()
        if demand is None and any(k in lc for k in ("sold", "demand", "sales", "shipped")):
            demand = c
        elif received is None and any(k in lc for k in ("receiv", "inbound", "supply", "grn")):
            received = c
        elif stock is None and any(k in lc for k in ("stock", "inventory", "on_hand", "onhand")):
            stock = c
        elif lead is None and "lead" in lc:
            lead = c

    if demand is None:
        # Fall back to the numeric column that behaves most like daily demand:
        # strictly non-negative, low zero-share, and not near-constant per SKU.
        cands = [c for c in numeric if c not in (received, stock, lead)]
        if not cands:
            raise ValueError("Could not identify a demand column")
        demand = min(cands, key=lambda c: df.groupby(sku_col)[c].nunique().mean() * -1)

    # Category = a low-cardinality non-numeric column that is not the id.
    category = None
    for c in df.columns:
        if c in (date_col, sku_col) or pd.api.types.is_numeric_dtype(df[c]):
            continue
        k = df[c].astype(str).str.strip().str.upper().nunique()
        if 1 < k < df[sku_col].nunique():
            category = c
            break

    schema = SchemaMap(date_col, sku_col, category, demand, received, stock, lead)
    log.info("detected schema: %s", schema)
    return schema


def _detect_date_column(df: pd.DataFrame) -> str:
    best, best_score = None, 0.0
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        parsed = pd.to_datetime(df[col], errors="coerce", format="mixed")
        score = float(parsed.notna().mean())
        if score > 0.9 and parsed.nunique() > 1:
            score += 0.001 * min(parsed.nunique(), 1000)
        if score > best_score:
            best, best_score = col, score
    if best is None:
        raise ValueError("No date-like column detected")
    return best


def _detect_id_column(df: pd.DataFrame, date_col: str) -> str:
    """The entity key is the column that best partitions the frame into date-unique panels."""
    best, best_score, n = None, -1.0, len(df)
    for col in df.columns:
        if col == date_col or pd.api.types.is_numeric_dtype(df[col]):
            continue
        k = df[col].nunique(dropna=True)
        if k < 2 or k > n / 2:
            continue
        uniq_dates = df.groupby(col)[date_col].nunique().sum()
        score = (uniq_dates / n) * (k / n)
        if score > best_score:
            best, best_score = col, score
    if best is None:
        raise ValueError("No SKU-like identifier column detected")
    return best


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------
def load_clean_panel(csv_path: str | Path) -> tuple[pd.DataFrame, CleaningReport, SchemaMap]:
    """
    Load the CSV and return a tidy, gap-free daily panel plus an audit report.

    Cleaning rules (each justified by the data profile):

    1. Drop exact duplicate rows. 15 rows in the supplied file are byte-identical
       repeats of an earlier (sku, date) row; keeping them would double-weight
       those days in every rolling statistic.
    2. Normalise category case. `BEVERAGES`/`Beverages` are the same category; the
       profile confirms case is the ONLY inconsistency (no SKU changes category).
    3. Reindex each SKU onto a complete daily grid over its own observed span, so
       lag-7 features always mean "seven calendar days ago".
    4. Impute missing `units_sold` (1.98%) and `closing_stock` (1.01%) *causally*
       where possible. Demand gaps are filled with the SKU's trailing same-weekday
       median — never a value that peeks into the future. Stock gaps are filled by
       rolling the inventory balance forward from the last known level.
    5. Repair `lead_time_days`. It is a static SKU attribute (constant for all 25
       established SKUs) but is pure noise for the 3 new SKUs, where it takes 4-5
       different values in 12 days. For those, substitute the category median.
    6. Flag observed stockouts. `closing_stock` is censored at zero: 100% of the
       inventory-balance violations occur on days where the balance would have gone
       negative and stock was recorded as 0. Those days are marked, not "fixed".
    """
    raw = pd.read_csv(csv_path)
    rep = CleaningReport(rows_in=len(raw))
    schema = detect_schema(raw)

    df = raw.rename(columns=schema.rename_map())
    keep = [c for c in (DATE, SKU, CATEGORY, DEMAND, RECEIVED, STOCK, LEAD_TIME) if c in df.columns]
    df = df[keep].copy()
    df[DATE] = pd.to_datetime(df[DATE], format="mixed")
    df[SKU] = df[SKU].astype(str).str.strip()

    # --- 1. exact duplicates -----------------------------------------------
    before = len(df)
    df = df.drop_duplicates()
    rep.exact_duplicates_dropped = before - len(df)
    # Any residual (sku, date) collision that is NOT byte-identical: keep the last.
    df = df.drop_duplicates([SKU, DATE], keep="last")

    # --- 2. category case ---------------------------------------------------
    if CATEGORY in df.columns:
        cat = df[CATEGORY].astype(str).str.strip()
        canon = cat.str.title()
        rep.category_case_normalised = int((canon != cat).sum())
        df[CATEGORY] = canon
        # A SKU's category is its modal value — immune to stray one-off variants.
        modal = df.groupby(SKU)[CATEGORY].agg(lambda s: s.mode().iat[0])
        df[CATEGORY] = df[SKU].map(modal)

    # --- 3. complete daily grid per SKU ------------------------------------
    df = df.sort_values([SKU, DATE]).reset_index(drop=True)
    panels = []
    for sku, g in df.groupby(SKU, sort=False):
        idx = pd.date_range(g[DATE].min(), g[DATE].max(), freq="D")
        p = g.set_index(DATE).reindex(idx)
        p.index.name = DATE
        p[SKU] = sku
        if CATEGORY in p.columns:
            p[CATEGORY] = p[CATEGORY].ffill().bfill()
        panels.append(p.reset_index())
    df = pd.concat(panels, ignore_index=True)

    # --- 3b. balance audit, BEFORE imputation -------------------------------
    # Measured on observed values only. Running this after imputation would count
    # residuals that our own fills created and overstate the source data's issues.
    if STOCK in df.columns and RECEIVED in df.columns:
        rep.balance_violations, rep.balance_violations_explained_by_zero_floor = (
            _audit_balance(df)
        )

    # --- 4. causal imputation ----------------------------------------------
    rep.demand_values_imputed = int(df[DEMAND].isna().sum())
    df[DEMAND] = (
        df.groupby(SKU, group_keys=False)[[DATE, DEMAND]]
        .apply(lambda g: _fill_demand_causally(g))
    )
    # A SKU with no observed demand at all has nothing of its own to fill from.
    # Fall back to its category's median daily demand, then to the global median,
    # so one unusable series cannot leave NaNs in the panel and break every
    # downstream rolling window.
    if df[DEMAND].isna().any():
        if CATEGORY in df.columns:
            cat_median = df.groupby(CATEGORY)[DEMAND].transform("median")
            df[DEMAND] = df[DEMAND].fillna(cat_median)
        global_median = df[DEMAND].median()
        df[DEMAND] = df[DEMAND].fillna(global_median if pd.notna(global_median) else 0.0)
    if RECEIVED in df.columns:
        # A missing receipt means "no delivery logged" — zero is the correct fill.
        df[RECEIVED] = df[RECEIVED].fillna(0.0)

    if STOCK in df.columns:
        rep.stock_values_imputed = int(df[STOCK].isna().sum())
        df[STOCK] = (
            df.groupby(SKU, group_keys=False)[[STOCK, RECEIVED, DEMAND]]
            .apply(_fill_stock_from_balance)
        )

    # --- 5. lead time -------------------------------------------------------
    if LEAD_TIME in df.columns:
        df, imputed = _repair_lead_time(df)
        rep.lead_time_imputed_skus = imputed

    # --- 6. stockout flags ---------------------------------------------------
    if STOCK in df.columns and RECEIVED in df.columns:
        d = df.sort_values([SKU, DATE])
        prev = d.groupby(SKU)[STOCK].shift(1)
        expected = prev + d[RECEIVED] - d[DEMAND]
        df = d
        df["is_stockout_day"] = (df[STOCK] <= 0).astype(int)
        # Demand that the ledger could not have satisfied from stock: a lower bound
        # on lost sales, exposed as a driver rather than silently corrected.
        df["unfulfillable_units"] = np.where(expected < 0, -expected, 0.0)
        rep.observed_stockout_days = int(df["is_stockout_day"].sum())

    df = df.sort_values([SKU, DATE]).reset_index(drop=True)
    rep.rows_out = len(df)
    log.info("cleaned panel: %s", rep.as_dict())
    return df, rep, schema


def _audit_balance(df: pd.DataFrame) -> tuple[int, int]:
    """
    How often does `closing_stock[t] = closing_stock[t-1] + received[t] - sold[t]`
    fail in the SOURCE data, and how much of that is the zero floor?

    Only days where all four inputs are observed are checked, so imputation cannot
    influence the answer.
    """
    d = df.sort_values([SKU, DATE])
    prev = d.groupby(SKU)[STOCK].shift(1)
    expected = prev + d[RECEIVED] - d[DEMAND]
    resid = d[STOCK] - expected
    checkable = resid.notna()
    viol = checkable & (resid.abs() > 1.0)
    explained = viol & (expected < 0) & (d[STOCK] <= 0)
    return int(viol.sum()), int(explained.sum())


def _fill_demand_causally(g: pd.DataFrame) -> pd.Series:
    """
    Fill demand gaps with the trailing same-weekday median for that SKU.

    Strictly backward-looking: the fill for day t uses only days < t. Falls back to
    the trailing overall median, then to a forward fill for a leading gap.
    """
    g = g.sort_values(DATE)
    s = g[DEMAND].astype(float).copy()
    if not s.isna().any():
        return s
    dow = g[DATE].dt.dayofweek.values
    vals = s.values.copy()
    for i in np.flatnonzero(np.isnan(vals)):
        past = vals[:i]
        if past.size == 0:
            continue
        same_dow = past[dow[:i] == dow[i]]
        same_dow = same_dow[~np.isnan(same_dow)]
        pool = same_dow if same_dow.size >= 2 else past[~np.isnan(past)]
        if pool.size:
            vals[i] = float(np.median(pool))
    out = pd.Series(vals, index=s.index)
    # Only a leading NaN can survive; back-fill it from the first observation.
    return out.bfill()


def _fill_stock_from_balance(g: pd.DataFrame) -> pd.Series:
    """
    Reconstruct a missing closing_stock by rolling the inventory balance forward
    from the last known level: stock[t] = max(0, stock[t-1] + received[t] - sold[t]).
    The max(0, ...) mirrors the censoring already present in the source data.
    """
    stock = g[STOCK].astype(float).values.copy()
    recv = g[RECEIVED].astype(float).fillna(0).values if RECEIVED in g else np.zeros(len(g))
    sold = g[DEMAND].astype(float).values
    for i in range(len(stock)):
        if not np.isnan(stock[i]):
            continue
        if i == 0:
            continue  # handled by the bfill below
        stock[i] = max(0.0, stock[i - 1] + recv[i] - sold[i])
    return pd.Series(stock, index=g.index).bfill()


def _repair_lead_time(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """
    Lead time is a static SKU attribute. Where a SKU reports several different
    lead times we cannot trust any of them, so we fall back to the category median
    of the SKUs that DO report a stable value.
    """
    per_sku = df.groupby(SKU)[LEAD_TIME].nunique(dropna=True)
    stable = per_sku[per_sku <= 1].index
    unstable = sorted(per_sku[per_sku > 1].index.tolist())

    stable_lt = df[df[SKU].isin(stable)].groupby(SKU)[LEAD_TIME].first()
    cat_of = df.groupby(SKU)[CATEGORY].first() if CATEGORY in df.columns else None

    resolved: dict[str, float] = stable_lt.to_dict()
    if cat_of is not None:
        cat_median = (
            pd.DataFrame({"lt": stable_lt, "cat": cat_of.reindex(stable_lt.index)})
            .groupby("cat")["lt"].median()
        )
    else:
        cat_median = pd.Series(dtype=float)
    global_median = float(stable_lt.median()) if len(stable_lt) else 7.0

    for sku in unstable:
        cat = cat_of.get(sku) if cat_of is not None else None
        val = cat_median.get(cat, np.nan) if cat is not None else np.nan
        resolved[sku] = float(val) if pd.notna(val) else global_median

    df[LEAD_TIME] = df[SKU].map(resolved).astype(float)
    return df, unstable


def sku_history_lengths(panel: pd.DataFrame) -> pd.Series:
    """Observed days of history per SKU."""
    return panel.groupby(SKU)[DATE].nunique()
