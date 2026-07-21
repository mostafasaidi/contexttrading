"""Order block domain models: order blocks, breaker blocks, mitigation blocks.

All three block kinds share one lifecycle (chronological first-touch scan,
shared :class:`MitigationStatus` enum):

- ``UNMITIGATED`` — untouched/valid: price never entered the zone.
- ``PARTIALLY_MITIGATED`` — price traded into the zone (max penetration tracked).
- ``MITIGATED`` — price traded through the mitigation threshold (far boundary
  for unrefined zones; halfway through the refined zone when ``is_refined``).
- ``VIOLATED`` — a candle *closed* through the far side (consumed/invalid;
  wick-through is NOT a violation). Terminal.

``is_valid`` is literally ``status is UNMITIGATED`` (unmitigated & unviolated).
``is_consumed`` means MITIGATED and price subsequently closed back outside the
zone on the origin side (sticky once set).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import AwareDatetime, Field, model_validator

from contexttrading.core.constants import BlockOrigin, MitigationStatus, TrendDirection
from contexttrading.core.versioning import SCHEMA_VERSION_ORDERBLOCK
from contexttrading.models.base import AnalysisObject, VersionedModel
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

_BULL = "#22ab94"
_BEAR = "#f23645"
_BREAKER = "#9c27b0"
_MITIGATION = "#ff9800"
_CONSUMED = "#787b86"


def block_style(
    kind: str,
    direction: TrendDirection,
    status: MitigationStatus,
) -> VisualStyle:
    """Default zone style for blocks.

    Order blocks are teal/rose boxes, breaker blocks purple, mitigation
    blocks amber; filled zones fade; violated zones render gray and dotted.
    """
    color = {
        "ob": _BULL if direction is TrendDirection.BULLISH else _BEAR,
        "brk": _BREAKER,
        "mb": _MITIGATION,
    }[kind]
    opacity = 0.20
    line_style = LineStyle.SOLID
    if status is MitigationStatus.MITIGATED:
        opacity = 0.08
    if status is MitigationStatus.VIOLATED:
        color = _CONSUMED
        opacity = 0.10
        line_style = LineStyle.DOTTED
    name = {"ob": "order block", "brk": "breaker", "mb": "mitigation block"}[kind]
    return VisualStyle(
        color=color,
        opacity=opacity,
        line_style=line_style,
        render_type=RenderType.BOX,
        fill=True,
        priority=7,
        layer=f"orderblocks.{kind}",
        tooltip=f"{direction.value} {name} ({status.value})",
    )


class BlockBase(AnalysisObject):
    """Shared geometry + lifecycle for all block kinds."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_ORDERBLOCK

    # -- identity & geometry -------------------------------------------------
    direction: TrendDirection = Field(description="BULLISH (demand) or BEARISH (supply).")
    zone_bottom: float = Field(gt=0, description="Lower zone boundary.")
    zone_top: float = Field(gt=0, description="Upper zone boundary.")
    candle_index: int = Field(ge=0, description="Index of the anchor candle.")
    formed_at: AwareDatetime = Field(description="Anchor candle timestamp (UTC).")
    actionable_from_index: int = Field(
        ge=0, description="Lifecycle scan starts at this candle index."
    )

    # -- lifecycle -------------------------------------------------------------
    status: MitigationStatus = Field(default=MitigationStatus.UNMITIGATED)
    first_touch_index: int | None = Field(default=None, ge=0)
    mitigation_index: int | None = Field(
        default=None, ge=0, description="Candle that traded through the mitigation threshold."
    )
    violation_index: int | None = Field(
        default=None, ge=0, description="Candle that closed through the far side."
    )
    max_penetration_fraction: float = Field(default=0.0, ge=0, le=1)
    touches: int = Field(default=0, ge=0)
    age: int = Field(
        ge=0, description="Candles from actionable_from to mitigation/violation or series end."
    )
    is_consumed: bool = Field(
        default=False, description="Mitigated and price departed the zone (sticky)."
    )
    is_valid: bool = Field(
        default=True, description="Literal: status is UNMITIGATED (unmitigated & unviolated)."
    )

    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(
            color=_BULL, opacity=0.2, render_type=RenderType.BOX, fill=True, layer="orderblocks.ob"
        )
    )

    @model_validator(mode="after")
    def _check_geometry(self) -> BlockBase:
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"zone_top ({self.zone_top}) must be > zone_bottom ({self.zone_bottom})"
            )
        if self.status is MitigationStatus.UNMITIGATED and self.first_touch_index is not None:
            raise ValueError("UNMITIGATED block cannot have first_touch_index")
        return self


class OrderBlock(BlockBase):
    """The last opposite-close candle (cluster) before a displacement BOS."""

    ID_PREFIX: ClassVar[str] = "ob"

    body_bottom: float = Field(gt=0, description="Lower body boundary of the OB candle.")
    body_top: float = Field(gt=0, description="Upper body boundary of the OB candle.")
    cluster_start_index: int = Field(
        ge=0, description="First candle of the same-sign cluster (== candle_index if single)."
    )
    is_refined: bool = Field(default=False)
    refined_bottom: float | None = Field(
        default=None, description="Refined zone lower bound (extreme wick fraction)."
    )
    refined_top: float | None = Field(default=None, description="Refined zone upper bound.")
    origin: BlockOrigin = Field(description="CONTINUATION (BOS with trend) or REVERSAL (at CHoCH).")
    linked_break_id: str = Field(min_length=1, description="StructureBreak that produced the OB.")
    displacement_margin_atr: float | None = Field(
        default=None, description="margin_atr of the linked break."
    )
    volume_zscore: float | None = Field(
        default=None, description="Volume z-score of the OB candle (None when undefined)."
    )
    overlapping_fvg_ids: list[str] = Field(
        default_factory=list, description="FVGs whose zone intersects this OB zone."
    )

    @model_validator(mode="after")
    def _check_refinement(self) -> OrderBlock:
        if self.is_refined and (self.refined_bottom is None or self.refined_top is None):
            raise ValueError("is_refined requires refined zone bounds")
        if self.is_refined:
            assert self.refined_bottom is not None and self.refined_top is not None
            inside = self.zone_bottom <= self.refined_bottom < self.refined_top <= self.zone_top
            if not inside:
                raise ValueError("refined zone must lie strictly inside the zone")
        return self


class BreakerBlock(BlockBase):
    """A violated order block whose role flipped after a confirming break."""

    ID_PREFIX: ClassVar[str] = "brk"

    source_order_block_id: str = Field(min_length=1)
    flip_index: int = Field(ge=0, description="Candle that closed through the source OB.")
    confirming_break_id: str = Field(
        min_length=1, description="Counter-direction break confirming the role flip."
    )


class MitigationBlock(BlockBase):
    """Origin candle of a failed leg that swept liquidity without a BOS."""

    ID_PREFIX: ClassVar[str] = "mb"

    linked_sweep_id: str = Field(min_length=1, description="LiquiditySweep of the failed move.")
    failed_swing_id: str = Field(
        min_length=1, description="Swing backing the swept pool that was never broken."
    )


class OrderBlockResult(VersionedModel):
    """Payload of the order block module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_ORDERBLOCK

    order_blocks: list[OrderBlock] = Field(default_factory=list)
    breaker_blocks: list[BreakerBlock] = Field(default_factory=list)
    mitigation_blocks: list[MitigationBlock] = Field(default_factory=list)
    total_count: int = Field(ge=0)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    counts_by_direction: dict[str, int] = Field(default_factory=dict)
