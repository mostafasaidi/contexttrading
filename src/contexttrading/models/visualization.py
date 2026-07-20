"""Visualization style models.

`VisualStyle` captures everything a renderer (Plotly today, TradingView
Lightweight Charts later) needs to draw one analysis object — colors,
opacity, line style, render primitive, tooltip, and stacking order. Engine
modules attach styles to their outputs so the visualization layer never
invents presentation or recomputes data.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import ClassVar

from pydantic import Field, field_validator

from contexttrading.core.versioning import SCHEMA_VERSION_VISUAL_STYLE
from contexttrading.models.base import VersionedModel

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


class LineStyle(StrEnum):
    """Stroke styles understood by both Plotly and Lightweight Charts."""

    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"


class RenderType(StrEnum):
    """Render primitives an analysis object can map to."""

    LINE = "line"
    AREA = "area"
    BOX = "box"
    MARKER = "marker"
    LABEL = "label"
    HISTOGRAM = "histogram"
    CANDLES = "candles"


class VisualStyle(VersionedModel, frozen=True):
    """Renderer-agnostic drawing style for one analysis object."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_VISUAL_STYLE

    color: str = Field(description="Primary color as '#rgb', '#rrggbb', or '#rrggbbaa'.")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Fill/line opacity.")
    line_style: LineStyle = Field(default=LineStyle.SOLID)
    line_width: float = Field(default=1.0, gt=0, description="Stroke width in pixels.")
    render_type: RenderType = Field(default=RenderType.BOX)
    tooltip: str | None = Field(default=None, description="Hover text (renderer-formatted).")
    priority: int = Field(default=0, description="Z-order/selection priority (higher wins).")
    layer: str = Field(default="default", description="Named layer for grouping/toggling.")
    visible: bool = Field(default=True)
    fill: bool = Field(default=False, description="Fill the shape (boxes/areas).")

    @field_validator("color")
    @classmethod
    def _validate_color(cls, value: str) -> str:
        if not _HEX_COLOR_RE.match(value):
            raise ValueError(f"color must be '#rgb', '#rrggbb', or '#rrggbbaa', got {value!r}")
        return value.lower()
