"""Tests for analysis.structure.legs: alternating sequence & classification."""

from __future__ import annotations

import pytest

from contexttrading.analysis.structure.legs import alternating_swings, classify_legs
from contexttrading.analysis.structure.swings import detect_swing_sets
from contexttrading.core.constants import LegKind, SwingType, TrendDirection
from tests.fixtures import engine_config, uptrend_series


def _external():
    _, external = detect_swing_sets(uptrend_series(), engine_config())
    return external


class TestAlternatingSwings:
    def test_alternates_types(self) -> None:
        alt = alternating_swings(_external())
        assert [s.swing_type for s in alt] == [
            SwingType.HIGH,
            SwingType.LOW,
            SwingType.HIGH,
            SwingType.LOW,
            SwingType.HIGH,
            SwingType.LOW,
        ]

    def test_keeps_more_extreme_same_type(self) -> None:
        alt = alternating_swings(_external())
        highs = [s for s in alt if s.swing_type is SwingType.HIGH]
        assert [h.price for h in highs] == sorted(h.price for h in highs)

    def test_empty(self) -> None:
        assert alternating_swings([]) == []


class TestLegClassification:
    def test_leg_geometry(self) -> None:
        legs = classify_legs(_external(), [None] * 100)
        first = legs[0]
        assert first.direction is TrendDirection.BEARISH  # H15 -> L12
        assert first.magnitude == pytest.approx(15.05 - 11.95)
        assert first.duration == 8 - 4
        assert first.retracement_ratio is None
        assert first.kind is LegKind.IMPULSE  # first leg by convention

    def test_impulse_vs_correction(self) -> None:
        legs = classify_legs(_external(), [None] * 100)
        kinds = [leg.kind for leg in legs]
        # L12->H17 new high: IMPULSE; H17->L14 higher low: CORRECTION;
        # L14->H19 new high: IMPULSE; H19->L16 higher low: CORRECTION.
        assert kinds == [
            LegKind.IMPULSE,
            LegKind.IMPULSE,
            LegKind.CORRECTION,
            LegKind.IMPULSE,
            LegKind.CORRECTION,
        ]

    def test_retracement_ratio(self) -> None:
        legs = classify_legs(_external(), [None] * 100)
        # leg2 (H17->L14) retraces leg1 (L12->H17): 3.10 / 5.10
        assert legs[2].retracement_ratio == pytest.approx(3.10 / 5.10)

    def test_atr_multiple(self) -> None:
        atr = [None] * 100
        atr[8] = 2.0  # ATR at first leg's end
        legs = classify_legs(_external(), atr)
        assert legs[0].atr_multiple == pytest.approx((15.05 - 11.95) / 2.0)
        assert legs[1].atr_multiple is None  # no ATR at index 12

    def test_direction_alternates(self) -> None:
        legs = classify_legs(_external(), [None] * 100)
        directions = [leg.direction for leg in legs]
        assert directions == [
            TrendDirection.BEARISH,
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
        ]
