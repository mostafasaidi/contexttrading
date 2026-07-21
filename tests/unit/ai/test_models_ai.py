"""Unit tests for AI output models: constraints and round-trips."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from contexttrading.core.versioning import SCHEMA_VERSION_AI
from contexttrading.models.ai import (
    AIAnalysisReport,
    AIReportResult,
    ConfidenceScore,
    JournalReviewReport,
    PerformanceReviewReport,
    TradeEvaluation,
    TradeSetup,
)
from tests.unit.ai.test_validation import _minimal_report


class TestRoundTrips:
    def test_analysis_report(self) -> None:
        report = AIAnalysisReport.model_validate(_minimal_report())
        assert report.schema_version == SCHEMA_VERSION_AI
        assert AIAnalysisReport.model_validate(report.model_dump()) == report

    def test_journal_report(self) -> None:
        data = {
            "recurring_mistakes": [],
            "strengths": [],
            "discipline_flags": [
                {
                    "kind": "overtrading",
                    "detected": True,
                    "rationale": {"text": "stat shows 40 trades/day", "evidence_ids": ["stat:x"]},
                }
            ],
            "improvement_plan": [],
            "confidence_score": {
                "score": 0.4,
                "justification": {"text": "small sample", "evidence_ids": ["stat:n"]},
                "factor_ids": [],
            },
            "data_quality": {"level": "fair", "limitations": ["small_sample:5"]},
            "evidence_citations": ["stat:x"],
        }
        report = JournalReviewReport.model_validate(data)
        assert JournalReviewReport.model_validate_json(report.model_dump_json()) == report

    def test_performance_report(self) -> None:
        data = {
            "period": "2024-W01",
            "summary": {"text": "ok week", "evidence_ids": ["stat:win_rate"]},
            "what_worked": [],
            "what_failed": [],
            "risk_review": {"text": "drawdown contained", "evidence_ids": ["stat:max_dd"]},
            "plan_next_period": [],
            "confidence_score": {
                "score": 0.6,
                "justification": {"text": "25 trades", "evidence_ids": ["stat:trade_count"]},
                "factor_ids": [],
            },
            "data_quality": {"level": "good", "limitations": []},
            "evidence_citations": ["stat:win_rate"],
        }
        report = PerformanceReviewReport.model_validate(data)
        assert PerformanceReviewReport.model_validate_json(report.model_dump_json()) == report

    def test_envelope(self) -> None:
        report = AIAnalysisReport.model_validate(_minimal_report())
        envelope = AIReportResult[AIAnalysisReport](
            module="ai.market_analysis", subject="SESS/15m", payload=report
        )
        assert envelope.engine_version
        assert (
            AIReportResult[AIAnalysisReport].model_validate(envelope.model_dump(mode="json"))
            == envelope
        )


class TestConstraints:
    def test_risk_level_literal(self) -> None:
        bad = _minimal_report()
        bad["risk_assessment"]["volatility_risk"] = "wild"
        with pytest.raises(ValidationError):
            AIAnalysisReport.model_validate(bad)

    def test_confidence_bounds(self) -> None:
        stmt = {"text": "x", "evidence_ids": []}
        with pytest.raises(ValidationError):
            ConfidenceScore(score=1.5, justification=stmt, factor_ids=[])

    def test_trade_setup_requires_take_profit(self) -> None:
        with pytest.raises(ValidationError):
            TradeSetup(direction="long", entry_price=1.0, stop_loss=0.5, take_profits=[])

    def test_quality_grade_literal(self) -> None:
        stmt = {"text": "x", "evidence_ids": ["a"]}
        with pytest.raises(ValidationError):
            TradeEvaluation(
                entry_quality="amazing",
                stop_loss_quality="fair",
                take_profit_quality="fair",
                rr_assessment=stmt,
                confluence_alignment=stmt,
                timing=stmt,
                probability="high",
                invalidation=stmt,
                overall=stmt,
            )

    def test_provenance_optional_for_provider(self) -> None:
        report = AIAnalysisReport.model_validate(_minimal_report())
        assert report.provenance is None
