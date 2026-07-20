"""Property-based tests (hypothesis) for swing detection and ID stability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from contexttrading.analysis.structure.swings import detect_swings
from contexttrading.core.constants import SwingClass, SwingType
from contexttrading.models.candle import CandleSeries

T0 = datetime(2024, 1, 1, tzinfo=UTC)

# Valid OHLC candles with strictly positive prices:
# base >= 100, wicks <= 20 → low >= 100 - 5 - 20 > 0 always.
_ohlc = st.lists(
    st.tuples(
        st.floats(min_value=100.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    ),
    min_size=11,
    max_size=40,
)


def _to_series(rows: list[tuple[float, float, float]]) -> CandleSeries:
    records = []
    for i, (base, up, down) in enumerate(rows):
        o = base
        c = base + (up - down) / 4
        records.append(
            {
                "timestamp": (T0 + timedelta(minutes=i)).isoformat(),
                "open": o,
                "high": max(o, c) + up,
                "low": min(o, c) - down,
                "close": c,
                "volume": 100.0,
            }
        )
    return CandleSeries.from_records(records, symbol="PROP", timeframe="1m")


@given(rows=_ohlc, lookback=st.integers(min_value=1, max_value=4))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_same_type_swings_respect_lookback_spacing(
    rows: list[tuple[float, float, float]], lookback: int
) -> None:
    """Two swing highs can never be closer than `lookback` bars (nor lows)."""
    series = _to_series(rows)
    swings = detect_swings(series, lookback, SwingClass.INTERNAL)
    for swing_type in (SwingType.HIGH, SwingType.LOW):
        indices = sorted(s.index for s in swings if s.swing_type is swing_type)
        for a, b in pairwise(indices):
            assert b - a >= lookback


@given(rows=_ohlc)
@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_swings_are_local_extremes(rows: list[tuple[float, float, float]]) -> None:
    """Every detected swing strictly dominates its lookback neighborhood."""
    series = _to_series(rows)
    lookback = 2
    candles = series.candles
    for swing in detect_swings(series, lookback, SwingClass.INTERNAL):
        i = swing.index
        for j in range(i - lookback, i + lookback + 1):
            if j == i:
                continue
            if swing.swing_type is SwingType.HIGH:
                assert candles[i].high > candles[j].high
            else:
                assert candles[i].low < candles[j].low


@given(rows=_ohlc)
@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_swing_ids_stable_across_reruns(rows: list[tuple[float, float, float]]) -> None:
    """Identical input → identical IDs (determinism contract)."""
    series = _to_series(rows)
    first = [s.id for s in detect_swings(series, 2, SwingClass.INTERNAL)]
    second = [s.id for s in detect_swings(series, 2, SwingClass.INTERNAL)]
    assert first == second


@given(rows=_ohlc)
@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_swing_indices_within_confirmable_range(rows: list[tuple[float, float, float]]) -> None:
    """No swings in the first/last `lookback` bars (unconfirmed region)."""
    series = _to_series(rows)
    lookback = 3
    swings = detect_swings(series, lookback, SwingClass.EXTERNAL)
    assert all(lookback <= s.index < len(series) - lookback for s in swings)
