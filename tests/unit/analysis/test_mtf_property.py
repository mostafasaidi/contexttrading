"""Property-based tests (hypothesis) for deterministic resampling."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from contexttrading.analysis.mtf import bucket_end, bucket_start, resample_series
from contexttrading.core.constants import Timeframe
from contexttrading.models.candle import Candle, CandleSeries

T0 = datetime(2024, 1, 1, tzinfo=UTC)

_ohlc = st.lists(
    st.tuples(
        st.floats(min_value=100.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
    ),
    min_size=5,
    max_size=120,
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
                "volume": 10.0 + i,
            }
        )
    return CandleSeries.from_records(records, symbol="PROP", timeframe="1m")


def _members(series: CandleSeries, bar: Candle, tf: Timeframe) -> list[Candle]:
    end = bucket_end(bar.timestamp, tf)
    return [c for c in series if bar.timestamp <= c.timestamp < end]


@given(rows=_ohlc, tf=st.sampled_from([Timeframe.M5, Timeframe.M15, Timeframe.H1]))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_resample_aggregates_exactly(rows: list[tuple[float, float, float]], tf: Timeframe) -> None:
    """Every output bar is the exact first/max/min/last/sum of its members."""
    series = _to_series(rows)
    out = resample_series(series, tf)
    assert 1 <= len(out) <= len(series)
    for bar in out:
        members = _members(series, bar, tf)
        assert members, "no phantom bars: every bar has at least one member"
        assert bar.open == members[0].open
        assert bar.high == max(m.high for m in members)
        assert bar.low == min(m.low for m in members)
        assert bar.close == members[-1].close
        assert math.isclose(bar.volume, sum(m.volume for m in members), rel_tol=1e-9)


@given(rows=_ohlc, tf=st.sampled_from([Timeframe.M5, Timeframe.M15, Timeframe.H1]))
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_resample_buckets_aligned_and_ordered(
    rows: list[tuple[float, float, float]], tf: Timeframe
) -> None:
    """Bar timestamps are anchored, strictly increasing, and deduplicated."""
    series = _to_series(rows)
    out = resample_series(series, tf)
    timestamps = [c.timestamp for c in out]
    assert timestamps == sorted(set(timestamps))
    for ts in timestamps:
        assert bucket_start(ts, tf) == ts


@given(rows=_ohlc)
@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_only_last_bar_may_be_incomplete(rows: list[tuple[float, float, float]]) -> None:
    series = _to_series(rows)
    out = resample_series(series, Timeframe.M15)
    flags = [c.is_closed for c in out]
    assert all(flags[:-1]), "mid-series bars are always complete"
