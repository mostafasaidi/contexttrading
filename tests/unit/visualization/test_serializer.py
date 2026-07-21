"""Unit tests for the chart payload serializer."""

from __future__ import annotations

import json

from contexttrading.core.config import VisualizationConfig
from contexttrading.visualization.primitives import to_unix_seconds
from contexttrading.visualization.serializer import (
    LAYER_SPECS,
    THEMES,
    build_chart_payload,
)
from tests.fixtures import engine_config, full_stack_results, uptrend_series


def _chart(config: VisualizationConfig | None = None):
    series = uptrend_series()
    results = full_stack_results(series, engine_config())
    return series, build_chart_payload(series, results, config)


class TestEnvelope:
    def test_module_and_window(self) -> None:
        series, chart = _chart()
        assert chart.module == "chart"
        assert chart.symbol == series.symbol
        assert chart.generated_from.candle_count == len(series)
        assert chart.payload.symbol == series.symbol

    def test_json_serializable(self) -> None:
        _, chart = _chart()
        json.loads(chart.model_dump_json())  # must not raise


class TestCandlesAndVolume:
    def test_candle_times_are_seconds(self) -> None:
        series, chart = _chart()
        assert len(chart.payload.candles) == len(series)
        for candle, source in zip(chart.payload.candles, series.candles, strict=True):
            assert candle.time == to_unix_seconds(source.timestamp)
            assert candle.time < 10**12
            assert candle.open == source.open
            assert candle.close == source.close

    def test_volume_colored_by_direction(self) -> None:
        series, chart = _chart()
        theme = chart.payload.theme
        for bar, source in zip(chart.payload.volume, series.candles, strict=True):
            expected = theme.up_color if source.close >= source.open else theme.down_color
            assert bar.color == expected
            assert bar.value == source.volume


class TestLayers:
    def test_all_spec_layers_present_in_order(self) -> None:
        _, chart = _chart()
        names = [layer.name for layer in chart.payload.layers]
        assert names == [spec[0] for spec in LAYER_SPECS]
        assert [layer.z_order for layer in chart.payload.layers] == list(range(len(LAYER_SPECS)))

    def test_primitives_grouped_by_layer(self) -> None:
        _, chart = _chart()
        for layer in chart.payload.layers:
            assert all(p.layer == layer.name for p in layer.primitives)

    def test_z_order_rule(self) -> None:
        _, chart = _chart()
        for layer in chart.payload.layers:
            for prim in layer.primitives:
                assert prim.z_order == layer.z_order * 100 + prim.priority
        for layer in chart.payload.layers:
            keys = [(p.z_order, p.source_id) for p in layer.primitives]
            assert keys == sorted(keys), "primitives must be sorted for determinism"

    def test_internal_swings_hidden_by_default(self) -> None:
        _, chart = _chart()
        visibility = {layer.name: layer.visible for layer in chart.payload.layers}
        assert visibility["swings.internal"] is False
        assert visibility["swings.external"] is True

    def test_hidden_and_shown_overrides(self) -> None:
        config = VisualizationConfig(hidden_layers=["fvg.zones"], shown_layers=["swings.internal"])
        _, chart = _chart(config)
        visibility = {layer.name: layer.visible for layer in chart.payload.layers}
        assert visibility["fvg.zones"] is False
        assert visibility["swings.internal"] is True

    def test_legend_covers_every_layer(self) -> None:
        _, chart = _chart()
        assert set(chart.payload.legend) == {spec[0] for spec in LAYER_SPECS}


class TestTheme:
    def test_dark_default(self) -> None:
        _, chart = _chart()
        assert chart.payload.theme == THEMES["dark"]

    def test_light_theme(self) -> None:
        _, chart = _chart(VisualizationConfig(theme="light"))
        assert chart.payload.theme == THEMES["light"]
        assert chart.payload.theme.background == "#ffffff"


class TestDeterminism:
    def test_byte_identical_rebuild(self) -> None:
        series = uptrend_series()
        results = full_stack_results(series, engine_config())
        first = build_chart_payload(series, results).model_dump_json()
        second = build_chart_payload(series, results).model_dump_json()
        assert first == second

    def test_fresh_results_same_bytes(self) -> None:
        series = uptrend_series()
        first = build_chart_payload(
            series, full_stack_results(series, engine_config())
        ).model_dump_json()
        second = build_chart_payload(
            series, full_stack_results(series, engine_config())
        ).model_dump_json()
        assert first == second
