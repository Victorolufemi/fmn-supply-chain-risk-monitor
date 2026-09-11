"""
Artifact loading and in-memory access.

The bundle produced by `app.ml.training` is read ONCE at process start and held in
memory. No request re-reads the CSV, re-fits a model or re-runs a forecast; the
API only slices precomputed frames. On this dataset that is ~250 KB resident and
sub-millisecond lookups.

If the bundle is missing (a fresh clone, or a Render build where the training step
has not run), `ensure_ready()` trains it on the spot rather than serving errors.
"""
from __future__ import annotations

import logging
import math
import subprocess
import sys
import threading
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import joblib
import numpy as np
import pandas as pd

from app.config import BACKEND_DIR, get_settings
from app.ml.training import ARTIFACT_NAME

log = logging.getLogger(__name__)
_lock = threading.Lock()


def _denan(obj):
    """Recursively replace NaN/inf with None so responses are always JSON-valid."""
    if isinstance(obj, dict):
        return {k: _denan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_denan(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if obj is not None and isinstance(obj, (np.floating, np.integer)):
        v = obj.item()
        return None if isinstance(v, float) and not math.isfinite(v) else v
    return obj


class DataService:
    """Read-only façade over the trained artifact bundle."""

    def __init__(self, bundle: dict[str, Any]) -> None:
        self._b = bundle
        self._risk: pd.DataFrame = bundle["risk"]
        self._panel: pd.DataFrame = bundle["panel"]
        self._forecast: pd.DataFrame = bundle["forecast"]
        # Round-tripping the assessments through a DataFrame turns Python `None`
        # into float NaN, which is not JSON-serialisable. Normalise once, here, so
        # no endpoint has to remember to.
        self._risk_by_sku = {
            r["sku_id"]: _denan(r) for r in self._risk.to_dict("records")
        }
        # Pre-slice per-SKU history and forecast so a detail request is a dict hit.
        self._hist_by_sku = {
            sku: g.sort_values("date") for sku, g in self._panel.groupby("sku_id")
        }
        self._fc_by_sku = {
            sku: g.sort_values("horizon") for sku, g in self._forecast.groupby("sku_id")
        }

    # --- basics -------------------------------------------------------------
    @property
    def as_of(self) -> str:
        return self._b["as_of_date"]

    @property
    def bundle(self) -> dict[str, Any]:
        return self._b

    @property
    def sku_ids(self) -> list[str]:
        return sorted(self._risk_by_sku)

    @property
    def categories(self) -> list[str]:
        return sorted(self._panel["category"].dropna().unique().tolist())

    def has_sku(self, sku_id: str) -> bool:
        return sku_id in self._risk_by_sku

    def resolve_sku(self, raw: str) -> str | None:
        """Case- and whitespace-insensitive SKU lookup, so `sku-1004` also works."""
        if raw in self._risk_by_sku:
            return raw
        key = raw.strip().upper()
        for s in self._risk_by_sku:
            if s.upper() == key:
                return s
        return None

    # --- risk ---------------------------------------------------------------
    def risk_records(self) -> list[dict]:
        return list(self._risk_by_sku.values())

    def risk(self, sku_id: str) -> dict | None:
        return self._risk_by_sku.get(sku_id)

    def risk_frame(self) -> pd.DataFrame:
        return self._risk

    # --- series -------------------------------------------------------------
    def history(self, sku_id: str, last_n: int | None = None) -> pd.DataFrame:
        h = self._hist_by_sku.get(sku_id, pd.DataFrame())
        return h.tail(last_n) if (last_n and len(h)) else h

    def forecast(self, sku_id: str, horizon: int | None = None) -> pd.DataFrame:
        f = self._fc_by_sku.get(sku_id, pd.DataFrame())
        return f[f["horizon"] <= horizon] if (horizon and len(f)) else f

    # --- ranking ------------------------------------------------------------
    RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "HEALTHY": 4}

    def ranked(self, records: list[dict] | None = None) -> list[dict]:
        """
        Order for the attention list: severity first, then the most decisive
        tiebreaker within a band — soonest projected stockout, else highest score.
        """
        recs = records if records is not None else self.risk_records()

        def key(r: dict):
            d = r.get("days_to_projected_stockout")
            return (
                self.RANK.get(r["risk_level"], 9),
                d if d is not None else 1e9,
                -float(r.get("risk_score") or 0.0),
                r["sku_id"],
            )

        return sorted(recs, key=key)


# ---------------------------------------------------------------------------
_service: DataService | None = None


def _artifact_path():
    return get_settings().artifact_dir / ARTIFACT_NAME


def _train_now() -> None:
    """Build the artifact bundle in a subprocess. Used only when it is absent."""
    log.warning("artifact bundle not found — running training once")
    subprocess.run(
        [sys.executable, "-m", "app.ml.training"],
        cwd=str(BACKEND_DIR), check=True,
    )


def ensure_ready(train_if_missing: bool = True) -> DataService:
    """Load the bundle, training it first if it does not exist. Idempotent."""
    global _service
    with _lock:
        if _service is not None:
            return _service
        path = _artifact_path()
        if not path.exists():
            if not train_if_missing:
                raise FileNotFoundError(f"artifact bundle missing: {path}")
            _train_now()
        log.info("loading artifact bundle from %s", path)
        bundle = joblib.load(path)
        _service = DataService(bundle)
        log.info("loaded %d SKUs, as_of=%s, model=%s",
                 len(_service.sku_ids), _service.as_of,
                 bundle.get("serving_model", bundle.get("selected_model")))
        return _service


def get_service() -> DataService:
    """FastAPI dependency. Raises if startup did not complete."""
    if _service is None:
        raise RuntimeError("data service not initialised")
    return _service


def is_ready() -> bool:
    return _service is not None


def reset_for_tests() -> None:
    global _service
    with _lock:
        _service = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def report_text(name: str) -> str:
    p = get_settings().reports_dir / name
    return p.read_text(encoding="utf-8") if p.exists() else ""
