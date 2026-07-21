"""Unit tests for the per-module object -> primitive mappers.

Covers counts, geometry, color/style passthrough (VisualStyle is copied,
never recomputed), structured tooltips, and the seconds-only time rule.
"""

from __future__ import annotations

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.mtf import analyze_mtf
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.premium_discount import analyze_dealing_range
from contexttrading.analysis.sessions import analyze_sessions
from contexttrading.analysis.structure import analyze_structure
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.constants import SwingType, TrendDirection
from contexttrading.visualization import mappers
from contexttrading.visualization.primitives import (
    AreaBand,
    Box,
    Marker,
    PriceLine,
    RenderPrimitive,
    Segment,
    to_unix_seconds,
)
from tests.fixtures import (
    engine_config,
    fakeout_records,
    five_day_15m_series,
    judas_15m_series,
    to_series,
    uptrend_series,
    v_reversal_series,
)
from tests.ob_fixtures import rbd_records


def _assert_time_rule(primitives: list[RenderPrimitive], first: int, last: int) -> None:
    for prim in primitives:
        fields = prim.model_dump()
        for key, value in fields.items():
            if key.endswith("time") and isinstance(value, int):
                assert value < 10**12, f"millisecond leak in {key}"
                assert first <= value <= last, f"{key}={value} outside series bounds"


def _bounds(series) -> tuple[int, int]:
    return (
        to_unix_seconds(series.candles[0].timestamp),
        to_unix_seconds(series.candles[-1].timestamp),
    )


class TestMapStructure:
    def setup_method(self) -> None:
        self.series = uptrend_series()
        self.result = analyze_structure(self.series, engine_config()).payload
        self.prims = mappers.map_structure(self.result, self.series)

    def test_counts(self) -> None:
        markers = [p for p in self.prims if isinstance(p, Marker)]
        segments = [p for p in self.prims if isinstance(p, Segment)]
        lines = [p for p in self.prims if isinstance(p, PriceLine)]
        assert len(markers) == len(self.result.swings)
        assert len(segments) == len(self.result.breaks)
        expected_lines = int(self.result.protected_high is not None) + int(
            self.result.protected_low is not None
        )
        assert len(lines) == expected_lines

    def test_swing_marker_geometry_and_style(self) -> None:
        by_id = {p.source_id: p for p in self.prims if isinstance(p, Marker)}
        for swing in self.result.swings:
            marker = by_id[swing.id]
            assert marker.time == to_unix_seconds(self.series.candles[swing.index].timestamp)
            assert marker.price == swing.price
            assert marker.color == swing.style.color  # passthrough, not recomputed
            assert marker.layer == swing.style.layer
            expected_position = "aboveBar" if swing.swing_type is SwingType.HIGH else "belowBar"
            assert marker.position == expected_position
            assert marker.tooltip["index"] == str(swing.index)

    def test_break_segments_anchor_on_broken_swing(self) -> None:
        swings_by_id = {s.id: s for s in self.result.swings}
        by_id = {p.source_id: p for p in self.prims if isinstance(p, Segment)}
        for brk in self.result.breaks:
            seg = by_id[brk.id]
            origin = swings_by_id.get(brk.broken_swing_id)
            if origin is not None:
                assert seg.start_time == to_unix_seconds(origin.timestamp)
            assert seg.end_time == to_unix_seconds(brk.break_timestamp)
            assert seg.color == brk.style.color
            assert seg.line_style == brk.style.line_style

    def test_time_rule(self) -> None:
        _assert_time_rule(self.prims, *_bounds(self.series))


class TestMapLiquidity:
    def setup_method(self) -> None:
        self.series = to_series(fakeout_records(), symbol="FAKE")
        self.result = analyze_liquidity(self.series, engine_config()).payload
        self.prims = mappers.map_liquidity(self.result, self.series)

    def test_counts(self) -> None:
        lines = [p for p in self.prims if isinstance(p, PriceLine)]
        markers = [p for p in self.prims if isinstance(p, Marker)]
        assert len(lines) == len(self.result.equal_levels) + len(self.result.pools)
        assert len(markers) == len(self.result.sweeps)

    def test_pool_style_passthrough(self) -> None:
        by_id = {p.source_id: p for p in self.prims}
        for pool in self.result.pools:
            prim = by_id[pool.id]
            assert prim.color == pool.style.color
            assert prim.line_style == pool.style.line_style  # e.g. swept pools stay dotted
            assert prim.tooltip["status"] == pool.status.value

    def test_time_rule(self) -> None:
        _assert_time_rule(self.prims, *_bounds(self.series))


class TestMapFvg:
    def test_boxes_span_formation_to_fill_or_end(self) -> None:
        series = uptrend_series()
        result = analyze_fvg(series, engine_config()).payload
        prims = mappers.map_fvg(result, series)
        assert len(prims) == len(result.fvgs)
        by_id = {p.source_id: p for p in prims}
        last = len(series) - 1
        for gap in result.fvgs:
            box = by_id[gap.id]
            assert isinstance(box, Box)
            assert box.start_time == to_unix_seconds(
                series.candles[gap.formation_start_index].timestamp
            )
            expected_end = gap.filled_index if gap.filled_index is not None else last
            assert box.end_time == to_unix_seconds(series.candles[expected_end].timestamp)
            assert box.color == gap.style.color
            assert box.opacity == gap.style.opacity
        _assert_time_rule(prims, *_bounds(series))


class TestMapOrderBlocks:
    def test_one_box_per_block(self) -> None:
        series = v_reversal_series()
        result = analyze_orderblocks(series, engine_config()).payload
        prims = mappers.map_orderblocks(result, series)
        blocks = result.order_blocks + result.breaker_blocks + result.mitigation_blocks
        assert len(prims) == len(blocks)
        by_id = {p.source_id: p for p in prims}
        for block in blocks:
            box = by_id[block.id]
            assert box.start_time == to_unix_seconds(series.candles[block.candle_index].timestamp)
            assert box.layer == block.style.layer
            assert box.color == block.style.color
            assert box.tooltip["status"] == block.status.value
        _assert_time_rule(prims, *_bounds(series))


class TestMapSupplyDemand:
    def test_zone_boxes(self) -> None:
        series = to_series(rbd_records(), symbol="RBD")
        result = analyze_supplydemand(series, engine_config()).payload
        prims = mappers.map_supplydemand(result, series)
        assert len(prims) == len(result.zones)
        by_id = {p.source_id: p for p in prims}
        for zone in result.zones:
            box = by_id[zone.id]
            assert box.start_time == to_unix_seconds(
                series.candles[zone.base_start_index].timestamp
            )
            assert box.layer == zone.style.layer
            assert box.color == zone.style.color
        _assert_time_rule(prims, *_bounds(series))


class TestMapRange:
    def test_premium_discount_ote_plus_equilibrium(self) -> None:
        series = uptrend_series()
        result = analyze_dealing_range(series, engine_config()).payload
        prims = mappers.map_range(result, series)
        if result.dealing_range is None:
            assert prims == []
            return
        boxes = {p.source_id: p for p in prims if isinstance(p, Box)}
        lines = [p for p in prims if isinstance(p, PriceLine)]
        assert set(boxes) == {"range:premium", "range:discount", "range:ote"}
        assert len(lines) == 1
        assert lines[0].source_id == "range:equilibrium"
        first, last = _bounds(series)
        for box in boxes.values():
            assert (box.start_time, box.end_time) == (first, last)
        dr = result.dealing_range
        assert boxes["range:premium"].top == dr.high
        assert boxes["range:premium"].bottom == dr.equilibrium
        assert boxes["range:discount"].top == dr.equilibrium
        assert boxes["range:discount"].bottom == dr.low
        _assert_time_rule(prims, first, last)


class TestMapSessions:
    def test_five_day_counts(self) -> None:
        series = five_day_15m_series()
        result = analyze_sessions(series, engine_config()).payload
        prims = mappers.map_sessions(result, series)
        bands = [p for p in self._typed(prims, AreaBand)]
        lines = [p for p in self._typed(prims, PriceLine)]
        markers = [p for p in self._typed(prims, Marker)]
        assert len(bands) == len(result.sessions)
        assert len(lines) == len(result.pools)
        assert len(markers) == len(result.session_sweeps)
        _assert_time_rule(prims, *_bounds(series))

    def test_judas_marker(self) -> None:
        series = judas_15m_series()
        result = analyze_sessions(series, engine_config()).payload
        prims = mappers.map_sessions(result, series)
        judas = [p for p in prims if isinstance(p, Marker) and p.text == "J"]
        assert len(judas) == len(result.session_sweeps)
        for marker in judas:
            assert marker.shape == "diamond"
            assert marker.layer == "sessions.sweeps"

    @staticmethod
    def _typed(prims, kind):
        return [p for p in prims if isinstance(p, kind)]


class TestMapConfluence:
    def test_one_box_per_zone(self) -> None:
        from contexttrading.analysis.confluence import analyze_confluence

        series = five_day_15m_series()
        result = analyze_confluence(series, engine_config()).payload
        prims = mappers.map_confluence(result, series)
        assert len(prims) == len(result.zones)
        by_id = {p.source_id: p for p in prims}
        first, last = _bounds(series)
        for zone in result.zones:
            box = by_id[zone.id]
            assert (box.start_time, box.end_time) == (first, last)
            assert box.color == zone.style.color
            assert box.layer == "confluence.zones"
            assert "score" in box.tooltip
        _assert_time_rule(prims, first, last)


class TestMapMtf:
    def test_three_lines_per_htf_context(self) -> None:
        series = five_day_15m_series()
        result = analyze_mtf(series, ["1h", "4h"], engine_config()).payload
        prims = mappers.map_mtf(result, series)
        contexts = [c for c in result.contexts[1:] if c.dealing_range is not None]
        assert len(prims) == 3 * len(contexts)
        for prim in prims:
            assert isinstance(prim, PriceLine)
            assert prim.layer == "mtf.levels"
        for context in contexts:
            expected = (
                "#22ab94"
                if context.direction is TrendDirection.BULLISH
                else "#f23645" if context.direction is TrendDirection.BEARISH else "#787b86"
            )
            lines = [p for p in prims if p.source_id.startswith(f"mtf:{context.timeframe}:")]
            assert len(lines) == 3
            assert all(p.color == expected for p in lines)
