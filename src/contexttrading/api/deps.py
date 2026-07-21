"""Shared route helpers: series building, engine-config merging, analyst DI."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from pydantic import ValidationError as PydanticValidationError

from contexttrading.api.models import CandlesInput
from contexttrading.core.config import EngineConfig, Settings
from contexttrading.core.errors import (
    ConfigurationError,
    RequestTooLargeError,
    ValidationError,
)
from contexttrading.models.candle import CandleSeries


def settings_of(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def build_series(candles: CandlesInput, settings: Settings) -> CandleSeries:
    """Validate size cap, then build the CandleSeries."""
    if len(candles.candles) > settings.api.max_candles_per_request:
        raise RequestTooLargeError(
            "Candle count exceeds the configured request cap",
            context={
                "received": len(candles.candles),
                "max": settings.api.max_candles_per_request,
            },
        )
    return candles.to_series()


def build_engine_config(settings: Settings, overrides: dict[str, Any]) -> EngineConfig:
    """Merge validated EngineConfig overrides over the service defaults."""
    if not overrides:
        return settings.engine
    try:
        return EngineConfig.model_validate({**settings.engine.model_dump(), **overrides})
    except PydanticValidationError as exc:
        raise ValidationError(
            "Invalid engine config overrides",
            context={"error": str(exc)[:500]},
        ) from exc


def analyst_of(request: Request):
    """The configured InstitutionalAnalyst (None when provider is 'none')."""
    analyst = request.app.state.analyst
    if analyst is None:
        raise ConfigurationError(
            "AI provider is not configured on this service",
            context={"hint": "set CT_AI__PROVIDER=mock|openai|anthropic"},
        )
    return analyst
