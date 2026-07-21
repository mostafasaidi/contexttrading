"""Stored-result retrieval routes (ResultStore)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from contexttrading.api.auth import require_api_key
from contexttrading.api.models import StoredResultResponse
from contexttrading.core.errors import NotFoundError

router = APIRouter(
    prefix="/v1/results",
    tags=["results"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/{symbol}/{timeframe}/{module}")
def get_result(
    request: Request,
    symbol: str,
    timeframe: str,
    module: str,
    series_hash: str = Query(min_length=8, max_length=64),
) -> StoredResultResponse:
    """Fetch a persisted result by its full store key (404 when absent).

    Schema-version compatibility is enforced by the store
    (``SchemaVersionError`` -> 422 envelope on incompatible rows).
    """
    store = request.app.state.store
    result = store.load(symbol, timeframe, module, series_hash)
    if result is None:
        raise NotFoundError(
            "No stored result for this key",
            context={
                "symbol": symbol,
                "timeframe": timeframe,
                "module": module,
                "series_hash": series_hash,
            },
        )
    return StoredResultResponse(
        symbol=symbol,
        timeframe=timeframe,
        module=module,
        series_hash=series_hash,
        result=result.model_dump(mode="json"),
    )
