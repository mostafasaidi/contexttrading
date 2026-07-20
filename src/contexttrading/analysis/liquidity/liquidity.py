"""Liquidity module orchestrator.

Pipeline: structure scan (swings + false breaks + ATR) → equal levels →
pools → chronological sweep scan with status resolution. Uses **external**
swings for pool construction; internal swings are reserved for finer-grained
setups in later phases.
"""

from __future__ import annotations

from contexttrading.analysis.liquidity.equal_levels import detect_equal_levels
from contexttrading.analysis.liquidity.pools import build_pools
from contexttrading.analysis.liquidity.sweeps import scan_sweeps
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.core.config import EngineConfig
from contexttrading.models.candle import CandleSeries
from contexttrading.models.liquidity import LiquidityResult
from contexttrading.models.outputs import AnalysisResult, DataWindow


def analyze_liquidity(
    series: CandleSeries,
    config: EngineConfig | None = None,
) -> AnalysisResult[LiquidityResult]:
    """Run the full liquidity pipeline over a series.

    Args:
        series: Input candles.
        config: Engine thresholds (defaults when None).

    Returns:
        Envelope with equal levels, pools (final statuses), and sweeps.
    """
    config = config or EngineConfig()
    scan = StructureScanner(config).run(series)
    equal_levels = detect_equal_levels(scan.external_swings, scan.atr_values, config)
    pools = build_pools(scan.external_swings, equal_levels)
    updated_pools, sweeps = scan_sweeps(series, pools, scan.breaks, scan.atr_values, config)
    payload = LiquidityResult(equal_levels=equal_levels, pools=updated_pools, sweeps=sweeps)
    return AnalysisResult[LiquidityResult](
        module="liquidity",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
