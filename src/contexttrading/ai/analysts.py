"""The institutional analyst pipeline (MP03).

Each method follows the same deterministic skeleton:

    build/augment context -> render versioned prompt -> provider call ->
    parse + citation validation (retry ONCE with feedback) -> provenance ->
    versioned report envelope.

The AI never calculates; this module enforces that by construction — the
provider only ever sees engine-produced JSON, and its output only becomes
a report after schema + citation validation.
"""

from __future__ import annotations

from typing import Any

from contexttrading.ai.context import (
    AnalysisContext,
    EvidenceEntry,
    JournalContext,
    build_analysis_context,
    build_journal_context,
    build_performance_context,
)
from contexttrading.ai.prompts.loader import SYSTEM_PROMPT, get_prompt
from contexttrading.ai.providers import LLMProvider
from contexttrading.ai.validation import parse_and_validate
from contexttrading.core.config import AIConfig
from contexttrading.core.errors import ContextTradingError
from contexttrading.models.ai import (
    AIAnalysisReport,
    AIReportResult,
    JournalReviewReport,
    PerformanceReviewReport,
    ReportProvenance,
    TradeSetup,
)
from contexttrading.models.base import VersionedModel
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult

_RETRY_FEEDBACK = (
    "Your previous output failed validation and was rejected. Error: {error}\n"
    "Regenerate the COMPLETE JSON object. Rules: output ONLY schema-valid JSON; "
    "cite only ids present in the context evidence_index; unknown ids are "
    "fabrications and are rejected."
)


class InstitutionalAnalyst:
    """MP03 analyst: interprets engine JSON into evidence-bound reports.

    Args:
        provider: Injected LLM provider (mock for tests, HTTP for real use).
        ai_config: Provider/context knobs (defaults when None).
        context_builder: Overridable for experiments; defaults to the
            deterministic :func:`build_analysis_context`.
    """

    def __init__(
        self,
        provider: LLMProvider,
        ai_config: AIConfig | None = None,
        context_builder: Any = build_analysis_context,
    ) -> None:
        self._provider = provider
        self._config = ai_config or AIConfig()
        self._context_builder = context_builder

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def analyze_market(
        self,
        series: CandleSeries,
        results: dict[str, AnalysisResult],  # type: ignore[type-arg]
    ) -> AIReportResult[AIAnalysisReport]:
        """Full MP03 market analysis over engine results."""
        context = self._context_builder(series, results, self._config)
        report = self._run("market_analysis", context, AIAnalysisReport)
        return AIReportResult[AIAnalysisReport](
            module="ai.market_analysis",
            subject=f"{series.symbol}/{series.timeframe}",
            generated_from=context.generated_from,
            payload=report,
        )

    def evaluate_trade(
        self,
        setup: TradeSetup,
        series: CandleSeries,
        results: dict[str, AnalysisResult],  # type: ignore[type-arg]
    ) -> AIReportResult[AIAnalysisReport]:
        """Evaluate a proposed setup against the engine context."""
        context = self._context_builder(series, results, self._config)
        setup_digest = setup.model_dump(mode="json")
        context = context.model_copy(
            update={
                "setup": setup_digest,
                "evidence_index": {
                    **context.evidence_index,
                    "setup:current": EvidenceEntry(
                        id="setup:current", kind="trade_setup", digest=setup_digest
                    ),
                },
            }
        )
        report = self._run("trade_evaluation", context, AIAnalysisReport)
        return AIReportResult[AIAnalysisReport](
            module="ai.trade_evaluation",
            subject=f"{series.symbol}/{series.timeframe}",
            generated_from=context.generated_from,
            payload=report,
        )

    def review_journal(
        self,
        trades: list[dict[str, Any]],
        *,
        period: str = "",
    ) -> AIReportResult[JournalReviewReport]:
        """Review journal trades (statistics computed in the context builder)."""
        context = build_journal_context(trades, period=period)
        report = self._run("journal_review", context, JournalReviewReport)
        return AIReportResult[JournalReviewReport](
            module="ai.journal_review",
            subject=f"journal:{period or 'all'}",
            payload=report,
        )

    def weekly_review(
        self,
        statistics: dict[str, Any],
        *,
        period: str,
        trades: list[dict[str, Any]] | None = None,
    ) -> AIReportResult[PerformanceReviewReport]:
        """Interpret provided weekly/monthly performance statistics."""
        context = build_performance_context(statistics, period=period, trades=trades)
        report = self._run("weekly_review", context, PerformanceReviewReport)
        return AIReportResult[PerformanceReviewReport](
            module="ai.weekly_review",
            subject=f"performance:{period}",
            payload=report,
        )

    # ------------------------------------------------------------------
    # pipeline skeleton
    # ------------------------------------------------------------------

    def _run[ReportT: VersionedModel](
        self,
        prompt_name: str,
        context: AnalysisContext | JournalContext,
        report_model: type[ReportT],
    ) -> ReportT:
        template = get_prompt(prompt_name)
        schema = report_model.model_json_schema()
        rendered = template.render(context=context.model_dump(mode="json"), schema=schema)
        messages = [
            {"role": "system", "content": get_prompt(SYSTEM_PROMPT).content},
            {"role": "user", "content": rendered},
        ]
        raw = self._provider.complete(messages, schema)
        try:
            report, warnings = parse_and_validate(raw, report_model, context.evidence_index)
        except ContextTradingError as first_error:
            # Retry exactly once, feeding the failure back to the provider.
            retry_messages = [
                *messages,
                {"role": "assistant", "content": raw},
                {"role": "user", "content": _RETRY_FEEDBACK.format(error=first_error)},
            ]
            raw = self._provider.complete(retry_messages, schema)
            report, warnings = parse_and_validate(raw, report_model, context.evidence_index)

        report.provenance = ReportProvenance(  # type: ignore[attr-defined]
            prompt_name=template.name,
            prompt_version=template.version,
            prompt_sha256=template.sha256,
            provider=self._provider.name,
            model=self._provider.model,
            validation_warnings=warnings,
        )
        return report
