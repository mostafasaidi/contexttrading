"""Hand-crafted deterministic candle fixtures for analysis tests.

All builders produce reproducible series (no randomness, no wall-clock) so
unit and regression tests assert exact engine behavior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

from contexttrading.core.config import EngineConfig
from contexttrading.models.candle import CandleSeries

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def engine_config(**overrides: Any) -> EngineConfig:
    """Small-scale config for hand-crafted fixtures."""
    base: dict[str, Any] = {
        "min_candles": 5,
        "internal_swing_lookback": 2,
        "external_swing_lookback": 3,
        "atr_period": 3,
        "equal_level_min_separation": 2,
    }
    base.update(overrides)
    return EngineConfig(**base)


def make_candle(
    i: int, o: float, h: float, low: float, c: float, v: float = 100.0
) -> dict[str, Any]:
    """One 1-minute candle record."""
    return {
        "timestamp": (T0 + timedelta(minutes=i)).isoformat(),
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": v,
    }


def zigzag_records(
    pivots: list[float],
    leg_bars: int = 4,
    wick: float = 0.05,
    volume: float = 100.0,
) -> list[dict[str, Any]]:
    """Linear zig-zag series through pivot closes.

    Pivot ``k`` sits at index ``k * leg_bars``; each leg is interpolated into
    ``leg_bars`` candles. Every bar gets ``+wick``/``-wick`` extremes, so
    pivot bars are strict local extremes for lookbacks <= ``leg_bars - 1``.
    """
    closes = [pivots[0]]
    for a, b in pairwise(pivots):
        for k in range(1, leg_bars + 1):
            closes.append(a + (b - a) * k / leg_bars)
    records = []
    for i, c in enumerate(closes):
        o = closes[i - 1] if i > 0 else c
        # Asymmetric wicks: full wick on the close side, small on the open
        # side — otherwise the bar after a pivot (which opens at the pivot
        # close) would tie the pivot's extreme and void the fractal rule.
        if c >= o:
            h, lo = c + wick, o - wick * 0.2
        else:
            h, lo = o + wick * 0.2, c - wick
        records.append(make_candle(i, o, h, lo, c, volume))
    return records


def zigzag_series(
    pivots: list[float],
    leg_bars: int = 4,
    wick: float = 0.05,
    symbol: str = "TEST",
    volume: float = 100.0,
) -> CandleSeries:
    """CandleSeries variant of :func:`zigzag_records`."""
    return CandleSeries.from_records(
        zigzag_records(pivots, leg_bars, wick, volume), symbol=symbol, timeframe="1m"
    )


def flat_series(count: int = 30, price: float = 100.0) -> CandleSeries:
    """Completely flat candles (low-liquidity scenario)."""
    records = [make_candle(i, price, price, price, price, 0.0) for i in range(count)]
    return CandleSeries.from_records(records, symbol="FLAT", timeframe="1m")


def to_series(records: list[dict[str, Any]], symbol: str = "TEST") -> CandleSeries:
    """Wrap records into a 1m CandleSeries."""
    return CandleSeries.from_records(records, symbol=symbol, timeframe="1m")


# --- Named scenarios ---------------------------------------------------------


def uptrend_series() -> CandleSeries:
    """Clean uptrend: higher highs/lows, two bullish BOS events.

    Pivots: 10 → 15 → 12 → 17 → 14 → 19 → 16 → 18 (leg_bars=4).
    External swings: H15@4, L12@8, H17@12, L14@16, H19@20, L16@24.
    Expected: BOS at idx11 (above 15.05) and idx19 (above 17.05),
    protected_low = L14@16 (13.95), trend BULLISH.
    """
    return zigzag_series([10, 15, 12, 17, 14, 19, 16, 18])


def downtrend_series() -> CandleSeries:
    """Clean downtrend: mirrored bearish structure."""
    return zigzag_series([20, 15, 18, 13, 16, 11, 14, 12])


def v_reversal_series() -> CandleSeries:
    """Uptrend then sharp breakdown through the protected low (CHoCH).

    Pivots: 10 → 15 → 12 → 17 → 14 → 9 → 9.5.
    Expected: BOS at idx11 (above 15.05, protected L12=11.95),
    CHoCH bearish when closes fall below 11.95 during the 14 → 9 leg (idx18).
    """
    return zigzag_series([10, 15, 12, 17, 14, 9, 9.5])


def ranging_series() -> CandleSeries:
    """Sideways oscillation between ~10 and ~11 (no extremes break)."""
    return zigzag_series([10.5, 11.0, 10.2, 10.9, 10.3, 10.8, 10.4, 10.7, 10.5])


def fakeout_records() -> list[dict[str, Any]]:
    """Uptrend with a wick-only breach of the last high (false BOS).

    Base zig-zag 10 → 15 → 12 → 16 → 14, then two hand-crafted bars:
    bar 20 wicks above 16.05 (high 16.3) but closes at 15.7 (FALSE break),
    bar 21 drifts down. The false break links the H16 pool as STOP_HUNT.
    """
    records = zigzag_records([10, 15, 12, 16, 14, 15.5])
    records[20] = make_candle(20, 15.5, 16.3, 15.4, 15.7)  # wick above 16.05, close below
    records.append(make_candle(21, 15.7, 15.8, 14.9, 15.0))
    return records


def news_spike_series() -> CandleSeries:
    """Quiet series with one huge range+volume candle."""
    records = zigzag_records([10, 10.5, 10.2, 10.6, 10.4], leg_bars=4, volume=100.0)
    records[10] = make_candle(10, 10.5, 13.0, 10.0, 12.5, 5000.0)  # news spike
    return to_series(records, symbol="NEWS")
