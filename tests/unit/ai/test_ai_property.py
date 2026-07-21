"""Property tests: citation integrity is enforced by construction.

For every fixture and every analyst method, every evidence id anywhere in
a validated report must resolve in the producing context's evidence index
— and reruns must be byte-identical.
"""

from __future__ import annotations

import json

import pytest

from contexttrading.ai import InstitutionalAnalyst, MockProvider, build_analysis_context
from contexttrading.models.base import VersionedModel
from tests.fixtures import (
    engine_config,
    five_day_15m_series,
    full_stack_results,
    judas_15m_series,
    uptrend_series,
)


def _all_ids(obj, out: set[str]) -> set[str]:
    """Recursively collect every id-looking string from a validated report."""
    if isinstance(obj, VersionedModel):
        for field_name, value in obj.__dict__.items():
            if field_name in ("evidence_ids", "factor_ids", "evidence_citations") and isinstance(
                value, list
            ):
                out.update(v for v in value if isinstance(v, str))
            elif field_name == "zone_id" and isinstance(value, str):
                out.add(value)
            else:
                _all_ids(value, out)
    elif isinstance(obj, list):
        for item in obj:
            _all_ids(item, out)
    return out


_FIXTURES = {
    "five_day": five_day_15m_series,
    "uptrend": uptrend_series,
    "judas": judas_15m_series,
}


@pytest.mark.parametrize("fixture_name", sorted(_FIXTURES))
def test_report_citations_resolve_and_deterministic(fixture_name: str) -> None:
    series = _FIXTURES[fixture_name]()
    results = full_stack_results(series, engine_config())
    context = build_analysis_context(series, results)
    analyst = InstitutionalAnalyst(MockProvider())

    envelope = analyst.analyze_market(series, results)
    cited = _all_ids(envelope.payload, set())
    assert cited, "mock report must cite something"
    unknown = cited - set(context.evidence_index)
    assert not unknown, f"unresolvable citations: {unknown}"

    again = analyst.analyze_market(series, results)
    assert envelope.model_dump_json() == again.model_dump_json()
    json.loads(envelope.model_dump_json())  # JSON-serializable


def test_journal_citations_resolve() -> None:
    trades = [{"id": f"t{i}", "pnl": float(i - 5)} for i in range(12)]
    from contexttrading.ai.context import build_journal_context

    context = build_journal_context(trades, period="2024-W02")
    envelope = InstitutionalAnalyst(MockProvider()).review_journal(trades, period="2024-W02")
    cited = _all_ids(envelope.payload, set())
    assert cited <= set(context.evidence_index)
