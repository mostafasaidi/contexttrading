"""Phase 8 integration: engine pipeline -> context -> analyst -> report.

Runs the complete engine stack over the shared 2000-candle dataset, builds
the AI context, and produces a validated mock-analyst report. Verifies the
end-to-end contract: deterministic bytes, resolvable citations, honest
data-quality flow, and provenance recording.
"""

from __future__ import annotations

import json

from contexttrading.ai import InstitutionalAnalyst, MockProvider, build_analysis_context
from contexttrading.ai.validation import parse_and_validate
from contexttrading.models.ai import AIAnalysisReport, TradeSetup
from tests.fixtures import full_stack_results
from tests.integration.test_pipeline import _dataset


class TestPhase8AiPipeline:
    def test_full_pipeline_report(self) -> None:
        series = _dataset()
        results = full_stack_results(series)
        context = build_analysis_context(series, results)
        assert len(context.evidence_index) > 0

        envelope = InstitutionalAnalyst(MockProvider()).analyze_market(series, results)
        assert envelope.module == "ai.market_analysis"
        report = envelope.payload
        assert report.evidence_citations
        assert set(report.evidence_citations) <= set(context.evidence_index)
        assert report.data_quality.level == context.data_quality.level
        provenance = report.provenance
        assert provenance.prompt_name == "market_analysis"
        assert len(provenance.prompt_sha256) == 64

    def test_byte_identical_reruns(self) -> None:
        series = _dataset()
        first = (
            InstitutionalAnalyst(MockProvider())
            .analyze_market(series, full_stack_results(series))
            .model_dump_json()
        )
        second = (
            InstitutionalAnalyst(MockProvider())
            .analyze_market(series, full_stack_results(series))
            .model_dump_json()
        )
        assert first == second
        json.loads(first)

    def test_trade_evaluation_pipeline(self) -> None:
        series = _dataset()
        results = full_stack_results(series)
        price = series.candles[-1].close
        setup = TradeSetup(
            direction="long",
            entry_price=price,
            stop_loss=round(price * 0.99, 2),
            take_profits=[round(price * 1.02, 2)],
        )
        envelope = InstitutionalAnalyst(MockProvider()).evaluate_trade(setup, series, results)
        assert envelope.payload.trade_evaluation is not None

    def test_raw_provider_output_revalidates(self) -> None:
        """The mock's raw output independently passes parse_and_validate."""
        series = _dataset()
        results = full_stack_results(series)
        context = build_analysis_context(series, results)
        from contexttrading.ai.prompts.loader import get_prompt

        schema = AIAnalysisReport.model_json_schema()
        rendered = get_prompt("market_analysis").render(
            context=context.model_dump(mode="json"), schema=schema
        )
        raw = MockProvider().complete([{"role": "user", "content": rendered}], schema)
        report, warnings = parse_and_validate(raw, AIAnalysisReport, context.evidence_index)
        assert warnings == []
        assert report.bias.value == context.confluence["bias"]
