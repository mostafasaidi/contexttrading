"""Backtest example: the reference SMC pullback strategy.

Run:  PYTHONPATH=src python examples/backtest_smc.py

Expected output: a statistics table (trades, win rate, profit factor,
expectancy, max drawdown, Sharpe) plus the first few trades with their
exit reasons, R-multiples, and evidence ids. Deterministic for the seeded
series; recompute_interval=4 keeps runtime at a few seconds (freshness
trade-off documented in docs/modules/backtesting.md).
"""

from __future__ import annotations

from _data import regime_series

from contexttrading.backtesting import SMCPullbackStrategy, run_backtest
from contexttrading.backtesting.strategies import SMCPullbackParams
from contexttrading.core.config import BacktestConfig, EngineConfig


def main() -> None:
    series = regime_series("trend_up", count=300)
    config = BacktestConfig(warmup_bars=60, min_trades=1, recompute_interval=4, window_bars=200)
    # Thresholds are data-dependent; 0.35 suits this gentle-trend regime
    # (the strategy default 0.5 targets stronger institutional flows).
    strategy = SMCPullbackStrategy(SMCPullbackParams(min_confluence_score=0.35))
    result = run_backtest(series, strategy, EngineConfig(), config)
    stats = result.statistics

    print(f"backtest: {result.strategy} over {len(series.candles)} bars")
    rows = [
        ("trades", stats.total_trades),
        ("win_rate", f"{stats.win_rate:.1%}"),
        ("net_pnl", f"{stats.net_pnl:+.2f}"),
        ("profit_factor", f"{stats.profit_factor:.2f}" if stats.profit_factor else "n/a"),
        ("expectancy_r", f"{stats.expectancy_r:+.2f}"),
        ("max_drawdown", f"{stats.drawdown.max_drawdown_pct:.1%}"),
        ("sharpe", f"{stats.sharpe:.2f}" if stats.sharpe is not None else "n/a"),
    ]
    for label, value in rows:
        print(f"  {label:<14} {value}")
    for trade in result.trades[:5]:
        print(
            f"  #{trade.sequence} {trade.direction.value:<8} {trade.exit_reason:<11}"
            f" R={trade.r_multiple:+.2f} bars={trade.holding_bars}"
            f" evidence={len(trade.evidence_ids)}"
        )


if __name__ == "__main__":
    main()
