"""FVG test fixtures: hand-crafted candles for detection/lifecycle cases."""

from __future__ import annotations

from typing import Any

from contexttrading.models.candle import CandleSeries
from tests.fixtures import make_candle, to_series


def bullish_fvg_records() -> list[dict[str, Any]]:
    """One bullish FVG [10.0, 10.5] (middle idx1), then mitigation story.

    c4 enters the zone (partial 0.4), c5 wicks through far side (fill,
    close back inside → no inversion), c6 closes through (inversion is
    blocked — already... no: c5 filled by wick only, c6 closes through →
    inverse).
    """
    return [
        make_candle(0, 9.8, 10.0, 9.7, 9.9),
        make_candle(1, 9.9, 11.0, 9.85, 10.9),  # displacement candle
        make_candle(2, 10.9, 11.2, 10.5, 11.1),  # low 10.5 > high[0] 10.0
        make_candle(3, 11.1, 11.3, 10.6, 11.2),  # low 10.6: no counter-FVG with c5
        make_candle(4, 11.2, 11.25, 10.3, 10.6),  # enters zone (partial 0.4)
        make_candle(5, 10.6, 10.7, 9.9, 10.0),  # wick fill, close inside
        make_candle(6, 10.35, 10.4, 9.8, 9.85),  # close-through → inverse (high blocks bear-FVG)
    ]


def bearish_fvg_records() -> list[dict[str, Any]]:
    """One bearish FVG [10.5, 11.0] (middle idx1), filled by wick later."""
    return [
        make_candle(0, 11.2, 11.3, 11.0, 11.1),
        make_candle(1, 11.1, 11.15, 10.0, 10.1),  # displacement down
        make_candle(2, 10.1, 10.5, 9.8, 9.9),  # high 10.5 < low[0] 11.0
        make_candle(3, 9.9, 10.0, 9.7, 9.8),
        make_candle(4, 9.8, 10.7, 9.75, 10.4),  # enters zone (partial 0.4)
        make_candle(5, 10.4, 11.2, 9.95, 11.05),  # wick fill + close-through (low blocks bull-FVG)
        make_candle(6, 11.05, 11.2, 10.6, 10.9),  # continuation (pattern-neutral)
    ]


def nested_fvg_records() -> list[dict[str, Any]]:
    """Big FVG [10, 11] with a smaller nested FVG [10.5, 10.6] inside.

    The parent is partially filled (never filled) when the child forms, so
    the child links parent_fvg_id.
    """
    return [
        make_candle(0, 9.8, 10.0, 9.7, 9.9),
        make_candle(1, 9.9, 12.0, 9.8, 11.9),  # big displacement
        make_candle(2, 11.9, 12.2, 11.0, 12.1),  # FVG1 zone [10, 11]
        make_candle(3, 12.1, 12.3, 10.45, 12.2),  # low dips into FVG1 (no counter-FVG with c5)
        make_candle(4, 12.2, 12.25, 10.4, 10.5),  # enters FVG1 (partial)
        make_candle(5, 10.5, 10.5, 10.35, 10.4),  # inside FVG1
        make_candle(6, 10.4, 10.9, 10.38, 10.85),
        make_candle(7, 10.85, 11.0, 10.6, 10.95),  # FVG2 zone [10.5, 10.6]
        make_candle(8, 10.95, 11.2, 10.9, 11.1),
    ]


def untouched_fvg_records() -> list[dict[str, Any]]:
    """FVG that price never revisits (aging test)."""
    return [
        make_candle(0, 9.8, 10.0, 9.7, 9.9),
        make_candle(1, 9.9, 11.0, 9.85, 10.9),
        make_candle(2, 10.9, 11.2, 10.5, 11.1),
        make_candle(3, 11.1, 11.4, 11.05, 11.3),
        make_candle(4, 11.3, 11.6, 11.25, 11.5),
        make_candle(5, 11.5, 11.8, 11.45, 11.7),
        make_candle(6, 11.7, 12.0, 11.5, 11.9),  # continuation (pattern-neutral)
    ]


def inversion_series() -> CandleSeries:
    """Bullish FVG inverted by a close-through (wick fill first)."""
    return to_series(bullish_fvg_records(), symbol="INV")


def wick_only_fill_records() -> list[dict[str, Any]]:
    """Bullish FVG filled by wick only — close back inside, never closes through."""
    return [
        make_candle(0, 9.8, 10.0, 9.7, 9.9),
        make_candle(1, 9.9, 11.0, 9.85, 10.9),
        make_candle(2, 10.9, 11.2, 10.5, 11.1),
        make_candle(3, 11.1, 11.3, 9.9, 10.4),  # wick through, close inside
        make_candle(4, 10.4, 10.6, 10.1, 10.5),
        make_candle(5, 10.5, 10.8, 10.4, 10.7),  # continuation (pattern-neutral)
        make_candle(6, 10.7, 10.9, 10.5, 10.8),  # continuation (pattern-neutral)
    ]
