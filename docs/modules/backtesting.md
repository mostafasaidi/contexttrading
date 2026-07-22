# backtesting

Event-driven deterministic backtesting: bar-by-bar replay over a
CandleSeries with engine-driven strategies, realistic fills/costs, pure
statistics, and deterministic optimization.

## Invariants (enforced, not aspirational)

1. **NO LOOKAHEAD.** Strategies decide at bar CLOSE `i` using only engine
   results for the window ending at bar `i`; fills happen on bar `i+1`
   (open for market/close, range touch for limit/stop). Proven by
   construction test: a run truncated at bar T reproduces the full run's
   per-bar equity and trades on every shared bar.
2. **Engines are never re-implemented.** Strategies consume
   `analysis.pipeline.run_module` outputs (`window_results`) only; the
   only strategy-side math is order construction (and engine-entrypoint
   ATR via `analysis.indicators`).
3. **Byte-identical determinism.** Same series + configs + strategy →
   identical `BacktestResult` JSON. No wall-clock, no randomness anywhere.
4. **Conservative conflict resolution.** Ambiguities always resolve
   against the trader (SL-first, see below).

## Responsibilities

| Module | Responsibility |
|---|---|
| `backtesting/replay.py` | `Strategy` protocol + `run_backtest` loop: fills, SL/TP, mark-to-market, warmup/recompute/window handling, end-of-data close. |
| `backtesting/execution.py` | Fill rules, cost models, position sizing, mutable `PositionState`, MAE/MFE, breakeven, `TradeRecord` construction. |
| `backtesting/statistics.py` | Pure metrics over trades + equity curve (`compute_statistics`, `max_drawdown`, `bar_returns`). |
| `backtesting/optimize.py` | Deterministic grid search + anchored walk-forward. |
| `backtesting/strategies/smc_pullback.py` | Reference strategy: BOS-pullback into linked OB/FVG with confluence + premium/discount filters. |
| `models/backtest.py` | Versioned wire models (`SCHEMA_VERSION_BACKTEST` 1.0.0, all schema-exported). |

## Replay contract

- `Strategy.modules` declares the engine subset (canonical `MODULE_ORDER`
  order). `on_bar(bar_index, series, results, position, equity)` is called
  every bar close from `warmup_bars` onward and returns `OrderIntent`s
  stamped with `created_index == bar_index` (validated).
- Intents live exactly one bar: unfilled limit/stop entries EXPIRE after
  the next bar. `kind="close"` exits at the next bar's open (market).
- One open position at a time; entry intents while positioned are ignored
  at fill time. Entries REQUIRE a stop_loss (risk-first design).
- A position filled at bar `i`'s open can be stopped on bar `i` itself.
- `recompute_interval` (default 1): engines re-run every N bars; the
  strategy sees the LATEST results between recomputes (documented
  staleness). The window passed to `on_bar` is always current.
- `window_bars` (default None = full prefix): bounds engine input cost.
  Windowed != prefix once the window truncates engine warm-up history —
  prefer prefixes for report-grade runs. Full-prefix replay is O(n^2);
  since Phase 12 the confluence engine reuses the replay's precomputed
  module payloads (`analyze_confluence(precomputed=...)` via
  `run_modules`), cutting a 480-bar interval-1 replay from 65 s to 38.5 s.
  Incremental engine updates remain a Phase-13+ roadmap item.

## Fill & cost rules

- **Spread** (`spread_bps`, full bid/ask): half applied per fill against
  the direction.
- **Slippage** (`slippage_bps`): market + stop fills only, adverse.
  Limit fills (incl. take-profits) never slip.
- **Commission** (`commission_bps`): per side, on notional.
- **Market entry**: next bar OPEN + costs.
- **Limit**: fills when the bar's range TOUCHES the price (ties fill —
  conservative); a gap through fills at the open (better price).
- **Stop entry**: fills when the range touches the trigger; a gap through
  fills at the open (worse price).
- **SL exit** (stop order): fills at SL + slippage; if the bar OPENS
  beyond the SL (gap-through), fills at the open.
- **TP exit** (limit order): fills at TP, no slippage; if the bar opens
  beyond the TP, fills at the open (chronologically first).
- **Intrabar ambiguity**: SL and TP both inside one bar's range → SL is
  assumed hit FIRST. Fixed rule, not a config flag.
- **Sizing**: explicit `size_units`, else `fixed_units`, else
  `risk_percent`: `units = equity * risk% / |entry - SL|`.
- **Breakeven** (`breakeven_after_r`, default off): at bar close, once MFE
  reaches X R, the stop moves to entry (never backwards).

## TradeRecord

Entry/exit time+price (cost-adjusted fills), direction, size, SL/TP,
`exit_reason` (stop_loss | take_profit | signal | end_of_data),
gross/net PnL (net = gross − commissions), `r_multiple` (price-based,
gross of costs, over the initial risk distance), MAE/MFE in price and R
(intrabar extremes during the holding period), `holding_bars` (0 when
stopped on the fill bar), and `evidence_ids` from the strategy.

## Statistics (formulas)

- win = `net_pnl > 0`; `profit_factor` = gross_profit/gross_loss (None if
  no losses); `expectancy_currency`/`expectancy_r` = per-trade means.
- Bar returns `r_i = eq_i/eq_{i-1} − 1` on the mark-to-market curve.
- `sharpe` = mean(r)/sample_std(r)·√ann; `sortino` replaces std with
  downside deviation `√mean(min(r,0)²)` (both None when undefined).
- `annualization_factor` = calendar seconds/year (365.25 d) ÷ timeframe
  seconds (continuous-trading assumption, documented).
- `calmar` = annualized return ÷ max drawdown %; annualized =
  `(eq_final/eq_initial)^(ann/n) − 1` in log space; None when the
  drawdown is 0 or the exponent overflows (tiny-sample absurdity).
- `max_drawdown_abs/pct` with peak/trough curve indices; `exposure_pct` =
  bars in market ÷ total bars; `statistics_reliable` =
  `total_trades >= min_trades`.

## Optimization protocol

- Grid: exhaustive cartesian product in DECLARED key order (last key
  varies fastest). Param paths: `engine.<field>`, `backtest.<field>`,
  `strategy.<field>` (validated; unknown → CT-2000).
- Leaderboard: objective desc, None objectives last, ties by declaration
  index. Objectives: `net_pnl | sharpe | profit_factor | expectancy_r`.
- Walk-forward: K contiguous folds; fold i optimizes on the anchored
  expanding prefix and evaluates on fold i. `overfit` when the test
  objective degrades by more than
  `optimization_overfit_threshold` (default 0.5) vs train, or is
  undefined while train is defined.
- No parallelism (deterministic ordering is trivial sequentially).

## Reference strategy rules (smc_pullback)

Long (short mirrored): trend agrees → most recent confirmed BOS ≤
`max_bars_since_break` old → bar trades into an open OB linked to that
BOS (else unmitigated FVG) → zone in DISCOUNT of the confirmed dealing
range, OR above the confirmed range entirely (fresh BOS leg — the
confirmed range lags active legs; zone qualifies by construction) →
confluence same-side score ≥ `min_confluence_score` (default 0.5).
Entry = market next open; SL = zone extreme − `sl_atr_buffer`·ATR
(`analysis.indicators.atr` on the decision window); TP = nearest untapped
opposing pool, else `tp_r_multiple` × risk from the decision close
(documented approximation). Evidence: BOS id, zone id, pool id (when
used), same-side confluence factor source ids. Exits via SL/TP only.

## API

`POST /v1/backtest` — `{series, strategy, engine_overrides,
backtest_overrides, strategy_params, mtf_timeframes}` → `BacktestResult`.
Strategies resolve via the registry in `api/routes/backtest.py`; unknown
name → 422 CT-2000. Same auth/envelope conventions as all v1 routes.

## Limitations

- O(n²) replay (full prefix), mitigated since Phase 12 by confluence
  payload-sharing (~41% faster: 65 s → 38.5 s on 480 bars at
  `recompute_interval=1`). Use `recompute_interval`/`window_bars` to
  trade freshness/input-size for speed (integration config: every 20
  bars, 400-bar window → ~40s for 2,000 bars incl. determinism checks).
  Measured tripwires live in `tests/performance/`.
- Single position, no partial exits/scaling, no trailing stop (breakeven
  only). Long/short spot semantics; no leverage/margin modeling.
- Mark-to-market uses closes only; intrabar equity path is not tracked.
- No parallel grid search.

## Testing

- Unit (71): fill rules (gap-through, limit ties, stop triggers), cost
  and sizing math, SL-first ambiguity, breakeven, replay ordering
  (next-open fills, expiry, warmup, recompute staleness, window caps,
  validation), statistics vs hand-computed values, grid order/leaderboard,
  walk-forward folds, error taxonomy.
- Property (hypothesis): accounting identity (final equity == initial +
  Σ net PnL), no-fill-before-next-open, SL-fill bounds, metric
  boundedness. Found and fixed a real Calmar overflow.
- Goldens (2): `backtest_smc_five_day.json`,
  `backtest_statistics.json`.
- Integration: 2,000-candle seeded dataset — byte-identical reruns,
  truncated-vs-full lookahead construction proof, evidence ids resolve in
  the recompute window, accounting sanity.
