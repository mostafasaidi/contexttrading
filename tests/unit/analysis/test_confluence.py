"""Unit tests for the confluence engine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contexttrading.analysis.confluence import (
    analyze_confluence,
    build_confluence_zones,
    default_mtf_timeframes,
)
from contexttrading.analysis.confluence.factors import (
    liquidity_factor,
    premium_discount_factor,
    structure_factor,
    trend_factor,
)
from contexttrading.analysis.confluence.zones import ZoneMember
from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.structure.structure import StructureScan
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.constants import (
    BreakStrength,
    LiquiditySide,
    MarketPhase,
    PriceLocation,
    StructureBreakClass,
    StructureBreakSignificance,
    StructureBreakType,
    SweepClassification,
    SwingClass,
    Timeframe,
    TrendDirection,
    TrendStrength,
)
from contexttrading.models.liquidity import LiquidityResult, LiquiditySweep
from contexttrading.models.range import DealingRange
from contexttrading.models.structure import StructureBreak, TrendState
from tests.fixtures import (
    engine_config,
    five_day_15m_series,
    judas_15m_series,
    uptrend_series,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _trend_state(direction: TrendDirection, strength: TrendStrength) -> TrendState:
    return TrendState(
        direction=direction,
        external_trend=direction,
        internal_trend=direction,
        strength=strength,
        market_phase=MarketPhase.EXPANSION,
    )


def _break(direction: TrendDirection, i: int) -> StructureBreak:
    return StructureBreak(
        broken_swing_id=f"swing_{i}",
        broken_swing_price=100.0 + i,
        broken_swing_class=SwingClass.EXTERNAL,
        break_index=i,
        break_timestamp=T0,
        break_price=101.0 + i,
        direction=direction,
        break_type=StructureBreakType.BOS,
        break_class=StructureBreakClass.EXTERNAL,
        significance=StructureBreakSignificance.MAJOR,
        strength=BreakStrength.STRONG,
    )


def _scan(breaks: list[StructureBreak]) -> StructureScan:
    return StructureScan(
        internal_swings=[],
        external_swings=[],
        breaks=breaks,
        legs=[],
        protected_high=None,
        protected_low=None,
        external_trend=TrendDirection.BULLISH,
        internal_trend=TrendDirection.BULLISH,
        external_sequence_trend=TrendDirection.BULLISH,
        internal_sequence_trend=TrendDirection.BULLISH,
        atr_values=(),
    )


def _sweep(side: LiquiditySide, i: int, cls: SweepClassification) -> LiquiditySweep:
    return LiquiditySweep(
        pool_id=f"pool_{i}",
        pool_price=100.0,
        side=side,
        candle_index=i,
        timestamp=T0,
        wick_extreme=100.5,
        penetration_atr=None,
        close_back_inside=True,
        classification=cls,
    )


def _dealing_range(location: PriceLocation, ref: float) -> DealingRange:
    return DealingRange(
        high=110.0,
        low=90.0,
        high_swing_id="swing_h",
        low_swing_id="swing_l",
        direction=TrendDirection.BULLISH,
        equilibrium=100.0,
        ote_low=95.0,
        ote_high=100.0,
        ote_fibs=(0.62, 0.79),
        reference_price=ref,
        price_location=location,
    )


class TestFactorBoundaries:
    def test_trend_strong_full_raw(self) -> None:
        f = trend_factor(
            _trend_state(TrendDirection.BULLISH, TrendStrength.STRONG), engine_config()
        )
        assert f.raw == 1.0
        assert f.direction is TrendDirection.BULLISH
        assert f.contribution == f.weight

    def test_trend_unknown_dilutes_with_zero(self) -> None:
        f = trend_factor(_trend_state(TrendDirection.UNKNOWN, TrendStrength.WEAK), engine_config())
        assert f.raw == 0.0
        assert f.direction is TrendDirection.RANGING
        assert f.contribution == 0.0
        assert f.weight > 0  # still counted in the normalization

    def test_structure_majority_and_tie(self) -> None:
        config = engine_config()
        bull = _scan([_break(TrendDirection.BULLISH, i) for i in range(4)])
        f = structure_factor(bull, config)
        assert f is not None and f.direction is TrendDirection.BULLISH and f.raw == 1.0
        tied = _scan([_break(TrendDirection.BULLISH, 0), _break(TrendDirection.BEARISH, 1)])
        f2 = structure_factor(tied, config)
        assert f2 is not None and f2.direction is TrendDirection.RANGING and f2.raw == 0.0

    def test_structure_lookback_window(self) -> None:
        config = engine_config(conf_structure_lookback=2)
        breaks = [_break(TrendDirection.BEARISH, i) for i in range(3)] + [
            _break(TrendDirection.BULLISH, 3),
            _break(TrendDirection.BULLISH, 4),
        ]
        f = structure_factor(_scan(breaks), config)
        assert f is not None and f.direction is TrendDirection.BULLISH and f.raw == 1.0

    def test_structure_none_when_no_confirmed_breaks(self) -> None:
        assert structure_factor(_scan([]), engine_config()) is None

    def test_liquidity_sellside_sweeps_are_bullish(self) -> None:
        result = LiquidityResult(
            sweeps=[
                _sweep(LiquiditySide.SELLSIDE, i, SweepClassification.STOP_HUNT) for i in range(3)
            ]
        )
        f = liquidity_factor(result, engine_config())
        assert f is not None and f.direction is TrendDirection.BULLISH and f.raw == 1.0

    def test_liquidity_class_weights_break_ties(self) -> None:
        # One STOP_HUNT sellside (1.0) vs two shallow SWEEP buyside (0.6 + 0.6 = 1.2).
        result = LiquidityResult(
            sweeps=[
                _sweep(LiquiditySide.SELLSIDE, 0, SweepClassification.STOP_HUNT),
                _sweep(LiquiditySide.BUYSIDE, 1, SweepClassification.SWEEP),
                _sweep(LiquiditySide.BUYSIDE, 2, SweepClassification.SWEEP),
            ]
        )
        f = liquidity_factor(result, engine_config())
        assert f is not None and f.direction is TrendDirection.BEARISH
        assert f.raw == pytest.approx(1.2 / 2.2)

    def test_premium_discount_raw_scales_with_distance(self) -> None:
        f = premium_discount_factor(_dealing_range(PriceLocation.DISCOUNT, 95.0), engine_config())
        assert f is not None and f.direction is TrendDirection.BULLISH
        assert f.raw == pytest.approx(0.5)  # |95 - 100| / 10
        f_eq = premium_discount_factor(
            _dealing_range(PriceLocation.EQUILIBRIUM, 100.0), engine_config()
        )
        assert f_eq is not None and f_eq.direction is TrendDirection.RANGING and f_eq.raw == 0.0
        assert premium_discount_factor(None, engine_config()) is None


class TestZones:
    def test_overlap_forms_zone_with_envelope(self) -> None:
        members = [
            ZoneMember("fvg", "fvg_a", TrendDirection.BULLISH, 100.0, 101.0, 0.8),
            ZoneMember("orderblock", "ob_b", TrendDirection.BULLISH, 100.5, 101.5, 1.0),
        ]
        zones = build_confluence_zones(members, engine_config())
        assert len(zones) == 1
        zone = zones[0]
        assert zone.direction is TrendDirection.BULLISH
        assert zone.zone_bottom == 100.0 and zone.zone_top == 101.5
        assert zone.member_ids == ["fvg_a", "ob_b"]
        assert zone.member_kinds == ["fvg", "orderblock"]
        # score = (0.8 * 1.0 + 1.0 * 1.0) / (1.0 + 1.0 + 1.0 + 0.5) = 1.8 / 3.5
        assert zone.score == pytest.approx(1.8 / 3.5)

    def test_single_kind_never_forms_zone(self) -> None:
        members = [
            ZoneMember("fvg", "a", TrendDirection.BULLISH, 100.0, 101.0, 1.0),
            ZoneMember("fvg", "b", TrendDirection.BULLISH, 100.5, 101.5, 1.0),
        ]
        assert build_confluence_zones(members, engine_config()) == []

    def test_conflicted_cluster_forms_no_zone(self) -> None:
        members = [
            ZoneMember("fvg", "a", TrendDirection.BULLISH, 100.0, 101.0, 1.0),
            ZoneMember("orderblock", "b", TrendDirection.BEARISH, 100.5, 101.5, 1.0),
        ]
        assert build_confluence_zones(members, engine_config()) == []

    def test_separate_clusters_scored_independently(self) -> None:
        members = [
            ZoneMember("fvg", "a", TrendDirection.BULLISH, 100.0, 101.0, 1.0),
            ZoneMember("orderblock", "b", TrendDirection.BULLISH, 100.2, 100.8, 1.0),
            ZoneMember("fvg", "c", TrendDirection.BEARISH, 110.0, 111.0, 0.5),
            ZoneMember("supplydemand", "d", TrendDirection.BEARISH, 110.5, 111.5, 0.5),
        ]
        zones = build_confluence_zones(members, engine_config())
        assert len(zones) == 2
        assert zones[0].score >= zones[1].score  # sorted by score desc

    def test_chain_merging_through_overlap(self) -> None:
        members = [
            ZoneMember("fvg", "a", TrendDirection.BULLISH, 100.0, 101.0, 1.0),
            ZoneMember("orderblock", "b", TrendDirection.BULLISH, 100.9, 102.0, 1.0),
            ZoneMember("supplydemand", "c", TrendDirection.BULLISH, 101.9, 103.0, 1.0),
        ]
        zones = build_confluence_zones(members, engine_config())
        assert len(zones) == 1
        assert zones[0].zone_top == 103.0
        assert zones[0].member_kinds == ["fvg", "orderblock", "supplydemand"]


class TestEndToEnd:
    def test_uptrend_scores_bullish(self) -> None:
        result = analyze_confluence(uptrend_series(), engine_config())
        payload = result.payload
        assert payload.bias is TrendDirection.BULLISH
        assert payload.bullish_score > payload.bearish_score
        assert payload.score == payload.bullish_score

    def test_judas_fixture_scores_bearish(self) -> None:
        result = analyze_confluence(judas_15m_series(), engine_config())
        payload = result.payload
        assert payload.bias is TrendDirection.BEARISH
        assert any(f.factor == "session" for f in payload.factors)

    def test_score_math_matches_factor_list(self) -> None:
        result = analyze_confluence(five_day_15m_series(), engine_config())
        payload = result.payload
        total = sum(f.weight for f in payload.factors)
        bull = sum(f.contribution for f in payload.factors if f.direction is TrendDirection.BULLISH)
        assert payload.bullish_score == pytest.approx(bull / total)
        assert payload.score == max(payload.bullish_score, payload.bearish_score)
        agreeing = sum(
            1 for f in payload.factors if f.contribution > 0 and f.direction is payload.bias
        )
        assert payload.agreeing_factors == agreeing

    def test_zone_member_ids_reference_real_objects(self) -> None:
        series = five_day_15m_series()
        config = engine_config()
        result = analyze_confluence(series, config)
        fvg_ids = {f.id for f in analyze_fvg(series, config).payload.fvgs}
        ob_result = analyze_orderblocks(series, config).payload
        block_ids = {b.id for b in ob_result.order_blocks}
        block_ids |= {b.id for b in ob_result.breaker_blocks}
        block_ids |= {b.id for b in ob_result.mitigation_blocks}
        sd_ids = {z.id for z in analyze_supplydemand(series, config).payload.zones}
        known = fvg_ids | block_ids | sd_ids | {"premium_discount"}
        for zone in result.payload.zones:
            assert set(zone.member_ids) <= known

    def test_deterministic_repeat_runs(self) -> None:
        a = analyze_confluence(five_day_15m_series(), engine_config())
        b = analyze_confluence(five_day_15m_series(), engine_config())
        assert a.model_dump_json() == b.model_dump_json()

    def test_default_mtf_timeframes(self) -> None:
        assert default_mtf_timeframes(Timeframe.M15) == [Timeframe.M30, Timeframe.H1]
        assert default_mtf_timeframes(Timeframe.MN1) == []

    def test_envelope_metadata(self) -> None:
        series = judas_15m_series()
        result = analyze_confluence(series, engine_config())
        assert result.module == "confluence"
        assert result.generated_from.candle_count == len(series)
