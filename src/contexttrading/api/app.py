"""FastAPI application factory for the ContextTrading service.

``create_app(settings)`` wires DI (settings, ResultStore, analyst),
request-id middleware, the CT-error -> JSON-envelope mapping, health
endpoints, and all versioned routers. Run with::

    uvicorn contexttrading.api.app:create_app --factory --host 0.0.0.0

Error mapping (all failures return ``ErrorEnvelope`` JSON):

- ``RequestValidationError`` / core ``ValidationError`` (CT-2xxx) -> 422
- ``DataError`` (CT-1xxx) -> 400
- ``InsufficientDataError`` (CT-3001) -> 422 (client-supplied data problem)
- other ``AnalysisError`` (CT-3xxx) -> 500
- ``ConfigurationError`` (CT-4xxx) -> 500
- ``AIProviderError`` (CT-5xxx) -> 502 (504 when the failure was a timeout)
- ``AuthenticationError`` (CT-7001) -> 401
- ``RequestTooLargeError`` (CT-7002) -> 413
- ``NotFoundError`` (CT-7003) -> 404
- anything else -> 500 (CT-0000)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from contexttrading import __version__
from contexttrading.ai.analysts import InstitutionalAnalyst
from contexttrading.ai.providers import provider_from_config
from contexttrading.api.models import ErrorDetail, ErrorEnvelope
from contexttrading.core.config import Settings
from contexttrading.core.errors import (
    AIProviderError,
    AnalysisError,
    AuthenticationError,
    ConfigurationError,
    ContextTradingError,
    DataError,
    InsufficientDataError,
    NotFoundError,
    RequestTooLargeError,
    ValidationError,
)
from contexttrading.data.postgres import PostgresResultStore
from contexttrading.data.store import ResultStore

_TAGS = [
    {"name": "analysis", "description": "Engine modules, single or full stack."},
    {"name": "charts", "description": "Renderer-ready chart payloads."},
    {"name": "ai", "description": "Evidence-bound AI analyst reports."},
    {"name": "results", "description": "Persisted result retrieval."},
    {"name": "stream", "description": "Progressive NDJSON analysis stream."},
    {"name": "backtest", "description": "Deterministic no-lookahead backtesting."},
    {"name": "meta", "description": "Health and readiness."},
]


def _status_for(exc: ContextTradingError) -> int:
    if isinstance(exc, (AuthenticationError,)):
        return 401
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, RequestTooLargeError):
        return 413
    if isinstance(exc, InsufficientDataError):
        return 422
    if isinstance(exc, AnalysisError):
        return 500
    if isinstance(exc, DataError):
        return 400
    if isinstance(exc, ValidationError):
        return 422
    if isinstance(exc, ConfigurationError):
        return 500
    if isinstance(exc, AIProviderError):
        return 504 if "timeout" in str(exc).lower() else 502
    return 500


def _build_store(settings: Settings) -> ResultStore | PostgresResultStore:
    """Select the result-store backend from ``settings.storage``."""
    backend = settings.storage.backend
    if backend == "sqlite":
        return ResultStore(settings.storage.url.removeprefix("sqlite:///"))
    if backend == "postgresql":
        return PostgresResultStore(settings.storage.url)
    raise ConfigurationError(
        f"Unsupported storage backend {backend!r} for the result store",
        context={"backend": backend},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ContextTrading FastAPI application."""
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.store = _build_store(settings)
        app.state.analyst = (
            None
            if settings.ai.provider == "none"
            else InstitutionalAnalyst(provider_from_config(settings.ai), settings.ai)
        )
        yield
        app.state.store.close()

    app = FastAPI(
        title="ContextTrading",
        version=__version__,
        description=(
            "Deterministic SMC analysis engine, chart payloads, and the "
            "evidence-bound AI analyst. Every response is versioned JSON; "
            "every error is an ErrorEnvelope with a CT-xxxx code."
        ),
        openapi_tags=_TAGS,
        lifespan=lifespan,
    )
    if settings.api.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(ContextTradingError)
    async def ct_error_handler(request: Request, exc: ContextTradingError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        body = ErrorEnvelope(
            error=ErrorDetail(
                code=exc.code,
                message=exc.message,
                context=exc.context,
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=_status_for(exc), content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        body = ErrorEnvelope(
            error=ErrorDetail(
                code="CT-2000",
                message="Request failed schema validation",
                context={"errors": exc.errors()[:10]},
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump(mode="json"))

    @app.exception_handler(Exception)
    async def fallback_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", uuid.uuid4().hex)
        body = ErrorEnvelope(
            error=ErrorDetail(
                code="CT-0000",
                message="Unexpected internal error",
                context={"type": type(exc).__name__},
                request_id=request_id,
            )
        )
        return JSONResponse(status_code=500, content=body.model_dump(mode="json"))

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", tags=["meta"])
    def readyz(request: Request) -> dict[str, Any]:
        request.app.state.store.ping()  # raises -> 500 envelope when not ready
        return {
            "status": "ready",
            "version": __version__,
            "ai_provider": request.app.state.settings.ai.provider,
            "auth_enabled": request.app.state.settings.api.auth_enabled
            and not request.app.state.settings.api.allow_anonymous,
        }

    from contexttrading.api.routes import ai, analysis, backtest, charts, results, stream

    error_responses: dict[int | str, Any] = {
        status: {"model": ErrorEnvelope, "description": description}
        for status, description in (
            (400, "Malformed data (CT-1xxx)"),
            (401, "Missing or invalid API key (CT-7001)"),
            (404, "Unknown module or stored result (CT-1000/CT-7003)"),
            (413, "Request exceeds the candle cap (CT-7002)"),
            (422, "Validation or insufficient data (CT-2xxx/CT-3001)"),
            (500, "Engine, configuration, or unexpected failure"),
            (502, "AI provider failure (CT-5xxx)"),
            (504, "AI provider timeout (CT-5xxx)"),
        )
    }
    for module in (analysis, charts, ai, results, stream, backtest):
        app.include_router(module.router, responses=error_responses)
    return app
