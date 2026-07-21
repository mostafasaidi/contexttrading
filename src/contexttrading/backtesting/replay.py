"""Event-driven backtest replay.

The loop enforces the no-lookahead contract by construction:

- Strategies decide at bar CLOSE ``i`` using only the engine results for
  the window ending at bar ``i`` (never beyond).
- Entry/close intents fill on bar ``i + 1`` at its open (market) or when
  its range touches the trigger (limit/stop). Unfilled limit/stop intents
  EXPIRE after that single bar — the strategy must re-issue them.
- One open position at a time; entry intents arriving while a position is
  open are ignored at fill time (documented strategy contract).

Performance: engine modules re-run every ``recompute_interval`` bars on
the rolling window (``window_bars``, default None = full prefix from bar
0). Between recomputes the strategy sees the LATEST results (documented
staleness). The full-prefix default is O(n^2) in bars — acceptable for
correctness-first; incremental engine updates are a Phase-12 roadmap
item. ``window_bars`` bounds the cost but changes engine inputs (windowed
!= prefix once the window truncates warm-up history; use with care and
prefer prefixes for report-grade runs).

The window passed to ``on_bar`` is always the CURRENT window (fresh),
while ``results`` may be up to ``recompute_interval - 1`` bars old.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from contexttrading import __version__
from contexttrading.analysis.pipeline import MODULE_ORDER, run_module
from contexttrading.backtesting.execution import (
    PositionState,
    close_trade,
    commission,
    manage_position,
    market_fill,
    size_position,
    try_fill_intent,
)
from contexttrading.core.config import BacktestConfig, EngineConfig
from contexttrading.core.constants import Timeframe
from contexttrading.core.errors import BacktestError
from contexttrading.models.backtest import (
    BacktestResult,
    EquityPoint,
    OrderIntent,
    TradeRecord,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow


@runtime_checkable
class Strategy(Protocol):
    """Backtest strategy contract.

    ``modules`` declares the engine subset the strategy consumes (subset
    of ``MODULE_ORDER``; computed in canonical order). ``on_bar`` is called
    at every bar close from ``warmup_bars`` onward and returns entry/close
    intents to attempt on the NEXT bar. ``results`` is None only when the
    first recompute has not happened yet (warmup edge).
    """

    name: str
    modules: Sequence[str]

    def on_bar(
        self,
        bar_index: int,
        series: CandleSeries,
        results: dict[str, AnalysisResult] | None,  # type: ignore[type-arg]
        position: PositionState | None,
        equity: float,
    ) -> list[OrderIntent]: ...


def _validate_intent(intent: OrderIntent, bar_index: int) -> None:
    if intent.created_index != bar_index:
        raise BacktestError(
            "Intents must be stamped with the decision bar index",
            context={"created_index": intent.created_index, "bar_index": bar_index},
        )
    if intent.kind != "close" and intent.stop_loss is None:
        raise BacktestError(
            "Entry intents require a stop_loss (risk-first design)",
            context={"bar_index": bar_index, "kind": intent.kind},
        )


def run_backtest(
    series: CandleSeries,
    strategy: Strategy,
    engine_config: EngineConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    *,
    mtf_timeframes: Sequence[Timeframe | str] = ("1h", "4h"),
) -> BacktestResult:
    """Replay ``strategy`` over ``series`` and return the full result."""
    engine_config = engine_config or EngineConfig()
    config = backtest_config or BacktestConfig()
    unknown = [m for m in strategy.modules if m not in MODULE_ORDER]
    if unknown:
        raise BacktestError("Strategy declares unknown modules", context={"modules": unknown})
    candles = series.candles
    if not candles:
        raise BacktestError("Backtest requires a non-empty series")

    ordered_modules = [m for m in MODULE_ORDER if m in strategy.modules]
    position: PositionState | None = None
    pending: list[OrderIntent] = []
    trades: list[TradeRecord] = []
    curve: list[EquityPoint] = []
    results: dict[str, AnalysisResult] | None = None  # type: ignore[type-arg]
    closed_equity = config.initial_equity

    for i, bar in enumerate(candles):
        # 1. Fill intents created at the previous bar close.
        if pending:
            for intent in pending:
                if intent.kind == "close":
                    if position is not None:
                        exit_fill = market_fill(-position.sign, bar.open, config, slippage=True)
                        trades.append(
                            close_trade(
                                position,
                                exit_price=exit_fill,
                                exit_index=i,
                                exit_timestamp=bar.timestamp,
                                reason="signal",
                                sequence=len(trades),
                                config=config,
                            )
                        )
                        closed_equity += trades[-1].net_pnl
                        position = None
                elif position is None:
                    fill = try_fill_intent(intent, bar, config)
                    if fill is not None:
                        size = size_position(intent, closed_equity, fill, config)
                        risk = abs(fill - intent.stop_loss)  # type: ignore[arg-type]
                        position = PositionState(
                            direction=intent.direction,
                            sign=intent.direction.sign,
                            size_units=size,
                            entry_index=i,
                            entry_timestamp=bar.timestamp,
                            entry_price=fill,
                            stop_loss=intent.stop_loss,  # type: ignore[arg-type]
                            take_profit=intent.take_profit,
                            initial_risk_distance=risk,
                            commission_entry=commission(fill, size, config),
                            evidence_ids=list(intent.evidence_ids),
                            tag=intent.tag,
                        )
            pending = []

        # 2. SL/TP management on this bar (including the fill bar itself).
        if position is not None:
            position.update_excursion(bar)
            outcome = manage_position(position, bar, config)
            if outcome is not None:
                exit_fill, reason = outcome
                trades.append(
                    close_trade(
                        position,
                        exit_price=exit_fill,
                        exit_index=i,
                        exit_timestamp=bar.timestamp,
                        reason=reason,
                        sequence=len(trades),
                        config=config,
                    )
                )
                closed_equity += trades[-1].net_pnl
                position = None

        # 3. Mark-to-market at this close.
        open_pnl = position.open_pnl(bar.close) if position is not None else 0.0
        curve.append(
            EquityPoint(
                bar_index=i,
                timestamp=bar.timestamp,
                equity=closed_equity + open_pnl,
                closed_equity=closed_equity,
                open_pnl=open_pnl,
                in_position=position is not None,
            )
        )

        # 4. Decision point at this close.
        if i >= config.warmup_bars:
            start = 0 if config.window_bars is None else max(0, i + 1 - config.window_bars)
            window = series[start : i + 1]
            if results is None or (i - config.warmup_bars) % config.recompute_interval == 0:
                results = {
                    module: run_module(module, window, engine_config, mtf_timeframes=mtf_timeframes)
                    for module in ordered_modules
                }
            if (
                position is not None
                and config.breakeven_after_r is not None
                and position.mfe_r() >= config.breakeven_after_r
            ):
                position.apply_breakeven()
            intents = strategy.on_bar(i, window, results, position, closed_equity)
            for intent in intents:
                _validate_intent(intent, i)
            pending.extend(intents)

    # 5. End-of-data close at the final bar close.
    if position is not None and config.eod_close:
        last = candles[-1]
        exit_fill = market_fill(-position.sign, last.close, config, slippage=True)
        trades.append(
            close_trade(
                position,
                exit_price=exit_fill,
                exit_index=len(candles) - 1,
                exit_timestamp=last.timestamp,
                reason="end_of_data",
                sequence=len(trades),
                config=config,
            )
        )
        closed_equity += trades[-1].net_pnl
        curve[-1] = EquityPoint(
            bar_index=len(candles) - 1,
            timestamp=last.timestamp,
            equity=closed_equity,
            closed_equity=closed_equity,
            open_pnl=0.0,
            in_position=False,
        )

    from contexttrading.backtesting.statistics import compute_statistics

    statistics = compute_statistics(trades, curve, config, series.timeframe)
    params = getattr(strategy, "params", None)
    return BacktestResult(
        symbol=series.symbol,
        timeframe=series.timeframe,
        engine_version=__version__,
        strategy=strategy.name,
        generated_from=DataWindow(
            start=candles[0].timestamp, end=candles[-1].timestamp, candle_count=len(candles)
        ),
        backtest_config=config.model_dump(mode="json"),
        strategy_params=(params.model_dump(mode="json") if hasattr(params, "model_dump") else {}),
        trades=trades,
        equity_curve=curve,
        statistics=statistics,
    )
