"""Full-stack pipeline orchestration: run every engine module in fixed order.

Single source of truth for "run all analyzers over a series" — used by the
API layer, tests, and demos. Module order is FIXED (deterministic): the
streaming endpoint and full-analysis responses always emit modules in
``MODULE_ORDER``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from contexttrading.analysis.confluence import analyze_confluence
from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.mtf import analyze_mtf
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.premium_discount import analyze_dealing_range
from contexttrading.analysis.sessions import analyze_sessions
from contexttrading.analysis.structure import analyze_structure, analyze_trend
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import Timeframe
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult

#: Fixed module execution/streaming order (dependencies flow downwards).
MODULE_ORDER: tuple[str, ...] = (
    "structure",
    "trend",
    "liquidity",
    "premium_discount",
    "fvg",
    "orderblocks",
    "supplydemand",
    "sessions",
    "confluence",
    "mtf",
)

#: Public single-module names exposed by the API (URL slug -> module key).
MODULE_SLUGS: dict[str, str] = {
    "structure": "structure",
    "trend": "trend",
    "liquidity": "liquidity",
    "premium-discount": "premium_discount",
    "fvg": "fvg",
    "orderblocks": "orderblocks",
    "supplydemand": "supplydemand",
    "sessions": "sessions",
    "confluence": "confluence",
    "mtf": "mtf",
}


def run_module(
    slug: str,
    series: CandleSeries,
    config: EngineConfig | None = None,
    *,
    mtf_timeframes: Sequence[Timeframe | str] = ("1h", "4h"),
) -> AnalysisResult:  # type: ignore[type-arg]
    """Run one engine module by API slug.

    Raises:
        KeyError: Unknown slug (callers map to 404).
    """
    config = config or EngineConfig()
    runners: dict[str, Callable[[], AnalysisResult]] = {  # type: ignore[type-arg]
        "structure": lambda: analyze_structure(series, config),
        "trend": lambda: analyze_trend(series, config),
        "liquidity": lambda: analyze_liquidity(series, config),
        "premium_discount": lambda: analyze_dealing_range(series, config),
        "fvg": lambda: analyze_fvg(series, config),
        "orderblocks": lambda: analyze_orderblocks(series, config),
        "supplydemand": lambda: analyze_supplydemand(series, config),
        "sessions": lambda: analyze_sessions(series, config),
        "confluence": lambda: analyze_confluence(series, config),
        "mtf": lambda: analyze_mtf(series, list(mtf_timeframes), config),
    }
    module = MODULE_SLUGS.get(slug, slug if slug in runners else None)
    if module is None:
        raise KeyError(slug)
    return runners[module]()


def run_full_stack(
    series: CandleSeries,
    config: EngineConfig | None = None,
    *,
    mtf_timeframes: Sequence[Timeframe | str] = ("1h", "4h"),
) -> dict[str, AnalysisResult]:  # type: ignore[type-arg]
    """Run every analysis module over a series, keyed by module name."""
    config = config or EngineConfig()
    return {
        module: run_module(module, series, config, mtf_timeframes=mtf_timeframes)
        for module in MODULE_ORDER
    }
