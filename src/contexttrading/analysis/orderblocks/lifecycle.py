"""Shared block lifecycle: chronological first-touch scan.

Applies to order blocks, breaker blocks, and mitigation blocks alike. Zone
``[bottom, top]``; **bullish** blocks (demand) mitigate from above, **bearish**
from below (mirrored rules):

- **entry**: any trade into the zone (bullish: ``low <= top``; wicks count).
- **penetration fraction**: depth traded into the full zone, clamped [0, 1].
- **MITIGATED**: traded through the *mitigation level* — the far boundary for
  unrefined zones, or the midpoint of the refined zone when refined (50% rule).
- **VIOLATED**: a candle *closed* through the far side (wick-through is NOT a
  violation). Terminal.
- **consumed**: MITIGATED and a later candle closed back outside the zone on
  the origin side (sticky once set).

Transitions are monotonic UNMITIGATED → PARTIALLY_MITIGATED → MITIGATED →
VIOLATED; a wick-mitigated block can still be violated later (consistent with
the FVG lifecycle).
"""

from __future__ import annotations

from dataclasses import dataclass

from contexttrading.core.constants import MitigationStatus, TrendDirection
from contexttrading.models.candle import Candle


@dataclass
class BlockState:
    """Mutable per-block scan state (finalized into the block model)."""

    status: MitigationStatus = MitigationStatus.UNMITIGATED
    first_touch_index: int | None = None
    mitigation_index: int | None = None
    violation_index: int | None = None
    max_penetration_fraction: float = 0.0
    touches: int = 0
    is_consumed: bool = False


def update_block_state(
    state: BlockState,
    *,
    direction: TrendDirection,
    zone_bottom: float,
    zone_top: float,
    mitigation_level: float,
    candle: Candle,
    index: int,
) -> None:
    """Advance one block's lifecycle by one candle (in place).

    Order: entry/penetration bookkeeping first (wick semantics), then
    violation (close semantics), then departure (consumption).
    """
    if state.status is MitigationStatus.VIOLATED:
        return
    bullish = direction is TrendDirection.BULLISH

    if state.status is MitigationStatus.MITIGATED:
        # Already mitigated; only a close-through can violate, and a close
        # back outside the zone on the origin side marks consumption.
        violated = candle.close < zone_bottom if bullish else candle.close > zone_top
        if violated:
            state.status = MitigationStatus.VIOLATED
            state.violation_index = index
            return
        departed = candle.close > zone_top if bullish else candle.close < zone_bottom
        if departed:
            state.is_consumed = True
        return

    entered = candle.low <= zone_top if bullish else candle.high >= zone_bottom
    if not entered:
        return

    state.touches += 1
    if state.first_touch_index is None:
        state.first_touch_index = index

    size = zone_top - zone_bottom
    if bullish:
        depth = zone_top - max(candle.low, zone_bottom)
    else:
        depth = min(candle.high, zone_top) - zone_bottom
    fraction = min(max(depth / size, 0.0), 1.0)
    state.max_penetration_fraction = max(state.max_penetration_fraction, fraction)

    mitigated = candle.low <= mitigation_level if bullish else candle.high >= mitigation_level
    if mitigated:
        state.status = MitigationStatus.MITIGATED
        state.mitigation_index = index
        violated = candle.close < zone_bottom if bullish else candle.close > zone_top
        if violated:
            state.status = MitigationStatus.VIOLATED
            state.violation_index = index
    elif state.status is MitigationStatus.UNMITIGATED:
        state.status = MitigationStatus.PARTIALLY_MITIGATED


def resolve_age(state: BlockState, actionable_from: int, last_index: int) -> int:
    """Candles from actionable_from to resolution (or series end)."""
    end = state.violation_index or state.mitigation_index or last_index
    return max(end - actionable_from, 0)
