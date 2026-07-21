"""Tests for analysis.orderblocks: detection, lifecycle, breakers, MBs."""

from __future__ import annotations

import pytest

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.indicators import atr
from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.orderblocks import (
    analyze_orderblocks,
    update_block_state,
)
from contexttrading.analysis.orderblocks.lifecycle import BlockState
from contexttrading.analysis.structure import analyze_structure
from contexttrading.core.constants import (
    BlockOrigin,
    MitigationStatus,
    TrendDirection,
)
from contexttrading.models.candle import Candle
from contexttrading.models.orderblock import OrderBlock
from tests.fixtures import (
    engine_config,
    make_candle,
    to_series,
    uptrend_series,
    v_reversal_series,
)
from tests.ob_fixtures import (
    bearish_ob_records,
    bullish_ob_records,
    mb_sweep_records,
    ob_violation_no_break_records,
    refined_ob_records,
)


def _candle(o: float, h: float, low: float, c: float) -> Candle:
    return to_series([make_candle(0, o, h, low, c)]).candles[0]


def _bullish_kwargs() -> dict:
    return dict(
        direction=TrendDirection.BULLISH,
        zone_bottom=10.0,
        zone_top=10.5,
        mitigation_level=10.0,  # unrefined: far boundary
    )


class TestBlockLifecycleUnit:
    def test_partial_then_mitigated_then_violated(self) -> None:
        state = BlockState()
        update_block_state(
            state, **_bullish_kwargs(), candle=_candle(11.0, 11.2, 10.3, 10.6), index=3
        )
        assert state.status is MitigationStatus.PARTIALLY_MITIGATED
        assert state.first_touch_index == 3
        assert state.max_penetration_fraction == pytest.approx(0.4)
        update_block_state(
            state, **_bullish_kwargs(), candle=_candle(10.6, 10.7, 9.9, 10.2), index=4
        )
        assert state.status is MitigationStatus.MITIGATED
        assert state.mitigation_index == 4
        update_block_state(
            state, **_bullish_kwargs(), candle=_candle(10.2, 10.3, 9.8, 9.9), index=5
        )
        assert state.status is MitigationStatus.VIOLATED
        assert state.violation_index == 5

    def test_wick_through_is_not_violation(self) -> None:
        state = BlockState()
        # wick through far side, close back inside → mitigated, not violated
        update_block_state(
            state, **_bullish_kwargs(), candle=_candle(10.4, 10.6, 9.9, 10.4), index=3
        )
        assert state.status is MitigationStatus.MITIGATED
        assert state.violation_index is None

    def test_refined_fifty_percent_rule(self) -> None:
        kwargs = _bullish_kwargs() | {"mitigation_level": 10.25}  # refined midpoint
        state = BlockState()
        update_block_state(state, **kwargs, candle=_candle(10.6, 10.7, 10.3, 10.5), index=3)
        assert state.status is MitigationStatus.PARTIALLY_MITIGATED  # above midpoint
        update_block_state(state, **kwargs, candle=_candle(10.5, 10.55, 10.2, 10.4), index=4)
        assert state.status is MitigationStatus.MITIGATED  # below midpoint (wick)

    def test_consumed_after_departure(self) -> None:
        state = BlockState()
        update_block_state(
            state, **_bullish_kwargs(), candle=_candle(10.4, 10.5, 9.9, 10.3), index=3
        )
        assert state.status is MitigationStatus.MITIGATED
        assert not state.is_consumed
        update_block_state(
            state, **_bullish_kwargs(), candle=_candle(10.3, 10.8, 10.2, 10.7), index=4
        )
        assert state.is_consumed  # closed back above zone top
        assert state.status is MitigationStatus.MITIGATED

    def test_violated_is_terminal(self) -> None:
        state = BlockState(status=MitigationStatus.VIOLATED, violation_index=4)
        update_block_state(
            state, **_bullish_kwargs(), candle=_candle(11.0, 11.5, 10.9, 11.4), index=5
        )
        assert state.touches == 0 and state.status is MitigationStatus.VIOLATED


class TestOrderBlockDetection:
    def test_bullish_ob_geometry_and_origin(self) -> None:
        result = analyze_orderblocks(to_series(bullish_ob_records()), engine_config())
        ob = next(b for b in result.payload.order_blocks if b.direction is TrendDirection.BULLISH)
        assert ob.candle_index == 4
        assert (ob.zone_bottom, ob.zone_top) == (pytest.approx(10.1), pytest.approx(10.65))
        assert (ob.body_bottom, ob.body_top) == (pytest.approx(10.15), pytest.approx(10.6))
        assert ob.origin is BlockOrigin.CONTINUATION
        assert not ob.is_refined
        assert ob.linked_break_id

    def test_bearish_ob_geometry(self) -> None:
        result = analyze_orderblocks(to_series(bearish_ob_records()), engine_config())
        ob = result.payload.order_blocks[0]
        assert ob.direction is TrendDirection.BEARISH
        assert ob.candle_index == 4
        assert (ob.zone_bottom, ob.zone_top) == (pytest.approx(9.95), pytest.approx(10.15))

    def test_reversal_origin_at_choch(self) -> None:
        result = analyze_orderblocks(v_reversal_series(), engine_config())
        origins = {b.origin for b in result.payload.order_blocks}
        assert BlockOrigin.REVERSAL in origins
        reversal = next(b for b in result.payload.order_blocks if b.origin is BlockOrigin.REVERSAL)
        scan = analyze_structure(v_reversal_series(), engine_config())
        linked = next(b for b in scan.payload.breaks if b.id == reversal.linked_break_id)
        assert linked.break_type.value == "choch"

    def test_refinement_threshold_strict(self) -> None:
        series = to_series(refined_ob_records())
        atr_at = atr(series.candles, 3)[4]
        assert atr_at is not None
        height = 10.49 - 9.5
        # condition is height > multiple * ATR (strict): exact ratio → unrefined
        out = analyze_orderblocks(
            series, engine_config(ob_refine_atr_multiple=height / atr_at)
        ).payload.order_blocks
        assert out and not out[0].is_refined
        out = analyze_orderblocks(
            series, engine_config(ob_refine_atr_multiple=height / atr_at * 0.99)
        ).payload.order_blocks
        assert out and out[0].is_refined

    def test_refined_zone_geometry(self) -> None:
        result = analyze_orderblocks(to_series(refined_ob_records()), engine_config())
        ob = result.payload.order_blocks[0]
        assert ob.is_refined
        assert ob.refined_bottom == pytest.approx(9.5)
        assert ob.refined_top == pytest.approx(9.5 + 0.5 * (10.49 - 9.5))

    def test_fvg_overlap_links(self) -> None:
        config = engine_config()
        result = analyze_orderblocks(uptrend_series(), config)
        fvg_ids = {f.id for f in analyze_fvg(uptrend_series(), config).payload.fvgs}
        linked = [b for b in result.payload.order_blocks if b.overlapping_fvg_ids]
        assert linked, "expected OB/FVG overlaps in the uptrend fixture"
        for ob in linked:
            assert set(ob.overlapping_fvg_ids) <= fvg_ids


class TestOrderBlockLifecycle:
    def test_bullish_story(self) -> None:
        result = analyze_orderblocks(to_series(bullish_ob_records()), engine_config())
        ob = next(b for b in result.payload.order_blocks if b.direction is TrendDirection.BULLISH)
        assert ob.first_touch_index == 10
        assert ob.mitigation_index == 11  # wick through far boundary
        assert ob.violation_index == 12  # close-through
        assert ob.status is MitigationStatus.VIOLATED
        assert not ob.is_valid
        assert ob.max_penetration_fraction == 1.0

    def test_bearish_wick_mitigation_not_violated(self) -> None:
        result = analyze_orderblocks(to_series(bearish_ob_records()), engine_config())
        ob = result.payload.order_blocks[0]
        assert ob.first_touch_index == 9
        assert ob.mitigation_index == 10
        assert ob.violation_index is None
        assert ob.status is MitigationStatus.MITIGATED
        assert ob.is_consumed  # c11 closes back below the zone

    def test_departure_candle_not_a_touch(self) -> None:
        result = analyze_orderblocks(to_series(refined_ob_records()), engine_config())
        ob = result.payload.order_blocks[0]
        assert ob.status is MitigationStatus.UNMITIGATED
        assert ob.touches == 0
        assert ob.is_valid


class TestBreakerBlocks:
    def test_violation_with_confirming_break_flips(self) -> None:
        result = analyze_orderblocks(to_series(bullish_ob_records()), engine_config())
        payload = result.payload
        assert len(payload.breaker_blocks) == 1
        brk = payload.breaker_blocks[0]
        ob = next(b for b in payload.order_blocks if b.id == brk.source_order_block_id)
        assert brk.direction is TrendDirection.BEARISH  # bullish OB violated downward
        assert (brk.zone_bottom, brk.zone_top) == (ob.zone_bottom, ob.zone_top)
        assert brk.flip_index == ob.violation_index == 12
        scan = analyze_structure(to_series(bullish_ob_records()), engine_config())
        assert brk.confirming_break_id in {b.id for b in scan.payload.breaks}
        # breaker lifecycle: c13 returns into the zone
        assert brk.status is MitigationStatus.PARTIALLY_MITIGATED

    def test_violation_without_confirming_break_no_breaker(self) -> None:
        result = analyze_orderblocks(to_series(ob_violation_no_break_records()), engine_config())
        violated = [b for b in result.payload.order_blocks if b.status is MitigationStatus.VIOLATED]
        assert violated, "fixture must contain a violated OB"
        assert result.payload.breaker_blocks == []


class TestMitigationBlocks:
    def test_sweep_without_bos_creates_block(self) -> None:
        series = to_series(mb_sweep_records())
        config = engine_config()
        result = analyze_orderblocks(series, config)
        mbs = result.payload.mitigation_blocks
        bullish = next(m for m in mbs if m.direction is TrendDirection.BULLISH)
        assert bullish.candle_index == 5  # origin = swing low before the sweep
        assert (bullish.zone_bottom, bullish.zone_top) == (
            pytest.approx(10.0),
            pytest.approx(10.15),
        )
        assert bullish.status is MitigationStatus.MITIGATED
        assert bullish.mitigation_index == 15
        # cross-module referential integrity
        sweeps = analyze_liquidity(series, config).payload.sweeps
        assert bullish.linked_sweep_id in {s.id for s in sweeps}
        scan = analyze_structure(series, config)
        assert bullish.failed_swing_id in {s.id for s in scan.payload.swings}


class TestModelValidators:
    def _kwargs(self, **overrides):
        base = dict(
            direction=TrendDirection.BULLISH,
            zone_bottom=10.0,
            zone_top=10.5,
            body_bottom=10.1,
            body_top=10.4,
            candle_index=2,
            cluster_start_index=2,
            formed_at="2024-01-01T00:02:00+00:00",
            actionable_from_index=5,
            origin=BlockOrigin.CONTINUATION,
            linked_break_id="break_x",
            age=0,
        )
        base.update(overrides)
        return base

    def test_inverted_zone_rejected(self) -> None:
        with pytest.raises(ValueError, match="zone_top"):
            OrderBlock(**self._kwargs(zone_bottom=10.5, zone_top=10.0))

    def test_unmitigated_cannot_have_touch(self) -> None:
        with pytest.raises(ValueError, match="first_touch_index"):
            OrderBlock(**self._kwargs(first_touch_index=6))

    def test_refined_requires_bounds(self) -> None:
        with pytest.raises(ValueError, match="refined"):
            OrderBlock(**self._kwargs(is_refined=True))

    def test_refined_must_be_inside(self) -> None:
        with pytest.raises(ValueError, match="inside"):
            OrderBlock(**self._kwargs(is_refined=True, refined_bottom=9.9, refined_top=10.2))

    def test_deterministic_ids(self) -> None:
        a = OrderBlock(**self._kwargs())
        b = OrderBlock(**self._kwargs())
        assert a.id == b.id
        assert a.id != OrderBlock(**self._kwargs(candle_index=3)).id
