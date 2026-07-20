"""Tests for analysis.liquidity: equal levels, pools, sweeps."""

from __future__ import annotations

import pytest

from contexttrading.analysis.indicators import atr
from contexttrading.analysis.liquidity import (
    analyze_liquidity,
    build_pools,
    detect_equal_levels,
    scan_sweeps,
)
from contexttrading.analysis.structure.swings import detect_swing_sets
from contexttrading.core.constants import (
    BreakStrength,
    LiquidityPoolKind,
    LiquiditySide,
    PoolStatus,
    StructureBreakType,
    SweepClassification,
    SwingClass,
    SwingType,
    TrendDirection,
)
from contexttrading.models.liquidity import LiquidityPool
from contexttrading.models.structure import StructureBreak, swing_style
from tests.fixtures import engine_config, fakeout_records, make_candle, to_series, zigzag_series


def _external(series):
    _, external = detect_swing_sets(series, engine_config())
    return external


class TestEqualLevels:
    def test_detects_equal_highs(self) -> None:
        # Two swing highs at 15.05 and 15.10 (spread 0.05, within tolerance).
        series = zigzag_series([10, 15, 12, 15.05, 11, 12])
        config = engine_config(equal_level_atr_fraction=0.2)
        levels = detect_equal_levels(_external(series), atr(series.candles, 3), config)
        highs = [lv for lv in levels if lv.side is LiquiditySide.BUYSIDE]
        assert len(highs) == 1
        assert highs[0].count == 2
        assert highs[0].price == pytest.approx((15.05 + 15.10) / 2)

    def test_tolerance_boundary_inclusive(self) -> None:
        series = zigzag_series([10, 15, 12, 15.5, 11, 12])
        swings = _external(series)
        atr_values = atr(series.candles, 3)
        second = max((s for s in swings if s.swing_type is SwingType.HIGH), key=lambda s: s.index)
        atr_at = atr_values[second.index]
        assert atr_at is not None
        spread = 0.5
        # Exactly at tolerance → included; strictly beyond → excluded.
        config_in = engine_config(equal_level_atr_fraction=spread / atr_at)
        config_out = engine_config(equal_level_atr_fraction=spread / atr_at * 0.99)
        assert len(detect_equal_levels(swings, atr_values, config_in)) == 1
        assert detect_equal_levels(swings, atr_values, config_out) == []

    def test_min_separation_enforced(self) -> None:
        # leg_bars=2 → consecutive pivots only 2 bars apart; separation=3 blocks.
        series = zigzag_series([10, 15, 12, 15.02, 11], leg_bars=4)
        config = engine_config(equal_level_min_separation=9)
        levels = detect_equal_levels(_external(series), atr(series.candles, 3), config)
        assert levels == []

    def test_distinct_levels_not_merged(self) -> None:
        series = zigzag_series([10, 15, 12, 18, 11, 12])
        config = engine_config(equal_level_atr_fraction=0.1)
        assert detect_equal_levels(_external(series), atr(series.candles, 3), config) == []


class TestPools:
    def test_pools_from_swings(self) -> None:
        series = zigzag_series([10, 15, 12, 17, 14, 16])
        config = engine_config()
        swings = _external(series)
        levels = detect_equal_levels(swings, atr(series.candles, 3), config)
        pools = build_pools(swings, levels)
        assert len(pools) == len(swings)  # no equal levels → one pool per swing
        assert all(p.status is PoolStatus.UNTAPPED for p in pools)
        sides = {p.side for p in pools}
        assert sides == {LiquiditySide.BUYSIDE, LiquiditySide.SELLSIDE}
        kinds = {p.kind for p in pools}
        assert kinds == {LiquidityPoolKind.SWING_HIGH, LiquidityPoolKind.SWING_LOW}

    def test_equal_level_pool_replaces_member_pools(self) -> None:
        series = zigzag_series([10, 15, 12, 15.05, 11, 12])
        config = engine_config(equal_level_atr_fraction=0.2)
        swings = _external(series)
        levels = detect_equal_levels(swings, atr(series.candles, 3), config)
        pools = build_pools(swings, levels)
        eq_pools = [p for p in pools if p.kind is LiquidityPoolKind.EQUAL_HIGHS]
        assert len(eq_pools) == 1
        assert eq_pools[0].source_ids[0] == levels[0].id
        # Member swings must not also appear as single-swing pools.
        single = [p for p in pools if p.kind is LiquidityPoolKind.SWING_HIGH]
        assert all(set(levels[0].member_swing_ids).isdisjoint(p.source_ids) for p in single)


def _pool(price: float, side: LiquiditySide, formed: int = 0) -> LiquidityPool:
    from contexttrading.models.structure import SwingPoint

    swing_type = SwingType.HIGH if side is LiquiditySide.BUYSIDE else SwingType.LOW
    src = SwingPoint(
        index=formed,
        timestamp="2024-01-01T00:00:00Z",
        price=price,
        swing_type=swing_type,
        swing_class=SwingClass.EXTERNAL,
        lookback=3,
        style=swing_style(swing_type, SwingClass.EXTERNAL),
    )
    kind = (
        LiquidityPoolKind.SWING_HIGH
        if side is LiquiditySide.BUYSIDE
        else LiquidityPoolKind.SWING_LOW
    )
    return LiquidityPool(
        price=price,
        side=side,
        kind=kind,
        pool_class=SwingClass.EXTERNAL,
        source_ids=[src.id],
        formed_at_index=formed,
    )


class TestSweepClassification:
    def _run(self, records, pool, *, atr_value=1.0, false_breaks=()):
        series = to_series(records)
        atr_values = tuple(atr_value for _ in records)
        config = engine_config(sweep_grab_atr_fraction=0.5)
        return scan_sweeps(series, [pool], list(false_breaks), atr_values, config)

    def test_sweep_shallow(self) -> None:
        pool = _pool(15.0, LiquiditySide.BUYSIDE)
        records = [
            make_candle(0, 14, 14.5, 13.5, 14.2),
            make_candle(1, 14.2, 15.3, 14.0, 14.8),  # wick 0.3 < 0.5 ATR, close inside
        ]
        (updated,), sweeps = self._run(records, pool)
        assert updated.status is PoolStatus.SWEPT
        assert sweeps[0].classification is SweepClassification.SWEEP
        assert sweeps[0].close_back_inside is True

    def test_grab_deep(self) -> None:
        pool = _pool(15.0, LiquiditySide.BUYSIDE)
        records = [
            make_candle(0, 14, 14.5, 13.5, 14.2),
            make_candle(1, 14.2, 15.8, 14.0, 14.8),  # wick 0.8 >= 0.5 ATR, close inside
        ]
        (_,), sweeps = self._run(records, pool)
        assert sweeps[0].classification is SweepClassification.GRAB
        assert sweeps[0].penetration_atr == pytest.approx(0.8)

    def test_stop_hunt_via_false_break(self) -> None:
        pool = _pool(15.0, LiquiditySide.BUYSIDE)
        records = [
            make_candle(0, 14, 14.5, 13.5, 14.2),
            make_candle(1, 14.2, 15.3, 14.0, 14.8),
        ]
        false_break = StructureBreak(
            broken_swing_id=pool.source_ids[0],
            broken_swing_price=15.0,
            broken_swing_class=SwingClass.EXTERNAL,
            break_index=1,
            break_timestamp=records[1]["timestamp"],
            break_price=15.3,
            direction=TrendDirection.BULLISH,
            break_type=StructureBreakType.BOS,
            break_class="external",  # type: ignore[arg-type]
            significance="major",  # type: ignore[arg-type]
            strength=BreakStrength.FALSE,
            is_sweep_candidate=True,
        )
        (updated,), sweeps = self._run(records, pool, false_breaks=[false_break])
        assert updated.status is PoolStatus.SWEPT
        assert sweeps[0].classification is SweepClassification.STOP_HUNT
        assert sweeps[0].linked_break_id == false_break.id

    def test_close_through_breaks_pool(self) -> None:
        pool = _pool(15.0, LiquiditySide.BUYSIDE)
        records = [
            make_candle(0, 14, 14.5, 13.5, 14.2),
            make_candle(1, 14.8, 15.5, 14.7, 15.3),  # closes through
        ]
        (updated,), sweeps = self._run(records, pool)
        assert updated.status is PoolStatus.BROKEN
        assert sweeps == []

    def test_sellside_mirror(self) -> None:
        pool = _pool(12.0, LiquiditySide.SELLSIDE)
        records = [
            make_candle(0, 13, 13.5, 12.5, 13.2),
            make_candle(1, 13.2, 13.3, 11.7, 12.6),  # wick below, close back inside
        ]
        (updated,), sweeps = self._run(records, pool)
        assert updated.status is PoolStatus.SWEPT
        assert sweeps[0].wick_extreme == pytest.approx(11.7)

    def test_untouched_pool_stays_untapped(self) -> None:
        pool = _pool(15.0, LiquiditySide.BUYSIDE)
        records = [make_candle(i, 14, 14.5, 13.5, 14.2) for i in range(5)]
        (updated,), sweeps = self._run(records, pool)
        assert updated.status is PoolStatus.UNTAPPED
        assert sweeps == []

    def test_pool_inactive_before_formation(self) -> None:
        pool = _pool(15.0, LiquiditySide.BUYSIDE, formed=3)
        records = [
            make_candle(0, 16, 16.5, 15.5, 16.2),  # above the pool but before activation
            make_candle(1, 16, 16.5, 15.5, 16.2),
            make_candle(2, 16, 16.5, 15.5, 16.2),
            make_candle(3, 14, 14.5, 13.5, 14.2),
            make_candle(4, 14.2, 15.3, 14.0, 14.8),  # first active touch
        ]
        (updated,), sweeps = self._run(records, pool)
        assert updated.status is PoolStatus.SWEPT
        assert sweeps[0].candle_index == 4

    def test_first_touch_only(self) -> None:
        pool = _pool(15.0, LiquiditySide.BUYSIDE)
        records = [
            make_candle(0, 14, 14.5, 13.5, 14.2),
            make_candle(1, 14.2, 15.3, 14.0, 14.8),
            make_candle(2, 14.8, 15.4, 14.6, 14.9),  # second touch ignored
        ]
        (_,), sweeps = self._run(records, pool)
        assert len(sweeps) == 1


class TestLiquidityPipeline:
    def test_fakeout_stop_hunt(self) -> None:
        result = analyze_liquidity(to_series(fakeout_records(), symbol="FAKE"), engine_config())
        payload = result.payload
        stop_hunts = [
            s for s in payload.sweeps if s.classification is SweepClassification.STOP_HUNT
        ]
        assert len(stop_hunts) == 1
        hunt = stop_hunts[0]
        assert hunt.candle_index == 20
        assert hunt.pool_price == pytest.approx(16.05)
        assert hunt.linked_break_id is not None
        pool = next(p for p in payload.pools if p.id == hunt.pool_id)
        assert pool.status is PoolStatus.SWEPT

    def test_pool_statuses_resolve(self) -> None:
        result = analyze_liquidity(to_series(fakeout_records(), symbol="FAKE"), engine_config())
        statuses = {round(p.price, 2): p.status for p in result.payload.pools}
        assert statuses[15.05] is PoolStatus.BROKEN  # closed through on the way up
        assert statuses[16.05] is PoolStatus.SWEPT  # fakeout
        assert statuses[11.95] is PoolStatus.UNTAPPED
        assert statuses[13.95] is PoolStatus.UNTAPPED

    def test_envelope_and_determinism(self) -> None:
        series = to_series(fakeout_records(), symbol="FAKE")
        a = analyze_liquidity(series, engine_config())
        b = analyze_liquidity(series, engine_config())
        assert a.module == "liquidity"
        assert a.model_dump_json() == b.model_dump_json()
