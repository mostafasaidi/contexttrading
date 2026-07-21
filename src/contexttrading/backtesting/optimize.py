"""Deterministic parameter optimization: grid search + walk-forward.

- **Grid search**: exhaustive cartesian product of the declared parameter
  space. Iteration order is the DECLARED key order of the space (Python
  dicts preserve insertion order), and ``itertools.product`` varies the
  LAST key fastest — fully deterministic across runs.
- **Parameter paths**: dotted prefixes select the target config:
  ``engine.<field>`` -> EngineConfig, ``backtest.<field>`` ->
  BacktestConfig, ``strategy.<field>`` -> the strategy factory's params.
  Unknown fields raise ValidationError (extra="forbid" configs).
- **Leaderboard**: sorted by objective descending; None objectives rank
  last; remaining ties break by combination index (declaration order), so
  the ranking is stable and byte-identical across reruns.
- **Walk-forward**: the series splits into K contiguous folds; fold ``i``
  optimizes on bars ``[0, boundary_i)`` (anchored, expanding window) and
  evaluates the winning combo on fold ``i``. ``overfit`` flags folds where
  the test objective degrades by more than
  ``BacktestConfig.optimization_overfit_threshold`` versus train (or is
  undefined while train is defined).

Parallelism is deliberately NOT implemented: deterministic ordering is
trivial when sequential, and the replay is CPU-bound on engine reruns
(see replay.py's O(n^2) note).
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from typing import Any

from contexttrading.backtesting.replay import Strategy, run_backtest
from contexttrading.core.config import BacktestConfig, EngineConfig
from contexttrading.core.constants import Timeframe
from contexttrading.core.errors import BacktestError
from contexttrading.models.backtest import (
    OptimizationEntry,
    OptimizationResult,
    WalkForwardFold,
    WalkForwardResult,
)
from contexttrading.models.candle import CandleSeries

OBJECTIVES: tuple[str, ...] = ("net_pnl", "sharpe", "profit_factor", "expectancy_r")

#: strategy factory: strategy-param dict -> Strategy instance.
StrategyFactory = Callable[[dict[str, Any]], Strategy]


def _objective_value(statistics, objective: str) -> float | None:
    if objective == "net_pnl":
        return statistics.net_pnl
    if objective == "sharpe":
        return statistics.sharpe
    if objective == "profit_factor":
        return statistics.profit_factor
    if objective == "expectancy_r":
        return statistics.expectancy_r
    raise BacktestError("Unknown objective", context={"objective": objective})


def _combos(param_space: dict[str, Sequence[Any]]) -> list[dict[str, Any]]:
    if not param_space:
        return [{}]
    keys = list(param_space)
    for key in keys:
        if not param_space[key]:
            raise BacktestError("Empty parameter values", context={"param": key})
        if key.split(".", 1)[0] not in ("engine", "backtest", "strategy"):
            raise BacktestError(
                "Parameter paths must start with engine./backtest./strategy.",
                context={"param": key},
            )
    return [
        dict(zip(keys, values, strict=True))
        for values in itertools.product(*(param_space[key] for key in keys))
    ]


def _apply_params(
    combo: dict[str, Any],
    engine_config: EngineConfig,
    backtest_config: BacktestConfig,
) -> tuple[EngineConfig, BacktestConfig, dict[str, Any]]:
    engine_updates = {k.split(".", 1)[1]: v for k, v in combo.items() if k.startswith("engine.")}
    backtest_updates = {
        k.split(".", 1)[1]: v for k, v in combo.items() if k.startswith("backtest.")
    }
    strategy_params = {k.split(".", 1)[1]: v for k, v in combo.items() if k.startswith("strategy.")}
    engine = EngineConfig.model_validate({**engine_config.model_dump(), **engine_updates})
    backtest = BacktestConfig.model_validate({**backtest_config.model_dump(), **backtest_updates})
    return engine, backtest, strategy_params


def _leaderboard(
    rows: list[tuple[int, dict[str, Any], float | None, Any]],
    objective: str,
) -> list[OptimizationEntry]:
    """Rank (combo_index, params, value, statistics) deterministically."""

    def sort_key(row: tuple[int, dict[str, Any], float | None, Any]) -> tuple[bool, float, int]:
        index, _params, value, _stats = row
        return (value is None, -(value if value is not None else 0.0), index)

    ordered = sorted(rows, key=sort_key)
    return [
        OptimizationEntry(
            rank=rank,
            params=params,
            objective=objective,
            objective_value=value,
            net_pnl=statistics.net_pnl,
            total_trades=statistics.total_trades,
            statistics_reliable=statistics.statistics_reliable,
        )
        for rank, (_index, params, value, statistics) in enumerate(ordered, start=1)
    ]


def grid_search(
    series: CandleSeries,
    strategy_factory: StrategyFactory,
    param_space: dict[str, Sequence[Any]],
    *,
    objective: str = "net_pnl",
    engine_config: EngineConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    mtf_timeframes: Sequence[Timeframe | str] = ("1h", "4h"),
) -> OptimizationResult:
    """Exhaustive deterministic grid search over ``param_space``."""
    if objective not in OBJECTIVES:
        raise BacktestError("Unknown objective", context={"objective": objective})
    engine_config = engine_config or EngineConfig()
    backtest_config = backtest_config or BacktestConfig()
    combos = _combos(param_space)
    rows: list[tuple[int, dict[str, Any], float | None, Any]] = []
    for index, combo in enumerate(combos):
        engine, backtest, strategy_params = _apply_params(combo, engine_config, backtest_config)
        result = run_backtest(
            series,
            strategy_factory(strategy_params),
            engine,
            backtest,
            mtf_timeframes=mtf_timeframes,
        )
        value = _objective_value(result.statistics, objective)
        rows.append((index, combo, value, result.statistics))
    return OptimizationResult(
        strategy=strategy_factory({}).name,
        objective=objective,
        combos_evaluated=len(combos),
        leaderboard=_leaderboard(rows, objective),
    )


def walk_forward(
    series: CandleSeries,
    folds: int,
    strategy_factory: StrategyFactory,
    param_space: dict[str, Sequence[Any]],
    *,
    objective: str = "net_pnl",
    engine_config: EngineConfig | None = None,
    backtest_config: BacktestConfig | None = None,
    mtf_timeframes: Sequence[Timeframe | str] = ("1h", "4h"),
) -> WalkForwardResult:
    """Anchored walk-forward optimization over K contiguous folds."""
    if folds < 2:
        raise BacktestError("walk_forward requires at least 2 folds", context={"folds": folds})
    engine_config = engine_config or EngineConfig()
    backtest_config = backtest_config or BacktestConfig()
    total = len(series.candles)
    boundaries = [round(i * total / folds) for i in range(folds + 1)]
    threshold = backtest_config.optimization_overfit_threshold

    results: list[WalkForwardFold] = []
    for fold in range(1, folds):
        train = series[: boundaries[fold]]
        test = series[boundaries[fold] : boundaries[fold + 1]]
        if len(train.candles) == 0 or len(test.candles) == 0:
            continue
        search = grid_search(
            train,
            strategy_factory,
            param_space,
            objective=objective,
            engine_config=engine_config,
            backtest_config=backtest_config,
            mtf_timeframes=mtf_timeframes,
        )
        best = search.leaderboard[0]
        engine, backtest, strategy_params = _apply_params(
            best.params, engine_config, backtest_config
        )
        evaluation = run_backtest(
            test,
            strategy_factory(strategy_params),
            engine,
            backtest,
            mtf_timeframes=mtf_timeframes,
        )
        test_value = _objective_value(evaluation.statistics, objective)
        train_value = best.objective_value
        if test_value is None and train_value is not None:
            overfit = True  # failed to reproduce out of sample
        elif train_value in (None, 0):
            overfit = False  # no baseline to degrade from
        else:
            overfit = (train_value - test_value) / abs(train_value) > threshold  # type: ignore[operator]
        results.append(
            WalkForwardFold(
                fold=fold,
                train_bars=len(train.candles),
                test_bars=len(test.candles),
                best_params=best.params,
                train_objective=train_value,
                test_objective=test_value,
                test_net_pnl=evaluation.statistics.net_pnl,
                test_trades=evaluation.statistics.total_trades,
                overfit=overfit,
            )
        )
    return WalkForwardResult(
        strategy=strategy_factory({}).name,
        objective=objective,
        folds=results,
        overfit_folds=sum(1 for fold in results if fold.overfit),
    )
