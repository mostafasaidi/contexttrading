"""Equal highs / equal lows detection.

Algorithm
---------
1. Take external swing highs (lows) in index order.
2. **Greedy ordered clustering**: start a cluster at the first swing; absorb
   subsequent swings while ``max(cluster) - min(cluster) <= tolerance`` where
   ``tolerance = equal_level_atr_fraction * ATR[swing_index]`` (ATR at the
   candidate swing; falls back to the cluster's own tolerance when ATR is
   unavailable there). A swing that would widen the cluster beyond tolerance
   closes the cluster and starts a new one.
3. Clusters need ``count >= 2`` and every consecutive member pair separated
   by >= ``equal_level_min_separation`` candles (a pair violating separation
   splits the cluster at that point).
4. The level price is the arithmetic mean of member prices; the side is
   BUYSIDE for equal highs, SELLSIDE for equal lows.
"""

from __future__ import annotations

from collections.abc import Sequence

from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import LiquiditySide, SwingType
from contexttrading.models.liquidity import EqualLevel, equal_level_style
from contexttrading.models.structure import SwingPoint


def _detect_side(
    swings: Sequence[SwingPoint],
    atr_values: Sequence[float | None],
    side: LiquiditySide,
    config: EngineConfig,
) -> list[EqualLevel]:
    ordered = sorted(swings, key=lambda s: s.index)
    levels: list[EqualLevel] = []
    cluster: list[SwingPoint] = []

    def flush() -> None:
        if len(cluster) >= 2:
            price = sum(s.price for s in cluster) / len(cluster)
            tol = config.equal_level_atr_fraction * (atr_values[cluster[-1].index] or 0.0)
            levels.append(
                EqualLevel(
                    price=price,
                    side=side,
                    member_swing_ids=[s.id for s in cluster],
                    count=len(cluster),
                    tolerance=tol,
                    style=equal_level_style(side),
                )
            )
        cluster.clear()

    for swing in ordered:
        if cluster:
            tol_ref = atr_values[swing.index]
            cluster_ref = atr_values[cluster[0].index]
            base = tol_ref if tol_ref is not None else cluster_ref
            tolerance = config.equal_level_atr_fraction * base if base else None
            spread_ok = tolerance is not None and (
                max(max(s.price for s in cluster), swing.price)
                - min(min(s.price for s in cluster), swing.price)
                <= tolerance
            )
            separation_ok = swing.index - cluster[-1].index >= config.equal_level_min_separation
            if not (spread_ok and separation_ok):
                flush()
        cluster.append(swing)
    flush()
    return levels


def detect_equal_levels(
    swings: Sequence[SwingPoint],
    atr_values: Sequence[float | None],
    config: EngineConfig,
) -> list[EqualLevel]:
    """Detect equal highs and equal lows among the given swings.

    Args:
        swings: Swing points (typically external).
        atr_values: ATR series aligned with candle indices.
        config: Thresholds (``equal_level_atr_fraction``,
            ``equal_level_min_separation``).

    Returns:
        Equal levels: equal highs (index-ordered) followed by equal lows
        (index-ordered) — a deterministic order.
    """
    highs = [s for s in swings if s.swing_type is SwingType.HIGH]
    lows = [s for s in swings if s.swing_type is SwingType.LOW]
    levels = _detect_side(highs, atr_values, LiquiditySide.BUYSIDE, config)
    levels += _detect_side(lows, atr_values, LiquiditySide.SELLSIDE, config)
    return levels
