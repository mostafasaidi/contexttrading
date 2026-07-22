"""AI analyst example: MockProvider end-to-end market report.

Run:  PYTHONPATH=src python examples/ai_analysis_mock.py

Expected output: the deterministic mock analyst's bias, confidence level,
an executive-summary excerpt, and citation/weakness counts. The
MockProvider is a pure function of the engine context — no network, no
API key, identical output every run.
"""

from __future__ import annotations

from _data import regime_series

from contexttrading.ai import InstitutionalAnalyst, MockProvider
from contexttrading.analysis.pipeline import run_full_stack


def main() -> None:
    series = regime_series("trend_up", count=300)
    results = run_full_stack(series)
    report = InstitutionalAnalyst(MockProvider()).analyze_market(series, results)
    payload = report.payload

    print(f"ai report: {report.subject}")
    print(f"bias: {payload.bias.value} (confidence {payload.confidence_score.score:.2f})")
    print(f"summary: {payload.executive_summary.text[:120]}...")
    print(f"confluences cited: {len(payload.confluences)}")
    print(f"weaknesses (mandatory): {len(payload.weaknesses)}")
    print(f"action items: {len(payload.action_items)}")


if __name__ == "__main__":
    main()
