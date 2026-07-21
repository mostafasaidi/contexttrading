"""Chart payload route, with optional persistence to the ResultStore."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from contexttrading.analysis.pipeline import run_full_stack
from contexttrading.api.auth import require_api_key
from contexttrading.api.deps import build_engine_config, build_series, settings_of
from contexttrading.api.models import ChartRequest, ChartResponse
from contexttrading.core.config import VisualizationConfig
from contexttrading.data.store import hash_series
from contexttrading.visualization import build_chart_payload

router = APIRouter(
    prefix="/v1/charts",
    tags=["charts"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/payload")
def chart_payload(request: Request, body: ChartRequest) -> ChartResponse:
    """Candles -> full-stack -> renderer-ready chart payload."""
    settings = settings_of(request)
    series = build_series(body.series, settings)
    config = build_engine_config(settings, body.config_overrides)
    results = run_full_stack(series, config)
    visualization = settings.visualization
    if body.theme is not None or body.hidden_layers or body.shown_layers:
        visualization = VisualizationConfig(
            theme=body.theme or visualization.theme,
            hidden_layers=body.hidden_layers or visualization.hidden_layers,
            shown_layers=body.shown_layers or visualization.shown_layers,
        )
    chart = build_chart_payload(series, results, visualization)
    digest: str | None = None
    if body.persist:
        digest = hash_series(series)
        request.app.state.store.save(chart, digest)
    return ChartResponse(chart=chart, series_hash=digest)
