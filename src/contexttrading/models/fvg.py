"""Fair Value Gap domain models.

An FVG is a 3-candle imbalance zone. Lifecycle states reuse the shared
:class:`MitigationStatus` enum with this mapping (documented in
``docs/modules/fvg.md``):

- ``UNMITIGATED`` — untouched: price never entered the zone.
- ``PARTIALLY_MITIGATED`` — entered (any trade into the zone) but never
  traded through the far side.
- ``MITIGATED`` — filled: traded through the far side.
- ``VIOLATED`` — inverted: a candle *closed* through the far side
  (inverse FVG; role flips support ↔ resistance).
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import AwareDatetime, Field, model_validator

from contexttrading.core.constants import MitigationStatus, TrendDirection
from contexttrading.core.versioning import SCHEMA_VERSION_FVG
from contexttrading.models.base import AnalysisObject, VersionedModel
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

_BULL = "#22ab94"
_BEAR = "#f23645"


def fvg_style(
    direction: TrendDirection,
    is_inverse: bool,
    status: MitigationStatus,
) -> VisualStyle:
    """Default zone style for an FVG.

    Bullish zones are teal, bearish zones rose; filled zones fade; inverse
    FVGs render as a darker, dotted-border variant (role flipped).
    """
    color = _BULL if direction is TrendDirection.BULLISH else _BEAR
    opacity = 0.20
    line_style = LineStyle.SOLID
    tooltip = f"{'bullish' if direction is TrendDirection.BULLISH else 'bearish'} fvg"
    if status is MitigationStatus.MITIGATED:
        opacity = 0.08
        tooltip += " (filled)"
    if is_inverse:
        opacity = max(opacity, 0.30)
        line_style = LineStyle.DOTTED
        tooltip = f"inverse {tooltip.split(' (')[0]}"
    return VisualStyle(
        color=color,
        opacity=opacity,
        line_style=line_style,
        render_type=RenderType.BOX,
        fill=True,
        priority=8,
        layer="fvg.zones",
        tooltip=tooltip,
    )


class FVG(AnalysisObject):
    """A fair value gap with classification, lifecycle, and strength."""

    ID_PREFIX: ClassVar[str] = "fvg"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_FVG

    # -- identity & geometry ---------------------------------------------------
    direction: TrendDirection = Field(description="BULLISH or BEARISH imbalance.")
    zone_bottom: float = Field(gt=0, description="Lower zone boundary.")
    zone_top: float = Field(gt=0, description="Upper zone boundary.")
    formation_start_index: int = Field(ge=0, description="Index of candle i-1.")
    middle_index: int = Field(ge=0, description="Index of the displacement candle i.")
    formation_end_index: int = Field(ge=0, description="Index of candle i+1 (confirmation).")
    formed_at: AwareDatetime = Field(description="Middle candle timestamp (UTC).")

    # -- size ------------------------------------------------------------------
    gap_size: float = Field(gt=0, description="zone_top - zone_bottom.")
    gap_atr: float | None = Field(
        default=None, description="Gap size in ATRs at the middle candle (None in warmup)."
    )
    gap_percent: float = Field(gt=0, description="Gap size as a fraction of the zone mid.")

    # -- classification ----------------------------------------------------------
    is_nested: bool = Field(default=False)
    parent_fvg_id: str | None = Field(
        default=None, description="Containing older unfilled same-direction FVG."
    )
    stack_group_id: str | None = Field(
        default=None, description="Shared ID for stacked (overlapping/adjacent) FVGs."
    )
    linked_break_id: str | None = Field(
        default=None, description="StructureBreak at the middle candle, if any."
    )
    displacement_margin_atr: float | None = Field(
        default=None, description="margin_atr of the linked structure break."
    )
    is_inverse: bool = Field(default=False)
    inversion_index: int | None = Field(
        default=None, ge=0, description="Candle index where price closed through the far side."
    )

    # -- lifecycle -----------------------------------------------------------------
    status: MitigationStatus = Field(default=MitigationStatus.UNMITIGATED)
    first_touch_index: int | None = Field(default=None, ge=0)
    filled_index: int | None = Field(default=None, ge=0)
    max_fill_fraction: float = Field(default=0.0, ge=0, le=1)
    age: int = Field(ge=0, description="Candles from formation_end to fill or series end.")
    touches: int = Field(default=0, ge=0, description="Candles that traded into the zone.")

    # -- scoring ---------------------------------------------------------------------
    strength: float = Field(ge=0, le=1, description="Deterministic strength score in [0,1].")
    rank: int = Field(default=0, ge=0, description="1 = strongest within the result.")

    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(
            color=_BULL, opacity=0.2, render_type=RenderType.BOX, fill=True, layer="fvg.zones"
        )
    )

    @model_validator(mode="after")
    def _check_geometry(self) -> FVG:
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"zone_top ({self.zone_top}) must be > zone_bottom ({self.zone_bottom})"
            )
        if not (self.formation_start_index < self.middle_index < self.formation_end_index):
            raise ValueError("formation indices must satisfy start < middle < end")
        if self.is_inverse and self.inversion_index is None:
            raise ValueError("is_inverse requires inversion_index")
        if self.status is MitigationStatus.UNMITIGATED and self.first_touch_index is not None:
            raise ValueError("UNMITIGATED FVG cannot have first_touch_index")
        return self

    @model_validator(mode="after")
    def _ensure_deterministic_id(self) -> FVG:
        # Identity excludes presentation/derived scoring: id, label, rank,
        # strength. Everything else (detection + lifecycle) is identity.
        if not self.id:
            from contexttrading.core.ids import deterministic_id

            content = self.model_dump(mode="json", exclude={"id", "label", "rank", "strength"})
            object.__setattr__(self, "id", deterministic_id(content, prefix=self.ID_PREFIX))
        return self


class FVGResult(VersionedModel):
    """Payload of the FVG module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_FVG

    fvgs: list[FVG] = Field(
        default_factory=list, description="Sorted by strength desc (rank 1 first)."
    )
    total_count: int = Field(ge=0)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    counts_by_direction: dict[str, int] = Field(default_factory=dict)
