# Layers in Detail

This document defines each layer's responsibilities, inputs, outputs, and
explicit non-responsibilities.

## 1. Data (`contexttrading.data`)

- **Owns:** provider adapters (CSV, exchange APIs), OHLCV validation,
  deduplication, gap detection, timezone normalization to UTC, storage
  backends (SQLite → PostgreSQL/Redis in later phases).
- **Produces:** `CandleSeries` instances — ordered, gap-aware, tz-aware.
- **Never:** computes indicators or structure; mutates candle values
  (adjustments are explicit, versioned transforms).

## 2. Analysis (`contexttrading.analysis`)

Sub-packages, one responsibility each:

| Sub-package | Computes |
|---|---|
| `structure` | Swing highs/lows, BOS/CHoCH (internal/external, major/minor) |
| `liquidity` | Equal highs/lows, liquidity pools, sweeps |
| `fvg` | Fair value gaps, imbalance, inversion FVG |
| `orderblocks` | Bullish/bearish order blocks, breaker blocks, mitigation |
| `supplydemand` | Supply/demand zones, strength scoring |
| `premium_discount` | Range equilibrium, premium/discount/OTE bands |
| `sessions` | Session windows, killzones, session high/low |
| `confluence` | Weighted deterministic confluence scoring across modules |
| `mtf` | Multi-timeframe alignment and trend state |

- **Owns:** all market-structure math. Every module is a pure function of
  `(CandleSeries, module-config) → AnalysisResult[T]`.
- **Never:** wall-clock reads, randomness without an injected seed, I/O,
  imports from visualization/AI/backtesting/api.

## 3. Trading Logic

Composition of analysis outputs into deterministic signal objects (entries,
invalidations, targets) with fully specified rules. Lives close to
`analysis.confluence` and is consumed by backtesting and the API. Rules are
data, not discretion.

## 4. Visualization (`contexttrading.visualization`)

- **Owns:** mapping `AnalysisResult` payloads → `VisualStyle`-annotated
  render payloads for Plotly and TradingView Lightweight Charts.
- **Never:** recomputes structure. If the chart needs a number, the engine
  must emit it.

## 5. AI (`contexttrading.ai`)

- **Owns:** provider adapters (OpenAI, Anthropic, local), prompt assembly
  from *engine JSON only*, structured-output parsing back into versioned
  models (`NarrativeResult`, `RiskAssessment`).
- **Never:** receives raw candle series, computes levels, or emits
  numbers not present in its input payload. Prompts embed the engine's
  `schema_version` and `engine_version` for audit.

## 6. Backtesting (`contexttrading.backtesting`)

- **Owns:** event-driven replay, deterministic fill simulation, cost/slippage
  models, equity curves, performance reports — all seeded and reproducible.
- **Never:** live I/O; lookahead (enforced by event ordering tests).

## 7. API (`contexttrading.api`)

- **Owns:** HTTP surface (FastAPI), request validation, auth, serialization
  of engine results, schema endpoints.
- **Never:** business logic. Handlers delegate to engine facades.

## 8. Testing (`tests/`)

- `unit/` — per-module correctness, edge cases.
- `integration/` — cross-layer flows (data → engine → envelope).
- `regression/` — golden-file byte-equality of engine outputs per
  (dataset, engine_version).
- `performance/` — `pytest-benchmark` budgets for engine hot paths.

## 9. Documentation (`docs/`)

Architecture (this directory), per-module references in `docs/modules/`,
API reference in `docs/api/`, guides, roadmap, and machine-readable exported
JSON schemas in `docs/schemas/json/` (generated — do not hand-edit).
