"""Backtesting wire/result models.

Everything here is a versioned pydantic model — no ad-hoc dicts. The
runtime mutable position state lives in ``backtesting.execution``; these
models are the deterministic, serializable outputs (and the strategy ->
execution order contract).
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import AwareDatetime, Field

from contexttrading.core.constants import Timeframe, TrendDirection
from contexttrading.core.versioning import SCHEMA_VERSION_BACKTEST
from contexttrading.models.base import VersionedModel
from contexttrading.models.outputs import DataWindow

#: Why a position was closed.

ExitReasonLiteral = Literal["stop_loss", "take_profit", "signal", "end_of_data"]

#: Order kinds a strategy may emit. ``close`` exits the open position at the
#: next bar open (market); the others are entry orders.
OrderKindLiteral = Literal["market", "limit", "stop", "close"]


class OrderIntent(VersionedModel):
    """A strategy's instruction to the execution layer.

    Created at the close of bar ``created_index`` using only data up to that
    bar; the execution layer attempts the fill on the NEXT bar (never the
    decision bar). Unfilled limit/stop intents expire after that bar.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    kind: OrderKindLiteral = Field(description="market | limit | stop | close.")
    direction: TrendDirection = Field(
        description="BULLISH = long entry, BEARISH = short entry; ignored for close."
    )
    price: float | None = Field(
        default=None, gt=0, description="Trigger price for limit/stop kinds."
    )
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    size_units: float | None = Field(
        default=None,
        gt=0,
        description="Explicit size; None -> sized from risk config via SL distance.",
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Engine object ids behind the decision (must resolve in window results).",
    )
    tag: str = Field(default="", description="Free-form strategy label for grouping.")
    created_index: int = Field(ge=0, description="Decision bar index (fill next bar).")


class TradeRecord(VersionedModel):
    """One round-trip position, filled under the execution/cost rules."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    sequence: int = Field(ge=0, description="Closed-trade sequence number (0-based).")
    direction: TrendDirection = Field(description="BULLISH = long, BEARISH = short.")
    tag: str = Field(default="")
    entry_index: int = Field(ge=0)
    entry_timestamp: AwareDatetime
    entry_price: float = Field(gt=0, description="Fill price after spread/slippage.")
    exit_index: int = Field(ge=0)
    exit_timestamp: AwareDatetime
    exit_price: float = Field(gt=0, description="Fill price after spread/slippage.")
    size_units: float = Field(gt=0)
    stop_loss: float = Field(gt=0, description="Stop at exit time (breakeven may move it).")
    take_profit: float | None = Field(default=None, gt=0)
    initial_risk_distance: float = Field(
        gt=0, description="|entry - initial stop| in price; the 1R unit."
    )
    exit_reason: ExitReasonLiteral
    gross_pnl: float = Field(description="Price PnL before commission.")
    commission_paid: float = Field(ge=0, description="Entry + exit commission.")
    net_pnl: float = Field(description="gross_pnl - commission_paid.")
    r_multiple: float = Field(
        description="Price-based R: sign*(exit-entry)/initial_risk_distance (gross of costs)."
    )
    mae_price: float = Field(
        ge=0, description="Max adverse excursion in price while holding (intrabar path)."
    )
    mfe_price: float = Field(ge=0, description="Max favorable excursion in price.")
    mae_r: float = Field(ge=0, description="MAE in initial-risk units.")
    mfe_r: float = Field(ge=0, description="MFE in initial-risk units.")
    holding_bars: int = Field(ge=0, description="exit_index - entry_index.")
    evidence_ids: list[str] = Field(default_factory=list)


class EquityPoint(VersionedModel):
    """Mark-to-market equity at one bar close."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    bar_index: int = Field(ge=0)
    timestamp: AwareDatetime
    equity: float = Field(description="closed_equity + open PnL at this close.")
    closed_equity: float = Field(description="Realized equity after the last closed trade.")
    open_pnl: float = Field(description="Unrealized PnL of the open position (0 when flat).")
    in_position: bool


class DrawdownInfo(VersionedModel):
    """Worst peak-to-trough decline of the mark-to-market equity curve."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    max_drawdown_abs: float = Field(ge=0)
    max_drawdown_pct: float = Field(ge=0, description="Relative to the running peak.")
    peak_index: int = Field(ge=0, description="Equity-curve index of the peak.")
    trough_index: int = Field(ge=0, description="Equity-curve index of the trough.")


class BacktestStatistics(VersionedModel):
    """Aggregate performance metrics over the closed trades + equity curve.

    Sharpe/Sortino use per-bar returns of the mark-to-market equity curve,
    annualized by ``annualization_factor`` (bars per calendar year from the
    timeframe, 365.25 days). Risk-free rate is 0 (configurable later).
    Calmar = annualized return / max drawdown %. ``statistics_reliable`` is
    False when total_trades < BacktestConfig.min_trades.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    total_trades: int = Field(ge=0)
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    win_rate: float = Field(ge=0, le=1)
    gross_profit: float = Field(ge=0)
    gross_loss: float = Field(ge=0, description="Absolute value of summed losing net PnL.")
    net_pnl: float
    profit_factor: float | None = Field(
        default=None, ge=0, description="gross_profit / gross_loss; None when no losses."
    )
    expectancy_currency: float = Field(description="Mean net PnL per trade.")
    expectancy_r: float = Field(description="Mean R-multiple per trade.")
    avg_win: float | None = Field(default=None)
    avg_loss: float | None = Field(default=None, description="Absolute mean losing net PnL.")
    payoff_ratio: float | None = Field(default=None, ge=0, description="avg_win / avg_loss.")
    max_consecutive_wins: int = Field(ge=0)
    max_consecutive_losses: int = Field(ge=0)
    max_drawdown_abs: float = Field(ge=0)
    max_drawdown_pct: float = Field(ge=0)
    sharpe: float | None = Field(default=None, description="None when returns have zero std.")
    sortino: float | None = Field(default=None, description="None when no downside returns.")
    calmar: float | None = Field(default=None, description="None when max drawdown is 0.")
    exposure_pct: float = Field(ge=0, le=1, description="Fraction of bars in a position.")
    annualization_factor: float = Field(gt=0, description="Bars per calendar year.")
    statistics_reliable: bool = Field(
        description="total_trades >= config.min_trades; below that, metrics are noise."
    )


class BacktestResult(VersionedModel):
    """Complete backtest output: config echo, trades, equity, statistics."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    module: str = Field(default="backtest")
    symbol: str = Field(min_length=1)
    timeframe: Timeframe
    engine_version: str = Field(description="contexttrading version that produced this.")
    strategy: str = Field(min_length=1, description="Strategy registry name.")
    generated_from: DataWindow
    backtest_config: dict = Field(
        description="Effective BacktestConfig dump used for the run (determinism echo)."
    )
    strategy_params: dict = Field(default_factory=dict)
    trades: list[TradeRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    statistics: BacktestStatistics
    run_id: str | None = Field(default=None, description="Metadata only; not analytical.")


# -- optimization ---------------------------------------------------------------


class OptimizationEntry(VersionedModel):
    """One evaluated parameter combination."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    rank: int = Field(ge=1)
    params: dict = Field(description="Dotted-path -> value used for this run.")
    objective: str = Field(description="Objective metric name.")
    objective_value: float | None = Field(description="None when the metric is undefined.")
    net_pnl: float
    total_trades: int
    statistics_reliable: bool


class OptimizationResult(VersionedModel):
    """Deterministic grid-search output (leaderboard in rank order)."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    module: str = Field(default="backtest.optimize")
    strategy: str
    objective: str
    combos_evaluated: int = Field(ge=0)
    leaderboard: list[OptimizationEntry] = Field(default_factory=list)


class WalkForwardFold(VersionedModel):
    """Train/test evaluation of one walk-forward fold."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    fold: int = Field(ge=1)
    train_bars: int = Field(ge=0)
    test_bars: int = Field(ge=0)
    best_params: dict
    train_objective: float | None
    test_objective: float | None
    test_net_pnl: float
    test_trades: int = Field(ge=0)
    overfit: bool = Field(
        description="Test objective degraded beyond the configured threshold vs train."
    )


class WalkForwardResult(VersionedModel):
    """Anchored walk-forward optimization output."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_BACKTEST

    module: str = Field(default="backtest.walk_forward")
    strategy: str
    objective: str
    folds: list[WalkForwardFold] = Field(default_factory=list)
    overfit_folds: int = Field(ge=0)
