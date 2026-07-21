"""Chart payload serializer: candles + analysis results -> render contract.

``build_chart_payload`` is a pure function of ``(series, results, config)``:
same inputs, byte-identical output. It never recomputes analysis — every
primitive comes from the mappers, which copy ``VisualStyle`` presets from
the detected objects. The payload is the *only* thing a renderer needs:
OHLCV candles, named layers of typed primitives, a theme, and a legend.

Deterministic rules:

- Time is UNIX **seconds** (UTC) everywhere (Lightweight Charts
  ``UTCTimestamp``); milliseconds never appear.
- Layers are emitted in canonical ``LAYER_SPECS`` order (rank = z-order
  base); a primitive's ``z_order`` is ``rank * 100 + priority``.
- Primitives inside a layer are sorted by ``(z_order, source_id)`` so the
  serialized JSON is stable.
- Volume bars are colored by candle direction using the theme colors.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from contexttrading.core.config import VisualizationConfig
from contexttrading.core.constants import Timeframe
from contexttrading.core.versioning import SCHEMA_VERSION_VISUALIZATION
from contexttrading.models.base import VersionedModel
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.visualization import mappers
from contexttrading.visualization.primitives import RenderPrimitive, to_unix_seconds


class ChartCandle(VersionedModel, frozen=True):
    """One OHLC candle in Lightweight Charts format (time in seconds)."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_VISUALIZATION

    time: int = Field(ge=0, description="Candle open time, UNIX seconds (UTC).")
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)


class VolumeBar(VersionedModel, frozen=True):
    """One volume bar, colored by candle direction via the theme."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_VISUALIZATION

    time: int = Field(ge=0, description="Candle open time, UNIX seconds (UTC).")
    value: float = Field(ge=0)
    color: str = Field(description="Theme up/down color by candle direction.")


class LayerPayload(VersionedModel):
    """A named, toggleable layer of sorted render primitives."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_VISUALIZATION

    name: str = Field(min_length=1)
    visible: bool = Field(default=True)
    z_order: int = Field(ge=0, description="Layer rank (stacking base).")
    primitives: list[RenderPrimitive] = Field(default_factory=list)


class ChartTheme(VersionedModel, frozen=True):
    """Renderer color palette."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_VISUALIZATION

    name: Literal["dark", "light"]
    background: str
    text_color: str
    grid_color: str
    up_color: str = Field(description="Bullish candles / rising volume.")
    down_color: str = Field(description="Bearish candles / falling volume.")


class ChartPayload(VersionedModel):
    """Everything a renderer needs: candles, volume, layers, theme, legend."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_VISUALIZATION

    symbol: str = Field(min_length=1)
    timeframe: Timeframe
    candles: list[ChartCandle] = Field(default_factory=list)
    volume: list[VolumeBar] = Field(default_factory=list)
    layers: list[LayerPayload] = Field(default_factory=list)
    theme: ChartTheme
    legend: dict[str, str] = Field(
        default_factory=dict,
        description="Human-readable label per layer name (fixed strings).",
    )


#: Built-in palettes (hex colors, Lightweight Charts compatible).
THEMES: dict[str, ChartTheme] = {
    "dark": ChartTheme(
        name="dark",
        background="#131722",
        text_color="#d1d4dc",
        grid_color="#1e222d",
        up_color="#22ab94",
        down_color="#f23645",
    ),
    "light": ChartTheme(
        name="light",
        background="#ffffff",
        text_color="#131722",
        grid_color="#f0f3fa",
        up_color="#22ab94",
        down_color="#f23645",
    ),
}

#: Canonical layer order. Rank is the z-order base (primitive z_order =
#: rank * 100 + priority). Back layers paint first (background zones),
#: front layers last (swing markers, structure lines). Layers flagged
#: ``default_hidden`` ship visible=False unless ``shown_layers`` overrides.
#: Order: (name, label, default_hidden).
LAYER_SPECS: tuple[tuple[str, str, bool], ...] = (
    ("sessions.boxes", "Sessions", False),
    ("sessions.killzones", "Killzones", False),
    ("range.premium", "Premium zone", False),
    ("range.discount", "Discount zone", False),
    ("range.ote", "OTE zone", False),
    ("range.equilibrium", "Equilibrium (50%)", False),
    ("confluence.zones", "Confluence zones", False),
    ("fvg.zones", "Fair value gaps", False),
    ("orderblocks.ob", "Order blocks", False),
    ("orderblocks.brk", "Breaker blocks", False),
    ("orderblocks.mb", "Mitigation blocks", False),
    ("supplydemand.supply", "Supply zones", False),
    ("supplydemand.demand", "Demand zones", False),
    ("liquidity.equal_levels", "Equal highs/lows", False),
    ("liquidity.pools", "Liquidity pools", False),
    ("liquidity.sweeps", "Liquidity sweeps", False),
    ("sessions.levels", "Session levels", False),
    ("sessions.sweeps", "Session sweeps / Judas", False),
    ("mtf.levels", "HTF levels", False),
    ("swings.external", "External swings", False),
    ("swings.internal", "Internal swings", True),
    ("structure.breaks", "Structure breaks (BOS/CHoCH)", False),
    ("structure.protected", "Protected high/low", False),
)

#: Result-key -> mapper, in fixed dispatch order. "trend" has no geometry
#: of its own (its direction already colors other objects) and is skipped.
_MAPPERS = (
    ("structure", mappers.map_structure),
    ("liquidity", mappers.map_liquidity),
    ("premium_discount", mappers.map_range),
    ("fvg", mappers.map_fvg),
    ("orderblocks", mappers.map_orderblocks),
    ("supplydemand", mappers.map_supplydemand),
    ("sessions", mappers.map_sessions),
    ("confluence", mappers.map_confluence),
    ("mtf", mappers.map_mtf),
)


def build_chart_payload(
    series: CandleSeries,
    results: dict[str, AnalysisResult],  # type: ignore[type-arg]
    config: VisualizationConfig | None = None,
) -> AnalysisResult[ChartPayload]:
    """Serialize candles + analysis results into a renderer-ready payload.

    Args:
        series: Input candles (same window the results were computed from).
        results: ``AnalysisResult`` envelopes keyed by module name; unknown
            or geometry-less modules (``trend``) are ignored.
        config: Theme and layer visibility overrides (defaults when None).

    Returns:
        Envelope with module ``"chart"`` and a :class:`ChartPayload`.
    """
    config = config or VisualizationConfig()
    theme = THEMES[config.theme]

    candles = [
        ChartCandle(
            time=to_unix_seconds(c.timestamp),
            open=c.open,
            high=c.high,
            low=c.low,
            close=c.close,
        )
        for c in series.candles
    ]
    volume = [
        VolumeBar(
            time=to_unix_seconds(c.timestamp),
            value=c.volume,
            color=theme.up_color if c.close >= c.open else theme.down_color,
        )
        for c in series.candles
    ]

    by_layer: dict[str, list[RenderPrimitive]] = {}
    for key, mapper in _MAPPERS:
        result = results.get(key)
        if result is None:
            continue
        for primitive in mapper(result.payload, series):
            by_layer.setdefault(primitive.layer, []).append(primitive)

    hidden = set(config.hidden_layers)
    shown = set(config.shown_layers)
    layers: list[LayerPayload] = []
    for rank, (name, _label, default_hidden) in enumerate(LAYER_SPECS):
        primitives = by_layer.get(name, [])
        for primitive in primitives:
            primitive.z_order = rank * 100 + primitive.priority
        primitives.sort(key=lambda p: (p.z_order, p.source_id))
        visible = name in shown or (not default_hidden and name not in hidden)
        layers.append(
            LayerPayload(
                name=name,
                visible=visible,
                z_order=rank,
                primitives=primitives,
            )
        )

    payload = ChartPayload(
        symbol=series.symbol,
        timeframe=series.timeframe,
        candles=candles,
        volume=volume,
        layers=layers,
        theme=theme,
        legend={name: label for name, label, _ in LAYER_SPECS},
    )
    return AnalysisResult[ChartPayload](
        module="chart",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
