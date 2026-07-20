"""Premium/discount domain models: the dealing range."""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field, model_validator

from contexttrading.core.constants import PriceLocation, TrendDirection
from contexttrading.core.versioning import SCHEMA_VERSION_RANGE
from contexttrading.models.base import VersionedModel
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

_PREMIUM = "#f23645"
_DISCOUNT = "#22ab94"
_EQ = "#787b86"
_OTE = "#ff9800"


def _zone_style(color: str, layer: str, tooltip: str) -> VisualStyle:
    return VisualStyle(
        color=color,
        opacity=0.15,
        render_type=RenderType.BOX,
        fill=True,
        priority=2,
        layer=layer,
        tooltip=tooltip,
    )


class DealingRange(VersionedModel):
    """The active dealing range with equilibrium, OTE, and price location.

    For a BULLISH range the dealing range spans the last external swing low
    → swing high of the active leg; OTE is the ``ote_fib_lower..ote_fib_upper``
    retracement *below* the high (buy zone in discount). For BEARISH it is
    mirrored above the low (sell zone in premium).
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_RANGE

    high: float = Field(gt=0, description="Range upper bound (external swing high).")
    low: float = Field(gt=0, description="Range lower bound (external swing low).")
    high_swing_id: str = Field(min_length=1)
    low_swing_id: str = Field(min_length=1)
    direction: TrendDirection = Field(description="Trend the range serves (BULLISH or BEARISH).")
    equilibrium: float = Field(gt=0, description="50% of the range.")
    ote_low: float = Field(gt=0, description="OTE zone lower price bound.")
    ote_high: float = Field(gt=0, description="OTE zone upper price bound.")
    ote_fibs: tuple[float, float] = Field(description="Fib retracements used for the OTE zone.")
    reference_price: float = Field(gt=0, description="Price being located (last close).")
    price_location: PriceLocation = Field(description="PREMIUM / DISCOUNT / EQUILIBRIUM.")
    premium_style: VisualStyle = Field(
        default_factory=lambda: _zone_style(_PREMIUM, "range.premium", "premium zone")
    )
    discount_style: VisualStyle = Field(
        default_factory=lambda: _zone_style(_DISCOUNT, "range.discount", "discount zone")
    )
    equilibrium_style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(
            color=_EQ,
            line_style=LineStyle.DASHED,
            render_type=RenderType.LINE,
            priority=3,
            layer="range.equilibrium",
            tooltip="equilibrium (50%)",
        )
    )
    ote_style: VisualStyle = Field(
        default_factory=lambda: _zone_style(_OTE, "range.ote", "optimal trade entry")
    )

    @model_validator(mode="after")
    def _check_geometry(self) -> DealingRange:
        if self.high <= self.low:
            raise ValueError(f"high ({self.high}) must be > low ({self.low})")
        if not (self.low <= self.ote_low <= self.ote_high <= self.high):
            raise ValueError(
                f"OTE zone [{self.ote_low}, {self.ote_high}] must lie inside "
                f"[{self.low}, {self.high}]"
            )
        if not (self.low < self.equilibrium < self.high):
            raise ValueError("equilibrium must lie strictly inside the range")
        return self


class DealingRangeResult(VersionedModel):
    """Payload of the premium/discount module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_RANGE

    dealing_range: DealingRange | None = Field(
        default=None,
        description="None when no valid external swing pair exists yet.",
    )
