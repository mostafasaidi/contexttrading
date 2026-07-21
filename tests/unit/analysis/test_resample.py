"""Unit tests for deterministic timeframe resampling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from contexttrading.analysis.mtf import bucket_end, bucket_start, resample_series
from contexttrading.core.constants import Timeframe
from contexttrading.core.errors import DataError
from contexttrading.models.candle import CandleSeries
from tests.fixtures import T0, make_candle, to_series


class TestAnchoring:
    @pytest.mark.parametrize(
        ("ts", "tf", "expected"),
        [
            (
                datetime(2024, 1, 1, 0, 7, tzinfo=UTC),
                Timeframe.M15,
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            ),
            (
                datetime(2024, 1, 1, 0, 16, tzinfo=UTC),
                Timeframe.M15,
                datetime(2024, 1, 1, 0, 15, tzinfo=UTC),
            ),
            (
                datetime(2024, 1, 1, 13, 45, tzinfo=UTC),
                Timeframe.H1,
                datetime(2024, 1, 1, 13, 0, tzinfo=UTC),
            ),
            (
                datetime(2024, 1, 1, 13, 45, tzinfo=UTC),
                Timeframe.H4,
                datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
            ),
            (
                datetime(2024, 1, 1, 13, 45, tzinfo=UTC),
                Timeframe.D1,
                datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
            ),
        ],
    )
    def test_epoch_aligned_buckets(self, ts: datetime, tf: Timeframe, expected: datetime) -> None:
        assert bucket_start(ts, tf) == expected

    def test_week_buckets_start_monday(self) -> None:
        # T0 (2024-01-01) is a Monday; Wednesday shares its bucket.
        monday = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        wednesday = datetime(2024, 1, 3, 15, 30, tzinfo=UTC)
        sunday = datetime(2024, 1, 7, 23, 59, tzinfo=UTC)
        next_monday = datetime(2024, 1, 8, 0, 0, tzinfo=UTC)
        assert bucket_start(monday, Timeframe.W1) == monday
        assert bucket_start(wednesday, Timeframe.W1) == monday
        assert bucket_start(sunday, Timeframe.W1) == monday
        assert bucket_start(next_monday, Timeframe.W1) == next_monday

    def test_month_buckets_start_on_the_first(self) -> None:
        assert bucket_start(datetime(2024, 1, 15, 12, tzinfo=UTC), Timeframe.MN1) == datetime(
            2024, 1, 1, tzinfo=UTC
        )
        assert bucket_start(datetime(2024, 2, 2, 12, tzinfo=UTC), Timeframe.MN1) == datetime(
            2024, 2, 1, tzinfo=UTC
        )

    def test_bucket_end_month_rollover(self) -> None:
        assert bucket_end(datetime(2024, 12, 1, tzinfo=UTC), Timeframe.MN1) == datetime(
            2025, 1, 1, tzinfo=UTC
        )
        assert bucket_end(datetime(2024, 1, 1, tzinfo=UTC), Timeframe.W1) == datetime(
            2024, 1, 8, tzinfo=UTC
        )


class TestAggregation:
    def test_ohlcv_aggregation(self) -> None:
        records = [
            make_candle(0, 10.0, 10.5, 9.8, 10.2, 100.0),
            make_candle(1, 10.2, 10.9, 10.1, 10.7, 200.0),
            make_candle(2, 10.7, 10.8, 10.3, 10.4, 300.0),
            make_candle(3, 10.4, 10.6, 10.0, 10.5, 400.0),
            make_candle(4, 10.5, 11.0, 10.4, 10.9, 500.0),
        ]
        series = to_series(records)
        out = resample_series(series, Timeframe.M5)
        assert len(out) == 1
        bar = out.candles[0]
        assert bar.timestamp == T0
        assert bar.open == 10.0
        assert bar.high == 11.0
        assert bar.low == 9.8
        assert bar.close == 10.9
        assert bar.volume == 1500.0

    def test_empty_buckets_emit_no_bars(self) -> None:
        # Candles at minutes 0..2 and 20..22: the 5m buckets at 05/10/15 are empty.
        records = [make_candle(i, 10, 10.5, 9.5, 10.2) for i in (0, 1, 2, 20, 21, 22)]
        out = resample_series(to_series(records), Timeframe.M5)
        starts = [c.timestamp for c in out]
        assert starts == [T0, T0 + timedelta(minutes=20)]

    def test_metadata_preserved(self) -> None:
        series = to_series([make_candle(i, 10, 10.5, 9.5, 10.2) for i in range(10)])
        out = resample_series(series, "5m")
        assert out.symbol == series.symbol
        assert out.timezone_name == series.timezone_name
        assert out.timeframe is Timeframe.M5

    def test_empty_series_resamples_to_empty(self) -> None:
        series = CandleSeries([], symbol="EMPTY", timeframe="1m")
        out = resample_series(series, Timeframe.H1)
        assert len(out) == 0
        assert out.timeframe is Timeframe.H1


class TestIncompleteBar:
    def test_last_bar_marks_incomplete(self) -> None:
        # 7 x 1m candles: first 5m bucket complete, second still forming.
        records = [make_candle(i, 10, 10.5, 9.5, 10.2) for i in range(7)]
        out = resample_series(to_series(records), Timeframe.M5)
        assert [c.is_closed for c in out] == [True, False]

    def test_exact_coverage_closes_last_bar(self) -> None:
        records = [make_candle(i, 10, 10.5, 9.5, 10.2) for i in range(10)]
        out = resample_series(to_series(records), Timeframe.M5)
        assert all(c.is_closed for c in out)

    def test_incomplete_bar_dropped_when_excluded(self) -> None:
        records = [make_candle(i, 10, 10.5, 9.5, 10.2) for i in range(7)]
        out = resample_series(to_series(records), Timeframe.M5, include_incomplete=False)
        assert len(out) == 1
        assert out.candles[0].is_closed


class TestResampleErrors:
    def test_upsampling_rejected(self) -> None:
        series = to_series([make_candle(i, 10, 10.5, 9.5, 10.2) for i in range(10)])
        with pytest.raises(DataError, match="strictly higher"):
            resample_series(series.resample("5m"), "1m")

    def test_same_timeframe_rejected(self) -> None:
        series = to_series([make_candle(i, 10, 10.5, 9.5, 10.2) for i in range(10)])
        with pytest.raises(DataError, match="strictly higher"):
            resample_series(series, Timeframe.M1)
