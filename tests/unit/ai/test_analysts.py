"""Unit tests for the institutional analyst pipeline."""

from __future__ import annotations

import json

import pytest

from contexttrading.ai.analysts import InstitutionalAnalyst
from contexttrading.ai.prompts.loader import PROMPTS
from contexttrading.ai.providers import MockProvider
from contexttrading.core.errors import AIResponseError, CitationError
from contexttrading.models.ai import TradeSetup
from tests.fixtures import engine_config, five_day_15m_series, full_stack_results


def _inputs():
    series = five_day_15m_series()
    return series, full_stack_results(series, engine_config())


class _FlakyProvider(MockProvider):
    """Fails the first call with garbage, then behaves (retry-loop probe)."""

    def __init__(self, failure: str = "{not json") -> None:
        super().__init__()
        self._failure = failure

    def complete(self, messages, response_schema):
        if self.calls == 0:
            self.calls += 1
            return self._failure
        return super().complete(messages, response_schema)


class _HallucinatingProvider(MockProvider):
    """First response cites a ghost id; second response is clean."""

    def complete(self, messages, response_schema):
        raw = super().complete(messages, response_schema)
        if self.calls == 1:
            data = json.loads(raw)
            data["evidence_citations"] = ["ghost:definitely-not-real"]
            return json.dumps(data)
        return raw


class TestHappyPaths:
    def test_analyze_market(self) -> None:
        series, results = _inputs()
        envelope = InstitutionalAnalyst(MockProvider()).analyze_market(series, results)
        assert envelope.module == "ai.market_analysis"
        assert envelope.subject == f"{series.symbol}/{series.timeframe}"
        assert envelope.generated_from is not None
        report = envelope.payload
        provenance = report.provenance
        assert provenance.prompt_name == "market_analysis"
        assert provenance.prompt_version == PROMPTS["market_analysis"].version
        assert provenance.prompt_sha256 == PROMPTS["market_analysis"].sha256
        assert provenance.provider == "mock"
        assert provenance.validation_warnings == []

    def test_evaluate_trade(self) -> None:
        series, results = _inputs()
        setup = TradeSetup(
            direction="long", entry_price=100.0, stop_loss=99.0, take_profits=[101.0, 102.0]
        )
        envelope = InstitutionalAnalyst(MockProvider()).evaluate_trade(setup, series, results)
        assert envelope.module == "ai.trade_evaluation"
        evaluation = envelope.payload.trade_evaluation
        assert evaluation is not None
        assert "setup:current" in envelope.payload.evidence_citations

    def test_review_journal(self) -> None:
        trades = [{"id": f"t{i}", "pnl": float((-1) ** i * i)} for i in range(12)]
        envelope = InstitutionalAnalyst(MockProvider()).review_journal(trades, period="2024-W01")
        assert envelope.module == "ai.journal_review"
        assert envelope.subject == "journal:2024-W01"
        assert len(envelope.payload.discipline_flags) == 4
        assert all(not f.detected for f in envelope.payload.discipline_flags)

    def test_weekly_review(self) -> None:
        stats = {"trade_count": 25, "win_rate": 0.52, "profit_factor": 1.4, "max_drawdown": 3.1}
        envelope = InstitutionalAnalyst(MockProvider()).weekly_review(stats, period="2024-W01")
        assert envelope.module == "ai.weekly_review"
        assert envelope.payload.period == "2024-W01"

    def test_byte_identical_reruns(self) -> None:
        series, results = _inputs()
        analyst = InstitutionalAnalyst(MockProvider())
        assert (
            analyst.analyze_market(series, results).model_dump_json()
            == analyst.analyze_market(series, results).model_dump_json()
        )


class TestRetryPolicy:
    def test_retry_once_on_garbage(self) -> None:
        series, results = _inputs()
        provider = _FlakyProvider()
        envelope = InstitutionalAnalyst(provider).analyze_market(series, results)
        assert provider.calls == 2
        assert envelope.payload.bias in ("bullish", "bearish", "ranging")

    def test_retry_once_on_hallucination(self) -> None:
        series, results = _inputs()
        provider = _HallucinatingProvider()
        envelope = InstitutionalAnalyst(provider).analyze_market(series, results)
        assert provider.calls == 2
        assert "ghost:definitely-not-real" not in envelope.payload.evidence_citations

    def test_persistent_failure_propagates(self) -> None:
        series, results = _inputs()

        class AlwaysFails(MockProvider):
            def complete(self, messages, response_schema):
                self.calls += 1
                return "{still not json"

        provider = AlwaysFails()
        with pytest.raises(AIResponseError):
            InstitutionalAnalyst(provider).analyze_market(series, results)
        assert provider.calls == 2  # exactly one retry, never more

    def test_persistent_hallucination_propagates(self) -> None:
        series, results = _inputs()

        class AlwaysHallucinates(_HallucinatingProvider):
            def complete(self, messages, response_schema):
                raw = MockProvider.complete(self, messages, response_schema)
                data = json.loads(raw)
                data["evidence_citations"] = ["ghost:always"]
                return json.dumps(data)

        with pytest.raises(CitationError):
            InstitutionalAnalyst(AlwaysHallucinates()).analyze_market(series, results)
