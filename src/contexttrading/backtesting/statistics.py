"""Backtest performance statistics (pure functions).

Definitions (all deterministic; no sampling):

- A trade is a WIN when ``net_pnl > 0``; scratch/loss trades are losses.
- ``profit_factor`` = gross_profit / gross_loss (None when no losses).
- ``expectancy_currency`` = mean net PnL per trade; ``expectancy_r`` = mean
  R-multiple per trade.
- Bar returns derive from the mark-to-market equity curve:
  ``r_i = eq_i / eq_{i-1} - 1`` (bars with zero prior equity are skipped).
- ``sharpe`` = mean(r) / sample_std(r) * sqrt(annualization); None when
  fewer than 2 returns or zero std. Risk-free rate = 0.
- ``sortino`` = mean(r) / downside_dev * sqrt(annualization), where
  downside_dev = sqrt(mean(min(r, 0)^2)) over ALL returns; None when no
  downside deviation.
- ``annualization_factor`` = calendar seconds per year (365.25 d) /
  timeframe seconds — i.e. bars per year, assuming continuous trading.
- ``calmar`` = annualized_return / max_drawdown_pct, with
  annualized_return = (eq_final / eq_initial) ** (annualization / n) - 1
  (n = number of bar returns); None when max drawdown is 0 or n == 0.
- ``exposure_pct`` = fraction of bars with an open position.
- ``statistics_reliable`` = total_trades >= config.min_trades.
"""

from __future__ import annotations

import itertools
import math
import statistics as stats

from contexttrading.core.config import BacktestConfig
from contexttrading.core.constants import Timeframe
from contexttrading.models.backtest import (
    BacktestStatistics,
    DrawdownInfo,
    EquityPoint,
    TradeRecord,
)

_YEAR_SECONDS = 365.25 * 86_400.0


def annualization_factor(timeframe: Timeframe) -> float:
    """Bars per calendar year for ``timeframe`` (continuous-trading assumption)."""
    return _YEAR_SECONDS / timeframe.seconds


def max_drawdown(curve: list[EquityPoint]) -> DrawdownInfo:
    """Worst peak-to-trough decline of the mark-to-market equity curve."""
    peak = -math.inf
    peak_index = 0
    best = DrawdownInfo(max_drawdown_abs=0.0, max_drawdown_pct=0.0, peak_index=0, trough_index=0)
    for idx, point in enumerate(curve):
        if point.equity > peak:
            peak = point.equity
            peak_index = idx
        if peak > 0:
            dd_abs = peak - point.equity
            dd_pct = dd_abs / peak
            if dd_abs > best.max_drawdown_abs:
                best = DrawdownInfo(
                    max_drawdown_abs=dd_abs,
                    max_drawdown_pct=dd_pct,
                    peak_index=peak_index,
                    trough_index=idx,
                )
    return best


def bar_returns(curve: list[EquityPoint]) -> list[float]:
    """Per-bar simple returns of the mark-to-market equity curve."""
    returns: list[float] = []
    for prev, curr in itertools.pairwise(curve):
        if prev.equity > 0:
            returns.append(curr.equity / prev.equity - 1.0)
    return returns


def _max_streak(values: list[bool]) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def compute_statistics(
    trades: list[TradeRecord],
    curve: list[EquityPoint],
    config: BacktestConfig,
    timeframe: Timeframe,
) -> BacktestStatistics:
    """Aggregate closed trades + equity curve into BacktestStatistics."""
    total = len(trades)
    wins = [t for t in trades if t.net_pnl > 0]
    losses = [t for t in trades if t.net_pnl <= 0]
    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = -sum(t.net_pnl for t in losses)
    net_pnl = sum(t.net_pnl for t in trades)
    avg_win = gross_profit / len(wins) if wins else None
    avg_loss = gross_loss / len(losses) if losses else None

    ann = annualization_factor(timeframe)
    returns = bar_returns(curve)
    sharpe: float | None = None
    sortino: float | None = None
    calmar: float | None = None
    if len(returns) >= 2:
        mean_r = stats.fmean(returns)
        std_r = stats.stdev(returns)
        if std_r > 0:
            sharpe = mean_r / std_r * math.sqrt(ann)
        downside_dev = math.sqrt(stats.fmean(min(r, 0.0) ** 2 for r in returns))
        if downside_dev > 0:
            sortino = mean_r / downside_dev * math.sqrt(ann)

    drawdown = max_drawdown(curve)
    if returns and curve[0].equity > 0 and drawdown.max_drawdown_pct > 0:
        growth = curve[-1].equity / curve[0].equity
        if growth > 0:
            annualized_return = growth ** (ann / len(returns)) - 1.0
            calmar = annualized_return / drawdown.max_drawdown_pct

    exposure = sum(1 for point in curve if point.in_position) / len(curve) if curve else 0.0
    return BacktestStatistics(
        total_trades=total,
        wins=len(wins),
        losses=len(losses),
        win_rate=len(wins) / total if total else 0.0,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net_pnl,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        expectancy_currency=net_pnl / total if total else 0.0,
        expectancy_r=(stats.fmean(t.r_multiple for t in trades)) if trades else 0.0,
        avg_win=avg_win,
        avg_loss=avg_loss,
        payoff_ratio=(avg_win / avg_loss) if (avg_win and avg_loss) else None,
        max_consecutive_wins=_max_streak([t.net_pnl > 0 for t in trades]),
        max_consecutive_losses=_max_streak([t.net_pnl <= 0 for t in trades]),
        drawdown=drawdown,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        exposure_pct=exposure,
        annualization_factor=ann,
        statistics_reliable=total >= config.min_trades,
    )
