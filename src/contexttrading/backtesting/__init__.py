"""Event-driven deterministic backtesting (Phase 11 in roadmap numbering).

Public surface: ``run_backtest`` (replay), the ``Strategy`` protocol,
``compute_statistics``, grid/walk-forward optimization, and the reference
``SMCPullbackStrategy``.
"""

from contexttrading.backtesting.replay import Strategy, run_backtest
from contexttrading.backtesting.statistics import compute_statistics
from contexttrading.backtesting.strategies import SMCPullbackParams, SMCPullbackStrategy

__all__ = [
    "SMCPullbackParams",
    "SMCPullbackStrategy",
    "Strategy",
    "compute_statistics",
    "run_backtest",
]
