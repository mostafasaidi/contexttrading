"""Shared constants and enums — the cross-layer vocabulary.

This module is intentionally dependency-free (stdlib only) so every layer can
import it. See ``docs/modules/constants.md`` for the design contract.
"""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

# ---------------------------------------------------------------------------
# Floating-point policy (docs/architecture/determinism.md §3)
# ---------------------------------------------------------------------------

FLOAT_REL_TOL: float = 1e-9
"""Relative tolerance for float comparisons inside the engine."""

FLOAT_ABS_TOL: float = 1e-12
"""Absolute tolerance for float comparisons inside the engine."""

MONTH_SECONDS_CONVENTIONAL: int = 30 * 86_400
"""Conventional length of one calendar month used *only* for timeframe
ordering and rough gap estimation — never for real calendar arithmetic."""

WEEK_SECONDS: int = 7 * 86_400
DAY_SECONDS: int = 86_400


# ---------------------------------------------------------------------------
# Timeframes
# ---------------------------------------------------------------------------


class Timeframe(StrEnum):
    """Supported candle timeframes.

    Values are the canonical string codes (``"1m"`` … ``"1M"``). Ordering is
    by duration: ``M1 < M5 < H1 < D1 < W1 < MN1``.
    """

    M1 = "1m"
    M3 = "3m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H2 = "2h"
    H4 = "4h"
    H6 = "6h"
    H8 = "8h"
    H12 = "12h"
    D1 = "1d"
    W1 = "1w"
    MN1 = "1M"

    @property
    def seconds(self) -> int:
        """Duration of one candle in seconds (month uses the conventional value)."""
        return _TIMEFRAME_SECONDS[self]

    @property
    def minutes(self) -> float:
        """Duration of one candle in minutes."""
        return self.seconds / 60

    def to_timedelta(self) -> timedelta:
        """Duration as a :class:`datetime.timedelta`."""
        return timedelta(seconds=self.seconds)

    @classmethod
    def parse(cls, value: str | Timeframe) -> Timeframe:
        """Parse a timeframe from strings like ``"15m"``, ``"4h"``, ``"1d"``,
        ``"1w"``, ``"1M"`` (case-insensitive; ``"1mo"``/``"1mon"`` also map to
        the monthly timeframe).

        Args:
            value: Canonical code, member name (e.g. ``"H4"``), or alias.

        Returns:
            The matching :class:`Timeframe`.

        Raises:
            ValueError: If the string is not a recognized timeframe.
        """
        if isinstance(value, cls):
            return value
        key = value.strip()
        # Exact canonical match first (preserves the "1m" vs "1M" distinction).
        for member in cls:
            if member.value == key or member.name == key:
                return member
        lowered = key.lower()
        if lowered in _TIMEFRAME_ALIASES:
            return _TIMEFRAME_ALIASES[lowered]
        raise ValueError(f"Unknown timeframe: {value!r}")

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Timeframe):
            return self.seconds < other.seconds
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, Timeframe):
            return self.seconds <= other.seconds
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, Timeframe):
            return self.seconds > other.seconds
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, Timeframe):
            return self.seconds >= other.seconds
        return NotImplemented

    def __str__(self) -> str:  # canonical code, e.g. "15m"
        return self.value


_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M3: 3 * 60,
    Timeframe.M5: 5 * 60,
    Timeframe.M15: 15 * 60,
    Timeframe.M30: 30 * 60,
    Timeframe.H1: 3_600,
    Timeframe.H2: 2 * 3_600,
    Timeframe.H4: 4 * 3_600,
    Timeframe.H6: 6 * 3_600,
    Timeframe.H8: 8 * 3_600,
    Timeframe.H12: 12 * 3_600,
    Timeframe.D1: DAY_SECONDS,
    Timeframe.W1: WEEK_SECONDS,
    Timeframe.MN1: MONTH_SECONDS_CONVENTIONAL,
}

_TIMEFRAME_ALIASES: dict[str, Timeframe] = {
    **{tf.value.lower(): tf for tf in Timeframe if tf is not Timeframe.MN1},
    **{tf.name.lower(): tf for tf in Timeframe},
    "1mo": Timeframe.MN1,
    "1mon": Timeframe.MN1,
    "1month": Timeframe.MN1,
    "monthly": Timeframe.MN1,
    "weekly": Timeframe.W1,
    "daily": Timeframe.D1,
}


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class SessionName(StrEnum):
    """Named trading sessions / killzones (windows defined in SessionConfig)."""

    ASIA = "asia"
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    LONDON = "london"
    NEW_YORK = "new_york"
    LONDON_CLOSE = "london_close"
    NEW_YORK_AM = "new_york_am"
    NEW_YORK_PM = "new_york_pm"


# ---------------------------------------------------------------------------
# Trend & structure
# ---------------------------------------------------------------------------


class TrendDirection(StrEnum):
    """Directional state of price, a candle, or a structure leg."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    UNKNOWN = "unknown"

    @property
    def sign(self) -> int:
        """+1 bullish, -1 bearish, 0 otherwise."""
        if self is TrendDirection.BULLISH:
            return 1
        if self is TrendDirection.BEARISH:
            return -1
        return 0


class SwingType(StrEnum):
    """Kind of a detected swing point."""

    HIGH = "high"
    LOW = "low"


class StructureBreakType(StrEnum):
    """Break of Structure (trend continuation) vs Change of Character (reversal)."""

    BOS = "bos"
    CHOCH = "choch"


class StructureBreakClass(StrEnum):
    """Internal (short-range) vs external (leg-level) structure."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class StructureBreakSignificance(StrEnum):
    """Minor vs major breaks (major = confirmed by displacement/close)."""

    MINOR = "minor"
    MAJOR = "major"


# ---------------------------------------------------------------------------
# Zones & liquidity
# ---------------------------------------------------------------------------


class ZoneType(StrEnum):
    """Kinds of price zones the engine can emit."""

    ORDER_BLOCK = "order_block"
    BREAKER_BLOCK = "breaker_block"
    FAIR_VALUE_GAP = "fair_value_gap"
    INVERSION_FVG = "inversion_fvg"
    SUPPLY = "supply"
    DEMAND = "demand"
    LIQUIDITY_POOL = "liquidity_pool"
    PREMIUM = "premium"
    DISCOUNT = "discount"
    EQUILIBRIUM = "equilibrium"


class MitigationStatus(StrEnum):
    """Lifecycle of a zone with respect to price revisits."""

    UNMITIGATED = "unmitigated"
    PARTIALLY_MITIGATED = "partially_mitigated"
    MITIGATED = "mitigated"
    VIOLATED = "violated"


class LiquiditySide(StrEnum):
    """Side of the book where resting liquidity sits."""

    BUYSIDE = "buyside"
    SELLSIDE = "sellside"


class LiquidityPoolKind(StrEnum):
    """Formation that creates a liquidity pool."""

    EQUAL_HIGHS = "equal_highs"
    EQUAL_LOWS = "equal_lows"
    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"
    SESSION_HIGH = "session_high"
    SESSION_LOW = "session_low"
    PREVIOUS_DAY_HIGH = "previous_day_high"
    PREVIOUS_DAY_LOW = "previous_day_low"


# ---------------------------------------------------------------------------
# Phase 3: structure, trend, liquidity, ranges
# ---------------------------------------------------------------------------


class SwingClass(StrEnum):
    """Internal (short lookback, noise-level) vs external (leg-level) swings."""

    INTERNAL = "internal"
    EXTERNAL = "external"


class BreakStrength(StrEnum):
    """Confirmation quality of a structure break.

    - ``STRONG``: close beyond the level by >= ``strength_atr_fraction * ATR``.
    - ``WEAK``: close beyond the level, but by less than the strong threshold.
    - ``FALSE``: wick-only breach without close confirmation (sweep candidate).
    """

    STRONG = "strong"
    WEAK = "weak"
    FALSE = "false"


class TrendStrength(StrEnum):
    """Qualitative trend strength from leg statistics and follow-through."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class MarketPhase(StrEnum):
    """Wyckoff-style market phase from range/overlap heuristics."""

    ACCUMULATION = "accumulation"
    DISTRIBUTION = "distribution"
    EXPANSION = "expansion"
    CONSOLIDATION = "consolidation"


class LegKind(StrEnum):
    """Impulse (makes a new same-side extreme) vs correction (retraces)."""

    IMPULSE = "impulse"
    CORRECTION = "correction"


class PoolStatus(StrEnum):
    """Lifecycle of a liquidity pool.

    ``UNTAPPED`` → ``SWEPT`` (wicked through, closed back inside) or
    ``BROKEN`` (closed through = true break). Status transitions are
    monotonic in scan order.
    """

    UNTAPPED = "untapped"
    SWEPT = "swept"
    BROKEN = "broken"


class SweepClassification(StrEnum):
    """Stop-run taxonomy.

    - ``SWEEP``: wick through the pool, close back inside, shallow penetration.
    - ``GRAB``: same shape but penetration >= ``sweep_grab_atr_fraction * ATR``.
    - ``STOP_HUNT``: sweep coinciding with a false structure break at the pool.
    """

    SWEEP = "sweep"
    GRAB = "grab"
    STOP_HUNT = "stop_hunt"


class PriceLocation(StrEnum):
    """Where a reference price sits inside a dealing range."""

    PREMIUM = "premium"
    DISCOUNT = "discount"
    EQUILIBRIUM = "equilibrium"


# ---------------------------------------------------------------------------
# Phase 5: order blocks & supply/demand
# ---------------------------------------------------------------------------


class BlockOrigin(StrEnum):
    """Whether a block anchors a trend-continuation leg or a reversal."""

    CONTINUATION = "continuation"
    REVERSAL = "reversal"


class SDZoneStatus(StrEnum):
    """Lifecycle of a supply/demand zone.

    ``FRESH`` → ``TESTED`` (re-entered, not broken) → terminal ``MITIGATED``
    (traded through the base) or ``BROKEN`` (closed through the base).
    """

    FRESH = "fresh"
    TESTED = "tested"
    MITIGATED = "mitigated"
    BROKEN = "broken"
