"""Tests for core.constants: timeframes and shared enums."""

from __future__ import annotations

from datetime import timedelta

import pytest

from contexttrading.core.constants import (
    FLOAT_ABS_TOL,
    FLOAT_REL_TOL,
    LiquiditySide,
    MitigationStatus,
    SessionName,
    StructureBreakClass,
    StructureBreakSignificance,
    StructureBreakType,
    SwingType,
    Timeframe,
    TrendDirection,
    ZoneType,
)


class TestTimeframeParse:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("1m", Timeframe.M1),
            ("15m", Timeframe.M15),
            ("4h", Timeframe.H4),
            ("1h", Timeframe.H1),
            ("12h", Timeframe.H12),
            ("1d", Timeframe.D1),
            ("1w", Timeframe.W1),
            ("1M", Timeframe.MN1),
            ("1mo", Timeframe.MN1),
            ("1mon", Timeframe.MN1),
            ("H4", Timeframe.H4),
            ("MN1", Timeframe.MN1),
            ("daily", Timeframe.D1),
            ("weekly", Timeframe.W1),
            ("monthly", Timeframe.MN1),
            (" 5m ", Timeframe.M5),
        ],
    )
    def test_parse_valid(self, raw: str, expected: Timeframe) -> None:
        assert Timeframe.parse(raw) is expected

    def test_parse_passthrough_enum(self) -> None:
        assert Timeframe.parse(Timeframe.H4) is Timeframe.H4

    @pytest.mark.parametrize("raw", ["", "0m", "7m", "1y", "minute", "h4x", "2M"])
    def test_parse_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError, match="Unknown timeframe"):
            Timeframe.parse(raw)

    def test_minute_vs_month_case_sensitivity(self) -> None:
        assert Timeframe.parse("1m") is Timeframe.M1
        assert Timeframe.parse("1M") is Timeframe.MN1


class TestTimeframeDuration:
    @pytest.mark.parametrize(
        ("tf", "seconds"),
        [
            (Timeframe.M1, 60),
            (Timeframe.M15, 900),
            (Timeframe.H1, 3600),
            (Timeframe.H4, 14400),
            (Timeframe.D1, 86400),
            (Timeframe.W1, 604800),
            (Timeframe.MN1, 30 * 86400),
        ],
    )
    def test_seconds(self, tf: Timeframe, seconds: int) -> None:
        assert tf.seconds == seconds

    def test_minutes(self) -> None:
        assert Timeframe.H4.minutes == 240.0

    def test_to_timedelta(self) -> None:
        assert Timeframe.D1.to_timedelta() == timedelta(days=1)

    def test_str_is_canonical_code(self) -> None:
        assert str(Timeframe.M15) == "15m"
        assert str(Timeframe.MN1) == "1M"


class TestTimeframeOrdering:
    def test_total_ordering(self) -> None:
        assert Timeframe.M1 < Timeframe.M5 < Timeframe.H1 < Timeframe.H4
        assert Timeframe.H4 < Timeframe.D1 < Timeframe.W1 < Timeframe.MN1
        assert Timeframe.H1 <= Timeframe.H1
        assert Timeframe.MN1 > Timeframe.W1
        assert Timeframe.M5 >= Timeframe.M5

    def test_sorting(self) -> None:
        unordered = [Timeframe.D1, Timeframe.M1, Timeframe.W1, Timeframe.H4]
        assert sorted(unordered) == [Timeframe.M1, Timeframe.H4, Timeframe.D1, Timeframe.W1]

    def test_comparison_with_other_types(self) -> None:
        with pytest.raises(TypeError):
            _ = Timeframe.H1 < 3600


class TestEnums:
    def test_trend_direction_sign(self) -> None:
        assert TrendDirection.BULLISH.sign == 1
        assert TrendDirection.BEARISH.sign == -1
        assert TrendDirection.RANGING.sign == 0
        assert TrendDirection.UNKNOWN.sign == 0

    def test_enum_values_are_strings(self) -> None:
        assert StructureBreakType.BOS.value == "bos"
        assert StructureBreakType.CHOCH.value == "choch"
        assert StructureBreakClass.INTERNAL.value == "internal"
        assert StructureBreakClass.EXTERNAL.value == "external"
        assert StructureBreakSignificance.MAJOR.value == "major"
        assert SwingType.HIGH.value == "high"
        assert SessionName.NEW_YORK.value == "new_york"
        assert LiquiditySide.SELLSIDE.value == "sellside"
        assert MitigationStatus.UNMITIGATED.value == "unmitigated"
        assert ZoneType.ORDER_BLOCK.value == "order_block"

    def test_float_tolerances(self) -> None:
        assert FLOAT_REL_TOL == 1e-9
        assert FLOAT_ABS_TOL == 1e-12
