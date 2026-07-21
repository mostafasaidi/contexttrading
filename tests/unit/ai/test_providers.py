"""Unit tests for LLM providers (offline — mock only touches no network)."""

from __future__ import annotations

import json

import pytest

from contexttrading.ai.context import build_analysis_context, build_journal_context
from contexttrading.ai.prompts.loader import get_prompt
from contexttrading.ai.providers import (
    MockProvider,
    OpenAIProvider,
    provider_from_config,
)
from contexttrading.ai.validation import parse_and_validate
from contexttrading.core.config import AIConfig
from contexttrading.core.errors import AIProviderError, ConfigurationError
from contexttrading.models.ai import (
    AIAnalysisReport,
    JournalReviewReport,
    PerformanceReviewReport,
)
from tests.fixtures import engine_config, five_day_15m_series, full_stack_results


def _market_messages():
    series = five_day_15m_series()
    ctx = build_analysis_context(series, full_stack_results(series, engine_config()))
    schema = AIAnalysisReport.model_json_schema()
    rendered = get_prompt("market_analysis").render(
        context=ctx.model_dump(mode="json"), schema=schema
    )
    return ctx, [{"role": "user", "content": rendered}], schema


class TestMockProvider:
    def test_deterministic_bytes(self) -> None:
        _ctx, messages, schema = _market_messages()
        provider = MockProvider()
        first = provider.complete(messages, schema)
        second = provider.complete(messages, schema)
        assert first == second

    def test_output_passes_schema_and_citations(self) -> None:
        ctx, messages, schema = _market_messages()
        raw = MockProvider().complete(messages, schema)
        report, warnings = parse_and_validate(raw, AIAnalysisReport, ctx.evidence_index)
        assert report.evidence_citations
        assert warnings == []

    def test_journal_and_performance_canned(self) -> None:
        ctx = build_journal_context([{"id": "t1", "pnl": 5.0}], period="2024-W01")
        provider = MockProvider()
        for model in (JournalReviewReport, PerformanceReviewReport):
            schema = model.model_json_schema()
            rendered = get_prompt("journal_review").render(
                context=ctx.model_dump(mode="json"), schema=schema
            )
            raw = provider.complete([{"role": "user", "content": rendered}], schema)
            report, _warnings = parse_and_validate(raw, model, ctx.evidence_index)
            assert report is not None

    def test_unknown_schema_rejected(self) -> None:
        _ctx, messages, _schema = _market_messages()
        with pytest.raises(AIProviderError):
            MockProvider().complete(messages, {"title": "UnknownModel"})

    def test_calls_counter(self) -> None:
        _ctx, messages, schema = _market_messages()
        provider = MockProvider()
        provider.complete(messages, schema)
        provider.complete(messages, schema)
        assert provider.calls == 2

    def test_no_context_in_message_raises(self) -> None:
        with pytest.raises(AIProviderError):
            MockProvider().complete([{"role": "user", "content": "no json here"}], {})


class TestProviderFactory:
    def test_mock_from_config(self) -> None:
        provider = provider_from_config(AIConfig(provider="mock"))
        assert isinstance(provider, MockProvider)

    def test_none_provider_rejected(self) -> None:
        with pytest.raises(ConfigurationError):
            provider_from_config(AIConfig(provider="none"))

    def test_missing_api_key_raises_before_network(self, monkeypatch) -> None:
        monkeypatch.delenv("CT_AI_API_KEY", raising=False)
        provider = OpenAIProvider(AIConfig(provider="openai", model="gpt-test"))
        with pytest.raises(ConfigurationError):
            provider.complete([{"role": "user", "content": "{}"}], {"title": "X"})

    def test_api_key_from_configured_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MY_KEY_VAR", "secret")
        provider = OpenAIProvider(
            AIConfig(provider="openai", model="gpt-test", api_key_env="MY_KEY_VAR")
        )
        assert provider.model == "gpt-test"


class TestCannedContent:
    def test_bias_echoes_confluence(self) -> None:
        ctx, messages, schema = _market_messages()
        raw = MockProvider().complete(messages, schema)
        report = json.loads(raw)
        engine_bias = ctx.confluence["bias"]
        expected = engine_bias if engine_bias in ("bullish", "bearish") else "ranging"
        assert report["bias"] == expected
        assert report["confidence_score"]["score"] == ctx.confluence["score"]

    def test_data_quality_mirrored(self) -> None:
        ctx, messages, schema = _market_messages()
        raw = MockProvider().complete(messages, schema)
        report = json.loads(raw)
        assert report["data_quality"]["level"] == ctx.data_quality.level
        assert report["data_quality"]["limitations"] == ctx.data_quality.flags
