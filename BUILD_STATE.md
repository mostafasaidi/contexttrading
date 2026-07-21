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
| 5. Order block engine (OB, breaker, mitigation blocks, supply/demand, validation) | ⬅️ NEXT |
| 6. Session engine (Sydney, Tokyo, London, NY, kill zones) + MTF context | pending |
| 7. Visualization engine (TradingView Lightweight Charts objects/rendering) | pending |
| 8. AI layer (context builder, narrative, trade eval, risk, journal, reports, prompts) | pending |
| 9. REST API (FastAPI, OpenAPI, auth, endpoints, streaming) | pending |
| 10. Backtesting (replay, statistics, metrics, optimization) | pending |
| 11. Full test suite hardening (unit/integration/regression/performance/edge) | pending |
| 12. Final docs, examples, tutorials, CI verification | pending |

## Build mechanics (how to resume)

- Work is delegated to a **coder subagent, resumed across runs**: resume id = `agent-0` (it holds full context of Phases 1–3 and the conventions). Resume it with the Phase-4 task; if resume is unavailable, spawn a fresh coder subagent and point it at this file + `docs/` + `docs/architecture/determinism.md` + `docs/guides/developer-guide.md`.
- Each run: implement one phase → full unit/property/golden/integration tests → ruff + black clean → logical conventional commits.
- TodoList mirrors the 12 phases (Phase 5 = in_progress).

## Current verified state (end of Phase 4)

- **359 tests passing** (unit incl. hypothesis property tests for swings + FVG, 9 byte-exact regression goldens in `tests/regression/goldens/` — regenerate only with `CT_UPDATE_GOLDENS=1` + schema version bump, 13 integration on a 2,000-candle seeded dataset), ruff clean, black clean.
- Key commits: `41cbac1` scaffolding · `3d0c2fb` docs · `4957d46` core · `c349a84` models · `fcbea0f` refactor StrEnum/PEP695 · `3462ca4` phase-3 enums/thresholds · `b138a50`+`51a0058` indicators · `46afa5b` structure engine · `e3ccce3`+`dfd7987` tests · `ffe805c` schema exports + module docs · Phase 4: "feat(analysis): add FVG detection engine" / "feat(analysis): add FVG inversion and mitigation lifecycle" / "test(analysis): add FVG unit/property/golden tests" / "docs: document FVG engine".

## Phase 4 decisions (for Phase 5+ reuse)

- FVG lifecycle reuses the shared `MitigationStatus` enum: UNMITIGATED=untouched, PARTIALLY_MITIGATED=partial, MITIGATED=filled (wick suffices), VIOLATED=inverted (close-through only; terminal). MITIGATED is NOT terminal — a wick-filled zone can still invert later.
- Chronological first-touch pattern: single pass updates registered states per candle, registers new objects at their confirmation candle — same pattern Phase 5 order blocks should follow.
- Nested parenting = chronological snapshot of still-active containers at registration; stacked grouping = pure geometry (transitive chaining within `fvg_stacked_lookback`, groups of 1 excluded, group id = content hash of root member).
- Strength = weighted sum (gap ATR capped, displacement link, freshness, exp age decay, struct bonus), clamped [0,1]; weights in EngineConfig; rank = sort by (-strength, formation_end_index).
- FVG `is_inverse` (VIOLATED) is the input Phase 5 breaker-block logic should consume.

## Conventions Phase 4+ MUST follow (established in Phases 1–3)

- Module contract: pure `(CandleSeries, EngineConfig) -> AnalysisResult[T]`; no wall-clock, no I/O, no unseeded randomness; `generated_from` from series bounds.
- Detected objects subclass `AnalysisObject` (models/base.py) with `ID_PREFIX` → deterministic content-hash IDs; attach `VisualStyle` preset at detection time.
- Float compares via `FLOAT_REL_TOL`/`FLOAT_ABS_TOL`; thresholds are EngineConfig fields with defaults + docstrings; ATR may be `None` before `atr_period-1` — guard.
- `StructureScanner(...).run(series)` gives swings/breaks/atr_values in one pass — reuse, never recompute structure (see `analysis/liquidity/liquidity.py` template).
- New models: schema version slot in `core/versioning.py`, register in `EXPORTED_MODELS`, re-export via `python -m contexttrading.schemas.export`.
- Errors: `AnalysisError` CT-3000, `InsufficientDataError` CT-3001, `DataGapError`, always with `context={...}`.
- Docs per module in `docs/modules/`: Purpose/Responsibilities/Inputs/Outputs/Dependencies/Examples/Testing/Limitations; update `docs/roadmap.md`.
- Note: `PoolStatus` includes `BROKEN` (deviation from MP02 list, deliberate); MTF context moved to Phase 6 with sessions.

## Phase 5 brief (ready to hand to the coder subagent)

Order block engine under `src/contexttrading/analysis/orderblocks/`:
- Reuse `StructureScanner` — OBs anchor on the last opposite-direction candle(s) before a displacement BOS; never recompute structure.
- Follow the Phase-4 patterns: chronological first-touch lifecycle with the shared `MitigationStatus` enum, deterministic strength scoring with weights in EngineConfig, `AnalysisObject` content-hash IDs, schema slot + export, goldens + property + integration tests.
- Breaker blocks consume FVG `is_inverse`/VIOLATED semantics already established; mitigation blocks mirror with the opposite anchor leg.
- Docs: `docs/modules/orderblocks.md`; commits mirroring the Phase-4 four-commit split.

## User preferences observed

- Wants fully autonomous continuation ("continue automatically until production-ready"); interrupted once to pause for the night — resume tomorrow by continuing Phase 4 without re-asking.
- GitHub push: offer only at milestones; requires explicit confirmation.
