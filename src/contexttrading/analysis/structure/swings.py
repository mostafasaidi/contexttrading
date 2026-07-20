"""Fractal swing detection.

Algorithm
---------
A candle ``i`` is a **swing high** for lookback ``N`` when::

    high[i] > high[j]  for all j in [i-N, i+N], j != i

and symmetrically for **swing lows** on ``low``.

Tie rules (deterministic, documented):
    - Comparison is **strictly greater / strictly lower** — an equal-high
      neighbor disqualifies the bar. Equal levels are *not* swings; they are
      detected separately by the liquidity module.
    - The first and last ``N`` candles can never be swings (unconfirmed).
    - Internal swings use ``internal_swing_lookback`` (default 2), external
      swings use ``external_swing_lookback`` (default 5). A bar may be both
      an internal and an external swing; each class is emitted as its own
      :class:`SwingPoint` with its own deterministic ID.
"""

from __future__ import annotations

from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import SwingClass, SwingType
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import CandleSeries
from contexttrading.models.structure import SwingPoint, swing_style


def detect_swings(
    series: CandleSeries,
    lookback: int,
    swing_class: SwingClass,
) -> list[SwingPoint]:
    """Detect swing highs and lows with a fractal rule.

    Args:
        series: Ordered candle series.
        lookback: Neighbor bars required on each side (>= 1).
        swing_class: INTERNAL or EXTERNAL label for the emitted swings.

    Returns:
        Swing points sorted by candle index (highs and lows interleaved).

    Raises:
        ValueError: If ``lookback < 1``.
        InsufficientDataError: If the series cannot hold one confirmed swing.
    """
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    candles = series.candles
    if len(candles) < 2 * lookback + 1:
        raise InsufficientDataError(
            "Series too short for swing detection",
            context={
                "candles": len(candles),
                "required": 2 * lookback + 1,
                "lookback": lookback,
                "swing_class": swing_class.value,
            },
        )
    swings: list[SwingPoint] = []
    for i in range(lookback, len(candles) - lookback):
        bar = candles[i]
        is_high = True
        is_low = True
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if candles[j].high >= bar.high:
                is_high = False
            if candles[j].low <= bar.low:
                is_low = False
            if not is_high and not is_low:
                break
        if is_high:
            swings.append(
                SwingPoint(
                    index=i,
                    timestamp=bar.timestamp,
                    price=bar.high,
                    swing_type=SwingType.HIGH,
                    swing_class=swing_class,
                    lookback=lookback,
                    style=swing_style(SwingType.HIGH, swing_class),
                )
            )
        if is_low:
            swings.append(
                SwingPoint(
                    index=i,
                    timestamp=bar.timestamp,
                    price=bar.low,
                    swing_type=SwingType.LOW,
                    swing_class=swing_class,
                    lookback=lookback,
                    style=swing_style(SwingType.LOW, swing_class),
                )
            )
    return swings


def detect_swing_sets(
    series: CandleSeries,
    config: EngineConfig,
) -> tuple[list[SwingPoint], list[SwingPoint]]:
    """Detect internal and external swings per config.

    Returns:
        ``(internal_swings, external_swings)``, each sorted by index.
    """
    internal = detect_swings(series, config.internal_swing_lookback, SwingClass.INTERNAL)
    external = detect_swings(series, config.external_swing_lookback, SwingClass.EXTERNAL)
    return internal, external
