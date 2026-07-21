"""Tests for analysis.supplydemand: zone detection, lifecycle, strength."""

from __future__ import annotations

import pytest

from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.supplydemand import (
    analyze_supplydemand,
    strength_score,
    trend_aligned,
    update_zone_state,
)
from contexttrading.analysis.supplydemand.zones import RawZone, ZoneState
from contexttrading.core.constants import SDZoneStatus, TrendDirection, ZoneType
from contexttrading.models.supplydemand import SupplyDemandZone
from tests.fixtures import engine_config, make_candle, to_series
from tests.ob_fixtures import (
    bullish_ob_records,
    dbr_records,
    rbd_records,
    refined_ob_records,
)


def _raw_zone(kind: ZoneType = ZoneType.DEMAND, actionable: int = 0) -> RawZone:
    return RawZone(
        kind=kind,
        zone_bottom=10.0,
        zone_top=10.5,
        base_start_index=0,
        base_end_index=0,
        actionable_from_index=actionable,
        departure_leg_id=None,
        departure_atr_multiple=2.0,
        mean_base_body_atr=0.2,
    )


class TestZoneLifecycleUnit:
    def _series(self, candles: list[tuple[float, float, float, float]]):
        return to_series([make_candle(i, *c) for i, c in enumerate(candles)])

    def test_fresh_to_tested_counts_distinct_visits(self) -> None:
        # demand zone [10.0, 10.5]; two separate dips in, one stay-inside
        series = self._series(
            [
                (11.0, 11.1, 10.9, 11.05),
                (11.0, 11.05, 10.4, 10.6),  # dip 1 (low 10.4 <= 10.5)
                (10.6, 11.0, 10.55, 10.9),  # outside
                (10.9, 10.95, 10.45, 10.6),  # dip 2
                (10.6, 10.7, 10.3, 10.5),  # still inside (no new test)
                (10.5, 11.0, 10.45, 10.9),  # outside
            ]
        )
        state = ZoneState()
        update_zone_state(state, _raw_zone(actionable=0), series)
        assert state.status is SDZoneStatus.TESTED
        assert state.tests == 2
        assert state.first_touch_index == 1

    def test_wick_through_base_mitigates(self) -> None:
        series = self._series([(11.0, 11.1, 10.9, 11.05), (11.0, 11.05, 9.9, 10.4)])
        state = ZoneState()
        update_zone_state(state, _raw_zone(), series)
        assert state.status is SDZoneStatus.MITIGATED
        assert state.mitigated_index == 1

    def test_close_through_breaks_and_wins_over_mitigated(self) -> None:
        series = self._series([(11.0, 11.1, 10.9, 11.05), (11.0, 11.05, 9.9, 9.95)])
        state = ZoneState()
        update_zone_state(state, _raw_zone(), series)
        assert state.status is SDZoneStatus.BROKEN
        assert state.broken_index == 1

    def test_supply_mirror(self) -> None:
        series = self._series([(9.5, 9.6, 9.4, 9.45), (9.5, 10.6, 9.45, 10.4)])
        state = ZoneState()
        update_zone_state(state, _raw_zone(kind=ZoneType.SUPPLY), series)
        assert state.status is SDZoneStatus.MITIGATED  # wick through top, close inside

    def test_fresh_never_touched(self) -> None:
        series = self._series([(11.0, 11.1, 10.9, 11.05), (11.05, 11.2, 11.0, 11.15)])
        state = ZoneState()
        update_zone_state(state, _raw_zone(), series)
        assert state.status is SDZoneStatus.FRESH
        assert state.tests == 0 and state.first_touch_index is None


class TestPatternDetection:
    def test_rbd_supply_zone(self) -> None:
        result = analyze_supplydemand(to_series(rbd_records()), engine_config())
        zone = next(z for z in result.payload.zones if z.departure_leg_id is not None)
        assert zone.kind is ZoneType.SUPPLY
        assert (zone.zone_bottom, zone.zone_top) == (pytest.approx(10.52), pytest.approx(10.62))
        assert (zone.base_start_index, zone.base_end_index) == (7, 7)
        assert zone.status is SDZoneStatus.TESTED
        assert zone.tests == 1
        assert zone.actionable_from_index == 14  # swing c11 + external lookback 3

    def test_dbr_demand_zone(self) -> None:
        result = analyze_supplydemand(to_series(dbr_records()), engine_config())
        zone = next(z for z in result.payload.zones if z.departure_leg_id is not None)
        assert zone.kind is ZoneType.DEMAND
        assert (zone.zone_bottom, zone.zone_top) == (pytest.approx(9.85), pytest.approx(9.95))
        assert zone.status is SDZoneStatus.TESTED
        assert zone.tests == 1  # c15 stays inside: no second test

    def test_ob_derived_zones_link_back(self) -> None:
        config = engine_config()
        series = to_series(bullish_ob_records())
        result = analyze_supplydemand(series, config)
        ob_ids = {b.id for b in analyze_orderblocks(series, config).payload.order_blocks}
        derived = [z for z in result.payload.zones if z.departure_leg_id is None]
        assert derived, "expected OB-derived zones"
        for zone in derived:
            assert zone.linked_order_block_id in ob_ids


class TestDuplicateRule:
    def test_rbd_pattern_zone_marked_duplicate(self) -> None:
        series = to_series(rbd_records())
        result = analyze_supplydemand(series, engine_config())
        zone = next(z for z in result.payload.zones if z.departure_leg_id is not None)
        assert zone.is_duplicate
        assert zone.linked_order_block_id is not None  # OB preferred, linked

    def test_dbr_pattern_zone_not_duplicate(self) -> None:
        # overlap 0.07/0.10 = 0.7 < 0.8 threshold → kept as an independent zone
        result = analyze_supplydemand(to_series(dbr_records()), engine_config())
        zone = next(z for z in result.payload.zones if z.departure_leg_id is not None)
        assert not zone.is_duplicate
        assert zone.linked_order_block_id is None


class TestStrength:
    def test_deterministic_and_bounded(self) -> None:
        config = engine_config()
        kwargs = dict(
            departure_atr_multiple=2.0,
            mean_base_body_atr=0.2,
            status=SDZoneStatus.FRESH,
            tests=0,
            aligned=True,
            age=3,
            config=config,
        )
        first = strength_score(**kwargs)
        assert first == strength_score(**kwargs)
        assert 0.0 <= first <= 1.0

    def test_fresh_outranks_tested_outranks_broken(self) -> None:
        config = engine_config()
        base = dict(
            departure_atr_multiple=2.0, mean_base_body_atr=0.2, tests=0, aligned=False, age=0
        )
        scores = {
            s: strength_score(status=s, config=config, **base)
            for s in (
                SDZoneStatus.FRESH,
                SDZoneStatus.TESTED,
                SDZoneStatus.MITIGATED,
                SDZoneStatus.BROKEN,
            )
        }
        assert (
            scores[SDZoneStatus.FRESH]
            > scores[SDZoneStatus.TESTED]
            > scores[SDZoneStatus.MITIGATED]
            > scores[SDZoneStatus.BROKEN]
        )

    def test_tests_penalty_decays(self) -> None:
        config = engine_config()
        base = dict(
            departure_atr_multiple=2.0,
            mean_base_body_atr=0.2,
            status=SDZoneStatus.TESTED,
            aligned=False,
            age=0,
        )
        assert strength_score(tests=0, config=config, **base) > strength_score(
            tests=2, config=config, **base
        )

    def test_warmup_defaults(self) -> None:
        config = engine_config()
        score = strength_score(
            departure_atr_multiple=None,
            mean_base_body_atr=None,
            status=SDZoneStatus.FRESH,
            tests=0,
            aligned=False,
            age=0,
            config=config,
        )
        expected = (
            config.sd_weight_departure * 0.5
            + config.sd_weight_tightness * 0.5
            + config.sd_weight_freshness * 1.0
            + config.sd_weight_tests * 1.0
            + config.sd_weight_age * 1.0
        )
        assert score == pytest.approx(expected)

    def test_trend_alignment(self) -> None:
        assert trend_aligned(ZoneType.DEMAND, TrendDirection.BULLISH)
        assert trend_aligned(ZoneType.SUPPLY, TrendDirection.BEARISH)
        assert not trend_aligned(ZoneType.DEMAND, TrendDirection.BEARISH)
        assert not trend_aligned(ZoneType.SUPPLY, TrendDirection.RANGING)


class TestRankingAndEnvelope:
    def test_ranks_and_counts(self) -> None:
        result = analyze_supplydemand(to_series(rbd_records()), engine_config())
        payload = result.payload
        assert payload.total_count == len(payload.zones)
        assert sum(payload.counts_by_status.values()) == payload.total_count
        assert sum(payload.counts_by_kind.values()) == payload.total_count
        ranks = sorted(z.rank for z in payload.zones)
        assert ranks == list(range(1, len(ranks) + 1))
        strengths = [z.strength for z in payload.zones]
        assert strengths == sorted(strengths, reverse=True)
        assert result.module == "supplydemand"

    def test_fresh_zone_from_untouched_ob(self) -> None:
        result = analyze_supplydemand(to_series(refined_ob_records()), engine_config())
        zone = result.payload.zones[0]
        assert zone.status is SDZoneStatus.FRESH
        assert zone.tests == 0

    def test_deterministic_ids_across_runs(self) -> None:
        a = analyze_supplydemand(to_series(rbd_records()), engine_config())
        b = analyze_supplydemand(to_series(rbd_records()), engine_config())
        assert [z.id for z in a.payload.zones] == [z.id for z in b.payload.zones]


class TestModelValidators:
    def _kwargs(self, **overrides):
        base = dict(
            kind=ZoneType.DEMAND,
            zone_bottom=10.0,
            zone_top=10.5,
            base_start_index=2,
            base_end_index=3,
            formed_at="2024-01-01T00:03:00+00:00",
            actionable_from_index=6,
            age=0,
            strength=0.5,
        )
        base.update(overrides)
        return base

    def test_inverted_zone_rejected(self) -> None:
        with pytest.raises(ValueError, match="zone_top"):
            SupplyDemandZone(**self._kwargs(zone_bottom=10.5, zone_top=10.0))

    def test_base_ordering_rejected(self) -> None:
        with pytest.raises(ValueError, match="start <= end < actionable"):
            SupplyDemandZone(**self._kwargs(base_end_index=6))

    def test_fresh_cannot_have_touch(self) -> None:
        with pytest.raises(ValueError, match="first_touch_index"):
            SupplyDemandZone(**self._kwargs(first_touch_index=7))
