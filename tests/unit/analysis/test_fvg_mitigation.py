"""Tests for FVG mitigation lifecycle, inversion, strength, and ranking."""

from __future__ import annotations

import pytest

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.fvg.detection import RawFVG
from contexttrading.analysis.fvg.inversion import (
    closes_through_far_side,
    trades_through_far_side,
)
from contexttrading.analysis.fvg.mitigation import (
    LifecycleState,
    age_score,
    freshness_score,
    strength_score,
    structure_bonus,
    update_state,
)
from contexttrading.core.constants import (
    BreakStrength,
    MitigationStatus,
    TrendDirection,
)
from contexttrading.models.candle import Candle
from contexttrading.models.fvg import FVG
from tests.fixtures import engine_config, make_candle, to_series
from tests.fvg_fixtures import (
    bearish_fvg_records,
    bullish_fvg_records,
    untouched_fvg_records,
    wick_only_fill_records,
)


def _raw(direction: TrendDirection = TrendDirection.BULLISH) -> RawFVG:
    return RawFVG(
        direction=direction,
        zone_bottom=10.0,
        zone_top=10.5,
        formation_start_index=0,
        middle_index=1,
        formation_end_index=2,
        gap_size=0.5,
        gap_atr=None,
        gap_percent=0.05,
    )


def _candle(o: float, h: float, low: float, c: float) -> Candle:
    return to_series([make_candle(0, o, h, low, c)]).candles[0]


def _single(result, bottom: float = 10.0):
    return next(f for f in result.payload.fvgs if f.zone_bottom == pytest.approx(bottom))


class TestInversionPrimitives:
    def test_close_through_requires_close_not_wick(self) -> None:
        wick_only = _candle(10.4, 10.6, 9.9, 10.4)  # wick through, close inside
        close_through = _candle(10.4, 10.6, 9.9, 9.95)
        assert not closes_through_far_side(TrendDirection.BULLISH, 10.0, 10.5, wick_only)
        assert closes_through_far_side(TrendDirection.BULLISH, 10.0, 10.5, close_through)

    def test_trades_through_counts_wicks(self) -> None:
        wick_only = _candle(10.4, 10.6, 9.9, 10.4)
        assert trades_through_far_side(TrendDirection.BULLISH, 10.0, 10.5, wick_only)

    def test_bearish_mirror(self) -> None:
        candle = _candle(10.6, 11.1, 10.55, 11.05)  # wick + close above top
        assert trades_through_far_side(TrendDirection.BEARISH, 10.5, 11.0, candle)
        assert closes_through_far_side(TrendDirection.BEARISH, 10.5, 11.0, candle)


class TestUpdateState:
    def test_partial_then_fill_then_inverse(self) -> None:
        raw = _raw()
        state = LifecycleState()
        update_state(state, raw, _candle(11.0, 11.2, 10.3, 10.6), 3)  # partial 0.4
        assert state.status is MitigationStatus.PARTIALLY_MITIGATED
        assert state.first_touch_index == 3
        assert state.max_fill_fraction == pytest.approx(0.4)
        update_state(state, raw, _candle(10.6, 10.7, 9.9, 10.2), 4)  # wick fill, close inside
        assert state.status is MitigationStatus.MITIGATED
        assert state.filled_index == 4
        assert state.max_fill_fraction == 1.0
        assert not state.is_inverse
        update_state(state, raw, _candle(10.2, 10.3, 9.8, 9.9), 5)  # close-through
        assert state.status is MitigationStatus.VIOLATED
        assert state.is_inverse and state.inversion_index == 5

    def test_untouched_candles_do_nothing(self) -> None:
        raw = _raw()
        state = LifecycleState()
        update_state(state, raw, _candle(11.0, 11.2, 10.6, 11.1), 3)
        assert state.status is MitigationStatus.UNMITIGATED
        assert state.touches == 0 and state.first_touch_index is None

    def test_fill_and_inverse_same_candle(self) -> None:
        raw = _raw()
        state = LifecycleState()
        update_state(state, raw, _candle(10.4, 10.6, 9.8, 9.9), 3)
        assert state.status is MitigationStatus.VIOLATED
        assert state.filled_index == 3 and state.inversion_index == 3

    def test_violated_is_terminal(self) -> None:
        raw = _raw()
        state = LifecycleState(status=MitigationStatus.VIOLATED, is_inverse=True, inversion_index=4)
        update_state(state, raw, _candle(11.0, 11.5, 10.9, 11.4), 5)
        assert state.touches == 0 and state.status is MitigationStatus.VIOLATED


class TestPipelineLifecycle:
    def test_bullish_story(self) -> None:
        result = analyze_fvg(to_series(bullish_fvg_records()), engine_config())
        fvg = _single(result)
        assert fvg.direction is TrendDirection.BULLISH
        assert fvg.first_touch_index == 4
        assert fvg.filled_index == 5
        assert fvg.max_fill_fraction == 1.0
        assert fvg.touches == 2  # c6 close-through adds no touch (already filled)
        assert fvg.is_inverse and fvg.inversion_index == 6
        assert fvg.status is MitigationStatus.VIOLATED
        assert fvg.age == 5 - 2  # formation_end → fill

    def test_bearish_mirror(self) -> None:
        result = analyze_fvg(to_series(bearish_fvg_records()), engine_config())
        fvg = _single(result, bottom=10.5)
        assert fvg.direction is TrendDirection.BEARISH
        assert fvg.first_touch_index == 4
        assert fvg.filled_index == 5
        assert fvg.is_inverse and fvg.inversion_index == 5  # fill + close-through same candle
        assert fvg.status is MitigationStatus.VIOLATED

    def test_wick_only_fill_not_inverse(self) -> None:
        result = analyze_fvg(to_series(wick_only_fill_records()), engine_config())
        fvg = _single(result)
        assert fvg.status is MitigationStatus.MITIGATED
        assert fvg.filled_index == 3
        assert fvg.max_fill_fraction == 1.0
        assert not fvg.is_inverse and fvg.inversion_index is None

    def test_untouched_ages_to_series_end(self) -> None:
        result = analyze_fvg(to_series(untouched_fvg_records()), engine_config())
        fvg = _single(result)
        assert fvg.status is MitigationStatus.UNMITIGATED
        assert fvg.first_touch_index is None and fvg.filled_index is None
        assert fvg.touches == 0
        assert fvg.age == 6 - 2  # last candle index - formation_end


class TestStrength:
    def test_component_helpers(self) -> None:
        assert freshness_score(MitigationStatus.UNMITIGATED) == 1.0
        assert freshness_score(MitigationStatus.VIOLATED) == 0.0
        assert age_score(0, 50) == 1.0
        assert age_score(50, 50) == pytest.approx(0.5)
        assert structure_bonus(True, True) == 1.0
        assert structure_bonus(True, False) == 0.5

    def test_deterministic_and_bounded(self) -> None:
        config = engine_config()
        kwargs = dict(
            gap_atr=1.2,
            linked=None,
            status=MitigationStatus.UNMITIGATED,
            age=3,
            is_nested=False,
            is_stacked=False,
            config=config,
        )
        first = strength_score(**kwargs)
        assert first == strength_score(**kwargs)
        assert 0.0 <= first <= 1.0

    def test_warmup_gap_defaults_to_half(self) -> None:
        config = engine_config()
        warmup = strength_score(
            gap_atr=None,
            linked=None,
            status=MitigationStatus.UNMITIGATED,
            age=0,
            is_nested=False,
            is_stacked=False,
            config=config,
        )
        expected = (
            config.fvg_weight_gap * 0.5
            + config.fvg_weight_freshness * 1.0
            + config.fvg_weight_age * 1.0
        )
        assert warmup == pytest.approx(expected)

    def test_displacement_link_raises_strength(self) -> None:
        result = analyze_fvg(to_series(bullish_fvg_records()), engine_config())
        fvg = _single(result)
        manual = strength_score(
            gap_atr=fvg.gap_atr,
            linked=None,
            status=fvg.status,
            age=fvg.age,
            is_nested=fvg.is_nested,
            is_stacked=fvg.stack_group_id is not None,
            config=engine_config(),
        )
        with_break = strength_score(
            gap_atr=fvg.gap_atr,
            linked=_StrongBreak(),
            status=fvg.status,
            age=fvg.age,
            is_nested=fvg.is_nested,
            is_stacked=fvg.stack_group_id is not None,
            config=engine_config(),
        )
        assert with_break > manual

    def test_freshness_ordering(self) -> None:
        config = engine_config()
        base = dict(
            gap_atr=1.0, linked=None, age=0, is_nested=False, is_stacked=False, config=config
        )
        scores = {
            status: strength_score(status=status, **base)
            for status in (
                MitigationStatus.UNMITIGATED,
                MitigationStatus.PARTIALLY_MITIGATED,
                MitigationStatus.MITIGATED,
                MitigationStatus.VIOLATED,
            )
        }
        assert (
            scores[MitigationStatus.UNMITIGATED]
            > scores[MitigationStatus.PARTIALLY_MITIGATED]
            > scores[MitigationStatus.MITIGATED]
            > scores[MitigationStatus.VIOLATED]
        )


class _StrongBreak:
    """Minimal stand-in with the attributes displacement_score reads."""

    strength = BreakStrength.STRONG


class TestRankingAndEnvelope:
    def test_ranks_sequential_from_one(self) -> None:
        result = analyze_fvg(to_series(untouched_fvg_records()), engine_config())
        ranks = sorted(f.rank for f in result.payload.fvgs)
        assert ranks == list(range(1, len(ranks) + 1))
        strengths = [f.strength for f in result.payload.fvgs]
        assert strengths == sorted(strengths, reverse=True)

    def test_envelope_counts(self) -> None:
        result = analyze_fvg(to_series(bullish_fvg_records()), engine_config())
        payload = result.payload
        assert payload.total_count == len(payload.fvgs)
        assert sum(payload.counts_by_status.values()) == payload.total_count
        assert sum(payload.counts_by_direction.values()) == payload.total_count
        assert result.module == "fvg"

    def test_deterministic_ids_across_runs(self) -> None:
        a = analyze_fvg(to_series(bullish_fvg_records()), engine_config())
        b = analyze_fvg(to_series(bullish_fvg_records()), engine_config())
        assert [f.id for f in a.payload.fvgs] == [f.id for f in b.payload.fvgs]


class TestModelValidators:
    def _kwargs(self, **overrides):
        base = dict(
            direction=TrendDirection.BULLISH,
            zone_bottom=10.0,
            zone_top=10.5,
            formation_start_index=0,
            middle_index=1,
            formation_end_index=2,
            formed_at="2024-01-01T00:01:00+00:00",
            gap_size=0.5,
            gap_percent=0.05,
            age=0,
            strength=0.5,
        )
        base.update(overrides)
        return base

    def test_inverted_zone_rejected(self) -> None:
        with pytest.raises(ValueError, match="zone_top"):
            FVG(**self._kwargs(zone_bottom=10.5, zone_top=10.0))

    def test_scrambled_indices_rejected(self) -> None:
        with pytest.raises(ValueError, match="start < middle < end"):
            FVG(**self._kwargs(middle_index=2, formation_end_index=1))

    def test_inverse_requires_inversion_index(self) -> None:
        with pytest.raises(ValueError, match="inversion_index"):
            FVG(**self._kwargs(is_inverse=True))

    def test_unmitigated_cannot_have_touch(self) -> None:
        with pytest.raises(ValueError, match="first_touch_index"):
            FVG(**self._kwargs(first_touch_index=3))
