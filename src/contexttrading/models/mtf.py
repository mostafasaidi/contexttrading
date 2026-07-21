"""Multi-timeframe context models: per-timeframe trend snapshots and bias.

These are computed *summaries*, not detected objects, so they subclass
:class:`VersionedModel` (no content-hash IDs, no render styles).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from contexttrading.core.constants import Timeframe, TrendDirection, TrendStrength
from contexttrading.core.versioning import SCHEMA_VERSION_MTF
from contexttrading.models.base import VersionedModel
from contexttrading.models.range import DealingRange
from contexttrading.models.structure import TrendState


class TimeframeContext(VersionedModel):
    """Structure/trend snapshot of one timeframe in an MTF pass."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_MTF

    timeframe: Timeframe = Field(description="Timeframe of the (resampled) series.")
    trend: TrendState | None = Field(
        default=None,
        description="Trend state, or None when the resampled series is below "
        "``min_candles`` (direction is UNKNOWN then).",
    )
    direction: TrendDirection = Field(description="Trend direction (UNKNOWN when no trend).")
    dealing_range: DealingRange | None = Field(
        default=None, description="Active dealing range on this timeframe, if any."
    )
    weight: float = Field(
        gt=0, description="Aggregation weight: ``mtf_tf_weight_base ** rank`` (rank 0 = base)."
    )
    candle_count: int = Field(ge=0, description="Candles in the (resampled) series.")


class MTFBias(VersionedModel):
    """Aggregated multi-timeframe bias.

    Strength rule (deterministic):
        - STRONG: every context with a known trend agrees with the bias
          (and at least two contexts exist);
        - MODERATE: weighted agreement share >= ``mtf_moderate_share``;
        - WEAK: otherwise.

    ``htf_influence`` is the weighted share of higher-timeframe contexts
    whose direction opposes the base-timeframe trend (0 when they all agree).
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_MTF

    direction: TrendDirection = Field(description="Weighted-majority direction.")
    strength: TrendStrength = Field(description="STRONG / MODERATE / WEAK per the rule above.")
    agreement_share: float = Field(
        ge=0, le=1, description="Weighted share of contexts aligned with the bias."
    )
    htf_influence: float = Field(
        ge=0, le=1, description="Weighted share of HTF contexts opposing the base-TF trend."
    )
    recommended_execution_timeframe: Timeframe | None = Field(
        default=None,
        description="Lowest timeframe aligned with the bias; None when the base "
        "timeframe conflicts with it.",
    )
    conflict_notes: list[str] = Field(
        default_factory=list,
        description="Deterministic notes for adjacent timeframe pairs that disagree.",
    )


class MTFResult(VersionedModel):
    """Payload of the MTF module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_MTF

    base_timeframe: Timeframe = Field(description="Timeframe of the input series (rank 0).")
    contexts: list[TimeframeContext] = Field(
        default_factory=list, description="Base timeframe first, then ascending HTFs."
    )
    bias: MTFBias
