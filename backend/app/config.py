"""Central configuration. Everything tunable lives here or in the environment."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR / ".env", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- app ---------------------------------------------------------------
    app_name: str = "FMN Supply Chain Risk Monitor API"
    app_version: str = "1.0.0"
    log_level: str = "INFO"

    # --- data / artifacts --------------------------------------------------
    # Overridable so Render can point at a bundled copy.
    data_csv: Path = ROOT_DIR / "data" / "project1_supply_chain_demand.csv"
    artifact_dir: Path = ROOT_DIR / "models" / "supply_chain"
    reports_dir: Path = BACKEND_DIR / "reports"

    # --- CORS --------------------------------------------------------------
    # Comma-separated list of allowed origins. Localhost is always permitted so
    # local dev works without configuration; production adds FRONTEND_URL.
    frontend_url: str = ""

    # --- LLM ---------------------------------------------------------------
    anthropic_api_key: str = ""
    model_name: str = "claude-sonnet-5"
    llm_timeout_seconds: float = 30.0
    llm_max_tokens: int = 700
    llm_max_retries: int = 1
    llm_cache_size: int = 256

    # --- forecasting / risk ------------------------------------------------
    # Forecast horizon in days. Must cover the longest lead time in the data
    # (14 days) plus a review cycle, so lead-time demand is always in-horizon.
    forecast_horizon_days: int = 28
    # Service level used for the safety-stock buffer (z ≈ 1.645 at 95%).
    service_level_z: float = 1.645
    # A SKU with fewer than this many observed days is treated as cold-start.
    # Derived from the data (largest natural break in history length), see
    # backend/reports/data_profile.md §3.
    cold_start_max_days: int = 30
    # Review period: how often the planner is assumed to re-order.
    review_period_days: int = 7

    @property
    def allowed_origins(self) -> list[str]:
        origins = [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
        for raw in self.frontend_url.split(","):
            url = raw.strip().rstrip("/")
            if url and url not in origins:
                origins.append(url)
        return origins

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
