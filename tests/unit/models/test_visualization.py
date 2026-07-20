"""Tests for models.visualization: VisualStyle contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle


class TestVisualStyle:
    def test_defaults(self) -> None:
        style = VisualStyle(color="#22ab94")
        assert style.opacity == 1.0
        assert style.line_style is LineStyle.SOLID
        assert style.render_type is RenderType.BOX
        assert style.layer == "default"
        assert style.visible is True
        assert style.fill is False
        assert style.priority == 0

    @pytest.mark.parametrize("color", ["#fff", "#22AB94", "#22ab9480"])
    def test_valid_colors_normalized(self, color: str) -> None:
        assert VisualStyle(color=color).color == color.lower()

    @pytest.mark.parametrize("color", ["red", "22ab94", "#22ab9", "#12345", "#gggggg", ""])
    def test_invalid_colors_rejected(self, color: str) -> None:
        with pytest.raises(PydanticValidationError, match="color must be"):
            VisualStyle(color=color)

    @pytest.mark.parametrize("opacity", [-0.1, 1.1])
    def test_opacity_bounds(self, opacity: float) -> None:
        with pytest.raises(PydanticValidationError):
            VisualStyle(color="#ffffff", opacity=opacity)

    def test_line_width_positive(self) -> None:
        with pytest.raises(PydanticValidationError):
            VisualStyle(color="#ffffff", line_width=0)

    def test_full_style_serializes(self) -> None:
        style = VisualStyle(
            color="#f23645",
            opacity=0.35,
            line_style=LineStyle.DASHED,
            line_width=2.0,
            render_type=RenderType.LINE,
            tooltip="FVG 101.2-101.8",
            priority=10,
            layer="imbalance",
            fill=True,
        )
        dumped = style.model_dump(mode="json")
        assert dumped["line_style"] == "dashed"
        assert dumped["render_type"] == "line"
        assert dumped["tooltip"] == "FVG 101.2-101.8"

    def test_frozen(self) -> None:
        style = VisualStyle(color="#ffffff")
        with pytest.raises(PydanticValidationError):
            style.opacity = 0.5
