"""Dealing range, equilibrium, premium/discount, and OTE.

Algorithm
---------
1. Take the **alternating external swing sequence** (see
   :func:`contexttrading.analysis.structure.legs.alternating_swings`).
2. The dealing range is the most recent opposite-type swing pair consistent
   with the active trend:
   - BULLISH (or undetermined): latest swing low → latest swing high with
     ``high.index > low.index`` preferred; if the latest extreme is a low
     (price has already reversed), the pair is still (last low, last high)
     ordered by price.
   - BEARISH: mirrored.
   Concretely: ``high = last swing high``, ``low = last swing low``; a valid
   range requires ``high.price > low.price`` and both to exist.
3. ``equilibrium = (high + low) / 2``. Premium = prices above EQ (sell side),
   discount = below EQ (buy side).
4. **OTE** (Optimal Trade Entry): fib retracement of the range using
   ``ote_fib_lower`` / ``ote_fib_upper`` (defaults 0.62 / 0.79):
   - BULLISH: ``ote = high - fib * (high - low)`` → zone
     ``[high - 0.79R, high - 0.62R]`` (buy in discount).
   - BEARISH: ``ote = low + fib * (high - low)`` → zone
     ``[low + 0.62R, low + 0.79R]`` (sell in premium).
5. ``price_location`` classifies the last close: above EQ → PREMIUM, below →
   DISCOUNT, within ``float_abs_tol`` of EQ → EQUILIBRIUM.
"""

from __future__ import annotations

from contexttrading.analysis.structure.legs import alternating_swings
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import PriceLocation, SwingType, TrendDirection
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.models.range import DealingRange, DealingRangeResult
from contexttrading.models.structure import SwingPoint


def compute_dealing_range(
    external_swings: list[SwingPoint],
    direction: TrendDirection,
    reference_price: float,
    config: EngineConfig,
) -> DealingRange | None:
    """Build the current dealing range from external swings.

    Args:
        external_swings: External swing points.
        direction: Active trend the range serves.
        reference_price: Price to locate (typically last close).
        config: Thresholds (``ote_fib_lower``, ``ote_fib_upper``,
            ``float_abs_tol``).

    Returns:
        The :class:`DealingRange`, or None when no valid swing pair exists.
    """
    alt = alternating_swings(external_swings)
    highs = [s for s in alt if s.swing_type is SwingType.HIGH]
    lows = [s for s in alt if s.swing_type is SwingType.LOW]
    if not highs or not lows:
        return None
    high, low = highs[-1], lows[-1]
    if high.price <= low.price:
        return None

    span = high.price - low.price
    equilibrium = (high.price + low.price) / 2
    fib_lo, fib_hi = sorted((config.ote_fib_lower, config.ote_fib_upper))
    effective = (
        direction
        if direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        else (TrendDirection.BULLISH if low.index < high.index else TrendDirection.BEARISH)
    )
    if effective is TrendDirection.BULLISH:
        ote_low = high.price - fib_hi * span
        ote_high = high.price - fib_lo * span
    else:
        ote_low = low.price + fib_lo * span
        ote_high = low.price + fib_hi * span

    if abs(reference_price - equilibrium) <= config.float_abs_tol:
        location = PriceLocation.EQUILIBRIUM
    elif reference_price > equilibrium:
        location = PriceLocation.PREMIUM
    else:
        location = PriceLocation.DISCOUNT

    return DealingRange(
        high=high.price,
        low=low.price,
        high_swing_id=high.id,
        low_swing_id=low.id,
        direction=effective,
        equilibrium=equilibrium,
        ote_low=ote_low,
        ote_high=ote_high,
        ote_fibs=(fib_lo, fib_hi),
        reference_price=reference_price,
        price_location=location,
    )


def analyze_dealing_range(
    series: CandleSeries,
    config: EngineConfig | None = None,
) -> AnalysisResult[DealingRangeResult]:
    """Run the premium/discount module over a series."""
    config = config or EngineConfig()
    scan = StructureScanner(config).run(series)
    dealing_range = compute_dealing_range(
        scan.external_swings,
        scan.external_trend,
        series.candles[-1].close,
        config,
    )
    return AnalysisResult[DealingRangeResult](
        module="premium_discount",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=DealingRangeResult(dealing_range=dealing_range),
    )
