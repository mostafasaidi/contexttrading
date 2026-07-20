"""Tests for analysis.structure.trend: TrendEngine state composition."""

from __future__ import annotations

from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.analysis.structure.trend import (
    analyze_trend,
    bos_follow_through,
    impulse_correction_ratio,
    leg_overlap_fraction,
)
from contexttrading.core.constants import (
    LegKind,
    MarketPhase,
    TrendDirection,
    TrendStrength,
)
from contexttrading.models.structure import Leg
from tests.fixtures import (
    downtrend_series,
    engine_config,
    flat_series,
    ranging_series,
    uptrend_series,
    v_reversal_series,
)


def _scan(series, config=None):
    return StructureScanner(config or engine_config()).run(series)


def _leg(kind: LegKind, atr_multiple: float | None, start: float = 10.0, end: float = 12.0) -> Leg:
    return Leg(
        start_index=0,
        end_index=5,
        start_price=start,
        end_price=end,
        direction=TrendDirection.BULLISH if end > start else TrendDirection.BEARISH,
        kind=kind,
        magnitude=abs(end - start),
        atr_multiple=atr_multiple,
        duration=5,
    )


class TestRatios:
    def test_impulse_correction_ratio(self) -> None:
        legs = [
            _leg(LegKind.IMPULSE, 3.0),
            _leg(LegKind.IMPULSE, 1.0),
            _leg(LegKind.CORRECTION, 1.0),
        ]
        assert impulse_correction_ratio(legs) == 2.0

    def test_ratio_none_without_both_kinds(self) -> None:
        assert impulse_correction_ratio([_leg(LegKind.IMPULSE, 2.0)]) is None
        assert impulse_correction_ratio([]) is None

    def test_follow_through(self) -> None:
        scan = _scan(uptrend_series())
        value = bos_follow_through(scan.breaks)
        assert value is not None and 0.0 <= value <= 1.0

    def test_leg_overlap(self) -> None:
        a = _leg(LegKind.IMPULSE, None, start=10.0, end=14.0)
        b = _leg(LegKind.CORRECTION, None, start=14.0, end=12.0)
        # overlap of [10,14] and [12,14] = 2; shorter leg = 2 → 1.0
        assert leg_overlap_fraction([a, b]) == 1.0
        c = _leg(LegKind.IMPULSE, None, start=20.0, end=24.0)
        assert leg_overlap_fraction([a, c]) == 0.0
        assert leg_overlap_fraction([a]) is None


class TestTrendState:
    def test_uptrend_state(self) -> None:
        result = analyze_trend(uptrend_series(), engine_config())
        state = result.payload.state
        assert state.direction is TrendDirection.BULLISH
        assert state.external_trend is TrendDirection.BULLISH
        assert state.strength in (TrendStrength.MODERATE, TrendStrength.STRONG)
        assert state.confidence_basis  # evidence tags present
        assert "hh_hl_sequence" in state.confidence_basis

    def test_downtrend_state(self) -> None:
        result = analyze_trend(downtrend_series(), engine_config())
        state = result.payload.state
        assert state.direction is TrendDirection.BEARISH
        assert "lh_ll_sequence" in state.confidence_basis

    def test_v_reversal_flips(self) -> None:
        result = analyze_trend(v_reversal_series(), engine_config())
        assert result.payload.state.direction is TrendDirection.BEARISH

    def test_ranging_state(self) -> None:
        result = analyze_trend(ranging_series(), engine_config())
        state = result.payload.state
        assert state.direction is TrendDirection.UNKNOWN
        assert state.market_phase is MarketPhase.CONSOLIDATION

    def test_flat_series(self) -> None:
        result = analyze_trend(flat_series(), engine_config())
        state = result.payload.state
        assert state.direction is TrendDirection.UNKNOWN
        assert state.impulse_correction_ratio is None

    def test_basis_is_deterministic_data(self) -> None:
        a = analyze_trend(uptrend_series(), engine_config())
        b = analyze_trend(uptrend_series(), engine_config())
        assert a.payload.state.confidence_basis == b.payload.state.confidence_basis
        for tag in a.payload.state.confidence_basis:
            assert " " not in tag  # compact evidence tags, no prose

    def test_market_phase_expansion_after_bos(self) -> None:
        config = engine_config(consolidation_range_atr_multiple=0.1)  # disable compression
        result = analyze_trend(uptrend_series(), config)
        assert result.payload.state.market_phase is MarketPhase.EXPANSION

    def test_envelope(self) -> None:
        result = analyze_trend(uptrend_series(), engine_config())
        assert result.module == "trend"
        assert result.schema_version == "1.0.0"
