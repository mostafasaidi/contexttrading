"""Breaker blocks: violated order blocks whose role flips.

Deterministic rule
------------------
When an order block is **VIOLATED** (a candle closed through its far side)
and a **confirmed** structure break in the *violation direction* (against
the OB's direction) occurs at the violation candle or within
``breaker_confirm_lookback`` candles after it, the violated OB flips role:

- bullish OB violated downward → **bearish** breaker (supply),
- bearish OB violated upward → **bullish** breaker (demand).

The breaker inherits the OB's zone geometry; its lifecycle is tracked from
the flip candle onward with the standard block lifecycle (price returning
into the breaker zone = mitigation).
"""

from __future__ import annotations

from contexttrading.analysis.orderblocks.lifecycle import (
    BlockState,
    resolve_age,
    update_block_state,
)
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import BreakStrength, MitigationStatus, TrendDirection
from contexttrading.models.candle import CandleSeries
from contexttrading.models.orderblock import BreakerBlock, OrderBlock, block_style
from contexttrading.models.structure import StructureBreak


def _confirming_break(
    ob: OrderBlock,
    breaks: list[StructureBreak],
    lookback: int,
) -> StructureBreak | None:
    """First confirmed counter-direction break at/after the violation candle."""
    assert ob.violation_index is not None  # guarded by caller
    wanted = (
        TrendDirection.BEARISH if ob.direction is TrendDirection.BULLISH else TrendDirection.BULLISH
    )
    for brk in sorted(breaks, key=lambda b: b.break_index):
        if brk.break_index < ob.violation_index:
            continue
        if brk.break_index > ob.violation_index + lookback:
            break
        if brk.direction is wanted and brk.strength is not BreakStrength.FALSE:
            return brk
    return None


def build_breakers(
    order_blocks: list[OrderBlock],
    series: CandleSeries,
    breaks: list[StructureBreak],
    config: EngineConfig,
) -> list[BreakerBlock]:
    """Emit breaker blocks for violated OBs with a confirming break."""
    candles = series.candles
    out: list[BreakerBlock] = []
    for ob in order_blocks:
        if ob.violation_index is None:
            continue
        confirming = _confirming_break(ob, breaks, config.breaker_confirm_lookback)
        if confirming is None:
            continue
        direction = confirming.direction
        flip = ob.violation_index

        state = BlockState()
        actionable = flip + 1
        mitigation_level = ob.zone_bottom if direction is TrendDirection.BULLISH else ob.zone_top
        # Scan from the candle AFTER the flip: mitigation means price
        # *returning* to the breaker zone, not the violation candle itself.
        for i in range(actionable, len(candles)):
            update_block_state(
                state,
                direction=direction,
                zone_bottom=ob.zone_bottom,
                zone_top=ob.zone_top,
                mitigation_level=mitigation_level,
                candle=candles[i],
                index=i,
            )

        out.append(
            BreakerBlock(
                direction=direction,
                zone_bottom=ob.zone_bottom,
                zone_top=ob.zone_top,
                candle_index=flip,
                formed_at=candles[flip].timestamp,
                actionable_from_index=actionable,
                status=state.status,
                first_touch_index=state.first_touch_index,
                mitigation_index=state.mitigation_index,
                violation_index=state.violation_index,
                max_penetration_fraction=state.max_penetration_fraction,
                touches=state.touches,
                age=resolve_age(state, actionable, len(candles) - 1),
                is_consumed=state.is_consumed,
                is_valid=state.status is MitigationStatus.UNMITIGATED,
                source_order_block_id=ob.id,
                flip_index=flip,
                confirming_break_id=confirming.id,
                style=block_style("brk", direction, state.status),
            )
        )
    return out
