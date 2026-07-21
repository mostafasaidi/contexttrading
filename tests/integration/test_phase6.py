"""Integration: sessions and MTF over the 2,000-candle seeded dataset.

The dataset spans ~33 hours of 1m candles (two calendar days). Assertions
are cross-module invariants, not exact values.
"""

from __future__ import annotations

import pytest

from contexttrading.analysis.mtf import analyze_mtf
from contexttrading.analysis.sessions import analyze_sessions
from contexttrading.core.config import EngineConfig, SessionConfig
from contexttrading.core.constants import LiquidityPoolKind, Timeframe, TrendDirection
from contexttrading.models.candle import CandleSeries
from tests.integration.test_pipeline import _dataset


@pytest.fixture(scope="module")
def dataset() -> CandleSeries:
    return _dataset()


@pytest.fixture(scope="module")
def config() -> EngineConfig:
    return EngineConfig()


class TestSessionsIntegration:
    def test_sessions_run_and_cover_both_days(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        result = analyze_sessions(dataset, config, SessionConfig())
        payload = result.payload
        assert payload.sessions
        dates = {s.trading_date for s in payload.sessions}
        assert len(dates) >= 2
        assert any(s.session == "asia" for s in payload.sessions)

    def test_previous_day_pools_exist(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_sessions(dataset, config, SessionConfig())
        kinds = {p.kind for p in result.payload.pools}
        assert LiquidityPoolKind.PREVIOUS_DAY_HIGH in kinds
        assert LiquidityPoolKind.PREVIOUS_DAY_LOW in kinds

    def test_session_sweeps_link_to_liquidity_sweeps(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        result = analyze_sessions(dataset, config, SessionConfig())
        sweep_ids = {s.id for s in result.payload.sweeps}
        for event in result.payload.session_sweeps:
            assert event.linked_sweep_id in sweep_ids

    def test_day_extreme_counts_cover_days(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        result = analyze_sessions(dataset, config, SessionConfig())
        payload = result.payload
        days = len({s.trading_date for s in payload.sessions if not s.is_killzone})
        # Overlapping windows (tokyo/sydney/asia) may share a day's extreme,
        # so totals are at least the number of days.
        assert sum(payload.day_high_counts.values()) >= days
        assert sum(payload.day_low_counts.values()) >= days

    def test_deterministic_on_dataset(self, dataset: CandleSeries, config: EngineConfig) -> None:
        a = analyze_sessions(dataset, config, SessionConfig())
        b = analyze_sessions(dataset, config, SessionConfig())
        assert a.model_dump_json() == b.model_dump_json()


class TestMtfIntegration:
    def test_mtf_contexts_and_weights(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_mtf(dataset, ["5m", "15m", "1h"], config)
        contexts = result.payload.contexts
        assert [c.timeframe for c in contexts] == [
            Timeframe.M1,
            Timeframe.M5,
            Timeframe.M15,
            Timeframe.H1,
        ]
        assert [c.weight for c in contexts] == [1.0, 2.0, 4.0, 8.0]
        assert contexts[1].candle_count == 400
        assert contexts[2].candle_count in (133, 134)

    def test_bias_fields_coherent(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_mtf(dataset, ["5m", "15m", "1h"], config)
        bias = result.payload.bias
        assert 0.0 <= bias.agreement_share <= 1.0
        assert 0.0 <= bias.htf_influence <= 1.0
        base = result.payload.contexts[0]
        if bias.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH) and (
            base.direction is bias.direction
        ):
            assert bias.recommended_execution_timeframe is Timeframe.M1
        else:
            assert bias.recommended_execution_timeframe is None

    def test_resample_method_roundtrip(self, dataset: CandleSeries) -> None:
        out = dataset.resample("15m")
        assert out.timeframe is Timeframe.M15
        assert len(out) in (133, 134)  # ceil(2000 / 15)
        assert out.symbol == dataset.symbol

    def test_deterministic_on_dataset(self, dataset: CandleSeries, config: EngineConfig) -> None:
        a = analyze_mtf(dataset, ["5m", "15m", "1h"], config)
        b = analyze_mtf(dataset, ["5m", "15m", "1h"], config)
        assert a.model_dump_json() == b.model_dump_json()
