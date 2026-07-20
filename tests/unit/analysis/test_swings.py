"""Tests for analysis.structure.swings: fractal detection and tie rules."""

from __future__ import annotations

import pytest

from contexttrading.analysis.structure.swings import detect_swing_sets, detect_swings
from contexttrading.core.constants import SwingClass, SwingType
from contexttrading.core.errors import InsufficientDataError
from tests.fixtures import (
    engine_config,
    flat_series,
    make_candle,
    to_series,
    uptrend_series,
    zigzag_series,
)


class TestFractalRule:
    def test_detects_pivot_highs_and_lows(self) -> None:
        series = zigzag_series([10, 15, 12, 17], leg_bars=4)
        swings = detect_swings(series, lookback=3, swing_class=SwingClass.EXTERNAL)
        by_index = {s.index: s for s in swings}
        assert 4 in by_index and by_index[4].swing_type is SwingType.HIGH
        assert by_index[4].price == pytest.approx(15.05)
        assert 8 in by_index and by_index[8].swing_type is SwingType.LOW
        assert by_index[8].price == pytest.approx(11.95)

    def test_strict_inequality_disqualifies_ties(self) -> None:
        # Two bars share the exact same high → neither is a swing.
        records = [
            make_candle(0, 10, 10.5, 9.5, 10),
            make_candle(1, 10, 11.0, 9.8, 10.8),
            make_candle(2, 10.8, 12.0, 10.5, 11.5),
            make_candle(3, 11.5, 12.0, 11.0, 11.2),  # equal high with bar 2
            make_candle(4, 11.2, 11.3, 10.6, 10.9),
            make_candle(5, 10.9, 11.0, 10.4, 10.6),
            make_candle(6, 10.6, 10.8, 10.2, 10.4),
        ]
        swings = detect_swings(to_series(records), lookback=2, swing_class=SwingClass.INTERNAL)
        assert [s for s in swings if s.swing_type is SwingType.HIGH] == []

    def test_edge_bars_never_swings(self) -> None:
        series = zigzag_series([10, 14, 10, 14, 10], leg_bars=4)
        swings = detect_swings(series, lookback=3, swing_class=SwingClass.EXTERNAL)
        assert all(3 <= s.index <= len(series) - 4 for s in swings)

    def test_monotonic_series_has_no_swings(self) -> None:
        records = [make_candle(i, 10 + i, 10.5 + i, 9.5 + i, 10.2 + i) for i in range(12)]
        swings = detect_swings(to_series(records), lookback=2, swing_class=SwingClass.INTERNAL)
        assert swings == []

    def test_flat_series_has_no_swings(self) -> None:
        assert detect_swings(flat_series(), lookback=2, swing_class=SwingClass.INTERNAL) == []

    def test_lookback_one(self) -> None:
        records = [
            make_candle(0, 10, 10.5, 9.5, 10),
            make_candle(1, 10, 12.0, 9.8, 11.5),
            make_candle(2, 11.5, 11.6, 10.0, 10.5),
        ]
        swings = detect_swings(to_series(records), lookback=1, swing_class=SwingClass.INTERNAL)
        assert len(swings) == 1 and swings[0].index == 1

    def test_invalid_lookback(self) -> None:
        with pytest.raises(ValueError):
            detect_swings(uptrend_series(), lookback=0, swing_class=SwingClass.INTERNAL)

    def test_insufficient_data(self) -> None:
        series = zigzag_series([10, 12], leg_bars=2)  # 3 candles, need 7 for lookback 3
        with pytest.raises(InsufficientDataError) as excinfo:
            detect_swings(series, lookback=3, swing_class=SwingClass.EXTERNAL)
        assert excinfo.value.code == "CT-3001"


class TestSwingSets:
    def test_internal_and_external_classes(self) -> None:
        series = uptrend_series()
        internal, external = detect_swing_sets(series, engine_config())
        assert internal and external
        assert all(s.swing_class is SwingClass.INTERNAL for s in internal)
        assert all(s.swing_class is SwingClass.EXTERNAL for s in external)
        # External (lookback 3) pivots are a subset of internal (lookback 2) indices.
        ext_idx = {s.index for s in external}
        int_idx = {s.index for s in internal}
        assert ext_idx <= int_idx

    def test_external_swings_match_expected_pivots(self) -> None:
        _, external = detect_swing_sets(uptrend_series(), engine_config())
        highs = {s.index: s.price for s in external if s.swing_type is SwingType.HIGH}
        lows = {s.index: s.price for s in external if s.swing_type is SwingType.LOW}
        assert highs == {
            4: pytest.approx(15.05),
            12: pytest.approx(17.05),
            20: pytest.approx(19.05),
        }
        assert lows == {8: pytest.approx(11.95), 16: pytest.approx(13.95), 24: pytest.approx(15.95)}

    def test_deterministic_ids(self) -> None:
        config = engine_config()
        a_internal, a_external = detect_swing_sets(uptrend_series(), config)
        b_internal, b_external = detect_swing_sets(uptrend_series(), config)
        assert [s.id for s in a_internal] == [s.id for s in b_internal]
        assert [s.id for s in a_external] == [s.id for s in b_external]

    def test_ids_start_with_prefix(self) -> None:
        _, external = detect_swing_sets(uptrend_series(), engine_config())
        assert all(s.id.startswith("swing_") for s in external)
