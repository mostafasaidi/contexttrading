"""Supply & demand domain models.

Zones come from two deterministic sources:

- **OB-derived**: every order block maps to a zone (bullish OB → demand,
  bearish OB → supply) carrying ``linked_order_block_id``.
- **Pattern**: rally-base-drop (supply) / drop-base-rally (demand) — a tight
  base at an external swing followed by a strong departure leg.

Lifecycle (chronological first-touch scan):

- ``FRESH`` — never re-entered since formation.
- ``TESTED`` — re-entered but neither mitigated nor broken (visits counted).
- ``MITIGATED`` — traded through the base (wick suffices). Terminal.
- ``BROKEN`` — a candle *closed* through the base. Terminal.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import AwareDatetime, Field, model_validator

from contexttrading.core.constants import SDZoneStatus, ZoneType
from contexttrading.core.versioning import SCHEMA_VERSION_SUPPLYDEMAND
from contexttrading.models.base import AnalysisObject, VersionedModel
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

_SUPPLY = "#f23645"
_DEMAND = "#22ab94"
_DEAD = "#787b86"

_STATUS_OPACITY = {
    SDZoneStatus.FRESH: 0.20,
    SDZoneStatus.TESTED: 0.15,
    SDZoneStatus.MITIGATED: 0.08,
    SDZoneStatus.BROKEN: 0.05,
}


def sd_style(kind: ZoneType, status: SDZoneStatus) -> VisualStyle:
    """Default zone style: red-tinted supply, green-tinted demand, fading
    with lifecycle progression (broken zones go gray/dotted)."""
    color = _SUPPLY if kind is ZoneType.SUPPLY else _DEMAND
    if status in (SDZoneStatus.MITIGATED, SDZoneStatus.BROKEN):
        color = _DEAD
    return VisualStyle(
        color=color,
        opacity=_STATUS_OPACITY[status],
        line_style=LineStyle.DOTTED if status is SDZoneStatus.BROKEN else LineStyle.SOLID,
        render_type=RenderType.BOX,
        fill=True,
        priority=6,
        layer=f"supplydemand.{kind.value}",
        tooltip=f"{kind.value} zone ({status.value})",
    )


class SupplyDemandZone(AnalysisObject):
    """A supply or demand zone with lifecycle, cross-links, and strength."""

    ID_PREFIX: ClassVar[str] = "sd"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_SUPPLYDEMAND

    # -- identity & geometry -------------------------------------------------
    kind: ZoneType = Field(description="SUPPLY or DEMAND.")
    zone_bottom: float = Field(gt=0)
    zone_top: float = Field(gt=0)
    base_start_index: int = Field(ge=0, description="First base candle.")
    base_end_index: int = Field(ge=0, description="Last base candle.")
    formed_at: AwareDatetime = Field(description="Base end timestamp (UTC).")
    actionable_from_index: int = Field(
        ge=0, description="Lifecycle scan starts here (departure confirmation)."
    )

    # -- departure ------------------------------------------------------------
    departure_leg_id: str | None = Field(
        default=None, description="Impulse leg confirming departure (None for OB-derived)."
    )
    departure_atr_multiple: float | None = Field(
        default=None, description="Departure magnitude in ATRs (None during warmup)."
    )
    mean_base_body_atr: float | None = Field(
        default=None, description="Mean base-candle body in ATRs (tightness input)."
    )
    trend_aligned: bool = Field(
        default=False, description="Zone kind aligned with the external trend."
    )

    # -- lifecycle ------------------------------------------------------------
    status: SDZoneStatus = Field(default=SDZoneStatus.FRESH)
    tests: int = Field(default=0, ge=0, description="Distinct re-entries into the zone.")
    first_touch_index: int | None = Field(default=None, ge=0)
    mitigated_index: int | None = Field(
        default=None, ge=0, description="Candle that traded through the base."
    )
    broken_index: int | None = Field(
        default=None, ge=0, description="Candle that closed through the base."
    )
    age: int = Field(ge=0, description="Candles from actionable_from to resolution/series end.")

    # -- cross-links -----------------------------------------------------------
    linked_order_block_id: str | None = Field(
        default=None, description="Source order block for OB-derived zones."
    )
    is_duplicate: bool = Field(
        default=False, description="Pattern zone ~identical to an order block zone."
    )

    # -- scoring ----------------------------------------------------------------
    strength: float = Field(ge=0, le=1, description="Deterministic strength in [0, 1].")
    rank: int = Field(default=0, ge=0, description="1 = strongest within the result.")

    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(
            color=_DEMAND,
            opacity=0.2,
            render_type=RenderType.BOX,
            fill=True,
            layer="supplydemand.demand",
        )
    )

    @model_validator(mode="after")
    def _check_geometry(self) -> SupplyDemandZone:
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"zone_top ({self.zone_top}) must be > zone_bottom ({self.zone_bottom})"
            )
        if not (self.base_start_index <= self.base_end_index < self.actionable_from_index):
            raise ValueError("base indices must satisfy start <= end < actionable_from")
        if self.status is SDZoneStatus.FRESH and self.first_touch_index is not None:
            raise ValueError("FRESH zone cannot have first_touch_index")
        return self

    @model_validator(mode="after")
    def _ensure_deterministic_id(self) -> SupplyDemandZone:
        # Identity excludes presentation/derived scoring: id, label, rank,
        # strength. Everything else (detection + lifecycle) is identity.
        if not self.id:
            from contexttrading.core.ids import deterministic_id

            content = self.model_dump(mode="json", exclude={"id", "label", "rank", "strength"})
            object.__setattr__(self, "id", deterministic_id(content, prefix=self.ID_PREFIX))
        return self


class SupplyDemandResult(VersionedModel):
    """Payload of the supply/demand module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_SUPPLYDEMAND

    zones: list[SupplyDemandZone] = Field(
        default_factory=list, description="Sorted by strength desc (rank 1 first)."
    )
    total_count: int = Field(ge=0)
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    counts_by_kind: dict[str, int] = Field(default_factory=dict)
