"""Liquidity pool construction.

Pools
-----
- **Equal-level pools**: every :class:`EqualLevel` becomes a pool at its
  price — equal highs hold buy-side liquidity above them, equal lows
  sell-side below. Kind: ``EQUAL_HIGHS`` / ``EQUAL_LOWS``.
- **Swing pools**: external swing highs/lows that are *not* members of an
  equal level become single-swing pools (kind ``SWING_HIGH`` / ``SWING_LOW``).
- ``pool_class`` mirrors the swing class of the sources (EXTERNAL here;
  internal pools arise when the module is fed internal swings).

Pool statuses are updated by :mod:`contexttrading.analysis.liquidity.sweeps`
during the chronological scan — this module only constructs UNTAPPED pools.
"""

from __future__ import annotations

from collections.abc import Sequence

from contexttrading.core.constants import (
    LiquidityPoolKind,
    LiquiditySide,
    PoolStatus,
    SwingClass,
    SwingType,
)
from contexttrading.models.liquidity import EqualLevel, LiquidityPool, pool_style
from contexttrading.models.structure import SwingPoint


def build_pools(
    swings: Sequence[SwingPoint],
    equal_levels: Sequence[EqualLevel],
) -> list[LiquidityPool]:
    """Construct UNTAPPED liquidity pools from swings and equal levels.

    Args:
        swings: Swing points to source single-swing pools from.
        equal_levels: Equal levels (their member swings are excluded from
            single-swing pools).

    Returns:
        Pools sorted by ``(formed_at_index, side)``.
    """
    swing_by_id = {s.id: s for s in swings}
    member_ids = {sid for level in equal_levels for sid in level.member_swing_ids}
    pools: list[LiquidityPool] = []

    for level in equal_levels:
        members = [swing_by_id[sid] for sid in level.member_swing_ids if sid in swing_by_id]
        pool_class = members[0].swing_class if members else SwingClass.EXTERNAL
        kind = (
            LiquidityPoolKind.EQUAL_HIGHS
            if level.side is LiquiditySide.BUYSIDE
            else LiquidityPoolKind.EQUAL_LOWS
        )
        pools.append(
            LiquidityPool(
                price=level.price,
                side=level.side,
                kind=kind,
                pool_class=pool_class,
                source_ids=[level.id, *level.member_swing_ids],
                formed_at_index=max((s.index for s in members), default=0),
                status=PoolStatus.UNTAPPED,
                style=pool_style(level.side, PoolStatus.UNTAPPED),
            )
        )

    for swing in sorted(swings, key=lambda s: s.index):
        if swing.id in member_ids:
            continue
        side = (
            LiquiditySide.BUYSIDE if swing.swing_type is SwingType.HIGH else LiquiditySide.SELLSIDE
        )
        kind = (
            LiquidityPoolKind.SWING_HIGH
            if swing.swing_type is SwingType.HIGH
            else LiquidityPoolKind.SWING_LOW
        )
        pools.append(
            LiquidityPool(
                price=swing.price,
                side=side,
                kind=kind,
                pool_class=swing.swing_class,
                source_ids=[swing.id],
                formed_at_index=swing.index,
                status=PoolStatus.UNTAPPED,
                style=pool_style(side, PoolStatus.UNTAPPED),
            )
        )
    return sorted(pools, key=lambda p: (p.formed_at_index, p.side.value, p.price))
