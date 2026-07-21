# ContextTrading — Build State (pause checkpoint)

> Saved 2026-07-20 ~23:46. Resume point for the next session.
> This file tracks the autonomous build driven by MASTER PROMPTS 01–04.
> Delete or archive when the project reaches production-ready status.

## How this project is being built

- Spec = FOUR master prompts (all received, treated as one specification):
  1. **MP01 System Architect** — 9-layer architecture, deterministic-first philosophy, tech stack (Python 3.12+, FastAPI, Pydantic, NumPy/Pandas/Polars, Plotly, TV Lightweight Charts, SQLite/Postgres/Redis, Docker, Pytest, GH Actions), docs-before-code, 4 test tiers.
  2. **MP02 Trading Engine** — deterministic SMC engine: swings, BOS/CHoCH, liquidity, EQH/EQL, FVG/iFVG, order/breaker/mitigation blocks, supply/demand, premium/discount, sessions/kill zones, trend/bias, confluence scores, MTF, visualization-ready objects, streaming/large-data performance, full test matrix.
  3. **MP03 AI Analyst** — AI NEVER calculates; consumes engine JSON only; outputs structured JSON (Executive Summary, Market Narrative, Bias, Confluences, Risk, Weaknesses, Trade Evaluation, Alternative Scenarios, Confidence, Action Items); journal analysis; evidence-based confidence.
  4. **MP04 Autonomous Builder** — 12 build phases, production quality, logical commits, never stop until production-ready.
- Hard invariants: no placeholder code, no toy examples, no simplified architecture, every output = versioned structured JSON, identical input → identical output.

## Repo

- Path: `C:\Users\asus\Documents\kimi\workspace\ContextTrading` (local git repo; NOT yet pushed to GitHub — pushing needs explicit user confirmation; GitHub MCP plugin is connected and available when the user approves).
- Verify state: `git -C ContextTrading log --oneline | head -30` and `python -m pytest tests/ -q` from repo root.

## Phase status (12-phase roadmap in docs/roadmap.md)

| Phase | Status |
|---|---|
| 1. Repo structure, README, license, architecture & dev docs, roadmap | ✅ DONE |
| 2. Core models, JSON schemas, config, validation, logging, errors | ✅ DONE |
| 3. Market structure engine (swings, BOS/CHoCH, trend, liquidity, EQH/EQL, premium/discount, indicators) | ✅ DONE |
| 4. FVG engine (detection, nested/stacked, inverse, mitigation lifecycle, strength ranking) | ✅ DONE |
| 5. Order block engine (OB, breaker, mitigation blocks, supply/demand, validation) | ✅ DONE |
| 6. Session engine (Sydney, Tokyo, London, NY, kill zones) + MTF context | ⬅️ NEXT |
| 7. Visualization engine (TradingView Lightweight Charts objects/rendering) | pending |
| 8. AI layer (context builder, narrative, trade eval, risk, journal, reports, prompts) | pending |
| 9. REST API (FastAPI, OpenAPI, auth, endpoints, streaming) | pending |
| 10. Backtesting (replay, statistics, metrics, optimization) | pending |
| 11. Full test suite hardening (unit/integration/regression/performance/edge) | pending |
| 12. Final docs, examples, tutorials, CI verification | pending |

## Build mechanics (how to resume)

- Work is delegated to a **coder subagent, resumed across runs**: resume id = `agent-0` (it holds full context of Phases 1–3 and the conventions). Resume it with the Phase-4 task; if resume is unavailable, spawn a fresh coder subagent and point it at this file + `docs/` + `docs/architecture/determinism.md` + `docs/guides/developer-guide.md`.
- Each run: implement one phase → full unit/property/golden/integration tests → ruff + black clean → logical conventional commits.
- TodoList mirrors the 12 phases (Phase 6 = in_progress).

## Current verified state (end of Phase 5)

- **419 tests passing** (unit incl. hypothesis property tests for swings/FVG/OB/SD, 12 byte-exact regression goldens in `tests/regression/goldens/` — regenerate only with `CT_UPDATE_GOLDENS=1` + schema version bump, 23 integration on a 2,000-candle seeded dataset), ruff clean, black clean.
- Key commits: `41cbac1` scaffolding · `4957d46` core · `46afa5b` structure engine · `ffe805c` phase-3 schemas/docs · Phase 4: `aedbed5`/`f733a90`/`5cb8d9a`/`09ae472` · Phase 5: `f292d13` order block engine · `a5150ea` supply/demand engine · `a2b2325` detection fixes · `1d7a2d7` tests.

## Phase 5 decisions (for Phase 6+ reuse)

- OB anchors: last opposite-close candle before a confirmed break (single-candle; cluster merging deliberately dropped — trend legs are contiguous same-sign runs). Origin = REVERSAL iff the linked break is a CHoCH. Lifecycle starts at break_index + 1 (the break candle belongs to the departure).
- Refinement: zone height > `ob_refine_atr_multiple` x ATR (strict) → refined zone = extreme `ob_refine_wick_fraction`; mitigation level = refined midpoint (50% rule), else far boundary.
- Breaker = VIOLATED OB + confirmed counter-direction break within `breaker_confirm_lookback`; flips direction, keeps zone, lifecycle from flip+1.
- Mitigation blocks anchor on STOP_HUNT/GRAB sweeps; origin = candle at the last opposite external swing before the sweep; `failed_swing_id` = first member swing of the swept pool (equal-level pools store [level.id, *swing_ids]).
- SD zones: OB-derived (over the active/refined zone) + RBD/DBR pattern zones at reversal swings (base = 1..`sd_max_base_candles` small-body candles ending AT the swing; departure = impulse leg >= `sd_departure_atr_multiple` x ATR; actionable at leg end + external lookback, else skipped). Duplicate = overlap/min(heights) >= 0.8 vs an OB zone.
- SD lifecycle is its own enum (`SDZoneStatus` FRESH/TESTED/MITIGATED/BROKEN) — unlike blocks, MITIGATED is terminal there; BROKEN (close-through) beats MITIGATED on the same candle.
- External swings with lookback L need index >= L (fixtures must place the first swing at index >= external lookback).

## Conventions Phase 4+ MUST follow (established in Phases 1–3)

- Module contract: pure `(CandleSeries, EngineConfig) -> AnalysisResult[T]`; no wall-clock, no I/O, no unseeded randomness; `generated_from` from series bounds.
- Detected objects subclass `AnalysisObject` (models/base.py) with `ID_PREFIX` → deterministic content-hash IDs; attach `VisualStyle` preset at detection time.
- Float compares via `FLOAT_REL_TOL`/`FLOAT_ABS_TOL`; thresholds are EngineConfig fields with defaults + docstrings; ATR may be `None` before `atr_period-1` — guard.
- `StructureScanner(...).run(series)` gives swings/breaks/atr_values in one pass — reuse, never recompute structure (see `analysis/liquidity/liquidity.py` template).
- New models: schema version slot in `core/versioning.py`, register in `EXPORTED_MODELS`, re-export via `python -m contexttrading.schemas.export`.
- Errors: `AnalysisError` CT-3000, `InsufficientDataError` CT-3001, `DataGapError`, always with `context={...}`.
- Docs per module in `docs/modules/`: Purpose/Responsibilities/Inputs/Outputs/Dependencies/Examples/Testing/Limitations; update `docs/roadmap.md`.
- Note: `PoolStatus` includes `BROKEN` (deviation from MP02 list, deliberate); MTF context moved to Phase 6 with sessions.

## Phase 6 brief (ready to hand to the coder subagent)

Session engine + MTF context under `src/contexttrading/analysis/sessions/`:
- `SessionConfig` already exists (timezone-validated windows; `SessionName` enum in constants). Session windows are wall-clock — keep determinism by deriving everything from candle timestamps only (UTC-aware), never `now()`.
- Session high/low pools: `LiquidityPoolKind` already has SESSION_HIGH/SESSION_LOW/PREVIOUS_DAY_HIGH/PREVIOUS_DAY_LOW slots — feed them into the existing pool/sweep machinery rather than building a parallel lifecycle.
- MTF context: resample `CandleSeries` to higher timeframes deterministically (aggregate, no lookahead), run `StructureScanner` per timeframe, align trends; the engine already supports any series.
- Follow established patterns: chronological lifecycle, content-hash IDs, schema slots + export, unit/property/golden/integration tests, docs in `docs/modules/sessions.md`.

## User preferences observed

- Wants fully autonomous continuation ("continue automatically until production-ready"); interrupted once to pause for the night — resume tomorrow by continuing Phase 4 without re-asking.
- GitHub push: offer only at milestones; requires explicit confirmation.
