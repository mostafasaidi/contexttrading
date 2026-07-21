"""Leg classification between consecutive external swings.

Algorithm
---------
1. Build an **alternating** external-swing sequence: walking swings in index
   order, a swing of the opposite type to the last kept swing is appended; a
   same-type swing *replaces* the last kept one when it is more extreme
   (higher high / lower low), otherwise it is dropped.
2. A leg connects consecutive alternating swings ``s[i-1] -> s[i]``.
   Direction is ``BULLISH`` for low→high and ``BEARISH`` for high→low.
3. Classification: leg ``i`` is an **IMPULSE** when its endpoint exceeds the
   previous same-type swing (``s[i]`` vs ``s[i-2]``), i.e. it prints a new
   extreme; otherwise it is a **CORRECTION**. The first leg is an impulse by
   convention (it establishes the initial drive).
4. ``retracement_ratio`` is this leg's magnitude divided by the previous
   leg's magnitude (``None`` for the first leg). ``atr_multiple`` divides the
   magnitude by ATR at the leg's end index (``None`` when ATR is unavailable).
"""

from __future__ import annotations

from collections.abc import Sequence

from contexttrading.core.constants import LegKind, SwingType, TrendDirection
from contexttrading.models.structure import Leg, SwingPoint


def alternating_swings(swings: Sequence[SwingPoint]) -> list[SwingPoint]:
    """Reduce swings to an alternating high/low sequence (most extreme kept)."""
    kept: list[SwingPoint] = []
    for swing in sorted(swings, key=lambda s: (s.index, s.swing_type.value)):
        if not kept or kept[-1].swing_type is not swing.swing_type:
            kept.append(swing)
            continue
        last = kept[-1]
        more_extreme = (
            swing.price > last.price
            if swing.swing_type is SwingType.HIGH
            else swing.price < last.price
        )
        if more_extreme:
            kept[-1] = swing
    return kept


def classify_legs(
    swings: Sequence[SwingPoint],
    atr_values: Sequence[float | None],
) -> list[Leg]:
    """Classify legs between consecutive external swings.

    Args:
        swings: External swing points (any order; sorted internally).
        atr_values: ATR series aligned with the candle indices.

    Returns:
        Legs in chronological order.
    """
    alt = alternating_swings(swings)
    legs: list[Leg] = []
    for i in range(1, len(alt)):
        start, end = alt[i - 1], alt[i]
        if end.index == start.index:
            # A bar can be both swing high and swing low (small lookbacks,
            # volatile resampled series); a leg spans distinct bars, so the
            # same-bar alternation is noise — skip it rather than emit a
            # zero-duration leg.
            continue
        direction = (
            TrendDirection.BULLISH if end.swing_type is SwingType.HIGH else TrendDirection.BEARISH
        )
        magnitude = abs(end.price - start.price)
        if i == 1:
            kind = LegKind.IMPULSE
        else:
            previous_same_type = alt[i - 2]
            makes_new_extreme = (
                end.price > previous_same_type.price
                if end.swing_type is SwingType.HIGH
                else end.price < previous_same_type.price
            )
            kind = LegKind.IMPULSE if makes_new_extreme else LegKind.CORRECTION
        atr_at_end = atr_values[end.index] if end.index < len(atr_values) else None
        atr_multiple = magnitude / atr_at_end if atr_at_end else None
        retracement = magnitude / legs[-1].magnitude if legs else None
        legs.append(
            Leg(
                start_index=start.index,
                end_index=end.index,
                start_price=start.price,
                end_price=end.price,
                direction=direction,
                kind=kind,
                magnitude=magnitude,
                atr_multiple=atr_multiple,
                duration=end.index - start.index,
                retracement_ratio=retracement,
            )
        )
    return legs
