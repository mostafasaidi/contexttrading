"""Unit tests for render primitives and the time conversion rule."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from contexttrading.core.versioning import SCHEMA_VERSION_VISUALIZATION
from contexttrading.visualization.primitives import (
    AreaBand,
    Box,
    Label,
    Marker,
    PriceLine,
    RenderPrimitive,
    Segment,
    to_unix_seconds,
)

_UNION = TypeAdapter(RenderPrimitive)


class TestTimeRule:
    def test_unix_seconds(self) -> None:
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        assert to_unix_seconds(ts) == int(ts.timestamp())
        assert to_unix_seconds(ts) == 1704110400

    def test_returns_int_not_millis(self) -> None:
        ts = datetime(2024, 6, 15, 8, 30, tzinfo=UTC)
        seconds = to_unix_seconds(ts)
        assert isinstance(seconds, int)
        assert seconds < 10**12  # seconds, never milliseconds


def _base(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source_id": "obj-1",
        "layer": "test.layer",
        "color": "#22ab94",
    }
    base.update(overrides)
    return base


class TestPrimitiveTypes:
    def test_price_line(self) -> None:
        prim = _UNION.validate_python(_base(primitive="price_line", price=100.5))
        assert isinstance(prim, PriceLine)
        assert prim.line_style == "solid"
        assert prim.schema_version == SCHEMA_VERSION_VISUALIZATION

    def test_box(self) -> None:
        prim = _UNION.validate_python(
            _base(primitive="box", start_time=100, end_time=200, bottom=1.0, top=2.0)
        )
        assert isinstance(prim, Box)
        assert prim.opacity == pytest.approx(0.2)
        assert prim.fill is True

    def test_marker(self) -> None:
        prim = _UNION.validate_python(
            _base(primitive="marker", time=100, price=5.0, position="aboveBar", shape="diamond")
        )
        assert isinstance(prim, Marker)
        assert prim.text == ""

    def test_label(self) -> None:
        prim = _UNION.validate_python(_base(primitive="label", time=100, price=5.0, text="hi"))
        assert isinstance(prim, Label)

    def test_segment(self) -> None:
        prim = _UNION.validate_python(
            _base(
                primitive="segment",
                start_time=100,
                start_price=1.0,
                end_time=200,
                end_price=2.0,
            )
        )
        assert isinstance(prim, Segment)

    def test_area_band(self) -> None:
        prim = _UNION.validate_python(_base(primitive="area_band", start_time=100, end_time=200))
        assert isinstance(prim, AreaBand)
        assert prim.opacity == pytest.approx(0.1)

    def test_unknown_discriminator_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _UNION.validate_python(_base(primitive="sparkle", time=1, price=1.0))

    def test_tooltip_is_structured_dict(self) -> None:
        prim = _UNION.validate_python(
            _base(primitive="price_line", price=1.0, tooltip={"type": "pool", "status": "swept"})
        )
        assert prim.tooltip == {"type": "pool", "status": "swept"}

    def test_round_trip_preserves_discriminator(self) -> None:
        prim = _UNION.validate_python(_base(primitive="price_line", price=1.0))
        reparsed = _UNION.validate_python(prim.model_dump())
        assert reparsed == prim
