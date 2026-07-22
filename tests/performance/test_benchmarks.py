"""Performance benchmarks (plain timing tripwires — no pytest-benchmark).

Ceilings are calibrated to the reference dev machine (~4-5x the
observed timings, recorded below) — they exist to catch algorithmic
regressions, not to enforce SLAs. A failure means "investigate", not
"the build is too slow by 50 ms".

CI runners are ~1.5-2x slower than the dev machine, so ceilings are
SCALED there instead of weakened locally: when the standard ``CI``
environment variable is set (GitHub Actions sets ``CI=true``), ceilings
are multiplied by :data:`CEILING_MULTIPLIER` (default 2.5, overridable
via ``CT_BENCH_MULTIPLIER``). Ratio-based checks (scaling, interval
trade-off) self-normalize on any machine and are left unscaled; the
replay throughput floor is divided by the multiplier.

Observed (Windows, Python 3.12, seeded ``_dataset``):

| benchmark            | 500 bars | 2,000 bars | 8,000 bars |
| -------------------- | -------- | ---------- | ---------- |
| structure            | 21 ms    | 61 ms      | 258 ms     |
| fvg                  | 37 ms    | 203 ms     | 2,163 ms   |
| orderblocks          | 70 ms    | 383 ms     | 3,981 ms   |
| full_stack           | 364 ms   | 1,657 ms   | 12,871 ms  |
| replay interval=1    | 12 bars/s (240 bars, SMC strategy) |
| replay interval=6    | 72 bars/s (240 bars, SMC strategy) |
"""

from __future__ import annotations

import os
import time

import pytest

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.pipeline import run_full_stack
from contexttrading.analysis.structure import analyze_structure
from contexttrading.backtesting import SMCPullbackStrategy, run_backtest
from contexttrading.backtesting.strategies import SMCPullbackParams
from contexttrading.core.config import BacktestConfig, EngineConfig
from tests.integration.test_pipeline import _dataset

pytestmark = pytest.mark.benchmark

#: Tripwire scale factor for slower machines. Defaults to 2.5 under CI
#: (the ``CI`` env var convention), 1.0 locally; CT_BENCH_MULTIPLIER
#: overrides both. Keeps local regression detection at full sensitivity.
CEILING_MULTIPLIER = float(
    os.environ.get("CT_BENCH_MULTIPLIER", "2.5" if os.environ.get("CI") else "1.0")
)

# (analyze_fn, {bar_count: ceiling_seconds}) — tripwires, not SLAs.
MODULE_BENCHMARKS = [
    pytest.param(analyze_structure, {500: 0.25, 2000: 0.5, 8000: 1.5}, id="structure"),
    pytest.param(analyze_fvg, {500: 0.3, 2000: 1.5, 8000: 10.0}, id="fvg"),
    pytest.param(analyze_orderblocks, {500: 0.5, 2000: 2.5, 8000: 18.0}, id="orderblocks"),
    pytest.param(run_full_stack, {500: 2.0, 2000: 8.0, 8000: 60.0}, id="full_stack"),
]


def _timed(fn, series) -> float:
    start = time.perf_counter()
    fn(series)
    return time.perf_counter() - start


@pytest.mark.parametrize(("analyze", "ceilings"), MODULE_BENCHMARKS)
@pytest.mark.parametrize("count", [500, 2000, 8000])
def test_module_runtime(analyze, ceilings, count):
    series = _dataset(count=count)
    elapsed = _timed(analyze, series)
    ceiling = ceilings[count] * CEILING_MULTIPLIER
    assert elapsed < ceiling, (
        f"{analyze.__name__} on {count} bars took {elapsed:.2f}s "
        f"(tripwire {ceiling:.2f}s = {ceilings[count]}s x{CEILING_MULTIPLIER}) — "
        f"investigate for an algorithmic regression"
    )


def test_full_stack_scaling_subquadratic():
    """8x the bars should cost well under 64x the time (roughly linear-ish)."""
    small = _timed(run_full_stack, _dataset(count=500))
    large = _timed(run_full_stack, _dataset(count=4000))
    assert large < small * 64, f"full_stack scaling: {small:.2f}s -> {large:.2f}s for 8x bars"


def test_replay_recompute_interval_tradeoff():
    """Coarser recompute intervals must buy meaningful throughput."""
    series = _dataset(count=240)
    strategy = SMCPullbackStrategy(SMCPullbackParams(min_confluence_score=0.35))

    def replay(interval: int) -> float:
        config = BacktestConfig(
            warmup_bars=60, min_trades=1, recompute_interval=interval, window_bars=200
        )
        start = time.perf_counter()
        run_backtest(series, strategy, EngineConfig(), config)
        return time.perf_counter() - start

    every_bar = replay(1)
    every_six = replay(6)
    assert (
        every_six < every_bar * 0.5
    ), f"interval=6 ({every_six:.1f}s) should be >2x faster than interval=1 ({every_bar:.1f}s)"
    floor = 3.0 / CEILING_MULTIPLIER  # bars/s floor, relaxed on slower CI runners
    throughput = len(series.candles) / every_bar
    assert throughput > floor, (
        f"replay throughput {throughput:.1f} bars/s below {floor:.1f} bars/s floor "
        f"(3 bars/s / x{CEILING_MULTIPLIER})"
    )
