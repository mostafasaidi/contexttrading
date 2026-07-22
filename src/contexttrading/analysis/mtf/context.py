"""Multi-timeframe context: resample, per-timeframe structure, aligned bias.

The base timeframe is rank 0 (weight ``mtf_tf_weight_base ** 0 == 1``);
each requested higher timeframe is resampled deterministically and scanned
with the same structure/trend/dealing-range engines. Aggregation rules are
documented on :class:`~contexttrading.models.mtf.MTFBias`.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from contexttrading.analysis.mtf.resample import resample_series
from contexttrading.analysis.premium_discount.dealing_range import analyze_dealing_range
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.analysis.structure.trend import TrendEngine
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import Timeframe, TrendDirection, TrendStrength
from contexttrading.core.errors import DataError, InsufficientDataError
from contexttrading.models.candle import CandleSeries
from contexttrading.models.mtf import MTFBias, MTFResult, TimeframeContext
from contexttrading.models.outputs import AnalysisResult, DataWindow


def _context_for(series: CandleSeries, rank: int, config: EngineConfig) -> TimeframeContext:
    """Structure/trend/range snapshot of one (already correct-TF) series.

    A resampled series too short for structure analysis yields an UNKNOWN
    context (no trend, no range) instead of failing the whole MTF pass.
    """
    weight = config.mtf_tf_weight_base**rank
    try:
        scan = StructureScanner(config).run(series)
    except InsufficientDataError:
        return TimeframeContext(
            timeframe=series.timeframe,
            trend=None,
            direction=TrendDirection.UNKNOWN,
            dealing_range=None,
            weight=weight,
            candle_count=len(series),
        )
    trend = TrendEngine(config).evaluate(series, scan)
    dealing_range = analyze_dealing_range(series, config).payload.dealing_range
    return TimeframeContext(
        timeframe=series.timeframe,
        trend=trend,
        direction=trend.direction,
        dealing_range=dealing_range,
        weight=weight,
        candle_count=len(series),
    )


def aggregate_bias(contexts: list[TimeframeContext], config: EngineConfig) -> MTFBias:
    """Weighted-majority bias over the per-timeframe contexts."""
    known = [c for c in contexts if c.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)]
    total_weight = sum(c.weight for c in contexts)
    bull = sum(c.weight for c in known if c.direction is TrendDirection.BULLISH)
    bear = sum(c.weight for c in known if c.direction is TrendDirection.BEARISH)

    if not known or bull == bear:
        direction = TrendDirection.RANGING
        aligned = 0.0
    else:
        direction = TrendDirection.BULLISH if bull > bear else TrendDirection.BEARISH
        aligned = max(bull, bear)
    agreement_share = aligned / total_weight if total_weight else 0.0

    if (
        direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        and len(contexts) >= 2
        and len(known) == len(contexts)
        and aligned == total_weight
    ):
        strength = TrendStrength.STRONG
    elif agreement_share >= config.mtf_moderate_share:
        strength = TrendStrength.MODERATE
    else:
        strength = TrendStrength.WEAK

    conflict_notes = [
        f"conflict: {a.timeframe} {a.direction.value} vs {b.timeframe} {b.direction.value}"
        for a, b in pairwise(contexts)
        if a.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        and b.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        and a.direction is not b.direction
    ]

    base = contexts[0]
    recommended = (
        base.timeframe
        if direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
        and base.direction is direction
        else None
    )

    htf_known = [
        c for c in contexts[1:] if c.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
    ]
    if base.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH) and htf_known:
        opposing = sum(c.weight for c in htf_known if c.direction is not base.direction)
        htf_influence = opposing / sum(c.weight for c in htf_known)
    else:
        htf_influence = 0.0

    return MTFBias(
        direction=direction,
        strength=strength,
        agreement_share=agreement_share,
        htf_influence=htf_influence,
        recommended_execution_timeframe=recommended,
        conflict_notes=conflict_notes,
    )


def analyze_mtf(
    series: CandleSeries,
    timeframes: Sequence[Timeframe | str],
    config: EngineConfig | None = None,
) -> AnalysisResult[MTFResult]:
    """Build the multi-timeframe context for a base series.

    Args:
        series: Base-timeframe candles (rank 0).
        timeframes: Higher timeframes to align with (parsed, deduplicated,
            sorted ascending). Each must be strictly higher than the base.
        config: Engine thresholds and MTF weights.

    Returns:
        Envelope with per-timeframe contexts and the aggregated bias.

    Raises:
        DataError: When a requested timeframe is not higher than the base.
        InsufficientDataError: When the series has no candles (every other
            module rejects short series before reaching the envelope build;
            an empty base would otherwise surface a raw DataWindow
            validation error from the ``None`` start/end).
    """
    config = config or EngineConfig()
    if len(series) == 0:
        raise InsufficientDataError(
            "Series too short for MTF analysis",
            context={"candles": 0, "min_candles": 1},
        )
    targets = sorted({Timeframe.parse(t) for t in timeframes}, key=lambda t: t.seconds)
    for tf in targets:
        if tf.seconds <= series.timeframe.seconds:
            raise DataError(
                "MTF timeframes must be strictly higher than the base timeframe",
                context={"base": str(series.timeframe), "requested": str(tf)},
            )

    contexts = [_context_for(series, 0, config)]
    for rank, tf in enumerate(targets, start=1):
        resampled = resample_series(
            series, tf, include_incomplete=config.mtf_include_incomplete_bar
        )
        contexts.append(_context_for(resampled, rank, config))

    payload = MTFResult(
        base_timeframe=series.timeframe,
        contexts=contexts,
        bias=aggregate_bias(contexts, config),
    )
    return AnalysisResult[MTFResult](
        module="mtf",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
