"""Visualization: analysis results -> render-ready chart payloads.

Pure translation layer. Mappers convert detected objects into typed
primitives (copying their ``VisualStyle`` presets); the serializer packs
candles, volume, layered primitives, theme, and legend into a single
:class:`ChartPayload` that a renderer (e.g. TradingView Lightweight
Charts) consumes without any further computation.
"""

from contexttrading.visualization.primitives import (
    AreaBand,
    Box,
    Label,
    Marker,
    PriceLine,
    PrimitiveBase,
    RenderPrimitive,
    Segment,
    to_unix_seconds,
)
from contexttrading.visualization.serializer import (
    LAYER_SPECS,
    THEMES,
    ChartCandle,
    ChartPayload,
    ChartTheme,
    LayerPayload,
    VolumeBar,
    build_chart_payload,
)

__all__ = [
    "LAYER_SPECS",
    "THEMES",
    "AreaBand",
    "Box",
    "ChartCandle",
    "ChartPayload",
    "ChartTheme",
    "Label",
    "LayerPayload",
    "Marker",
    "PriceLine",
    "PrimitiveBase",
    "RenderPrimitive",
    "Segment",
    "VolumeBar",
    "build_chart_payload",
    "to_unix_seconds",
]
