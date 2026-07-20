"""Liquidity domain models: equal levels, pools, sweeps."""

from __future__ import annotations

from typing import ClassVar

from pydantic import AwareDatetime, Field

from contexttrading.core.constants import (
    LiquidityPoolKind,
    LiquiditySide,
    PoolStatus,
    SweepClassification,
    SwingClass,
)
from contexttrading.core.versioning import SCHEMA_VERSION_LIQUIDITY
from contexttrading.models.base import AnalysisObject, VersionedModel
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

_EQUAL = "#9c27b0"
_BUYSIDE = "#2962ff"
_SELLSIDE = "#ab47bc"
_SWEPT = "#787b86"
_SWEEP_MARK = "#ff9800"


def equal_level_style(side: LiquiditySide) -> VisualStyle:
    """Default style for an equal-highs/lows level line."""
    return VisualStyle(
        color=_EQUAL,
        line_style=LineStyle.DASHED,
        render_type=RenderType.LINE,
        priority=15,
        layer="liquidity.equal_levels",
        tooltip=f"equal {'highs' if side is LiquiditySide.BUYSIDE else 'lows'}",
    )


def pool_style(side: LiquiditySide, status: PoolStatus) -> VisualStyle:
    """Default style for a liquidity pool line."""
    color = _BUYSIDE if side is LiquiditySide.BUYSIDE else _SELLSIDE
    if status is not PoolStatus.UNTAPPED:
        color = _SWEPT
    return VisualStyle(
        color=color,
        line_style=LineStyle.SOLID if status is PoolStatus.UNTAPPED else LineStyle.DOTTED,
        render_type=RenderType.LINE,
        priority=12,
        layer="liquidity.pools",
        tooltip=f"{side.value} liquidity ({status.value})",
    )


def sweep_style(classification: SweepClassification) -> VisualStyle:
    """Default marker style for a sweep event."""
    return VisualStyle(
        color=_SWEEP_MARK,
        render_type=RenderType.MARKER,
        priority=25,
        layer="liquidity.sweeps",
        tooltip=classification.value.replace("_", " "),
    )


class EqualLevel(AnalysisObject):
    """Two or more swings at (nearly) the same price."""

    ID_PREFIX: ClassVar[str] = "eqlevel"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_LIQUIDITY

    price: float = Field(gt=0, description="Mean price of the member swings.")
    side: LiquiditySide = Field(description="BUYSIDE for equal highs, SELLSIDE for equal lows.")
    member_swing_ids: list[str] = Field(min_length=2, description="Swing IDs forming the level.")
    count: int = Field(ge=2, description="Number of member swings.")
    tolerance: float = Field(ge=0, description="ATR-fraction tolerance actually used (price).")
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_EQUAL, render_type=RenderType.LINE)
    )


class LiquidityPool(AnalysisObject):
    """Resting liquidity above highs / below lows."""

    ID_PREFIX: ClassVar[str] = "pool"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_LIQUIDITY

    price: float = Field(gt=0, description="Level where liquidity rests.")
    side: LiquiditySide
    kind: LiquidityPoolKind = Field(description="Formation creating the pool.")
    pool_class: SwingClass = Field(description="INTERNAL or EXTERNAL liquidity.")
    source_ids: list[str] = Field(
        min_length=1, description="Swing/equal-level IDs backing this pool."
    )
    formed_at_index: int = Field(ge=0, description="Candle index where the pool became known.")
    status: PoolStatus = Field(default=PoolStatus.UNTAPPED)
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_BUYSIDE, render_type=RenderType.LINE)
    )


class LiquiditySweep(AnalysisObject):
    """A stop-run event against a liquidity pool."""

    ID_PREFIX: ClassVar[str] = "sweep"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_LIQUIDITY

    pool_id: str = Field(min_length=1, description="ID of the swept pool.")
    pool_price: float = Field(gt=0)
    side: LiquiditySide
    candle_index: int = Field(ge=0, description="Index of the sweeping candle.")
    timestamp: AwareDatetime = Field(description="Sweeping candle timestamp (UTC).")
    wick_extreme: float = Field(gt=0, description="Deepest wick price beyond the pool.")
    penetration_atr: float | None = Field(
        default=None, description="Wick penetration beyond the pool, in ATRs."
    )
    close_back_inside: bool = Field(description="True when the candle closed back inside.")
    classification: SweepClassification
    linked_break_id: str | None = Field(
        default=None, description="False structure break linked to a STOP_HUNT, if any."
    )
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_SWEEP_MARK, render_type=RenderType.MARKER)
    )


class LiquidityResult(VersionedModel):
    """Payload of the liquidity module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_LIQUIDITY

    equal_levels: list[EqualLevel] = Field(default_factory=list)
    pools: list[LiquidityPool] = Field(default_factory=list)
    sweeps: list[LiquiditySweep] = Field(default_factory=list)
