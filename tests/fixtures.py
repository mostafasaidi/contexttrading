"""Hand-crafted deterministic candle fixtures for analysis tests.

All builders produce reproducible series (no randomness, no wall-clock) so
unit and regression tests assert exact engine behavior.
"""

from __future__ import annotations

import math
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
    bar_minutes: int = 1,
) -> list[dict[str, Any]]:
    """Linear zig-zag series through pivot closes.

    Pivot ``k`` sits at index ``k * leg_bars``; each leg is interpolated into
    ``leg_bars`` candles. Every bar gets ``+wick``/``-wick`` extremes, so
    pivot bars are strict local extremes for lookbacks <= ``leg_bars - 1``.
    Bars are ``bar_minutes`` apart (default 1m).
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
        records.append(
            {
                "timestamp": (T0 + timedelta(minutes=i * bar_minutes)).isoformat(),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": volume,
            }
        )
    return records


def zigzag_series(
    pivots: list[float],
    leg_bars: int = 4,
    wick: float = 0.05,
    symbol: str = "TEST",
    volume: float = 100.0,
    bar_minutes: int = 1,
) -> CandleSeries:
    """CandleSeries variant of :func:`zigzag_records`."""
    return CandleSeries.from_records(
        zigzag_records(pivots, leg_bars, wick, volume, bar_minutes),
        symbol=symbol,
        timeframe=f"{bar_minutes}m",
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


def long_news_spike_series(count: int = 80, spike_index: int = 40) -> CandleSeries:
    """Full-length (>= min_candles) zigzag with one huge range+volume candle.

    The short :func:`news_spike_series` predates the 50-candle scanner
    minimum; this variant lets the whole module stack process a news event.
    """
    pivots = [10 + (i % 4) * 0.4 for i in range(count // 4 + 2)]
    records = zigzag_records(pivots, leg_bars=4, volume=100.0)[:count]
    base = records[spike_index]
    mid = (base["high"] + base["low"]) / 2
    records[spike_index] = make_candle(spike_index, mid, mid * 1.25, mid * 0.8, mid * 1.2, 5000.0)
    return to_series(records, symbol="NEWS")


def low_liquidity_series(count: int = 80) -> CandleSeries:
    """Thin market: tiny ranges, near-zero sparse volume, slow drift.

    Distinct from :func:`flat_series` (identical OHLC, zero volume): prices
    move a little and volume is sporadic, exercising near-zero ATR and
    volume guards without the fully degenerate shape.
    """
    records = []
    price = 100.0
    for i in range(count):
        drift = 0.01 if i % 3 else -0.01
        o, c = price, price + drift
        h = max(o, c) + 0.005
        lo = min(o, c) - 0.005
        v = 1.0 if i % 5 else 7.0  # sporadic prints
        records.append(make_candle(i, o, h, lo, c, v))
        price = c
    return to_series(records, symbol="THIN")


# --- Phase 6: sessions / MTF fixtures (15-minute multi-day series) ------------

M15_SECONDS = 15 * 60

#: Clean 15m zigzag uptrend (leg_bars=16) used by MTF tests and goldens.
MTF_UPTREND_PIVOTS: list[float] = [10, 14, 12, 16, 14, 18, 16, 20, 18, 22, 20, 24, 22, 21]


def make_candle_15m(i: int, o: float, h: float, low: float, c: float, v: float = 100.0):
    """One 15-minute candle record (index i from T0)."""
    return {
        "timestamp": (T0 + timedelta(minutes=15 * i)).isoformat(),
        "open": o,
        "high": h,
        "low": low,
        "close": c,
        "volume": v,
    }


def five_day_15m_records() -> list[dict[str, Any]]:
    """Five days of 15m candles (480 bars) with a deterministic wave path.

    Composite of three sine drivers plus a slow drift — no randomness, so
    session statistics and MTF context are golden-stable. T0 is a Monday.
    """
    records = []
    price = 100.0
    for i in range(5 * 96):
        drift = 0.03 + 0.25 * math.sin(i / 9.0) + 0.18 * math.sin(i / 41.0)
        o = price
        c = price + drift
        h = max(o, c) + 0.07 + 0.05 * abs(math.sin(i / 5.0))
        low = min(o, c) - 0.07 - 0.05 * abs(math.cos(i / 7.0))
        records.append(make_candle_15m(i, o, h, low, c, 100.0 + 20.0 * abs(math.sin(i / 3.0))))
        price = c
    return records


def five_day_15m_series(symbol: str = "SESS") -> CandleSeries:
    """CandleSeries variant of :func:`five_day_15m_records`."""
    return CandleSeries.from_records(five_day_15m_records(), symbol=symbol, timeframe="15m")


def judas_15m_records() -> list[dict[str, Any]]:
    """Two days of 15m candles with a London-killzone sweep of the Asian high.

    Day 2 Asian range (21:00 day 1 to 07:00 day 2) prints its high 104.6 at
    02:00 (i=104). At 07:15 (i=125) — inside the London killzone — a candle
    wicks to 105.2 and closes at 104.2: a sweep of the Asian high during
    the London killzone, i.e. a Judas swing. London then sells off.
    """
    records: list[dict[str, Any]] = []
    # Day 1 (i 0..95): gentle drift 99.5 -> ~101.4, all below 101.6.
    price = 99.5
    for i in range(96):
        o = price
        c = price + (0.03 if i % 3 else -0.01)
        records.append(make_candle_15m(i, o, max(o, c) + 0.05, min(o, c) - 0.05, c))
        price = c
    # Day 2 Asian range (i 96..123): oscillate inside 103.5-104.5.
    path = [
        103.8,
        103.6,
        103.7,
        103.9,
        104.2,
        104.4,
        104.1,
        103.9,
        103.7,
        103.8,
        104.0,
        104.3,
        104.4,
        104.2,
        104.0,
        103.8,
        103.6,
        103.7,
        103.9,
        104.1,
        104.3,
        104.4,
        104.2,
        104.0,
        103.9,
        103.8,
        104.0,
        104.2,
    ]
    for k, close in enumerate(path):
        i = 96 + k
        o = path[k - 1] if k else 103.8
        h = max(o, close) + 0.1
        low = min(o, close) - 0.1
        if i == 104:  # 02:00 — Asian high prints here (unique extreme)
            h = 104.6
        records.append(make_candle_15m(i, o, h, low, close))
    # London (i 124..159): sweep at 07:15, then sell off to ~102.6.
    records.append(make_candle_15m(124, 104.2, 104.3, 103.9, 104.0))
    records.append(make_candle_15m(125, 104.0, 105.2, 103.9, 104.2))  # Judas sweep
    price = 104.2
    for i in range(126, 160):
        o = price
        c = price - 0.05
        records.append(make_candle_15m(i, o, max(o, c) + 0.04, min(o, c) - 0.04, c))
        price = c
    # New York (i 160..191): sideways drift, stays below the London high.
    for i in range(160, 192):
        o = price
        c = price + (0.02 if i % 2 else -0.02)
        records.append(make_candle_15m(i, o, max(o, c) + 0.04, min(o, c) - 0.04, c))
        price = c
    return records


def judas_15m_series(symbol: str = "JUDAS") -> CandleSeries:
    """CandleSeries variant of :func:`judas_15m_records`."""
    return CandleSeries.from_records(judas_15m_records(), symbol=symbol, timeframe="15m")


def full_stack_results(
    series: CandleSeries,
    config: EngineConfig | None = None,
    *,
    mtf_timeframes: tuple[str, ...] = ("1h", "4h"),
) -> dict[str, Any]:
    """Run every analysis module over a series; results keyed by module name.

    Delegates to ``analysis.pipeline.run_full_stack`` — the same
    orchestration the API layer uses, so tests and service agree.
    """
    from contexttrading.analysis.pipeline import run_full_stack

    return run_full_stack(series, config or EngineConfig(), mtf_timeframes=mtf_timeframes)
