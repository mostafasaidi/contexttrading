"""Confluence module orchestrator.

Composes existing module outputs into directional confidence scores — no
detection is reimplemented here; the module orchestrates the configured
engines (structure/trend, liquidity, premium/discount, FVG, order blocks,
supply/demand, sessions, MTF) and scores their versioned outputs.

Score semantics (documented in ``docs/modules/confluence.md``):

    bullish_score = sum(contribution of bullish factors) / total factor weight
    bearish_score = mirrored; both in [0, 1], their sum <= 1
    score = max(bullish_score, bearish_score); bias = its side (ties RANGING)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from contexttrading.analysis.confluence.factors import BLOCK_KIND_RAW, collect_factors
from contexttrading.analysis.confluence.zones import (
    build_confluence_zones,
    collect_zone_members,
)
from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.mtf import analyze_mtf
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.premium_discount import analyze_dealing_range
from contexttrading.analysis.sessions import analyze_sessions
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.analysis.structure.trend import TrendEngine
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.config import EngineConfig, SessionConfig
from contexttrading.core.constants import Timeframe, TrendDirection
from contexttrading.models.candle import CandleSeries
from contexttrading.models.confluence import ConfluenceResult
from contexttrading.models.outputs import AnalysisResult, DataWindow


def default_mtf_timeframes(base: Timeframe) -> list[Timeframe]:
    """The next two standard timeframes above ``base`` (may be shorter/empty)."""
    return [tf for tf in Timeframe if tf.seconds > base.seconds][:2]


def analyze_confluence(
    series: CandleSeries,
    config: EngineConfig | None = None,
    session_config: SessionConfig | None = None,
    mtf_timeframes: Sequence[Timeframe | str] | None = None,
    *,
    precomputed: Mapping[str, AnalysisResult] | None = None,  # type: ignore[type-arg]
) -> AnalysisResult[ConfluenceResult]:
    """Score directional confluence over a series.

    Args:
        series: Input candles.
        config: Engine thresholds and confluence weights.
        session_config: Session windows (forwarded to the sessions engine).
        mtf_timeframes: HTFs for the MTF context (defaults to the next two
            standard timeframes above the base).
        precomputed: Optional previously computed module envelopes keyed by
            module name ("liquidity", "premium_discount", "fvg",
            "orderblocks", "supplydemand", "sessions", "mtf"). Callers that
            already ran modules over the SAME series + config (e.g. the
            full-stack pipeline) pass them here so confluence reuses the
            payloads instead of recomputing them — output is identical to
            standalone recomputation (proven by goldens). Structure scan
            and trend state are always derived internally (cheap, and their
            non-payload objects are required for factor evaluation).

    Returns:
        Envelope with bias, normalized directional scores, every factor
        contribution, agree/conflict counts, and confluence zones.
    """
    config = config or EngineConfig()
    pre = precomputed or {}
    scan = StructureScanner(config).run(series)
    trend = TrendEngine(config).evaluate(series, scan)
    liquidity = (
        pre["liquidity"].payload
        if "liquidity" in pre
        else analyze_liquidity(series, config).payload
    )
    dealing_range = (
        pre["premium_discount"].payload.dealing_range
        if "premium_discount" in pre
        else analyze_dealing_range(series, config).payload.dealing_range
    )
    fvg = pre["fvg"].payload if "fvg" in pre else analyze_fvg(series, config).payload
    ob = (
        pre["orderblocks"].payload
        if "orderblocks" in pre
        else analyze_orderblocks(series, config).payload
    )
    sd = (
        pre["supplydemand"].payload
        if "supplydemand" in pre
        else analyze_supplydemand(series, config).payload
    )
    sessions = (
        pre["sessions"].payload
        if "sessions" in pre
        else analyze_sessions(series, config, session_config).payload
    )
    targets = (
        list(mtf_timeframes)
        if mtf_timeframes is not None
        else (default_mtf_timeframes(series.timeframe))
    )
    mtf = pre["mtf"].payload if "mtf" in pre else analyze_mtf(series, targets, config).payload

    price = series.candles[-1].close
    atr_last = scan.atr_values[-1] if scan.atr_values else None
    factors = collect_factors(
        trend,
        mtf,
        scan,
        liquidity,
        dealing_range,
        fvg,
        ob,
        sd,
        sessions,
        price,
        atr_last,
        config,
    )
    zones = build_confluence_zones(
        collect_zone_members(fvg, ob, sd, dealing_range, BLOCK_KIND_RAW), config
    )

    total_weight = sum(f.weight for f in factors)
    bull = sum(f.contribution for f in factors if f.direction is TrendDirection.BULLISH)
    bear = sum(f.contribution for f in factors if f.direction is TrendDirection.BEARISH)
    bullish_score = bull / total_weight if total_weight else 0.0
    bearish_score = bear / total_weight if total_weight else 0.0
    if bullish_score > bearish_score:
        bias = TrendDirection.BULLISH
    elif bearish_score > bullish_score:
        bias = TrendDirection.BEARISH
    else:
        bias = TrendDirection.RANGING
    agreeing = (
        sum(1 for f in factors if f.contribution > 0 and f.direction is bias)
        if bias in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        else 0
    )
    opposing = TrendDirection.BEARISH if bias is TrendDirection.BULLISH else TrendDirection.BULLISH
    conflicting = (
        sum(1 for f in factors if f.contribution > 0 and f.direction is opposing)
        if bias in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        else 0
    )

    payload = ConfluenceResult(
        bias=bias,
        score=max(bullish_score, bearish_score),
        bullish_score=bullish_score,
        bearish_score=bearish_score,
        reference_price=price,
        factors=factors,
        agreeing_factors=agreeing,
        conflicting_factors=conflicting,
        zones=zones,
    )
    return AnalysisResult[ConfluenceResult](
        module="confluence",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
