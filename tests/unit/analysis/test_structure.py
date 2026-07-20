"""Tests for analysis.structure.structure: the BOS/CHoCH state machine."""

from __future__ import annotations

import pytest

from contexttrading.analysis.structure.structure import (
    StructureScanner,
    analyze_structure,
    sequence_trend,
)
from contexttrading.core.constants import (
    BreakStrength,
    StructureBreakClass,
    StructureBreakSignificance,
    StructureBreakType,
    TrendDirection,
)
from contexttrading.core.errors import InsufficientDataError
from tests.fixtures import (
    downtrend_series,
    engine_config,
    fakeout_records,
    flat_series,
    ranging_series,
    to_series,
    uptrend_series,
    v_reversal_series,
)


def _external_breaks(series, config=None):
    scan = StructureScanner(config or engine_config()).run(series)
    return scan, [b for b in scan.breaks if b.break_class is StructureBreakClass.EXTERNAL]


class TestSequenceTrend:
    def test_bullish(self) -> None:
        assert sequence_trend([10, 12, 14], [8, 9, 10]) is TrendDirection.BULLISH

    def test_bearish(self) -> None:
        assert sequence_trend([14, 12, 10], [10, 9, 8]) is TrendDirection.BEARISH

    def test_ranging(self) -> None:
        # LH on highs + HL on lows → mixed sequence.
        assert sequence_trend([10, 12, 11], [9, 8, 8.5]) is TrendDirection.RANGING

    def test_unknown_when_thin(self) -> None:
        assert sequence_trend([10], [8]) is TrendDirection.UNKNOWN


class TestUptrend:
    def test_two_bullish_bos(self) -> None:
        _, ext = _external_breaks(uptrend_series())
        bos = [b for b in ext if b.break_type is StructureBreakType.BOS]
        assert len(bos) == 2
        assert all(b.direction is TrendDirection.BULLISH for b in bos)
        assert bos[0].break_index == 11
        assert bos[0].broken_swing_price == pytest.approx(15.05)
        assert bos[1].break_index == 19
        assert bos[1].broken_swing_price == pytest.approx(17.05)

    def test_bos_is_major_and_strong(self) -> None:
        _, ext = _external_breaks(uptrend_series())
        bos = [b for b in ext if b.break_type is StructureBreakType.BOS]
        assert all(b.significance is StructureBreakSignificance.MAJOR for b in bos)
        assert all(b.strength is BreakStrength.STRONG for b in bos)
        assert all(b.margin_atr is not None and b.margin_atr >= 0.25 for b in bos)

    def test_protected_low_after_bos(self) -> None:
        scan, _ = _external_breaks(uptrend_series())
        assert scan.protected_low is not None
        assert scan.protected_low.price == pytest.approx(13.95)  # L14@16
        assert scan.external_trend is TrendDirection.BULLISH
        assert scan.protected_high is None

    def test_levels_consumed_no_repeat_bos(self) -> None:
        _, ext = _external_breaks(uptrend_series())
        broken = [b.broken_swing_id for b in ext if b.strength is not BreakStrength.FALSE]
        assert len(broken) == len(set(broken))  # each level breaks at most once

    def test_every_break_references_existing_swing(self) -> None:
        scan = StructureScanner(engine_config()).run(uptrend_series())
        swing_ids = {s.id for s in scan.external_swings + scan.internal_swings}
        assert all(b.broken_swing_id in swing_ids for b in scan.breaks)


class TestDowntrend:
    def test_two_bearish_bos(self) -> None:
        scan, ext = _external_breaks(downtrend_series())
        bos = [b for b in ext if b.break_type is StructureBreakType.BOS]
        assert len(bos) == 2
        assert all(b.direction is TrendDirection.BEARISH for b in bos)
        assert scan.external_trend is TrendDirection.BEARISH
        assert scan.protected_high is not None
        assert scan.protected_high.price == pytest.approx(16.05)  # H16@16


class TestChoch:
    def test_v_reversal_flips_trend(self) -> None:
        scan, ext = _external_breaks(v_reversal_series())
        choch = [b for b in ext if b.break_type is StructureBreakType.CHOCH]
        assert len(choch) == 1
        event = choch[0]
        assert event.direction is TrendDirection.BEARISH
        assert event.break_index == 18
        assert event.broken_swing_price == pytest.approx(11.95)  # protected L12
        assert scan.external_trend is TrendDirection.BEARISH
        assert scan.protected_high is not None
        assert scan.protected_high.price == pytest.approx(17.05)
        assert scan.protected_low is None

    def test_bos_before_choch(self) -> None:
        _, ext = _external_breaks(v_reversal_series())
        ordered = sorted(ext, key=lambda b: b.break_index)
        # Bullish BOS establishes the trend, CHoCH flips it, then a bearish
        # BOS breaks L14 (13.95) in the new trend direction.
        assert [b.break_type for b in ordered] == [
            StructureBreakType.BOS,
            StructureBreakType.CHOCH,
            StructureBreakType.BOS,
        ]
        assert [b.direction for b in ordered] == [
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
            TrendDirection.BEARISH,
        ]


class TestFalseBreak:
    def test_wick_only_breach_is_false(self) -> None:
        _, ext = _external_breaks(to_series(fakeout_records(), symbol="FAKE"))
        false = [b for b in ext if b.strength is BreakStrength.FALSE]
        assert len(false) == 1
        event = false[0]
        assert event.break_index == 20
        assert event.break_price == pytest.approx(16.3)  # wick extreme
        assert event.broken_swing_price == pytest.approx(16.05)
        assert event.is_sweep_candidate is True

    def test_false_break_does_not_change_state(self) -> None:
        scan, ext = _external_breaks(to_series(fakeout_records(), symbol="FAKE"))
        assert scan.external_trend is TrendDirection.BULLISH  # no flip
        confirmed = [b for b in ext if b.strength is not BreakStrength.FALSE]
        assert all(b.break_type is StructureBreakType.BOS for b in confirmed)

    def test_false_emitted_once_per_level(self) -> None:
        scan = StructureScanner(engine_config()).run(to_series(fakeout_records(), symbol="FAKE"))
        false_ids = [
            (b.broken_swing_id, b.break_class)
            for b in scan.breaks
            if b.strength is BreakStrength.FALSE
        ]
        assert len(false_ids) == len(set(false_ids))


class TestWeakBreak:
    def test_small_margin_is_weak(self) -> None:
        # Close barely beyond the level → WEAK (margin < 0.25 * ATR).
        config = engine_config(strength_atr_fraction=0.9)  # very strict strong threshold
        _, ext = _external_breaks(uptrend_series(), config)
        bos = [b for b in ext if b.break_type is StructureBreakType.BOS]
        assert bos and all(b.strength is BreakStrength.WEAK for b in bos)


class TestInternalBreaks:
    def test_internal_breaks_are_minor(self) -> None:
        scan = StructureScanner(engine_config()).run(uptrend_series())
        internal = [b for b in scan.breaks if b.break_class is StructureBreakClass.INTERNAL]
        assert internal  # lookback-2 swings produce internal events
        assert all(b.significance is StructureBreakSignificance.MINOR for b in internal)


class TestEdgeCases:
    def test_ranging_no_breaks_unknown_trend(self) -> None:
        scan = StructureScanner(engine_config()).run(ranging_series())
        external = [b for b in scan.breaks if b.break_class is StructureBreakClass.EXTERNAL]
        assert external == []
        assert scan.external_trend is TrendDirection.UNKNOWN
        assert scan.external_sequence_trend is TrendDirection.RANGING

    def test_flat_series_no_swings_no_breaks(self) -> None:
        scan = StructureScanner(engine_config()).run(flat_series())
        assert scan.external_swings == []
        assert scan.breaks == []
        assert scan.legs == []
        assert scan.external_trend is TrendDirection.UNKNOWN

    def test_min_candles_rejection(self) -> None:
        from contexttrading.core.config import EngineConfig

        with pytest.raises(InsufficientDataError):
            StructureScanner(EngineConfig(min_candles=500)).run(uptrend_series())

    def test_envelope_contract(self) -> None:
        result = analyze_structure(uptrend_series(), engine_config())
        assert result.module == "structure"
        assert result.symbol == "TEST"
        assert str(result.timeframe) == "1m"
        assert result.generated_from.candle_count == len(uptrend_series())
        assert result.schema_version == "1.0.0"
        assert result.payload.protected_low is not None

    def test_deterministic_output(self) -> None:
        config = engine_config()
        a = analyze_structure(uptrend_series(), config)
        b = analyze_structure(uptrend_series(), config)
        assert a.model_dump_json() == b.model_dump_json()
