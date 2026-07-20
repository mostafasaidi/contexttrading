"""Output envelope models — the universal module return contract.

Every engine module returns ``AnalysisResult[T]`` where ``T`` is a
:class:`~contexttrading.models.base.VersionedModel` payload. No module
returns free text or raw dicts. See ``docs/architecture/data-flow.md``.
"""

from __future__ import annotations

from typing import ClassVar, Generic, TypeVar

from pydantic import AwareDatetime, Field, model_validator

from contexttrading import __version__ as _ENGINE_VERSION
from contexttrading.core.constants import Timeframe
from contexttrading.core.versioning import SCHEMA_VERSION_ENVELOPE
from contexttrading.models.base import VersionedModel

PayloadT = TypeVar("PayloadT", bound=VersionedModel)


class DataWindow(VersionedModel, frozen=True):
    """The exact input-data window an analysis was generated from.

    Timestamps always derive from candle data (never wall-clock) per the
    determinism contract.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_ENVELOPE

    start: AwareDatetime = Field(description="First input candle timestamp (UTC).")
    end: AwareDatetime = Field(description="Last input candle timestamp (UTC).")
    candle_count: int = Field(ge=0, description="Number of input candles.")

    @model_validator(mode="after")
    def _check_order(self) -> DataWindow:
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) must be >= start ({self.start})")
        return self


class AnalysisResult(VersionedModel, Generic[PayloadT]):
    """Envelope wrapping every module's payload.

    Consumers must check both ``schema_version`` (envelope/payload contract)
    and ``engine_version`` (computation semantics) before interpreting the
    payload.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_ENVELOPE

    module: str = Field(min_length=1, description="Producing module, e.g. 'fvg'.")
    symbol: str = Field(min_length=1, description="Instrument symbol.")
    timeframe: Timeframe = Field(description="Analysis timeframe.")
    engine_version: str = Field(
        default=_ENGINE_VERSION, description="contexttrading version that produced this."
    )
    generated_from: DataWindow = Field(description="Exact input data window.")
    payload: PayloadT = Field(description="Module-specific versioned payload.")
    run_id: str | None = Field(
        default=None,
        description="Optional run-scoped bookkeeping ID (metadata only; not part of "
        "analytical equality).",
    )

    def summary(self) -> dict[str, str]:
        """Compact identity of this result for logs and listings."""
        return {
            "module": self.module,
            "symbol": self.symbol,
            "timeframe": str(self.timeframe),
            "engine_version": self.engine_version,
            "schema_version": self.schema_version,
            "payload_type": type(self.payload).__name__,
        }
