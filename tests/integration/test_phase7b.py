"""Phase 7b integration: full pipeline -> chart payload -> store round-trip.

Runs the complete analysis stack over the shared 2000-candle dataset and
verifies the visualization contract end to end: styled objects produce
primitives, output is byte-deterministic, JSON-serializable, and survives
the SQLite store.
"""

from __future__ import annotations

import json

from contexttrading.data.store import ResultStore, hash_series
from contexttrading.visualization import build_chart_payload
from tests.fixtures import full_stack_results
from tests.integration.test_pipeline import _dataset


class TestPhase7bPipeline:
    def test_full_pipeline_produces_primitives(self) -> None:
        series = _dataset()
        results = full_stack_results(series)
        chart = build_chart_payload(series, results).payload
        assert len(chart.candles) == len(series)
        assert len(chart.volume) == len(series)
        total = sum(len(layer.primitives) for layer in chart.layers)
        assert total > 0, "styled analysis objects must produce primitives"
        # Every non-empty layer carries typed, colored primitives.
        for layer in chart.layers:
            for prim in layer.primitives:
                assert prim.color.startswith("#")
                assert prim.layer == layer.name

    def test_byte_identical_reruns(self) -> None:
        series = _dataset()
        first = build_chart_payload(series, full_stack_results(series)).model_dump_json()
        second = build_chart_payload(series, full_stack_results(series)).model_dump_json()
        assert first == second

    def test_payload_json_serializable(self) -> None:
        series = _dataset()
        chart = build_chart_payload(series, full_stack_results(series))
        parsed = json.loads(chart.model_dump_json())
        assert parsed["module"] == "chart"
        assert parsed["payload"]["layers"]

    def test_store_round_trip(self, tmp_path) -> None:
        series = _dataset()
        chart = build_chart_payload(series, full_stack_results(series))
        digest = hash_series(series)
        with ResultStore(tmp_path / "results.db") as store:
            store.save(chart, digest)
            loaded = store.load(series.symbol, str(series.timeframe), "chart", digest)
        assert loaded == chart
