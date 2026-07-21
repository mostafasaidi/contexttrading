"""Session-domain models: per-session statistics, Judas sweeps, results.

A *session instance* is one occurrence of a configured window on one
calendar date (in ``SessionConfig.default_timezone``). Windows that wrap
midnight belong to the date of their START bar. Instances are renderable
boxes, so they subclass :class:`AnalysisObject` and carry a
:class:`VisualStyle` preset.
"""

from __future__ import annotations

from datetime import date
from typing import ClassVar

from pydantic import AwareDatetime, Field

from contexttrading.core.constants import (
    LiquidityPoolKind,
    LiquiditySide,
    TrendDirection,
)
from contexttrading.core.versioning import SCHEMA_VERSION_SESSION
from contexttrading.models.base import AnalysisObject, VersionedModel
from contexttrading.models.liquidity import LiquidityPool, LiquiditySweep
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

# Deterministic per-session palette (fallback gray for custom windows).
_SESSION_COLORS: dict[str, str] = {
    "sydney": "#8d6e63",
    "tokyo": "#ff9800",
    "london": "#2962ff",
    "new_york": "#22ab94",
    "london_close": "#7b1fa2",
    "new_york_am": "#00897b",
    "new_york_pm": "#5e35b1",
    "asia": "#f23645",
}
_FALLBACK = "#787b86"
_SWEEP_MARK = "#f23645"


def session_style(name: str, is_killzone: bool = False) -> VisualStyle:
    """Default translucent box style for a session instance."""
    color = _SESSION_COLORS.get(name, _FALLBACK)
    return VisualStyle(
        color=color,
        opacity=0.08 if is_killzone else 0.12,
        line_style=LineStyle.SOLID,
        render_type=RenderType.BOX,
        fill=True,
        priority=1,
        layer="sessions.killzones" if is_killzone else "sessions.boxes",
        tooltip=f"{name.replace('_', ' ')}{' killzone' if is_killzone else ''} session",
    )


def session_level_style(side: LiquiditySide) -> VisualStyle:
    """Default style for a session high/low level line."""
    return VisualStyle(
        color="#f23645" if side is LiquiditySide.BUYSIDE else "#2962ff",
        line_style=LineStyle.DASHED,
        render_type=RenderType.LINE,
        priority=14,
        layer="sessions.levels",
        tooltip=f"session {'high' if side is LiquiditySide.BUYSIDE else 'low'}",
    )


def judas_style() -> VisualStyle:
    """Default marker style for a Judas-swing sweep."""
    return VisualStyle(
        color=_SWEEP_MARK,
        render_type=RenderType.MARKER,
        priority=26,
        layer="sessions.sweeps",
        tooltip="judas swing",
    )


class SessionStats(AnalysisObject):
    """Statistics of one session instance (window x calendar date)."""

    ID_PREFIX: ClassVar[str] = "sess"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_SESSION

    session: str = Field(min_length=1, description="Window name from SessionConfig.")
    is_killzone: bool = Field(default=False, description="True for kill-zone windows.")
    trading_date: date = Field(
        description="Calendar date (in the session timezone) of the instance's start bar."
    )
    start_time: AwareDatetime = Field(description="Timestamp of the first candle (UTC).")
    end_time: AwareDatetime = Field(description="Timestamp of the last candle (UTC).")
    open: float = Field(gt=0, description="Open of the first candle.")
    high: float = Field(gt=0, description="Highest high inside the window.")
    low: float = Field(gt=0, description="Lowest low inside the window.")
    close: float = Field(gt=0, description="Close of the last candle.")
    high_index: int = Field(ge=0, description="Candle index where the high formed.")
    low_index: int = Field(ge=0, description="Candle index where the low formed.")
    candle_count: int = Field(ge=1, description="Candles inside the window.")
    volume: float = Field(ge=0, description="Accumulated volume.")
    direction: TrendDirection = Field(
        description="BULLISH/BEARISH from close vs open; RANGING when the body is "
        "below session_doji_body_fraction of the range."
    )
    range_atr: float | None = Field(
        default=None, description="Session range in ATRs at the session end (None if unknown)."
    )
    forms_day_high: bool = Field(
        default=False, description="True when this instance printed the calendar-day high."
    )
    forms_day_low: bool = Field(
        default=False, description="True when this instance printed the calendar-day low."
    )
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_FALLBACK, render_type=RenderType.BOX)
    )


class SessionSweep(AnalysisObject):
    """A Judas-swing event: a session level swept during an opposing killzone.

    Patterns (deterministic):
        - Asian-range high/low swept during the London killzone;
        - London high/low swept during the New York killzones.
    The underlying stop-run is a normal :class:`LiquiditySweep` against a
    session-derived pool; this object adds the session semantics.
    """

    ID_PREFIX: ClassVar[str] = "ssweep"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_SESSION

    swept_group: str = Field(
        min_length=1, description="Level origin: 'asia' range or a session name."
    )
    swept_level_kind: LiquidityPoolKind = Field(
        description="SESSION_HIGH / SESSION_LOW / PREVIOUS_DAY_HIGH / PREVIOUS_DAY_LOW."
    )
    swept_price: float = Field(gt=0, description="Swept level price.")
    side: LiquiditySide = Field(description="BUYSIDE sweep of a high, SELLSIDE of a low.")
    sweeping_window: str = Field(min_length=1, description="Killzone active at the sweep.")
    candle_index: int = Field(ge=0, description="Index of the sweeping candle.")
    timestamp: AwareDatetime = Field(description="Sweeping candle timestamp (UTC).")
    linked_sweep_id: str = Field(min_length=1, description="ID of the underlying LiquiditySweep.")
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_SWEEP_MARK, render_type=RenderType.MARKER)
    )


class SessionResult(VersionedModel):
    """Payload of the sessions module."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_SESSION

    sessions: list[SessionStats] = Field(default_factory=list)
    pools: list[LiquidityPool] = Field(
        default_factory=list, description="Session-derived pools with final statuses."
    )
    sweeps: list[LiquiditySweep] = Field(
        default_factory=list, description="Sweeps against session-derived pools."
    )
    session_sweeps: list[SessionSweep] = Field(
        default_factory=list, description="Judas-swing events."
    )
    day_high_counts: dict[str, int] = Field(
        default_factory=dict, description="How often each window formed the calendar-day high."
    )
    day_low_counts: dict[str, int] = Field(
        default_factory=dict, description="How often each window formed the calendar-day low."
    )
    dominant_high_session: str | None = Field(
        default=None,
        description="Window that most often forms the day high (ties: first alphabetically).",
    )
    dominant_low_session: str | None = Field(
        default=None, description="Window that most often forms the day low."
    )
