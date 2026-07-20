"""Tests for models.outputs: DataWindow and AnalysisResult envelope."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError as PydanticValidationError

from contexttrading import __version__
from contexttrading.core.constants import Timeframe
from contexttrading.models.base import VersionedModel
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow


class DummyResult(VersionedModel):
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    count: int


def make_window(series: CandleSeries) -> DataWindow:
    return DataWindow(start=series.start, end=series.end, candle_count=len(series))


class TestDataWindow:
    def test_valid(self, series: CandleSeries) -> None:
        window = make_window(series)
        assert window.candle_count == 10
        assert window.start <= window.end

    def test_end_before_start_rejected(self, series: CandleSeries) -> None:
        with pytest.raises(PydanticValidationError, match=r"end .* must be >= start"):
            DataWindow(start=series.end, end=series.start, candle_count=10)

    def test_negative_count_rejected(self, series: CandleSeries) -> None:
        with pytest.raises(PydanticValidationError):
            DataWindow(start=series.start, end=series.end, candle_count=-1)

    def test_naive_timestamps_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            DataWindow(
                start="2024-01-01T00:00:00",
                end="2024-01-01T01:00:00",
                candle_count=60,
            )


class TestAnalysisResult:
    def test_envelope_shape(self, series: CandleSeries) -> None:
        result = AnalysisResult[DummyResult](
            module="structure",
            symbol="ES",
            timeframe=Timeframe.M15,
            generated_from=make_window(series),
            payload=DummyResult(count=3),
        )
        assert result.schema_version == "1.0.0"
        assert result.engine_version == __version__
        assert result.payload.count == 3
        assert result.run_id is None

    def test_timeframe_coerced_from_string(self, series: CandleSeries) -> None:
        result = AnalysisResult[DummyResult](
            module="fvg",
            symbol="ES",
            timeframe="15m",
            generated_from=make_window(series),
            payload=DummyResult(count=0),
        )
        assert result.timeframe is Timeframe.M15

    def test_serializes_to_json(self, series: CandleSeries) -> None:
        import json

        result = AnalysisResult[DummyResult](
            module="fvg",
            symbol="ES",
            timeframe="5m",
            generated_from=make_window(series),
            payload=DummyResult(count=1),
            run_id="run_abc123",
        )
        dumped = json.loads(result.model_dump_json())
        assert dumped["timeframe"] == "5m"
        assert dumped["payload"]["schema_version"] == "1.0.0"
        assert dumped["run_id"] == "run_abc123"

    def test_deterministic_serialization(self, series: CandleSeries) -> None:
        kwargs = {
            "module": "structure",
            "symbol": "ES",
            "timeframe": "1m",
            "generated_from": make_window(series),
            "payload": DummyResult(count=2),
        }
        a = AnalysisResult[DummyResult](**kwargs)
        b = AnalysisResult[DummyResult](**kwargs)
        assert a.model_dump_json() == b.model_dump_json()

    def test_summary(self, series: CandleSeries) -> None:
        result = AnalysisResult[DummyResult](
            module="confluence",
            symbol="NQ",
            timeframe="1h",
            generated_from=make_window(series),
            payload=DummyResult(count=9),
        )
        summary = result.summary()
        assert summary["module"] == "confluence"
        assert summary["payload_type"] == "DummyResult"
        assert summary["engine_version"] == __version__

    def test_empty_module_or_symbol_rejected(self, series: CandleSeries) -> None:
        with pytest.raises(PydanticValidationError):
            AnalysisResult[DummyResult](
                module="",
                symbol="ES",
                timeframe="1m",
                generated_from=make_window(series),
                payload=DummyResult(count=0),
            )
