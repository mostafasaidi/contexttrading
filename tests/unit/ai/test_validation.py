"""Unit tests for the anti-fabrication validation layer."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from contexttrading.ai.context import EvidenceEntry
from contexttrading.ai.validation import parse_and_validate
from contexttrading.core.errors import AIResponseError, CitationError
from contexttrading.models.ai import AIAnalysisReport, EvidenceStatement


def _minimal_report(**overrides):
    stmt = {"text": "claim", "evidence_ids": ["pool:abc"]}
    report = {
        "executive_summary": stmt,
        "market_narrative": {
            "control": stmt,
            "liquidity_objectives": stmt,
            "trend_health": stmt,
            "momentum": stmt,
            "accumulation_distribution": stmt,
            "expansion_correction": stmt,
        },
        "bias": "bullish",
        "bias_rationale": stmt,
        "confluences": [],
        "risk_assessment": {
            "market_risk": "low",
            "liquidity_risk": "low",
            "volatility_risk": "low",
            "session_risk": "low",
            "news_risk": "low",
            "trend_risk": "low",
            "position_size_suggestion": "normal",
            "risk_rationale": stmt,
            "capital_preservation_notes": stmt,
        },
        "weaknesses": [],
        "alternative_scenarios": [],
        "confidence_score": {
            "score": 0.5,
            "justification": stmt,
            "factor_ids": ["factor:00:trend"],
        },
        "action_items": [],
        "data_quality": {"level": "good", "limitations": []},
        "evidence_citations": ["pool:abc", "factor:00:trend"],
    }
    report.update(overrides)
    return report


_INDEX = {
    "pool:abc": EvidenceEntry(id="pool:abc", kind="pool", digest={"price": 100.0}),
    "factor:00:trend": EvidenceEntry(
        id="factor:00:trend", kind="factor", digest={"factor": "trend"}
    ),
}


class TestHappyPath:
    def test_valid_report_passes(self) -> None:
        report, warnings = parse_and_validate(
            json.dumps(_minimal_report()), AIAnalysisReport, _INDEX
        )
        assert report.bias == "bullish"
        assert warnings == []

    def test_markdown_fences_stripped(self) -> None:
        raw = "```json\n" + json.dumps(_minimal_report()) + "\n```"
        report, _ = parse_and_validate(raw, AIAnalysisReport, _INDEX)
        assert report.bias == "bullish"


class TestHardErrors:
    def test_invalid_json(self) -> None:
        with pytest.raises(AIResponseError) as exc_info:
            parse_and_validate("{not json", AIAnalysisReport, _INDEX)
        assert exc_info.value.code == "CT-5001"

    def test_schema_mismatch(self) -> None:
        bad = _minimal_report()
        del bad["risk_assessment"]
        with pytest.raises(AIResponseError):
            parse_and_validate(json.dumps(bad), AIAnalysisReport, _INDEX)

    def test_invalid_enum_rejected(self) -> None:
        bad = _minimal_report()
        bad["risk_assessment"]["market_risk"] = "extreme"
        with pytest.raises(AIResponseError):
            parse_and_validate(json.dumps(bad), AIAnalysisReport, _INDEX)

    def test_hallucinated_statement_id(self) -> None:
        bad = _minimal_report(
            executive_summary={"text": "invented", "evidence_ids": ["pool:does-not-exist"]}
        )
        with pytest.raises(CitationError) as exc_info:
            parse_and_validate(json.dumps(bad), AIAnalysisReport, _INDEX)
        assert exc_info.value.code == "CT-5002"
        assert "pool:does-not-exist" in str(exc_info.value)

    def test_hallucinated_flat_citation(self) -> None:
        bad = _minimal_report(evidence_citations=["pool:abc", "ghost:1"])
        with pytest.raises(CitationError):
            parse_and_validate(json.dumps(bad), AIAnalysisReport, _INDEX)

    def test_hallucinated_factor_id(self) -> None:
        bad = _minimal_report()
        bad["confidence_score"]["factor_ids"] = ["factor:99:nope"]
        with pytest.raises(CitationError):
            parse_and_validate(json.dumps(bad), AIAnalysisReport, _INDEX)

    def test_hallucinated_zone_id(self) -> None:
        bad = _minimal_report(
            confluences=[
                {
                    "description": {"text": "zone note", "evidence_ids": ["pool:abc"]},
                    "direction": "bullish",
                    "factor_ids": ["factor:00:trend"],
                    "zone_id": "conf:ghost",
                }
            ]
        )
        with pytest.raises(CitationError):
            parse_and_validate(json.dumps(bad), AIAnalysisReport, _INDEX)


class TestWarnings:
    def test_uncited_statement_warns_not_fails(self) -> None:
        report_dict = _minimal_report(
            weaknesses=[{"text": "an uncited observation", "evidence_ids": []}]
        )
        _report, warnings = parse_and_validate(json.dumps(report_dict), AIAnalysisReport, _INDEX)
        assert len(warnings) == 1
        assert "uncited observation" in warnings[0]

    def test_zone_id_none_accepted(self) -> None:
        report_dict = _minimal_report(
            confluences=[
                {
                    "description": {"text": "note", "evidence_ids": ["pool:abc"]},
                    "direction": "bullish",
                    "factor_ids": ["factor:00:trend"],
                    "zone_id": None,
                }
            ]
        )
        report, warnings = parse_and_validate(json.dumps(report_dict), AIAnalysisReport, _INDEX)
        assert report.confluences[0].zone_id is None
        assert warnings == []


class TestEvidenceStatementModel:
    def test_constraints(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceStatement(text="", evidence_ids=[])
        with pytest.raises(ValidationError):
            EvidenceStatement(text="x" * 2001, evidence_ids=[])
