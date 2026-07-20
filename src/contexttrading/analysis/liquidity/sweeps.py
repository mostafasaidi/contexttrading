"""Liquidity sweep / grab / stop-hunt detection and pool status updates.

Scan semantics (chronological, deterministic)
---------------------------------------------
A pool becomes **active** at candle ``formed_at_index + 1`` (the forming
swing must be complete). From then on, each candle is tested:

- **BUYSIDE pool** at price ``P``: ``high > P`` touches the pool.
  - ``close <= P`` → **sweep** (wick through, close back inside).
  - ``close > P`` → **close-through**: the pool is ``BROKEN`` (true break)
    unless a FALSE structure break was emitted for that level at the same
    candle — then it is a ``STOP_HUNT`` and the pool is ``SWEPT``.
- **SELLSIDE pool**: mirrored on ``low`` / ``close >= P``.

Classification of close-back-inside events:
    - ``STOP_HUNT`` when a FALSE structure break references this pool's level
      at the same candle index;
    - ``GRAB`` when wick penetration >= ``sweep_grab_atr_fraction * ATR``;
    - otherwise ``SWEEP``.

Status transitions are monotonic: ``UNTAPPED`` → ``SWEPT`` | ``BROKEN``.
Only the first event per pool is emitted; later touches of an already
resolved pool are ignored.
"""

from __future__ import annotations

from collections.abc import Sequence

from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BreakStrength,
    LiquiditySide,
    PoolStatus,
    SweepClassification,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.liquidity import (
    LiquidityPool,
    LiquiditySweep,
    pool_style,
    sweep_style,
)
from contexttrading.models.structure import StructureBreak


def scan_sweeps(
    series: CandleSeries,
    pools: Sequence[LiquidityPool],
    false_breaks: Sequence[StructureBreak],
    atr_values: Sequence[float | None],
    config: EngineConfig,
) -> tuple[list[LiquidityPool], list[LiquiditySweep]]:
    """Scan for sweeps and resolve pool statuses.

    Args:
        series: Input candles.
        pools: UNTAPPED pools (not mutated; updated copies returned).
        false_breaks: Structure breaks with ``strength == FALSE`` (sweep
            candidates) used for STOP_HUNT linkage.
        atr_values: ATR series aligned with candle indices.
        config: Thresholds (``sweep_grab_atr_fraction``).

    Returns:
        ``(updated_pools, sweeps)`` — pools in input order with final
        statuses; sweeps in chronological order.
    """
    candles = series.candles
    # FALSE breaks keyed by (broken swing id, candle index); a pool links when
    # any of its source swings matches at the same candle.
    false_index: dict[tuple[str, int], str] = {
        (b.broken_swing_id, b.break_index): b.id
        for b in false_breaks
        if b.strength is BreakStrength.FALSE
    }

    updated: list[LiquidityPool] = []
    sweeps: list[LiquiditySweep] = []
    for pool in pools:
        status = PoolStatus.UNTAPPED
        event: LiquiditySweep | None = None
        for i in range(pool.formed_at_index + 1, len(candles)):
            candle = candles[i]
            if pool.side is LiquiditySide.BUYSIDE:
                touched = candle.high > pool.price
                close_inside = candle.close <= pool.price
                penetration = candle.high - pool.price
                wick_extreme = candle.high
            else:
                touched = candle.low < pool.price
                close_inside = candle.close >= pool.price
                penetration = pool.price - candle.low
                wick_extreme = candle.low
            if not touched:
                continue

            linked = next(
                (false_index[(sid, i)] for sid in pool.source_ids if (sid, i) in false_index),
                None,
            )
            atr_at = atr_values[i] if i < len(atr_values) else None
            penetration_atr = penetration / atr_at if atr_at else None
            if close_inside or linked is not None:
                if linked is not None:
                    classification = SweepClassification.STOP_HUNT
                elif (
                    penetration_atr is not None
                    and penetration_atr >= config.sweep_grab_atr_fraction
                ):
                    classification = SweepClassification.GRAB
                else:
                    classification = SweepClassification.SWEEP
                status = PoolStatus.SWEPT
                event = LiquiditySweep(
                    pool_id=pool.id,
                    pool_price=pool.price,
                    side=pool.side,
                    candle_index=i,
                    timestamp=candle.timestamp,
                    wick_extreme=wick_extreme,
                    penetration_atr=penetration_atr,
                    close_back_inside=close_inside,
                    classification=classification,
                    linked_break_id=linked,
                    style=sweep_style(classification),
                )
            else:
                status = PoolStatus.BROKEN
            break  # first touch resolves the pool

        updated.append(
            pool.model_copy(update={"status": status, "style": pool_style(pool.side, status)})
        )
        if event is not None:
            sweeps.append(event)
    sweeps.sort(key=lambda s: (s.candle_index, s.pool_id))
    return updated, sweeps
