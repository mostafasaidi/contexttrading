"""Analysis routes: single-module and full-stack engine runs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from contexttrading.analysis.pipeline import MODULE_ORDER, run_full_stack, run_module
from contexttrading.api.auth import require_api_key
from contexttrading.api.deps import build_engine_config, build_series, settings_of
from contexttrading.api.models import AnalysisRequest, FullAnalysisResponse
from contexttrading.core.errors import NotFoundError

router = APIRouter(
    prefix="/v1/analysis",
    tags=["analysis"],
    dependencies=[Depends(require_api_key)],
)

_DEFAULT_MTF = ("1h", "4h")


@router.post("/full")
def run_full(request: Request, body: AnalysisRequest) -> FullAnalysisResponse:
    """Run every engine module over the posted candles (fixed module order)."""
    settings = settings_of(request)
    series = build_series(body.series, settings)
    config = build_engine_config(settings, body.config_overrides)
    results = run_full_stack(
        series, config, mtf_timeframes=tuple(body.mtf_timeframes or _DEFAULT_MTF)
    )
    return FullAnalysisResponse(
        results={module: results[module].model_dump(mode="json") for module in MODULE_ORDER}
    )


@router.post("/{module}")
def run_single(request: Request, module: str, body: AnalysisRequest):
    """Run one engine module over the posted candles."""
    settings = settings_of(request)
    series = build_series(body.series, settings)
    config = build_engine_config(settings, body.config_overrides)
    try:
        result = run_module(
            module,
            series,
            config,
            mtf_timeframes=tuple(body.mtf_timeframes or _DEFAULT_MTF),
        )
    except KeyError as exc:
        raise NotFoundError(
            f"Unknown analysis module {module!r}",
            context={"module": module},
        ) from exc
    return result
