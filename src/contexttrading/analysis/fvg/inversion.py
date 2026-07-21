"""Inverse FVG transitions.

An FVG **inverts** when a candle *closes* through the far side of its zone:

- bullish FVG ``[bottom, top]``: inversion when ``close < zone_bottom``;
- bearish FVG: inversion when ``close > zone_top``.

**Wick-through never inverts** — only the close confirms the role flip
(support ↔ resistance). Inversion implies the zone is also *filled* (a close
through the far side necessarily traded through it), so the lifecycle engine
applies fill bookkeeping first, then marks the FVG inverse
(``status = VIOLATED``). VIOLATED is terminal: the inverted zone stays in the
output with ``is_inverse=True`` and ``inversion_index`` for downstream
consumers (breaker-style logic arrives with order blocks in Phase 5).
"""

from __future__ import annotations

from contexttrading.core.constants import TrendDirection
from contexttrading.models.candle import Candle


def closes_through_far_side(
    direction: TrendDirection,
    zone_bottom: float,
    zone_top: float,
    candle: Candle,
) -> bool:
    """True when ``candle`` closes through the far side of the zone.

    Args:
        direction: FVG direction.
        zone_bottom: Lower zone boundary.
        zone_top: Upper zone boundary.
        candle: Candle to test.
    """
    if direction is TrendDirection.BULLISH:
        return candle.close < zone_bottom
    return candle.close > zone_top


def trades_through_far_side(
    direction: TrendDirection,
    zone_bottom: float,
    zone_top: float,
    candle: Candle,
) -> bool:
    """True when ``candle`` trades (wick or close) through the far side."""
    if direction is TrendDirection.BULLISH:
        return candle.low <= zone_bottom
    return candle.high >= zone_top
