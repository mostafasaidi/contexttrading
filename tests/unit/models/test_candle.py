"""Tests for models.candle: Candle validation and CandleSeries behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError as PydanticValidationError

from contexttrading.core.constants import Timeframe, TrendDirection
from contexttrading.core.errors import DataError, DataGapError
from contexttrading.models.candle import Candle, CandleSeries, GapWindow
from tests.conftest import make_records

TS = "2024-01-01T09:30:00Z"
VALID = {
    "timestamp": TS,
    "open": 100.0,
    "high": 101.0,
    "low": 99.0,
    "close": 100.5,
    "volume": 500.0,
}


class TestCandleValidation:
    def test_valid_candle(self) -> None:
        candle = Candle(**VALID)
        assert candle.timestamp.tzinfo is not None
        assert candle.timestamp.utcoffset() == timedelta(0)
        assert candle.is_closed is True

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            Candle(**{**VALID, "timestamp": "2024-01-01T09:30:00"})

    def test_non_utc_timestamp_normalized(self) -> None:
        candle = Candle(**{**VALID, "timestamp": "2024-01-01T10:30:00+01:00"})
        assert candle.timestamp == datetime(2024, 1, 1, 9, 30, tzinfo=UTC)

    def test_high_below_open_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match=r"high .* must be >= max"):
            Candle(**{**VALID, "high": 99.5})

    def test_high_below_close_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match=r"high .* must be >= max"):
            Candle(**{**VALID, "open": 102.0, "high": 101.0, "close": 102.0, "low": 99.0})

    def test_low_above_close_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match=r"low .* must be <= min"):
            Candle(**{**VALID, "low": 100.6})

    def test_negative_volume_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            Candle(**{**VALID, "volume": -1.0})

    def test_zero_volume_allowed(self) -> None:
        assert Candle(**{**VALID, "volume": 0.0}).volume == 0.0

    @pytest.mark.parametrize("field", ["open", "high", "low", "close"])
    def test_nonpositive_prices_rejected(self, field: str) -> None:
        with pytest.raises(PydanticValidationError):
            Candle(**{**VALID, field: 0.0})

    def test_frozen(self) -> None:
        candle = Candle(**VALID)
        with pytest.raises(PydanticValidationError):
            candle.close = 1.0

    def test_optional_tick_metadata(self) -> None:
        candle = Candle(**{**VALID, "tick_count": 42})
        assert candle.tick_count == 42

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(PydanticValidationError):
            Candle(**{**VALID, "exchange": "CME"})


class TestCandleDerived:
    def test_body_range_midpoint(self) -> None:
        candle = Candle(**VALID)
        assert candle.body == pytest.approx(0.5)
        assert candle.range == pytest.approx(2.0)
        assert candle.midpoint == pytest.approx(100.0)

    @pytest.mark.parametrize(
        ("open_", "close", "expected"),
        [
            (100.0, 100.5, TrendDirection.BULLISH),
            (100.5, 100.0, TrendDirection.BEARISH),
            (100.0, 100.0, TrendDirection.RANGING),
        ],
    )
    def test_direction(self, open_: float, close: float, expected: TrendDirection) -> None:
        candle = Candle(
            timestamp=TS,
            open=open_,
            high=max(open_, close) + 0.1,
            low=min(open_, close) - 0.1,
            close=close,
            volume=1.0,
        )
        assert candle.direction is expected
        assert candle.is_bullish is (expected is TrendDirection.BULLISH)


class TestCandleSeries:
    def test_from_records_sorts_by_timestamp(self) -> None:
        records = make_records(5)
        records.reverse()
        series = CandleSeries.from_records(records, symbol="TEST", timeframe="1m")
        timestamps = [c.timestamp for c in series]
        assert timestamps == sorted(timestamps)

    def test_duplicate_timestamps_rejected(self) -> None:
        records = make_records(3)
        records.append(dict(records[0]))
        with pytest.raises(DataError, match="Duplicate candle timestamps"):
            CandleSeries.from_records(records, symbol="TEST", timeframe="1m")

    def test_invalid_record_wrapped_in_data_error(self) -> None:
        records = make_records(2)
        records.append({"timestamp": TS, "open": -1, "high": 1, "low": 0, "close": 1, "volume": 1})
        with pytest.raises(DataError, match="Invalid candle record"):
            CandleSeries.from_records(records, symbol="TEST", timeframe="1m")

    def test_empty_symbol_rejected(self, series: CandleSeries) -> None:
        with pytest.raises(DataError):
            CandleSeries(series.candles, symbol="", timeframe="1m")

    def test_metadata(self, series: CandleSeries) -> None:
        assert series.symbol == "TEST"
        assert series.timeframe is Timeframe.M1
        assert series.timezone_name == "UTC"
        assert len(series) == 10
        assert series.start is not None and series.end is not None
        assert series.start < series.end

    def test_string_timeframe_parsed(self, candle_records) -> None:
        series = CandleSeries.from_records(candle_records, symbol="T", timeframe="15m")
        assert series.timeframe is Timeframe.M15

    def test_iteration_and_indexing(self, series: CandleSeries) -> None:
        first = series[0]
        assert isinstance(first, Candle)
        assert next(iter(series)) == first
        assert series[-1] == series.candles[-1]

    def test_slice_returns_series(self, series: CandleSeries) -> None:
        window = series[2:5]
        assert isinstance(window, CandleSeries)
        assert len(window) == 3
        assert window.symbol == series.symbol
        assert window.timeframe == series.timeframe

    def test_between_inclusive_bounds(self, series: CandleSeries) -> None:
        start = series[3].timestamp
        end = series[6].timestamp
        window = series.between(start, end)
        assert len(window) == 4
        assert window.start == start and window.end == end

    def test_between_open_bounds(self, series: CandleSeries) -> None:
        assert len(series.between()) == len(series)
        assert len(series.between(start=series[8].timestamp)) == 2
        assert len(series.between(end=series[1].timestamp)) == 2

    def test_between_naive_datetimes_interpreted_as_utc(self, series: CandleSeries) -> None:
        naive = series[3].timestamp.replace(tzinfo=None)
        assert series.between(start=naive).start == series[3].timestamp

    def test_equality(self, candle_records) -> None:
        a = CandleSeries.from_records(candle_records, symbol="TEST", timeframe="1m")
        b = CandleSeries.from_records(candle_records, symbol="TEST", timeframe="1m")
        c = CandleSeries.from_records(candle_records, symbol="OTHER", timeframe="1m")
        assert a == b
        assert a != c
        assert a != "not a series"

    def test_repr(self, series: CandleSeries) -> None:
        assert "TEST" in repr(series) and "1m" in repr(series)


class TestGaps:
    def test_gap_free_series(self, series: CandleSeries) -> None:
        assert series.gaps() == []
        series.require_gap_free()  # no raise

    def test_gap_detected(self) -> None:
        records = make_records(3) + make_records(
            2, start="2024-01-01T00:10:00Z"  # 7-minute hole after candle 3
        )
        series = CandleSeries.from_records(records, symbol="TEST", timeframe="1m")
        gaps = series.gaps()
        assert len(gaps) == 1
        gap = gaps[0]
        assert isinstance(gap, GapWindow)
        assert gap.missing_candles == 7  # candles expected at minutes 3..9
        assert gap.start == series[2].timestamp
        assert gap.end == series[3].timestamp

    def test_require_gap_free_raises(self) -> None:
        records = make_records(2) + make_records(1, start="2024-01-01T00:05:00Z")
        series = CandleSeries.from_records(records, symbol="TEST", timeframe="1m")
        with pytest.raises(DataGapError) as excinfo:
            series.require_gap_free()
        assert excinfo.value.code == "CT-1001"
        assert excinfo.value.context["gap_count"] == 1

    def test_tolerance_validation(self, series: CandleSeries) -> None:
        with pytest.raises(ValueError):
            series.gaps(tolerance=0.5)

    def test_tolerance_suppresses_small_gaps(self) -> None:
        records = make_records(2) + make_records(1, start="2024-01-01T00:02:30Z")
        series = CandleSeries.from_records(records, symbol="TEST", timeframe="1m")
        assert series.gaps(tolerance=1.5) == []  # 90s < 1.5 * 60s... adjusted below
        assert series.gaps(tolerance=3.0) == []

    def test_empty_series(self) -> None:
        series = CandleSeries([], symbol="TEST", timeframe="1m")
        assert len(series) == 0
        assert series.start is None and series.end is None
        assert series.gaps() == []


class TestResampleContract:
    def test_resample_upsampling_rejected(self, series: CandleSeries) -> None:
        with pytest.raises(DataError, match="strictly higher"):
            series.resample(series.timeframe)

    def test_resample_delegates_to_mtf(self, series: CandleSeries) -> None:
        resampled = series.resample(Timeframe.M5)
        assert resampled.timeframe is Timeframe.M5
        assert resampled.symbol == series.symbol

    def test_resample_accepts_string(self, series: CandleSeries) -> None:
        assert series.resample("5m").timeframe is Timeframe.M5


class TestSerialization:
    def test_to_records_round_trip(self, series: CandleSeries) -> None:
        records = series.to_records()
        rebuilt = CandleSeries.from_records(records, symbol="TEST", timeframe="1m")
        assert rebuilt == series

    def test_records_are_json_ready(self, series: CandleSeries) -> None:
        import json

        json.dumps(series.to_records())  # must not raise
