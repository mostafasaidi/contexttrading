# Backtesting tutorial: run and optimize the SMC strategy

Deterministic, no-lookahead event replay: strategies decide at bar
**close** on engine output only, fills happen on the **next bar**, and
every trade links to the engine evidence behind it. This tutorial runs
the reference SMC pullback strategy, reads its statistics, then optimizes
its parameters with grid search and walk-forward validation.

## 1. Run the example

```bash
cd examples
PYTHONPATH="../src;.." python backtest_smc.py
```

Expected output (seeded data, deterministic):

```
backtest: smc_pullback over 300 bars
  trades         7
  win_rate       100.0%
  net_pnl        +12412.15
  ...
  #0 bullish  take_profit R=+1.94 bars=18 evidence=4
```

## 2. The moving parts

```python
from contexttrading.backtesting import SMCPullbackStrategy, run_backtest
from contexttrading.backtesting.strategies import SMCPullbackParams
from contexttrading.core.config import BacktestConfig, EngineConfig

config = BacktestConfig(
    warmup_bars=60,        # engine warm-up before decisions start
    recompute_interval=4,  # engines re-run every N bars (staleness trade-off)
    window_bars=200,       # bound engine input size (None = full prefix)
    min_trades=1,          # statistics_reliable threshold (default 30)
)
strategy = SMCPullbackStrategy(SMCPullbackParams(min_confluence_score=0.35))
result = run_backtest(series, strategy, EngineConfig(), config)
```

- `SMCPullbackStrategy` — the reference strategy: pullback into a fresh
  bullish zone sitting in DISCOUNT of the confirmed dealing range (or
  above it on a fresh BOS leg), stop beyond the zone, TP at the nearest
  untapped opposing pool (`tp_r_multiple` fallback). Thresholds are
  data-dependent — 0.35 suits the gentle example trend; the 0.5 default
  targets stronger institutional flow.
- Fill rules (all documented in `docs/modules/backtesting.md`):
  half-spread per fill, slippage on market/stop fills only, limits never
  slip, SL-first intrabar ambiguity, gap-through fills at the open,
  one-bar intent expiry, one position at a time, stop-loss REQUIRED.
- No-lookahead is *proven*, not asserted: a truncated-at-T run equals
  the full run on the shared bars (construction test).

## 3. Reading the result

```python
stats = result.statistics
stats.total_trades, stats.win_rate, stats.profit_factor
stats.expectancy_r          # average R-multiple per trade
stats.drawdown.max_drawdown_pct
stats.sharpe                # calendar-annualized from bar returns
stats.statistics_reliable   # False below min_trades — treat numbers as anecdote

for trade in result.trades:
    trade.exit_reason       # take_profit / stop_loss / signal / end_of_data
    trade.r_multiple
    trade.evidence_ids      # engine objects behind the entry — cite them in AI reports
```

## 4. Grid search

```python
from contexttrading.backtesting.optimize import grid_search

space = {
    "strategy.min_confluence_score": [0.3, 0.35, 0.4, 0.5],
    "strategy.tp_r_multiple": [1.5, 2.0, 3.0],
}
search = grid_search(
    series,
    lambda params: SMCPullbackStrategy(SMCPullbackParams(**params)),
    space,
    objective="expectancy_r",        # or net_pnl, sharpe, profit_factor
    backtest_config=config,
)
for row in search.leaderboard[:3]:
    print(row.params, row.objective_value)
```

Dotted param paths route to `engine.` / `backtest.` / `strategy.`
namespaces; the search is an exhaustive cartesian product in declared
key order, deterministic down to tie-breaks.

## 5. Walk-forward validation

```python
from contexttrading.backtesting.optimize import walk_forward

wf = walk_forward(series, folds=4,
                  strategy_factory=lambda p: SMCPullbackStrategy(SMCPullbackParams(**p)),
                  param_space=space, objective="expectancy_r",
                  backtest_config=config)
for fold in wf.folds:
    print(fold.fold, fold.best_params, fold.test_objective, fold.overfit)
```

Anchored folds: each fold optimizes on everything up to the boundary and
validates on the next segment. `overfit` trips when train/test
degradation exceeds `optimization_overfit_threshold` (default 0.5) — a
flag, not a verdict.

## 6. Performance reality

Full-prefix replay is O(n²): a 480-bar interval-1 run takes ~38 s
(improved ~41% by confluence payload-sharing). Levers, in order of
preference for exploration: `recompute_interval` (12 → 72 bars/s at
interval 6 on the benchmark fixture), `window_bars`. For report-grade
runs prefer full prefixes — windowing truncates engine warm-up history.

## 7. Over HTTP

`POST /v1/backtest` with `{"series", "strategy": "smc_pullback",
"strategy_params": {...}, "backtest_overrides": {...}}` — same engine,
same determinism; see the [API tutorial](api-tutorial.md).
