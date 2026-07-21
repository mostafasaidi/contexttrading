"""Chart-agnostic render primitives.

Every detected object becomes one or more typed primitives carrying
coordinates, colors, layer, priority, and a *structured* tooltip (key/value
pairs derived from the source object — never free text). Each primitive
maps 1:1 onto a TradingView Lightweight Charts API surface:

- ``PriceLine`` → ``ISeriesApi.createPriceLine(...)``
- ``Marker`` → ``ISeriesApi.setMarkers(...)`` entries
- ``Box`` / ``AreaBand`` → rectangle shading; LW Charts v4 has no native
  rectangle primitive, so the reference frontend draws them on an overlay
  canvas (v5 could use ``attachPrimitive`` instead — see
  ``docs/modules/visualization.md``)
- ``Segment`` → two-point trend line (overlay canvas in the reference
  frontend; v5 plugin primitives)
- ``Label`` → anchored text (overlay canvas)

Time is UNIX **seconds** (UTC) — Lightweight Charts' ``UTCTimestamp``.
Millisecond values never appear in a payload (guarded by tests).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, ClassVar, Literal

from pydantic import Field

from contexttrading.core.versioning import SCHEMA_VERSION_VISUALIZATION
from contexttrading.models.base import VersionedModel
from contexttrading.models.visualization import LineStyle


def to_unix_seconds(ts: datetime) -> int:
    """UTC candle timestamp -> UNIX seconds (Lightweight Charts time)."""
    return int(ts.timestamp())


class PrimitiveBase(VersionedModel):
    """Shared identity/presentation fields of every render primitive."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_VISUALIZATION

    source_id: str = Field(min_length=1, description="ID of the backing AnalysisObject.")
    layer: str = Field(min_length=1, description="Named layer (grouping/toggling).")
    priority: int = Field(default=0, description="In-layer stacking priority.")
    z_order: int = Field(
        default=0, description="Global stacking order: layer_rank * 100 + priority."
    )
    tooltip: dict[str, str] = Field(
        default_factory=dict,
        description="Structured key/value pairs from the source object (deterministic).",
    )
    color: str = Field(description="Copied from the source object's VisualStyle.")


class PriceLine(PrimitiveBase):
    """Horizontal line at a price level (levels, pools, equilibrium)."""

    primitive: Literal["price_line"] = "price_line"
    price: float = Field(gt=0)
    line_style: LineStyle = Field(default=LineStyle.SOLID)
    line_width: float = Field(default=1.0, gt=0)
    title: str = Field(default="", description="Short line title (LW Charts price line).")


class Box(PrimitiveBase):
    """Price/time rectangle (zones: FVG, OB, SD, confluence, range bands)."""

    primitive: Literal["box"] = "box"
    start_time: int = Field(ge=0, description="Left edge, UNIX seconds.")
    end_time: int = Field(ge=0, description="Right edge, UNIX seconds.")
    bottom: float = Field(gt=0)
    top: float = Field(gt=0)
    opacity: float = Field(default=0.2, ge=0, le=1)
    line_style: LineStyle = Field(default=LineStyle.SOLID)
    fill: bool = Field(default=True)


class Marker(PrimitiveBase):
    """Point marker at a candle (swings, sweeps, Judas events)."""

    primitive: Literal["marker"] = "marker"
    time: int = Field(ge=0, description="Candle time, UNIX seconds.")
    price: float = Field(gt=0, description="Anchor price (swing/extreme).")
    position: Literal["aboveBar", "belowBar"]
    shape: Literal["arrowUp", "arrowDown", "circle", "diamond", "square"]
    text: str = Field(default="", description="Short marker text.")


class Label(PrimitiveBase):
    """Anchored text at a time/price point."""

    primitive: Literal["label"] = "label"
    time: int = Field(ge=0)
    price: float = Field(gt=0)
    text: str = Field(min_length=1)


class Segment(PrimitiveBase):
    """Two-point line segment (structure breaks, trend lines)."""

    primitive: Literal["segment"] = "segment"
    start_time: int = Field(ge=0)
    start_price: float = Field(gt=0)
    end_time: int = Field(ge=0)
    end_price: float = Field(gt=0)
    line_style: LineStyle = Field(default=LineStyle.SOLID)
    line_width: float = Field(default=1.0, gt=0)


class AreaBand(PrimitiveBase):
    """Full-height time-range shading (sessions, killzones)."""

    primitive: Literal["area_band"] = "area_band"
    start_time: int = Field(ge=0)
    end_time: int = Field(ge=0)
    opacity: float = Field(default=0.1, ge=0, le=1)


#: Discriminated union of all render primitives.
RenderPrimitive = Annotated[
    PriceLine | Box | Marker | Label | Segment | AreaBand,
    Field(discriminator="primitive"),
]
