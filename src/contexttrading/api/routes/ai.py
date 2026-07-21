"""AI analyst routes: evidence-bound reports via the configured provider."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from contexttrading.analysis.pipeline import run_full_stack
from contexttrading.api.auth import require_api_key
from contexttrading.api.deps import (
    analyst_of,
    build_engine_config,
    build_series,
    settings_of,
)
from contexttrading.api.models import (
    AnalysisRequest,
    JournalReviewRequest,
    TradeEvaluationRequest,
    WeeklyReviewRequest,
)
from contexttrading.models.ai import AIReportResult

router = APIRouter(
    prefix="/v1/ai",
    tags=["ai"],
    dependencies=[Depends(require_api_key)],
)


@router.post("/market-analysis")
def market_analysis(request: Request, body: AnalysisRequest) -> AIReportResult:
    """Full MP03 market analysis over the posted candles."""
    settings = settings_of(request)
    series = build_series(body.series, settings)
    config = build_engine_config(settings, body.config_overrides)
    results = run_full_stack(series, config)
    return analyst_of(request).analyze_market(series, results)


@router.post("/trade-evaluation")
def trade_evaluation(request: Request, body: TradeEvaluationRequest) -> AIReportResult:
    """Evaluate a proposed setup against the engine context."""
    settings = settings_of(request)
    series = build_series(body.series, settings)
    config = build_engine_config(settings, body.config_overrides)
    results = run_full_stack(series, config)
    return analyst_of(request).evaluate_trade(body.setup, series, results)


@router.post("/journal-review")
def journal_review(request: Request, body: JournalReviewRequest) -> AIReportResult:
    """Review journal trades (statistics computed server-side, in Python)."""
    return analyst_of(request).review_journal(body.trades, period=body.period)


@router.post("/weekly-review")
def weekly_review(request: Request, body: WeeklyReviewRequest) -> AIReportResult:
    """Interpret provided period statistics."""
    return analyst_of(request).weekly_review(
        body.statistics, period=body.period, trades=body.trades
    )
