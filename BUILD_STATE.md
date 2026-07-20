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
| 4. FVG engine (detection, nested/stacked, inverse, mitigation lifecycle, strength ranking) | ⬅️ NEXT — subagent run was interrupted before starting; nothing committed for this phase |
| 5. Order block engine (OB, breaker, mitigation blocks, supply/demand, validation) | pending |
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
- TodoList mirrors the 12 phases (Phase 4 = in_progress).

## Current verified state (end of Phase 3)

- **307 tests passing** (294 unit incl. 4 hypothesis property tests, 6 byte-exact regression goldens in `tests/regression/goldens/` — regenerate only with `CT_UPDATE_GOLDENS=1` + schema version bump, 7 integration on a 2,000-candle seeded dataset), ruff clean, black clean.
- Key commits: `41cbac1` scaffolding · `3d0c2fb` docs · `4957d46` core · `c349a84` models · `fcbea0f` refactor StrEnum/PEP695 · `3462ca4` phase-3 enums/thresholds · `b138a50`+`51a0058` indicators · `46afa5b` structure engine · `e3ccce3`+`dfd7987` tests · `ffe805c` schema exports + module docs.

## Conventions Phase 4+ MUST follow (established in Phases 1–3)

- Module contract: pure `(CandleSeries, EngineConfig) -> AnalysisResult[T]`; no wall-clock, no I/O, no unseeded randomness; `generated_from` from series bounds.
- Detected objects subclass `AnalysisObject` (models/base.py) with `ID_PREFIX` → deterministic content-hash IDs; attach `VisualStyle` preset at detection time.
- Float compares via `FLOAT_REL_TOL`/`FLOAT_ABS_TOL`; thresholds are EngineConfig fields with defaults + docstrings; ATR may be `None` before `atr_period-1` — guard.
- `StructureScanner(...).run(series)` gives swings/breaks/atr_values in one pass — reuse, never recompute structure (see `analysis/liquidity/liquidity.py` template).
- New models: schema version slot in `core/versioning.py`, register in `EXPORTED_MODELS`, re-export via `python -m contexttrading.schemas.export`.
- Errors: `AnalysisError` CT-3000, `InsufficientDataError` CT-3001, `DataGapError`, always with `context={...}`.
- Docs per module in `docs/modules/`: Purpose/Responsibilities/Inputs/Outputs/Dependencies/Examples/Testing/Limitations; update `docs/roadmap.md`.
- Note: `PoolStatus` includes `BROKEN` (deviation from MP02 list, deliberate); MTF context moved to Phase 6 with sessions.

## Phase 4 brief (ready to hand to the coder subagent)

FVG engine under `src/contexttrading/analysis/fvg/`:
- **detection.py**: 3-candle imbalance (bullish: low[i+1] > high[i-1], zone [high[i-1], low[i+1]]; bearish mirrored); min size `fvg_min_atr_fraction`×ATR[i]; nested (contained in older unfilled same-direction FVG → parent_fvg_id); stacked (consecutive same-direction within `fvg_stacked_lookback`, overlapping/adjacent zones → stack_group_id); displacement linkage to StructureBreak (linked_break_id, margin_atr).
- **inversion.py**: close through far side → inverse FVG (wick-through does NOT invert); is_inverse + inversion_index; lifecycle then tracks inverted zone.
- **mitigation.py**: chronological scan, first-touch semantics consistent with liquidity sweeps; UNTOUCHED → PARTIALLY_FILLED (track max_fill_fraction) → FILLED; first_touch_index, filled_index, age, touches.
- **strength/ranking**: deterministic score in [0,1] from gap size (ATR mult), displacement linkage (strong BOS > weak > none), freshness, age decay (half-life `fvg_strength_half_life`), nested/stacked capped bonuses; weights in EngineConfig; sort desc with rank field; document formula.
- **models/fvg.py**: `FVG(AnalysisObject)` ID_PREFIX="fvg", validated zone geometry, `FVGResult` with summary counts; register + export schemas.
- **Tests**: unit fixtures (boundary sizes, nested/stacked edges, inversion close-vs-wick, partial→filled monotonic, warmup guard), hypothesis properties (geometry valid, status monotonic, ID stability), 3 regression goldens, integration over the seeded 2,000-candle dataset (linked_break_id referential integrity, no NaN/inf, determinism).
- **Docs**: docs/modules/fvg.md incl. strength formula + ASCII lifecycle diagram; update roadmap/index.
- Finish green: pytest + ruff + black; commits: "feat(analysis): add FVG detection engine", "feat(analysis): add FVG inversion and mitigation lifecycle", "test(analysis): ...", "docs: document FVG engine".

## User preferences observed

- Wants fully autonomous continuation ("continue automatically until production-ready"); interrupted once to pause for the night — resume tomorrow by continuing Phase 4 without re-asking.
- GitHub push: offer only at milestones; requires explicit confirmation.
