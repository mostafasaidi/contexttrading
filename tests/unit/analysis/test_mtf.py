"""Unit tests for multi-timeframe context and bias aggregation."""

from __future__ import annotations

import pytest

from contexttrading.analysis.mtf import aggregate_bias, analyze_mtf
from contexttrading.core.constants import Timeframe, TrendDirection, TrendStrength
from contexttrading.core.errors import DataError
from contexttrading.models.mtf import TimeframeContext
from tests.fixtures import (
    MTF_UPTREND_PIVOTS,
    engine_config,
    five_day_15m_series,
    zigzag_series,
)


def _ctx(tf: Timeframe, direction: TrendDirection, weight: float) -> TimeframeContext:
    return TimeframeContext(
        timeframe=tf,
        trend=None,
        direction=direction,
        dealing_range=None,
        weight=weight,
        candle_count=100,
    )


class TestBiasAggregation:
    def test_full_agreement_is_strong(self) -> None:
        contexts = [
            _ctx(Timeframe.M15, TrendDirection.BULLISH, 1.0),
            _ctx(Timeframe.H1, TrendDirection.BULLISH, 2.0),
            _ctx(Timeframe.H4, TrendDirection.BULLISH, 4.0),
        ]
        bias = aggregate_bias(contexts, engine_config())
        assert bias.direction is TrendDirection.BULLISH
        assert bias.strength is TrendStrength.STRONG
        assert bias.agreement_share == 1.0
        assert bias.htf_influence == 0.0
        assert bias.recommended_execution_timeframe is Timeframe.M15
        assert bias.conflict_notes == []

    def test_htf_alignment_against_base_is_moderate(self) -> None:
        # Base bullish (1.0) vs 1h+4h bearish (2.0 + 4.0 = 6.0): share 6/7.
        contexts = [
            _ctx(Timeframe.M15, TrendDirection.BULLISH, 1.0),
            _ctx(Timeframe.H1, TrendDirection.BEARISH, 2.0),
            _ctx(Timeframe.H4, TrendDirection.BEARISH, 4.0),
        ]
        bias = aggregate_bias(contexts, engine_config())
        assert bias.direction is TrendDirection.BEARISH
        assert bias.strength is TrendStrength.MODERATE
        assert bias.agreement_share == pytest.approx(6.0 / 7.0)
        # Base conflicts with the bias: no execution timeframe.
        assert bias.recommended_execution_timeframe is None
        # All HTF weight opposes the base-TF trend.
        assert bias.htf_influence == 1.0
        assert bias.conflict_notes == ["conflict: 15m bullish vs 1h bearish"]

    def test_split_vote_is_weak(self) -> None:
        # Bull 1+2 = 3 vs bear 4: share 4/7 < 2/3.
        contexts = [
            _ctx(Timeframe.M15, TrendDirection.BULLISH, 1.0),
            _ctx(Timeframe.H1, TrendDirection.BULLISH, 2.0),
            _ctx(Timeframe.H4, TrendDirection.BEARISH, 4.0),
        ]
        bias = aggregate_bias(contexts, engine_config())
        assert bias.direction is TrendDirection.BEARISH
        assert bias.strength is TrendStrength.WEAK
        assert bias.agreement_share == pytest.approx(4.0 / 7.0)
        assert bias.htf_influence == pytest.approx(4.0 / 6.0)
        assert bias.conflict_notes == ["conflict: 1h bullish vs 4h bearish"]

    def test_tie_is_ranging(self) -> None:
        contexts = [
            _ctx(Timeframe.M15, TrendDirection.BULLISH, 1.0),
            _ctx(Timeframe.H1, TrendDirection.BEARISH, 1.0),
        ]
        bias = aggregate_bias(contexts, engine_config())
        assert bias.direction is TrendDirection.RANGING
        assert bias.strength is TrendStrength.WEAK
        assert bias.recommended_execution_timeframe is None

    def test_all_unknown_is_ranging_weak(self) -> None:
        contexts = [
            _ctx(Timeframe.M15, TrendDirection.UNKNOWN, 1.0),
            _ctx(Timeframe.H1, TrendDirection.UNKNOWN, 2.0),
        ]
        bias = aggregate_bias(contexts, engine_config())
        assert bias.direction is TrendDirection.RANGING
        assert bias.strength is TrendStrength.WEAK
        assert bias.agreement_share == 0.0
        assert bias.htf_influence == 0.0


class TestMtfEndToEnd:
    def test_aligned_uptrend_strong_bias(self) -> None:
        config = engine_config(internal_swing_lookback=1, external_swing_lookback=2)
        series = zigzag_series(MTF_UPTREND_PIVOTS, leg_bars=16, symbol="UP", bar_minutes=15)
        result = analyze_mtf(series, ["1h"], config)
        contexts = result.payload.contexts
        assert [str(c.timeframe) for c in contexts] == ["15m", "1h"]
        assert all(c.direction is TrendDirection.BULLISH for c in contexts)
        bias = result.payload.bias
        assert bias.direction is TrendDirection.BULLISH
        assert bias.strength is TrendStrength.STRONG
        assert bias.recommended_execution_timeframe is Timeframe.M15

    def test_contexts_sorted_deduplicated_and_weighted(self) -> None:
        result = analyze_mtf(five_day_15m_series(), ["4h", "1h", "1h"], engine_config())
        contexts = result.payload.contexts
        assert [c.timeframe for c in contexts] == [
            Timeframe.M15,
            Timeframe.H1,
            Timeframe.H4,
        ]
        assert [c.weight for c in contexts] == [1.0, 2.0, 4.0]
        assert contexts[0].candle_count == 480
        assert contexts[1].candle_count == 120
        assert contexts[2].candle_count == 30

    def test_short_htf_yields_unknown_context(self) -> None:
        series = zigzag_series([10, 12, 11, 13, 12, 14], leg_bars=4, symbol="SHORT")
        result = analyze_mtf(series, ["1d"], engine_config())
        htf = result.payload.contexts[-1]
        assert htf.timeframe is Timeframe.D1
        assert htf.direction is TrendDirection.UNKNOWN
        assert htf.trend is None
        assert htf.dealing_range is None

    def test_recommendation_consistency(self) -> None:
        result = analyze_mtf(five_day_15m_series(), ["1h", "4h"], engine_config())
        bias = result.payload.bias
        base = result.payload.contexts[0]
        if bias.direction is base.direction and bias.direction in (
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
        ):
            assert bias.recommended_execution_timeframe is base.timeframe
        else:
            assert bias.recommended_execution_timeframe is None

    def test_deterministic_repeat_runs(self) -> None:
        a = analyze_mtf(five_day_15m_series(), ["1h", "4h", "1d"], engine_config())
        b = analyze_mtf(five_day_15m_series(), ["1h", "4h", "1d"], engine_config())
        assert a.model_dump_json() == b.model_dump_json()

    def test_envelope_metadata(self) -> None:
        series = five_day_15m_series()
        result = analyze_mtf(series, ["1h"], engine_config())
        assert result.module == "mtf"
        assert result.payload.base_timeframe is Timeframe.M15
        assert result.generated_from.candle_count == len(series)


class TestMtfErrors:
    def test_same_timeframe_rejected(self) -> None:
        with pytest.raises(DataError, match="strictly higher"):
            analyze_mtf(five_day_15m_series(), ["15m"], engine_config())

    def test_lower_timeframe_rejected(self) -> None:
        with pytest.raises(DataError, match="strictly higher"):
            analyze_mtf(five_day_15m_series(), ["5m"], engine_config())
