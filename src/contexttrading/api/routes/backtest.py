"""Backtest route: candles + strategy name -> deterministic BacktestResult."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError as PydanticValidationError

from contexttrading.api.auth import require_api_key
from contexttrading.api.deps import build_engine_config, build_series, settings_of
from contexttrading.api.models import BacktestRequest
from contexttrading.backtesting.replay import Strategy, run_backtest
from contexttrading.backtesting.strategies import SMCPullbackParams, SMCPullbackStrategy
from contexttrading.core.config import BacktestConfig
from contexttrading.core.errors import ValidationError
from contexttrading.models.backtest import BacktestResult

#: Registered strategies: name -> factory(strategy_params) -> Strategy.
STRATEGIES: dict[str, Callable[[dict[str, Any]], Strategy]] = {
    "smc_pullback": lambda params: SMCPullbackStrategy(SMCPullbackParams(**params)),
}

router = APIRouter(
    prefix="/v1/backtest",
    tags=["backtest"],
    dependencies=[Depends(require_api_key)],
)


@router.post("")
def backtest(request: Request, body: BacktestRequest) -> BacktestResult:
    """Replay a registered strategy over posted candles (no lookahead)."""
    settings = settings_of(request)
    factory = STRATEGIES.get(body.strategy)
    if factory is None:
        raise ValidationError(
            "Unknown backtest strategy",
            context={"strategy": body.strategy, "available": sorted(STRATEGIES)},
        )
    series = build_series(body.series, settings)
    engine_config = build_engine_config(settings, body.engine_overrides)
    try:
        backtest_config = BacktestConfig.model_validate(
            {**settings.backtest.model_dump(), **body.backtest_overrides}
        )
    except PydanticValidationError as exc:
        raise ValidationError(
            "Invalid backtest config overrides",
            context={"error": str(exc)[:500]},
        ) from exc
    return run_backtest(
        series,
        factory(body.strategy_params),
        engine_config,
        backtest_config,
        mtf_timeframes=body.mtf_timeframes,
    )
