"""Confluence domain models: factor contributions, zones, and the score.

The confluence engine composes existing module outputs into numerical
confidence scores. Every score is explainable: each
:class:`FactorContribution` names its factor, the backing object, the
weight, the raw evidence value in [0, 1], and the resulting contribution —
complete, self-describing input for the Phase-8 AI narrative layer.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import Field, model_validator

from contexttrading.core.constants import TrendDirection
from contexttrading.core.versioning import SCHEMA_VERSION_CONFLUENCE
from contexttrading.models.base import AnalysisObject, VersionedModel
from contexttrading.models.visualization import LineStyle, RenderType, VisualStyle

_BULL = "#22ab94"
_BEAR = "#f23645"


def confluence_zone_style(direction: TrendDirection, score: float) -> VisualStyle:
    """Default box style for a confluence zone (stronger = more opaque)."""
    return VisualStyle(
        color=_BULL if direction is TrendDirection.BULLISH else _BEAR,
        opacity=0.10 + 0.25 * score,
        line_style=LineStyle.SOLID,
        line_width=2.0,
        render_type=RenderType.BOX,
        fill=True,
        priority=9,
        layer="confluence.zones",
        tooltip=f"{direction.value} confluence zone (score {score:.2f})",
    )


class FactorContribution(VersionedModel):
    """One piece of directional evidence with its weighted contribution.

    ``direction`` is the side the evidence supports (RANGING = evaluated
    but no directional evidence — it still dilutes the normalized scores).
    ``contribution`` is exactly ``weight * raw``.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_CONFLUENCE

    factor: str = Field(min_length=1, description="Factor kind, e.g. 'trend', 'fvg'.")
    source_id: str | None = Field(
        default=None, description="ID of the backing object (None for aggregate factors)."
    )
    direction: TrendDirection = Field(description="Side the evidence supports.")
    weight: float = Field(ge=0, description="Configured factor weight.")
    raw: float = Field(ge=0, le=1, description="Evidence strength in [0, 1].")
    contribution: float = Field(ge=0, description="weight * raw.")
    detail: str = Field(
        min_length=1, description="Deterministic self-describing summary for narration."
    )


class ConfluenceZone(AnalysisObject):
    """A price band where several factor kinds spatially overlap.

    Emitted only when at least ``conf_zone_min_factors`` distinct factor
    kinds overlap AND all member zones agree in direction. ``score`` is the
    raw-weighted kind coverage normalized by the full zone-kind weight set,
    so a zone with every kind at full strength scores 1.0.
    """

    ID_PREFIX: ClassVar[str] = "conf"
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_CONFLUENCE

    direction: TrendDirection = Field(description="Unanimous member direction.")
    zone_bottom: float = Field(gt=0, description="Envelope lower bound.")
    zone_top: float = Field(gt=0, description="Envelope upper bound.")
    member_ids: list[str] = Field(
        min_length=2, description="Backing object IDs, ordered by zone bottom."
    )
    member_kinds: list[str] = Field(
        min_length=1, description="Distinct factor kinds present (sorted)."
    )
    score: float = Field(ge=0, le=1, description="Normalized confluence score in [0, 1].")
    style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color=_BULL, render_type=RenderType.BOX)
    )

    @model_validator(mode="after")
    def _check_geometry(self) -> ConfluenceZone:
        if self.zone_top <= self.zone_bottom:
            raise ValueError(
                f"zone_top ({self.zone_top}) must be > zone_bottom ({self.zone_bottom})"
            )
        return self


class ConfluenceResult(VersionedModel):
    """Payload of the confluence module.

    ``bullish_score`` / ``bearish_score`` are the per-side sums of factor
    contributions, each normalized by the total emitted factor weight (so
    both lie in [0, 1] and their sum is <= 1). ``score`` is the larger of
    the two; ``bias`` is its side (RANGING on ties, including 0 == 0).
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_CONFLUENCE

    bias: TrendDirection = Field(description="Winning side (RANGING on ties).")
    score: float = Field(ge=0, le=1, description="max(bullish_score, bearish_score).")
    bullish_score: float = Field(ge=0, le=1)
    bearish_score: float = Field(ge=0, le=1)
    reference_price: float = Field(gt=0, description="Last close the scores were computed at.")
    factors: list[FactorContribution] = Field(
        default_factory=list, description="Every evaluated factor, in assembly order."
    )
    agreeing_factors: int = Field(
        ge=0, description="Factors with contribution > 0 supporting the bias."
    )
    conflicting_factors: int = Field(
        ge=0, description="Factors with contribution > 0 opposing the bias."
    )
    zones: list[ConfluenceZone] = Field(
        default_factory=list, description="Spatial overlap zones, score desc."
    )
