"""
FastAPI application entrypoint.

Artifacts are loaded once during startup, so the first request is already warm and
no request path ever trains a model or re-reads the CSV.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import dashboard, meta, qa, skus
from app.config import get_settings
from app.schemas.models import HealthResponse
from app.services import data_service
from app.services.llm_client import get_llm

settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        data_service.ensure_ready()
    except Exception as exc:  # keep /health serving so the failure is diagnosable
        log.exception("startup failed to load artifacts: %s", exc)
    get_llm()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Forecast-driven stockout and overstock risk for SKU-level inventory, with "
        "runtime LLM explanations grounded in computed evidence."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Explicit origins, never "*": localhost for development plus whatever
    # FRONTEND_URL names in production.
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",  # Vercel preview deployments
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(dashboard.router, prefix="/api")
app.include_router(skus.router, prefix="/api")
app.include_router(qa.router, prefix="/api")
app.include_router(meta.router, prefix="/api")


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    ready = data_service.is_ready()
    return HealthResponse(
        status="ok" if ready else "degraded",
        version=settings.app_version,
        artifacts_loaded=ready,
        llm_configured=get_llm().available,
        as_of=data_service.get_service().as_of if ready else None,
    )


@app.get("/", include_in_schema=False)
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    """A request that arrives before artifacts are loaded gets a clear 503."""
    if "not initialised" in str(exc):
        log.error("request to %s before artifacts were ready", request.url.path)
        return JSONResponse(
            status_code=503,
            content={"detail": "Service is still starting up. Please retry shortly."},
        )
    log.exception("unhandled runtime error on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
