"""Tests for analysis.indicators: ATR, relative volume, z-scores."""

from __future__ import annotations

import pytest

from contexttrading.analysis.indicators import (
    atr,
    latest_atr,
    prior_rolling_mean,
    prior_rolling_std,
    relative_volumes,
    rolling_mean,
    true_ranges,
    volume_imbalance_flags,
    volume_zscores,
)
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import Candle


def make_candle(i: int, o: float, h: float, low: float, c: float, v: float = 100.0) -> Candle:
    return Candle(
        timestamp=f"2024-01-01T00:{i:02d}:00Z",
        open=o,
        high=h,
        low=low,
        close=c,
        volume=v,
    )


class TestTrueRanges:
    def test_first_candle_is_range(self) -> None:
        candles = [make_candle(0, 10, 12, 9, 11)]
        assert true_ranges(candles) == (3.0,)

    def test_gaps_count(self) -> None:
        candles = [
            make_candle(0, 10, 11, 9, 10),  # TR = 2
            make_candle(1, 12, 13, 11.5, 12.5),  # max(1.5, 3, 1.5) = 3
            make_candle(2, 12, 12.5, 11, 11.5),  # max(1.5, 0.5, 1.5) = 1.5
        ]
        assert true_ranges(candles) == (2.0, 3.0, 1.5)

    def test_empty(self) -> None:
        assert true_ranges(()) == ()


class TestAtr:
    def test_constant_range(self) -> None:
        candles = [make_candle(i, 10, 11, 9, 10) for i in range(10)]
        values = atr(candles, 5)
        assert values[:4] == (None, None, None, None)
        assert values[4] == pytest.approx(2.0)
        assert values[-1] == pytest.approx(2.0)  # constant TR ⇒ ATR stays 2

    def test_wilder_smoothing(self) -> None:
        # TRs: 1,1,1,1,1 then a 10 spike; period 3.
        tr_pattern = [(10, 11, 10, 10.5)] * 3 + [(10, 20, 10, 15)]
        candles = [make_candle(i, o, h, low, c) for i, (o, h, low, c) in enumerate(tr_pattern)]
        values = atr(candles, 3)
        first = values[2]
        assert first is not None
        # TRs: c0: 1.0 ; c1: max(1, .5, .5)=1 ; c2: 1 ; c3: max(10, 9.5, .5)=10
        assert first == pytest.approx(1.0)
        assert values[3] == pytest.approx((first * 2 + 10) / 3)

    def test_period_one(self) -> None:
        candles = [make_candle(i, 10, 12, 9, 10) for i in range(4)]
        values = atr(candles, 1)
        assert all(v == pytest.approx(3.0) for v in values if v is not None)
        assert values[0] == pytest.approx(3.0)

    def test_short_series_all_none(self) -> None:
        candles = [make_candle(i, 10, 11, 9, 10) for i in range(3)]
        assert atr(candles, 14) == (None, None, None)

    def test_invalid_period(self) -> None:
        with pytest.raises(ValueError):
            atr([], 0)

    def test_latest_atr(self) -> None:
        candles = [make_candle(i, 10, 11, 9, 10) for i in range(20)]
        assert latest_atr(candles, 14) == pytest.approx(2.0)

    def test_latest_atr_insufficient(self) -> None:
        candles = [make_candle(i, 10, 11, 9, 10) for i in range(5)]
        with pytest.raises(InsufficientDataError) as excinfo:
            latest_atr(candles, 14)
        assert excinfo.value.code == "CT-3001"


class TestRollingStats:
    def test_rolling_mean(self) -> None:
        assert rolling_mean([1.0, 2.0, 3.0, 4.0], 2) == (None, 1.5, 2.5, 3.5)

    def test_prior_mean_no_lookahead(self) -> None:
        # out[i] must not include values[i]
        assert prior_rolling_mean([1.0, 3.0, 100.0], 2) == (None, None, 2.0)

    def test_prior_std_population(self) -> None:
        stds = prior_rolling_std([2.0, 4.0, 6.0], 2)
        assert stds[0] is None and stds[1] is None
        assert stds[2] == pytest.approx(1.0)  # std of [2,4]


class TestVolumeAnalytics:
    def test_relative_volume(self) -> None:
        candles = [make_candle(i, 10, 11, 9, 10, v) for i, v in enumerate([100, 100, 100, 300])]
        rel = relative_volumes(candles, 2)
        assert rel[:2] == (None, None)
        assert rel[2] == pytest.approx(1.0)
        assert rel[3] == pytest.approx(3.0)

    def test_relative_volume_zero_mean(self) -> None:
        candles = [make_candle(i, 10, 11, 9, 10, 0.0) for i in range(4)]
        assert relative_volumes(candles, 2) == (None, None, None, None)

    def test_zscore_flags(self) -> None:
        volumes = [100.0] * 9 + [100.0, 1000.0]
        candles = [make_candle(i % 60, 10, 11, 9, 10, v) for i, v in enumerate(volumes)]
        zscores = volume_zscores(candles, 10)
        assert zscores[10] is None  # flat prior window → std 0 → None
        flags = volume_imbalance_flags(candles, 10, 2.0)
        assert flags[10] is False

    def test_zscore_spike_detected(self) -> None:
        volumes = [90.0, 110.0, 95.0, 105.0, 100.0] * 4 + [1000.0]
        candles = [make_candle(i % 60, 10, 11, 9, 10, v) for i, v in enumerate(volumes)]
        zscores = volume_zscores(candles, 20)
        assert zscores[-1] is not None and zscores[-1] > 2.0
        flags = volume_imbalance_flags(candles, 20, 2.0)
        assert flags[-1] is True
        assert all(f is False for f in flags[:-1])

    def test_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            volume_imbalance_flags([], 5, 0.0)
