"""AI-layer output models (Phase 8): structured, evidence-bound reports.

The institutional analyst (MP03) NEVER calculates — every model here is a
container for *interpretation* of engine JSON. The anti-fabrication
contract:

- Every free-text claim is an :class:`EvidenceStatement` (constrained
  string + ``evidence_ids``), and every id must exist in the producing
  context's ``evidence_index`` (enforced by ``ai.validation``).
- Enumerated judgments (risk levels, quality grades, probabilities) are
  ``Literal`` fields — no free-form verdicts.
- ``confidence_score`` is a float WITH a justification statement and the
  factor ids it is derived from.
- Each report carries :class:`ReportProvenance` (prompt name/version/hash,
  provider, model, validation warnings) for full reproducibility.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field

from contexttrading import __version__ as _ENGINE_VERSION
from contexttrading.core.constants import TrendDirection
from contexttrading.core.versioning import SCHEMA_VERSION_AI
from contexttrading.models.base import VersionedModel
from contexttrading.models.outputs import DataWindow

#: Enumerated judgments (no free-form verdicts anywhere in a report).
RiskLevel = Literal["low", "medium", "high"]
QualityGrade = Literal["poor", "fair", "good", "excellent"]
Probability = Literal["low", "medium", "high"]
PositionSizeSuggestion = Literal["avoid", "reduced", "normal"]
DataQualityLevel = Literal["good", "fair", "poor"]


class EvidenceStatement(VersionedModel):
    """A constrained text claim with its supporting engine-object ids."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Ids into the context evidence_index backing this claim.",
    )


class ReportProvenance(VersionedModel):
    """How a report was produced — prompt, provider, and validation trail."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    prompt_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    prompt_sha256: str = Field(min_length=64, max_length=64)
    provider: str = Field(min_length=1)
    model: str = Field(default="")
    validation_warnings: list[str] = Field(default_factory=list)


class DataQualityDeclaration(VersionedModel):
    """The AI's mandatory declaration of input-data limitations."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    level: DataQualityLevel
    limitations: list[str] = Field(default_factory=list)


class MarketNarrative(VersionedModel):
    """MP03 narrative sections — each one an evidence-bound statement."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    control: EvidenceStatement = Field(description="Which side controls the market and why.")
    liquidity_objectives: EvidenceStatement = Field(
        description="Where resting liquidity likely sits (untapped pools, equal levels)."
    )
    trend_health: EvidenceStatement
    momentum: EvidenceStatement
    accumulation_distribution: EvidenceStatement
    expansion_correction: EvidenceStatement


class ConfluenceNote(VersionedModel):
    """One confluence observation, bound to confluence-engine factor ids."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    description: EvidenceStatement
    direction: TrendDirection
    factor_ids: list[str] = Field(
        default_factory=list, description="'factor:NN:name' keys from the context."
    )
    zone_id: str | None = Field(
        default=None, description="ConfluenceZone id when the note is zone-based."
    )


class RiskAssessment(VersionedModel):
    """MP03 risk block: categorized levels + sizing + capital preservation."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    market_risk: RiskLevel
    liquidity_risk: RiskLevel
    volatility_risk: RiskLevel
    session_risk: RiskLevel
    news_risk: RiskLevel = Field(description="'high' only from input flags, never assumed.")
    trend_risk: RiskLevel
    position_size_suggestion: PositionSizeSuggestion
    risk_rationale: EvidenceStatement
    capital_preservation_notes: EvidenceStatement


class TradeSetup(VersionedModel):
    """Caller-supplied proposed trade (input to trade evaluation)."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    direction: Literal["long", "short"]
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profits: list[float] = Field(min_length=1)
    rationale: str = Field(default="", max_length=2000)


class TradeEvaluation(VersionedModel):
    """MP03 trade evaluation — every judgment evidence-bound."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    entry_quality: QualityGrade
    stop_loss_quality: QualityGrade
    take_profit_quality: QualityGrade
    rr_assessment: EvidenceStatement = Field(
        description="Interpretation of the caller-provided reward/risk only — never recomputed."
    )
    confluence_alignment: EvidenceStatement
    timing: EvidenceStatement
    probability: Probability
    invalidation: EvidenceStatement = Field(
        description="Conditions that void the setup, citing structure/liquidity objects."
    )
    alternative_entries: list[EvidenceStatement] = Field(default_factory=list)
    overall: EvidenceStatement


class AlternativeScenario(VersionedModel):
    """One plausible alternative path with its trigger."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    scenario: EvidenceStatement
    probability: Probability
    trigger: EvidenceStatement


class ConfidenceScore(VersionedModel):
    """Confidence with a mandatory evidence-based justification."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    score: float = Field(ge=0, le=1)
    justification: EvidenceStatement
    factor_ids: list[str] = Field(
        default_factory=list, description="Confluence factor keys the score leans on."
    )


class AIAnalysisReport(VersionedModel):
    """MP03 market-analysis report (all required sections)."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    executive_summary: EvidenceStatement
    market_narrative: MarketNarrative
    bias: TrendDirection
    bias_rationale: EvidenceStatement
    confluences: list[ConfluenceNote] = Field(default_factory=list)
    risk_assessment: RiskAssessment
    weaknesses: list[EvidenceStatement] = Field(
        default_factory=list, description="Contradictory evidence and gaps in the bull/bear case."
    )
    trade_evaluation: TradeEvaluation | None = None
    alternative_scenarios: list[AlternativeScenario] = Field(default_factory=list)
    confidence_score: ConfidenceScore
    action_items: list[EvidenceStatement] = Field(default_factory=list)
    data_quality: DataQualityDeclaration
    evidence_citations: list[str] = Field(
        default_factory=list, description="Flat union of every cited evidence id."
    )
    provenance: ReportProvenance | None = Field(
        default=None, description="Filled by the analyst pipeline, not the provider."
    )


class DisciplineFlag(VersionedModel):
    """One emotional-discipline flag, derived ONLY from provided statistics."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    kind: Literal["revenge_trading", "overtrading", "impatience", "poor_risk_management", "other"]
    detected: bool
    rationale: EvidenceStatement


class JournalReviewReport(VersionedModel):
    """MP03 journal review: patterns from provided journal statistics only."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    recurring_mistakes: list[EvidenceStatement] = Field(default_factory=list)
    strengths: list[EvidenceStatement] = Field(default_factory=list)
    discipline_flags: list[DisciplineFlag] = Field(default_factory=list)
    improvement_plan: list[EvidenceStatement] = Field(default_factory=list)
    confidence_score: ConfidenceScore
    data_quality: DataQualityDeclaration
    evidence_citations: list[str] = Field(default_factory=list)
    provenance: ReportProvenance | None = None


class PerformanceReviewReport(VersionedModel):
    """MP03 weekly/monthly review: interpretation of provided statistics."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    period: str = Field(min_length=1, description="e.g. '2024-W01' or '2024-01'.")
    summary: EvidenceStatement
    what_worked: list[EvidenceStatement] = Field(default_factory=list)
    what_failed: list[EvidenceStatement] = Field(default_factory=list)
    risk_review: EvidenceStatement
    plan_next_period: list[EvidenceStatement] = Field(default_factory=list)
    confidence_score: ConfidenceScore
    data_quality: DataQualityDeclaration
    evidence_citations: list[str] = Field(default_factory=list)
    provenance: ReportProvenance | None = None


class AIReportResult[PayloadT: VersionedModel](VersionedModel):
    """Envelope for AI-layer reports (AnalysisResult-style).

    Unlike the engine envelope, the subject may be a journal/performance
    period rather than a market series, so ``generated_from`` is optional
    and ``subject`` carries "SYMBOL/timeframe" or "journal:PERIOD".
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_AI

    module: str = Field(min_length=1, description="e.g. 'ai.market_analysis'.")
    subject: str = Field(min_length=1, description="'SYMBOL/timeframe' or 'journal:period'.")
    engine_version: str = Field(
        default=_ENGINE_VERSION, description="contexttrading version that produced this."
    )
    generated_from: DataWindow | None = Field(
        default=None, description="Market data window when the subject is a series."
    )
    payload: PayloadT
