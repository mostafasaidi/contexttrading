"""Mitigation blocks: origin candles of failed moves that swept liquidity.

Deterministic rule
------------------
A mitigation block forms when price sweeps liquidity **without** producing a
structure break — the failed-move fingerprint. Eligible sweeps are
:class:`SweepClassification` ``STOP_HUNT`` or ``GRAB`` events (deep or
structure-linked stop runs; shallow SWEEPs are excluded).

- **Direction**: a BUYSIDE sweep (highs run, reversal expected down) yields a
  **bullish** mitigation block; a SELLSIDE sweep yields a bearish one.
- **Origin candle** = the extreme candle of the failed leg that preceded the
  sweep: for a bullish block, the candle at the most recent external swing
  LOW before the sweep candle (mirrored for bearish). The zone is that
  candle's full range ``[low, high]``.
- ``failed_swing_id`` = the first source swing of the swept pool — the level
  that was swept but never broken.
- Lifecycle: actionable from the sweep candle onward; mitigation threshold is
  the far boundary (unrefined semantics).
"""

from __future__ import annotations

from contexttrading.analysis.orderblocks.lifecycle import (
    BlockState,
    resolve_age,
    update_block_state,
)
from contexttrading.core.constants import (
    LiquiditySide,
    MitigationStatus,
    SweepClassification,
    SwingType,
    TrendDirection,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.liquidity import LiquidityPool, LiquiditySweep
from contexttrading.models.orderblock import MitigationBlock, block_style
from contexttrading.models.structure import SwingPoint

_ELIGIBLE = {SweepClassification.STOP_HUNT, SweepClassification.GRAB}


def build_mitigation_blocks(
    sweeps: list[LiquiditySweep],
    pools: list[LiquidityPool],
    external_swings: list[SwingPoint],
    series: CandleSeries,
) -> list[MitigationBlock]:
    """Emit mitigation blocks for eligible sweeps (chronological order)."""
    candles = series.candles
    # The un-broken swing backing the pool: for equal-level pools source_ids
    # is [level.id, *member_swing_ids] — take the first member swing; for
    # standalone swing pools it is source_ids[0].
    pool_sources = {
        pool.id: pool.source_ids[1] if len(pool.source_ids) > 1 else pool.source_ids[0]
        for pool in pools
    }
    out: list[MitigationBlock] = []

    for sweep in sorted(sweeps, key=lambda s: s.candle_index):
        if sweep.classification not in _ELIGIBLE:
            continue
        bullish = sweep.side is LiquiditySide.BUYSIDE
        origin_type = SwingType.LOW if bullish else SwingType.HIGH
        origins = [
            s.index
            for s in external_swings
            if s.swing_type is origin_type and s.index < sweep.candle_index
        ]
        if not origins:
            continue
        origin_index = max(origins)
        origin = candles[origin_index]
        if origin.high <= origin.low:
            continue  # degenerate flat candle
        direction = TrendDirection.BULLISH if bullish else TrendDirection.BEARISH

        state = BlockState()
        actionable = sweep.candle_index
        mitigation_level = origin.low if bullish else origin.high
        for i in range(actionable, len(candles)):
            update_block_state(
                state,
                direction=direction,
                zone_bottom=origin.low,
                zone_top=origin.high,
                mitigation_level=mitigation_level,
                candle=candles[i],
                index=i,
            )

        out.append(
            MitigationBlock(
                direction=direction,
                zone_bottom=origin.low,
                zone_top=origin.high,
                candle_index=origin_index,
                formed_at=origin.timestamp,
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
                linked_sweep_id=sweep.id,
                failed_swing_id=pool_sources.get(sweep.pool_id, sweep.pool_id),
                style=block_style("mb", direction, state.status),
            )
        )
    return out
