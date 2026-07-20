"""Market-structure domain models: swings, legs, breaks, trend state.

Every detected object carries a :class:`VisualStyle` so the visualization
layer (Phase 8) renders without recomputing anything. Default styles are
deterministic functions of the object's semantic content.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import AwareDatetime, Field

from contexttrading.core.constants import (
    BreakStrength,
    LegKind,
    MarketPhase,
    StructureBreakClass,
    StructureBreakSignificance,
    StructureBreakType,
    SwingClass,
    SwingType,
    TrendDirection,
    TrendStrength,
)
from contexttrading.core.versioning import SCHEMA_VERSION_STRUCTURE
from contexttrading.models.base import AnalysisObject, VersionedModel
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

# ---------------------------------------------------------------------------
# Default styles (deterministic presets)
# ---------------------------------------------------------------------------

_BULL = "#22ab94"
_BEAR = "#f23645"
_NEUTRAL = "#787b86"
_CHOCH = "#ff9800"


def swing_style(swing_type: SwingType, swing_class: SwingClass) -> VisualStyle:
    """Default marker style for a swing point."""
    external = swing_class is SwingClass.EXTERNAL
    color = (_BULL if swing_type is SwingType.LOW else _BEAR) if external else _NEUTRAL
    return VisualStyle(
        color=color,
        render_type=RenderType.MARKER,
        priority=10 if external else 5,
        layer=f"swings.{swing_class.value}",
        tooltip=f"{swing_class.value} swing {swing_type.value}",
    )


def break_style(
    break_type: StructureBreakType,
    direction: TrendDirection,
    strength: BreakStrength,
) -> VisualStyle:
    """Default line style for a structure break."""
    if strength is BreakStrength.FALSE:
        color, line_style = _NEUTRAL, LineStyle.DOTTED
    elif break_type is StructureBreakType.CHOCH:
        color, line_style = _CHOCH, LineStyle.DASHED
    else:
        color = _BULL if direction is TrendDirection.BULLISH else _BEAR
        line_style = LineStyle.SOLID if strength is BreakStrength.STRONG else LineStyle.DASHED
    return VisualStyle(
        color=color,
        line_style=line_style,
        line_width=2.0 if strength is BreakStrength.STRONG else 1.0,
        render_type=RenderType.LINE,
        priority=20,
        layer="structure.breaks",
        tooltip=f"{break_type.value} {direction.value} ({strength.value})",
    )


# ---------------------------------------------------------------------------
# Swings & legs
# ---------------------------------------------------------------------------


class SwingPoint(AnalysisObject):
    """A fractal swing high/low.

    Identity hashes every field except ``id``/``label`` — identical
    detections (same index, price, class) get identical IDs across runs.
    """

    ID_PREFIX: ClassVar[str] = "swing"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_STRUCTURE

    index: int = Field(ge=0, description="Candle index of the swing bar.")
    timestamp: AwareDatetime = Field(description="Swing bar timestamp (UTC).")
    price: float = Field(gt=0, description="High (swing high) or low (swing low) price.")
    swing_type: SwingType
    swing_class: SwingClass = Field(description="Internal (noise) vs external (leg-level).")
    lookback: int = Field(ge=1, description="Neighbor bars required each side.")
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_NEUTRAL, render_type=RenderType.MARKER),
        description="Render style; engines set it via swing_style().",
    )


class Leg(AnalysisObject):
    """A directional leg between two consecutive external swings."""

    ID_PREFIX: ClassVar[str] = "leg"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_STRUCTURE

    start_index: int = Field(ge=0)
    end_index: int = Field(ge=0)
    start_price: float = Field(gt=0)
    end_price: float = Field(gt=0)
    direction: TrendDirection = Field(description="BULLISH or BEARISH (never RANGING here).")
    kind: LegKind = Field(description="IMPULSE if a new same-side extreme was made.")
    magnitude: float = Field(gt=0, description="Absolute price distance.")
    atr_multiple: float | None = Field(
        default=None, description="Magnitude in ATRs at the leg end (None if ATR unavailable)."
    )
    duration: int = Field(ge=1, description="Length in candles.")
    retracement_ratio: float | None = Field(
        default=None,
        ge=0,
        description="This leg's magnitude as a fraction of the previous leg's (None for leg 0).",
    )


# ---------------------------------------------------------------------------
# Structure breaks
# ---------------------------------------------------------------------------


class StructureBreak(AnalysisObject):
    """A BOS/CHoCH event (or a false, wick-only attempt)."""

    ID_PREFIX: ClassVar[str] = "break"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_STRUCTURE

    broken_swing_id: str = Field(min_length=1, description="ID of the swing that was breached.")
    broken_swing_price: float = Field(gt=0, description="Price level that was breached.")
    broken_swing_class: SwingClass = Field(description="Class of the breached swing.")
    break_index: int = Field(ge=0, description="Candle index of the breaking bar.")
    break_timestamp: AwareDatetime = Field(description="Breaking bar timestamp (UTC).")
    break_price: float = Field(
        gt=0, description="Confirmation price: close for confirmed breaks, wick extreme for FALSE."
    )
    direction: TrendDirection = Field(
        description="Direction of the break (BULLISH up / BEARISH down)."
    )
    break_type: StructureBreakType = Field(description="BOS (with trend) or CHoCH (against trend).")
    break_class: StructureBreakClass = Field(description="INTERNAL or EXTERNAL swing breached.")
    significance: StructureBreakSignificance = Field(
        description="MAJOR for external breaks, MINOR for internal."
    )
    strength: BreakStrength = Field(description="STRONG / WEAK / FALSE classification.")
    margin_atr: float | None = Field(
        default=None, description="Close margin beyond the level, in ATRs (None for FALSE)."
    )
    is_sweep_candidate: bool = Field(
        default=False, description="True for FALSE breaks — liquidity sweep candidates."
    )
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_NEUTRAL, render_type=RenderType.LINE),
        description="Render style; engines set it via break_style().",
    )


# ---------------------------------------------------------------------------
# Trend state & results
# ---------------------------------------------------------------------------


class TrendState(VersionedModel):
    """Composite trend assessment produced by the TrendEngine."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_STRUCTURE

    direction: TrendDirection = Field(description="Active external trend.")
    external_trend: TrendDirection = Field(description="Trend from external swing sequence.")
    internal_trend: TrendDirection = Field(description="Trend from internal swing sequence.")
    strength: TrendStrength = Field(description="From leg statistics and BOS follow-through.")
    market_phase: MarketPhase = Field(description="Wyckoff-style phase from range/overlap.")
    impulse_correction_ratio: float | None = Field(
        default=None, description="Mean impulse magnitude / mean correction magnitude (ATRs)."
    )
    bos_follow_through: float | None = Field(
        default=None, ge=0, le=1, description="Fraction of confirmed BOS that were STRONG."
    )
    confidence_basis: list[str] = Field(
        default_factory=list,
        description="Deterministic evidence tags, e.g. 'hh_hl_sequence', 'strong_bos:3/4'.",
    )


class MarketStructureResult(VersionedModel):
    """Payload of the structure module: swings, breaks, legs, protection."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_STRUCTURE

    swings: list[SwingPoint] = Field(default_factory=list)
    breaks: list[StructureBreak] = Field(default_factory=list)
    legs: list[Leg] = Field(default_factory=list)
    protected_high: SwingPoint | None = Field(
        default=None, description="Bearish-context protected swing high (None if none yet)."
    )
    protected_low: SwingPoint | None = Field(
        default=None, description="Bullish-context protected swing low (None if none yet)."
    )


class TrendResult(VersionedModel):
    """Payload of the trend module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_STRUCTURE

    state: TrendState
