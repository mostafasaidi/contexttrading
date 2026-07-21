"""Streaming analysis route: progressive NDJSON over the full stack.

Protocol: newline-delimited JSON (NDJSON), one object per line, in the
FIXED module order (``analysis.pipeline.MODULE_ORDER``):

    {"module": "structure", "result": {...AnalysisResult...}}\n
    ...
    {"module": "done", "modules": [...], "candle_count": N}\n

NDJSON (not SSE) because consumers are programmatic pipeline clients, not
browsers; concatenating the ``result`` lines yields the same data as
``POST /v1/analysis/full``. Deterministic: same request -> same bytes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from contexttrading.analysis.pipeline import MODULE_ORDER, run_module
from contexttrading.api.auth import require_api_key
from contexttrading.api.deps import build_engine_config, build_series, settings_of
from contexttrading.api.models import AnalysisRequest

router = APIRouter(
    prefix="/v1/stream",
    tags=["stream"],
    dependencies=[Depends(require_api_key)],
)

_MEDIA_TYPE = "application/x-ndjson"


@router.post("/analysis")
def stream_analysis(request: Request, body: AnalysisRequest) -> StreamingResponse:
    """Stream per-module results as each engine completes (NDJSON)."""
    settings = settings_of(request)
    series = build_series(body.series, settings)
    config = build_engine_config(settings, body.config_overrides)
    mtf_timeframes = tuple(body.mtf_timeframes or ("1h", "4h"))

    def lines() -> Iterator[bytes]:
        for module in MODULE_ORDER:
            result = run_module(module, series, config, mtf_timeframes=mtf_timeframes)
            line = {"module": module, "result": result.model_dump(mode="json")}
            yield (json.dumps(line, sort_keys=True) + "\n").encode("utf-8")
        done = {"module": "done", "modules": list(MODULE_ORDER), "candle_count": len(series)}
        yield (json.dumps(done, sort_keys=True) + "\n").encode("utf-8")

    return StreamingResponse(lines(), media_type=_MEDIA_TYPE)
