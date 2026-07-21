"""Versioned request/response models for the REST API (Phase 10 roadmap).

Every wire model is a :class:`VersionedModel` registered in
``core.versioning`` and exported via ``schemas.export`` — the OpenAPI
document is derived from these, never hand-written.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from contexttrading.core.versioning import SCHEMA_VERSION_API
from contexttrading.models.ai import TradeSetup
from contexttrading.models.base import VersionedModel
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult


class CandlesInput(VersionedModel):
    """Posted candle series (CandleSeries-compatible records)."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1, description="Timeframe code, e.g. '15m'.")
    timezone_name: str = Field(default="UTC", description="Original feed timezone label.")
    candles: list[dict[str, Any]] = Field(
        min_length=1, description="OHLCV records: timestamp/open/high/low/close/volume."
    )

    def to_series(self) -> CandleSeries:
        """Build the validated CandleSeries (raises DataError on bad records)."""
        return CandleSeries.from_records(
            self.candles,
            symbol=self.symbol,
            timeframe=self.timeframe,
            timezone_name=self.timezone_name,
        )


class AnalysisRequest(VersionedModel):
    """Single-module or full-stack analysis request."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    series: CandlesInput
    config_overrides: dict[str, Any] = Field(
        default_factory=dict,
        description="Subset of EngineConfig fields; unknown keys are rejected (422).",
    )
    mtf_timeframes: list[str] | None = Field(
        default=None, description="HTF ladder for mtf/full-stack runs (default ['1h', '4h'])."
    )


class FullAnalysisResponse(VersionedModel):
    """Full-stack response: module name -> versioned AnalysisResult JSON."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    results: dict[str, Any]


class ChartRequest(VersionedModel):
    """Chart payload request."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    series: CandlesInput
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    theme: Literal["dark", "light"] | None = None
    hidden_layers: list[str] = Field(default_factory=list)
    shown_layers: list[str] = Field(default_factory=list)
    persist: bool = Field(default=False, description="Store the payload in the ResultStore.")


class ChartResponse(VersionedModel):
    """Chart payload + optional store key."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    chart: AnalysisResult
    series_hash: str | None = Field(
        default=None, description="Store key component when persist=true."
    )


class BacktestRequest(VersionedModel):
    """Backtest request: candles + strategy + config overrides."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    series: CandlesInput
    strategy: str = Field(
        default="smc_pullback", description="Registered strategy name (see routes/backtest)."
    )
    engine_overrides: dict[str, Any] = Field(default_factory=dict)
    backtest_overrides: dict[str, Any] = Field(default_factory=dict)
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    mtf_timeframes: list[str] = Field(default_factory=lambda: ["1h", "4h"])


class TradeEvaluationRequest(VersionedModel):
    """AI trade-evaluation request."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    series: CandlesInput
    setup: TradeSetup
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class JournalReviewRequest(VersionedModel):
    """AI journal-review request."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    trades: list[dict[str, Any]] = Field(min_length=1)
    period: str = ""


class WeeklyReviewRequest(VersionedModel):
    """AI weekly/monthly performance-review request."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    statistics: dict[str, Any] = Field(min_length=1)
    period: str = Field(min_length=1)
    trades: list[dict[str, Any]] | None = None


class StoredResultResponse(VersionedModel):
    """A persisted result with its full store key."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    symbol: str
    timeframe: str
    module: str
    series_hash: str
    result: dict[str, Any]


class ErrorDetail(VersionedModel):
    """Structured error payload inside :class:`ErrorEnvelope`."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    code: str = Field(description="CT-xxxx taxonomy code.")
    message: str
    context: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorEnvelope(VersionedModel):
    """The consistent error body returned by every failure path."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_API

    error: ErrorDetail
