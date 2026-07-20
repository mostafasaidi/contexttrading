"""Tests for analysis.premium_discount: dealing range, EQ, OTE, location."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from contexttrading.analysis.premium_discount import analyze_dealing_range, compute_dealing_range
from contexttrading.analysis.structure.swings import detect_swing_sets
from contexttrading.core.constants import PriceLocation, TrendDirection
from tests.fixtures import downtrend_series, engine_config, flat_series, uptrend_series


def _uptrend_range():
    series = uptrend_series()
    _, external = detect_swing_sets(series, engine_config())
    return series, compute_dealing_range(
        external, TrendDirection.BULLISH, series.candles[-1].close, engine_config()
    )


class TestDealingRangeGeometry:
    def test_bounds_and_equilibrium(self) -> None:
        _, dr = _uptrend_range()
        assert dr is not None
        assert dr.high == pytest.approx(19.05)  # H19@20
        assert dr.low == pytest.approx(15.95)  # L16@24
        assert dr.equilibrium == pytest.approx((19.05 + 15.95) / 2)

    def test_ote_bullish(self) -> None:
        _, dr = _uptrend_range()
        assert dr is not None and dr.direction is TrendDirection.BULLISH
        span = 19.05 - 15.95
        assert dr.ote_high == pytest.approx(19.05 - 0.62 * span)
        assert dr.ote_low == pytest.approx(19.05 - 0.79 * span)
        assert dr.low <= dr.ote_low < dr.ote_high <= dr.high
        assert dr.ote_fibs == (0.62, 0.79)

    def test_ote_bearish_mirror(self) -> None:
        series = downtrend_series()
        _, external = detect_swing_sets(series, engine_config())
        dr = compute_dealing_range(
            external, TrendDirection.BEARISH, series.candles[-1].close, engine_config()
        )
        assert dr is not None and dr.direction is TrendDirection.BEARISH
        span = dr.high - dr.low
        assert dr.ote_low == pytest.approx(dr.low + 0.62 * span)
        assert dr.ote_high == pytest.approx(dr.low + 0.79 * span)

    def test_custom_fibs(self) -> None:
        series = uptrend_series()
        _, external = detect_swing_sets(series, engine_config())
        config = engine_config(ote_fib_lower=0.5, ote_fib_upper=0.7)
        dr = compute_dealing_range(external, TrendDirection.BULLISH, 18.0, config)
        assert dr is not None
        span = dr.high - dr.low
        assert dr.ote_high == pytest.approx(dr.high - 0.5 * span)
        assert dr.ote_low == pytest.approx(dr.high - 0.7 * span)

    def test_swing_refs(self) -> None:
        series = uptrend_series()
        _, external = detect_swing_sets(series, engine_config())
        dr = compute_dealing_range(external, TrendDirection.BULLISH, 18.0, engine_config())
        assert dr is not None
        ids = {s.id for s in external}
        assert dr.high_swing_id in ids and dr.low_swing_id in ids


class TestPriceLocation:
    @pytest.mark.parametrize(
        ("price", "expected"),
        [
            (18.0, PriceLocation.PREMIUM),  # above EQ 17.50
            (16.0, PriceLocation.DISCOUNT),
            (17.5, PriceLocation.EQUILIBRIUM),
        ],
    )
    def test_location(self, price: float, expected: PriceLocation) -> None:
        series = uptrend_series()
        _, external = detect_swing_sets(series, engine_config())
        dr = compute_dealing_range(external, TrendDirection.BULLISH, price, engine_config())
        assert dr is not None and dr.price_location is expected


class TestValidationAndEdges:
    def test_high_le_low_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="must be > low"):
            from contexttrading.models.range import DealingRange

            DealingRange(
                high=10.0,
                low=11.0,
                high_swing_id="a",
                low_swing_id="b",
                direction=TrendDirection.BULLISH,
                equilibrium=10.5,
                ote_low=10.2,
                ote_high=10.4,
                ote_fibs=(0.62, 0.79),
                reference_price=10.3,
                price_location=PriceLocation.DISCOUNT,
            )

    def test_no_swings_returns_none(self) -> None:
        assert compute_dealing_range([], TrendDirection.UNKNOWN, 100.0, engine_config()) is None

    def test_flat_series_pipeline(self) -> None:
        result = analyze_dealing_range(flat_series(), engine_config())
        assert result.payload.dealing_range is None

    def test_pipeline_result(self) -> None:
        result = analyze_dealing_range(uptrend_series(), engine_config())
        assert result.module == "premium_discount"
        dr = result.payload.dealing_range
        assert dr is not None
        assert dr.reference_price == uptrend_series().candles[-1].close

    def test_styles_attached(self) -> None:
        _, dr = _uptrend_range()
        assert dr is not None
        assert dr.premium_style.layer == "range.premium"
        assert dr.discount_style.fill is True
        assert dr.equilibrium_style.layer == "range.equilibrium"
        assert dr.ote_style.layer == "range.ote"
