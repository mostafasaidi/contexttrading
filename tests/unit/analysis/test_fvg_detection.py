"""Tests for analysis.fvg.detection: patterns, filters, grouping, linkage."""

from __future__ import annotations

import pytest

from contexttrading.analysis.fvg import (
    analyze_fvg,
    assign_stack_groups,
    detect_raw_fvgs,
    link_displacement,
)
from contexttrading.analysis.fvg.detection import RawFVG, find_parent
from contexttrading.analysis.indicators import atr
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.core.constants import (
    BreakStrength,
    MitigationStatus,
    StructureBreakType,
    TrendDirection,
)
from contexttrading.models.structure import StructureBreak
from tests.fixtures import engine_config, to_series, uptrend_series
from tests.fvg_fixtures import (
    bearish_fvg_records,
    bullish_fvg_records,
    nested_fvg_records,
)


def _raw(direction: TrendDirection, bottom: float, top: float, end: int) -> RawFVG:
    return RawFVG(
        direction=direction,
        zone_bottom=bottom,
        zone_top=top,
        formation_start_index=end - 2,
        middle_index=end - 1,
        formation_end_index=end,
        gap_size=top - bottom,
        gap_atr=None,
        gap_percent=(top - bottom) / ((top + bottom) / 2),
    )


class TestPatternDetection:
    def test_bullish_fvg(self) -> None:
        series = to_series(bullish_fvg_records())
        raws = detect_raw_fvgs(series, atr(series.candles, 3), engine_config())
        assert len(raws) == 1
        raw = raws[0]
        assert raw.direction is TrendDirection.BULLISH
        assert raw.zone_bottom == pytest.approx(10.0)
        assert raw.zone_top == pytest.approx(10.5)
        assert raw.middle_index == 1
        assert raw.formation_end_index == 2
        assert raw.gap_size == pytest.approx(0.5)

    def test_bearish_fvg(self) -> None:
        series = to_series(bearish_fvg_records())
        raws = detect_raw_fvgs(series, atr(series.candles, 3), engine_config())
        assert len(raws) == 1
        raw = raws[0]
        assert raw.direction is TrendDirection.BEARISH
        assert raw.zone_bottom == pytest.approx(10.5)
        assert raw.zone_top == pytest.approx(11.0)

    def test_gap_percent(self) -> None:
        series = to_series(bullish_fvg_records())
        raws = detect_raw_fvgs(series, atr(series.candles, 3), engine_config())
        assert raws[0].gap_percent == pytest.approx(0.5 / 10.25)


class TestMinSizeFilter:
    def _series(self):
        return to_series(bullish_fvg_records())

    def test_boundary_inclusive(self) -> None:
        series = self._series()
        atr_values = atr(series.candles, 2)  # first value at idx 1 (the FVG middle)
        atr_at = atr_values[1]
        assert atr_at is not None
        gap = 0.5
        config_in = engine_config(atr_period=2, fvg_min_atr_fraction=gap / atr_at)
        config_out = engine_config(atr_period=2, fvg_min_atr_fraction=gap / atr_at * 1.01)
        assert len(detect_raw_fvgs(series, atr_values, config_in)) == 1
        assert detect_raw_fvgs(series, atr_values, config_out) == []

    def test_zero_filter_keeps_all(self) -> None:
        series = self._series()
        config = engine_config(fvg_min_atr_fraction=0.0)
        assert len(detect_raw_fvgs(series, atr(series.candles, 3), config)) == 1


class TestAtrWarmup:
    def test_warmup_keeps_fvg_with_none_atr(self) -> None:
        series = to_series(bullish_fvg_records())
        config = engine_config(atr_period=14)  # ATR never available (7 candles)
        result = analyze_fvg(series, config)
        assert result.payload.total_count == 1
        fvg = result.payload.fvgs[0]
        assert fvg.gap_atr is None
        assert fvg.displacement_margin_atr is None


class TestNestedGrouping:
    def test_find_parent_smallest_container(self) -> None:
        big = _raw(TrendDirection.BULLISH, 10.0, 11.0, 2)
        mid = _raw(TrendDirection.BULLISH, 10.2, 10.8, 5)
        small = _raw(TrendDirection.BULLISH, 10.4, 10.6, 8)
        assert find_parent(small, [big, mid]) is mid  # smallest container wins

    def test_find_parent_requires_same_direction_and_active(self) -> None:
        bearish = _raw(TrendDirection.BEARISH, 10.0, 11.0, 2)
        small = _raw(TrendDirection.BULLISH, 10.4, 10.6, 8)
        assert find_parent(small, [bearish]) is None

    def test_pipeline_nested_link(self) -> None:
        result = analyze_fvg(to_series(nested_fvg_records()), engine_config())
        children = [f for f in result.payload.fvgs if f.is_nested]
        assert len(children) == 1
        child = children[0]
        assert (child.zone_bottom, child.zone_top) == (pytest.approx(10.5), pytest.approx(10.6))
        parent = next(f for f in result.payload.fvgs if f.id == child.parent_fvg_id)
        assert (parent.zone_bottom, parent.zone_top) == (
            pytest.approx(10.0),
            pytest.approx(11.0),
        )
        assert parent.status is MitigationStatus.PARTIALLY_MITIGATED  # never filled


class TestStackedGrouping:
    def test_overlap_chains_into_one_group(self) -> None:
        a = _raw(TrendDirection.BULLISH, 10.0, 10.5, 2)
        b = _raw(TrendDirection.BULLISH, 10.4, 10.9, 5)
        c = _raw(TrendDirection.BULLISH, 10.8, 11.3, 8)
        groups = assign_stack_groups([a, b, c], lookback=3)
        assert groups[id(a)] == groups[id(b)] == groups[id(c)]  # transitive chain

    def test_lookback_boundary_inclusive(self) -> None:
        a = _raw(TrendDirection.BULLISH, 10.0, 10.5, 2)
        b = _raw(TrendDirection.BULLISH, 10.4, 10.9, 7)  # diff 5 == lookback
        c = _raw(TrendDirection.BULLISH, 10.4, 10.9, 8)  # diff 6 > lookback
        groups = assign_stack_groups([a, b], lookback=5)
        assert id(a) in groups and groups[id(a)] == groups[id(b)]
        assert id(c) not in assign_stack_groups([a, c], lookback=5)

    def test_adjacent_zones_count(self) -> None:
        a = _raw(TrendDirection.BULLISH, 10.0, 10.5, 2)
        b = _raw(TrendDirection.BULLISH, 10.5, 11.0, 4)  # touches at 10.5
        groups = assign_stack_groups([a, b], lookback=3)
        assert groups[id(a)] == groups[id(b)]

    def test_directions_not_mixed(self) -> None:
        a = _raw(TrendDirection.BULLISH, 10.0, 10.5, 2)
        b = _raw(TrendDirection.BEARISH, 10.2, 10.7, 3)
        assert assign_stack_groups([a, b], lookback=5) == {}

    def test_single_fvg_not_stacked(self) -> None:
        a = _raw(TrendDirection.BULLISH, 10.0, 10.5, 2)
        assert assign_stack_groups([a], lookback=5) == {}


class TestDisplacementLinkage:
    def _break(self, index: int, strength: BreakStrength, brk_id: str = "") -> StructureBreak:
        return StructureBreak(
            id=brk_id,
            broken_swing_id="swing_x",
            broken_swing_price=15.05,
            broken_swing_class="external",  # type: ignore[arg-type]
            break_index=index,
            break_timestamp="2024-01-01T00:11:00Z",
            break_price=15.75,
            direction=TrendDirection.BULLISH,
            break_type=StructureBreakType.BOS,
            break_class="external",  # type: ignore[arg-type]
            significance="major",  # type: ignore[arg-type]
            strength=strength,
            margin_atr=0.6 if strength is BreakStrength.STRONG else 0.1,
        )

    def test_prefers_strong_over_weak(self) -> None:
        raw = _raw(TrendDirection.BULLISH, 10.0, 10.5, 2)
        weak = self._break(1, BreakStrength.WEAK, "brk_weak")
        strong = self._break(1, BreakStrength.STRONG, "brk_strong")
        linked = link_displacement(raw, {1: [weak, strong]})
        assert linked is not None and linked.id == "brk_strong"

    def test_none_when_no_break(self) -> None:
        raw = _raw(TrendDirection.BULLISH, 10.0, 10.5, 2)
        assert link_displacement(raw, {}) is None

    def test_pipeline_links_real_bos(self) -> None:
        result = analyze_fvg(uptrend_series(), engine_config())
        scan = StructureScanner(engine_config()).run(uptrend_series())
        break_ids = {b.id for b in scan.breaks}
        linked = [f for f in result.payload.fvgs if f.linked_break_id is not None]
        assert linked, "expected displacement-linked FVGs in the uptrend fixture"
        for fvg in linked:
            assert fvg.linked_break_id in break_ids
            assert fvg.displacement_margin_atr is not None
        # The FVG whose middle candle is the first BOS (idx 11) must link it.
        mid11 = next(f for f in result.payload.fvgs if f.middle_index == 11)
        assert mid11.linked_break_id is not None
