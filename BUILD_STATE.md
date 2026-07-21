# ContextTrading — Build State (pause checkpoint)

> Saved 2026-07-22 (end of backtesting). Resume point for the next session.
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
| 6. Session engine (Sydney, Tokyo, London, NY, kill zones, Judas swings) + MTF context | ✅ DONE |
| 7. Confluence engine (weighted deterministic scoring, explainable factors, confluence zones) | ✅ DONE |
| 8. Visualization & storage (render primitives, mappers, chart serializer, reference frontend, SQLite result store) | ✅ DONE |
| 9. AI analyst layer (prompts, context builder, providers, citation enforcement, structured reports) | ✅ DONE |
| 10. REST API service (FastAPI, analyze/AI endpoints, schema endpoints, docs/api/) | ✅ DONE |
| 11. Backtesting (replay, statistics, metrics, optimization) | ✅ DONE |
| 12. Examples, polish, performance (examples/, benchmarks, docs completion, PostgreSQL/Redis stores) | ⬅️ NEXT |
| 13. Release hardening (PyPI, Docker, security review, v1.0 schema freeze) | pending |

## Build mechanics (how to resume)

- Work is delegated to a **coder subagent, resumed across runs**: resume id = `agent-0` (it holds full context of Phases 1–3 and the conventions). Resume it with the Phase-4 task; if resume is unavailable, spawn a fresh coder subagent and point it at this file + `docs/` + `docs/architecture/determinism.md` + `docs/guides/developer-guide.md`.
- Each run: implement one phase → full unit/property/golden/integration tests → ruff + black clean → logical conventional commits.
- TodoList mirrors the 12 phases (Phase 11 = in_progress).

## Current verified state (end of backtesting)

- **785 tests passing** (unit incl. hypothesis property tests for swings/FVG/OB/SD/resampling/confluence/backtest invariants, 26 byte-exact regression goldens in `tests/regression/goldens/` incl. chart goldens, `openapi_v1.json`, 2 backtest goldens — regenerate only with `CT_UPDATE_GOLDENS=1` + schema version bump, 50 integration on a 2,000-candle seeded dataset), ruff clean, black clean.
- Key commits: `41cbac1` scaffolding · `4957d46` core · `46afa5b` structure engine · `ffe805c` phase-3 schemas/docs · Phase 4: `aedbed5`/`f733a90`/`5cb8d9a`/`09ae472` · Phase 5: `f292d13` order block engine · `a5150ea` supply/demand engine · `a2b2325` detection fixes · `1d7a2d7` tests · Phase 6: `82ff12e` session engine · `2a0591b` resampling + MTF context · `94cd231` tests · Phase 7: `3c6a1b8` confluence engine · `19f2829` tests · Phase 8: `bb3c621` primitives + mappers · `fdac1b0` chart serializer + schema exports · `e2931af` SQLite result store · `5044dd3` reference frontend + demo payload · `f4268b0` tests · AI layer: `a649745` report models + config · `d4d87ec` prompt assets + registry · `230606b` context builders · `6002ef0` providers · `a689ce5` validation + analyst pipeline · `312f167` tests · REST API: `1e67c5b` shared pipeline orchestration · `f9cf4b9` wire models + auth + config + thread-safe store · `6c0a90b` app factory + all v1 routes · `7ddb49a` tests + OpenAPI golden · `d989926` docs · Backtesting: `be6ec4e` models + config · `87dc194` execution + replay · `7dc3c68` statistics + SMC strategy · `b623ef4` grid + walk-forward · `469cc8a` /v1/backtest endpoint · `c0c7790` engine edge fixes · `6d8ff7e`/`7a5018f` tests · `a5c3e06` calmar overflow fix.

## Phase 5 decisions (for Phase 6+ reuse)

- OB anchors: last opposite-close candle before a confirmed break (single-candle; cluster merging deliberately dropped — trend legs are contiguous same-sign runs). Origin = REVERSAL iff the linked break is a CHoCH. Lifecycle starts at break_index + 1 (the break candle belongs to the departure).
- Refinement: zone height > `ob_refine_atr_multiple` x ATR (strict) → refined zone = extreme `ob_refine_wick_fraction`; mitigation level = refined midpoint (50% rule), else far boundary.
- Breaker = VIOLATED OB + confirmed counter-direction break within `breaker_confirm_lookback`; flips direction, keeps zone, lifecycle from flip+1.
- Mitigation blocks anchor on STOP_HUNT/GRAB sweeps; origin = candle at the last opposite external swing before the sweep; `failed_swing_id` = first member swing of the swept pool (equal-level pools store [level.id, *swing_ids]).
- SD zones: OB-derived (over the active/refined zone) + RBD/DBR pattern zones at reversal swings (base = 1..`sd_max_base_candles` small-body candles ending AT the swing; departure = impulse leg >= `sd_departure_atr_multiple` x ATR; actionable at leg end + external lookback, else skipped). Duplicate = overlap/min(heights) >= 0.8 vs an OB zone.
- SD lifecycle is its own enum (`SDZoneStatus` FRESH/TESTED/MITIGATED/BROKEN) — unlike blocks, MITIGATED is terminal there; BROKEN (close-through) beats MITIGATED on the same candle.
- External swings with lookback L need index >= L (fixtures must place the first swing at index >= external lookback).

## Phase 6 decisions (for Phase 7+ reuse)

- `analyze_sessions(series, engine_config=None, session_config=None)` deviates from the strict one-config contract deliberately: session windows live in `SessionConfig`, which now ships documented UTC defaults — sessions sydney 21:00-06:00, tokyo 00:00-09:00, london 07:00-16:00, new_york 12:00-21:00; killzones london 07:00-10:00, new_york_am 12:00-15:00, london_close 15:00-17:00, new_york_pm 18:00-20:00 (validated like `sessions`).
- Midnight-wrapping windows belong to the date of their START bar (in `default_timezone`). Overlapping windows are tracked independently; day-extreme counts can exceed the day count. Killzones get stats but no pools and are excluded from day-extreme counts.
- Asian range per day D = candles inside sydney/tokyo windows in `[london_open(D)-12h, london_open(D))`; synthesized as group `"asia"`. Session/asia pools activate at instance end + 1; PDH/PDL pools activate with the new day's first candle. All feed the standard `scan_sweeps` — no parallel lifecycle.
- Judas rules: `asia` level swept during the london killzone, or `london` level swept during `new_york_am`/`new_york_pm` → `SessionSweep` linked to the underlying `LiquiditySweep`. PDH/PDL sweeps are NOT Judas events.
- Resampling anchors: epoch floor up to 1d; 1w = Monday 00:00 UTC (epoch day 4); 1M = calendar month start (real calendar, never the 30-day constant). OHLCV = first/max/min/last/sum; empty buckets emit no bar; only the LAST bar may carry `is_closed=False` (dropped when `mtf_include_incomplete_bar=False`). Upsampling (target <= source) → `DataError`. `CandleSeries.resample()` now delegates to `analysis.mtf.resample` via lazy import (old NotImplementedError stub removed; its two contract tests rewritten).
- MTF: contexts = base (rank 0) + ascending HTFs, weight = `mtf_tf_weight_base ** rank` (default 2.0 → 1, 2, 4, 8). Bias = weighted majority (ties → RANGING); strength STRONG only when >= 2 contexts and all known agree; MODERATE at share >= `mtf_moderate_share` (2/3); UNKNOWN contexts dilute the share. `htf_influence` = weighted share of HTFs opposing the base-TF trend. recommended_execution_timeframe = base TF iff it agrees with the bias, else None. Resampled series too short for structure → UNKNOWN context, never an exception.
- MTFBias/TimeframeContext are plain VersionedModels (computed summaries, not detected objects); SessionStats/SessionSweep are AnalysisObjects with content-hash IDs (`sess_`, `ssweep_`).

## Phase 7 decisions (for Phase 8+ reuse)

- `analyze_confluence(series, config=None, session_config=None, mtf_timeframes=None)` orchestrates the module entrypoints (`analyze_*`) — it detects nothing itself. Default MTF ladder = next two enum timeframes above base (15m → 30m, 1h — 30m exists in the enum).
- Score semantics: per-side sums of `weight*raw` normalized by TOTAL emitted factor weight; factors with no directional evidence emit raw 0 and DILUTE (confidence semantics); non-evaluable factors (no breaks/sweeps/range) are omitted and don't dilute. bull+bear <= 1; bias = winning side, ties RANGING.
- Qualitative raw maps are documented module constants in `analysis/confluence/factors.py`, NOT config: TREND_STRENGTH_RAW (1.0/0.6/0.3), SWEEP_CLASS_RAW (1.0/0.8/0.6), BLOCK_KIND_RAW (ob 1.0 / brk 0.8 / mb 0.7). All weights/lookbacks/proximity are `conf_*` EngineConfig fields.
- Direction mapping: sellside sweep = bullish evidence (and mirrored); Judas buyside sweep = bearish; DISCOUNT = bullish. SD DEMAND = bullish; OB/FVG directions used directly.
- Confluence zones: chain-merge overlapping active zones (fvg/ob/sd + dealing-range premium/discount band, NO proximity filter); emit only unanimous-direction clusters with >= `conf_zone_min_factors` (2) distinct kinds; score = best-raw-per-kind weighted coverage / total zone-kind weight. ConfluenceZone is an AnalysisObject (ID_PREFIX "conf", layer `confluence.zones`, opacity scales with score); FactorContribution/ConfluenceResult are plain VersionedModels.
- Property-test gotcha: degenerate hypothesis walks (strictly monotonic, zero-wick) violate structure-engine Leg contracts (magnitude > 0, duration >= 1) — excluded via `assume(False)` in `test_confluence_property.py`, documented there. A latent Phase-3 engine edge; revisit only if real feeds hit it.

## Phase 8 decisions (for Phase 9+ reuse)

- Visualization is renderer-agnostic: `build_chart_payload(series, results, config=None) -> AnalysisResult[ChartPayload]` (module `"chart"`) is the ONLY render contract — candles + volume + 23 canonical layers + theme + legend. Plotly dropped deliberately (MP01 listed it; the payload serves any renderer). The renderer CONSUMES `VisualStyle` presets; the only colors born in visualization are theme colors and the bull/bear/neutral triplet for HTF level lines (MTF contexts carry no style).
- Primitives: discriminated union (`primitive` field) of `PriceLine`/`Box`/`Marker`/`Label`/`Segment`/`AreaBand` in `visualization/primitives.py`, schema version 1.0.0. `Label` is currently emitted by no mapper (reserved for AI annotations). Time = UNIX seconds everywhere; ms leak guarded by tests. Index→time via `series.candles[i].timestamp`; open-ended zones extend to the last candle.
- 23 layers in canonical z-order (`LAYER_SPECS` in serializer.py); `z_order = rank*100 + priority`; primitives sorted `(z_order, source_id)` → byte-identical payloads. `swings.internal` is the only default-hidden layer; `VisualizationConfig.hidden_layers/shown_layers` override. All layers emitted even when empty.
- Reference frontend: no-build static page (`visualization/frontend/`, LW Charts v4 UMD via CDN) — boxes/bands/segments on an overlay canvas (v4 has no native rectangle; v5 `attachPrimitive` is the upgrade path); marker shape `diamond` falls back to `square`. Serve via `python -m http.server` (fetch fails on file://). Demo payload committed (`demo-payload.json`, five-day 15m full stack).
- `data/store.py`: SQLite `ResultStore` keyed `(symbol, timeframe, module, series_hash)`, INSERT OR REPLACE; `hash_series` = sha256 over canonical records; load validates `is_compatible(stored, current)` → `SchemaVersionError` (CT-2001), storage failures → `DataError` (CT-1000). `PAYLOAD_MODELS` maps all 11 module names (incl. `chart`) to payload classes for typed round-trips. PostgreSQL/Redis deferred to Phase 11.
- Shared test helper `tests/fixtures.py::full_stack_results(series, config, mtf_timeframes=("1h","4h"))` runs all 10 analyzers once — used by visualization unit/property/golden/integration tests.

## Phase 10 decisions (REST API, for reuse)

- `analysis/pipeline.py` is the single orchestration source: `MODULE_ORDER` (10 modules), `MODULE_SLUGS` (URL slug -> key; "premium-discount" -> "premium_discount"), `run_module` (accepts slug or key), `run_full_stack`. `tests/fixtures.py::full_stack_results` delegates to it. `/v1/analysis/full` is registered BEFORE `/{module}` so "full" never matches the path param.
- Error envelope everywhere: `ErrorEnvelope{schema_version, error:{code,message,context,request_id}}` — also for 404/422/500; no FastAPI default bodies leak. Status mapping in `app._status_for`; deviation: `InsufficientDataError` (CT-3001) -> 422 (client data problem), other CT-3xxx -> 500. `AIProviderError` -> 502, or 504 only when "timeout" appears in the message. AI not configured (`provider="none"`) -> `ConfigurationError` CT-4000 -> 500.
- Auth: `X-API-Key` header, `hmac.compare_digest`, keys from `CT_API__API_KEYS` (comma-separated string or JSON array). `auth_enabled=False` opens everything; `allow_anonymous=True` passes missing keys (bad keys still 401). /healthz + /readyz always open.
- Wire models in `api/models.py` (`SCHEMA_VERSION_API="1.0.0"`, 10 models registered + exported). `config_overrides` merge via `EngineConfig.model_validate` -> unknown keys raise core `ValidationError` CT-2000 -> 422. Candle cap `max_candles_per_request` (20000) -> `RequestTooLargeError` CT-7002 -> 413. No byte-size limit; rate limiting documented as reverse-proxy concern.
- Streaming = NDJSON (`application/x-ndjson`), NOT SSE: finite response, trivially parsed by any HTTP client. Lines in `MODULE_ORDER` + terminal `{"module":"done","modules","candle_count"}`. Streamed results == full-stack results (tested).
- `ResultStore` made thread-safe (`check_same_thread=False` + lock) and gained `ping()` for /readyz. Persist happens only via `charts/payload?persist=true`; retrieval requires `series_hash` query param.
- OpenAPI spec is golden-tested (`openapi_v1.json`); `ErrorEnvelope` is attached to every v1 route via router-level `responses` so it appears in components.
- Docker: image CMD runs uvicorn with `--factory`; compose `api` service is default-on with `apidata:/data` SQLite volume; postgres/redis stay in the "later" profile (Phase 12).

## Phase 11 decisions (backtesting, for reuse)

- Replay contract: decisions at bar CLOSE i, fills on bar i+1 (open for market/close; range touch for limit/stop with ties-fills conservative); intents expire after one bar; one position at a time; entries REQUIRE stop_loss; `created_index == bar_index` validated. No-lookahead is proven by a construction test (truncated-at-T run == full run on shared bars).
- Fill/cost rules: half-spread per fill; slippage on market+stop fills only (limits never slip); SL-first intrabar ambiguity (fixed rule); gap-through SL fills at the open; TP gap at open fills at open (chronological); a position can stop out on its own fill bar (holding_bars=0). Sizing: risk_percent via SL distance (default) or fixed_units; breakeven_after_r optional.
- Statistics: bar-return Sharpe/Sortino with calendar annualization (365.25d / timeframe); Calmar in log space with overflow guard (None on absurd extrapolation — found by hypothesis); statistics_reliable < min_trades (30).
- Optimization: cartesian product in declared key order; dotted paths engine./backtest./strategy.; leaderboard objective-desc, None last, declaration-index tie-break; anchored walk-forward with overfit flag at `optimization_overfit_threshold` (0.5). No parallelism.
- SMC pullback strategy: zone-in-value rule — zone in DISCOUNT of the CONFIRMED dealing range, or above it entirely (fresh BOS leg; the confirmed range lags active legs — documented in docs/modules/backtesting.md). TP = nearest untapped opposing pool else tp_r_multiple fallback from decision close.
- Engine edges fixed along the way (`c0c7790`): classify_legs skipped same-bar high/low alternations (Leg duration=0 crash on resampled MTF series); run_module now forwards mtf_timeframes to analyze_confluence (was silently using the default ladder).
- Performance reality: full-prefix replay is O(n^2) (confluence ≈ 2/3 of per-bar cost; it re-runs all modules internally without exposing payloads). Tests use recompute_interval + window_bars; incremental engine updates and payload-sharing confluence are Phase-12 candidates.

## Phase 12 brief (ready to hand to the coder subagent)

Examples, polish, performance (roadmap Phase 12):
- `examples/`: runnable scripts (basic engine usage, full-stack analysis, chart payload render, backtest + optimization walkthrough) with README; keep them smoke-tested in CI (cheap subset).
- Benchmarks: `tests/benchmark/` or `benchmarks/` — engine module timings vs dataset size (100/1k/10k bars), replay throughput; document baseline numbers; no hard perf gates yet.
- Performance work (optional, correctness-safe): confluence payload-sharing (accept pre-computed module results), replay prefix-caching of engine results, profile-guided hotspots.
- Storage: PostgreSQL/Redis `ResultStore` adapters behind the existing store interface (decision: implement postgres, defer redis unless trivial); compose wiring moves them out of the "later" profile.
- Docs completion: examples cross-links, any remaining gaps vs the 4 master prompts; DX polish (Makefile or task runner?).

## AI-layer decisions (Phase 9 in roadmap numbering, for reuse)

- `AIReportResult[T]` envelope (subject = "SYMBOL/TF" or "journal:period") instead of reusing AnalysisResult — journal/performance subjects have no timeframe/window.
- Evidence ids: engine object ids + synthetic keys `trend:state`, `mtf:bias`, `range:dealing`, `factor:NN:name` (confluence assembly order), `setup:current`, `stat:*`, `trade:*`. The `evidence_index` is NEVER truncated (display sections are, with `TruncationEntry` records).
- Citation enforcement: hallucinated id anywhere (evidence_ids / factor_ids / zone_id / flat evidence_citations) → `CitationError` CT-5002 (hard); empty evidence_ids on an EvidenceStatement → warning in `provenance.validation_warnings`; parse/schema failure → `AIResponseError` CT-5001. Retry exactly once with error feedback, then propagate.
- MockProvider output is a pure function of the injected context (no seed needed); HTTP providers lazy-import httpx (optional dep) and read keys only from `AIConfig.api_key_env`.
- Prompts are `.md` files with `<!-- prompt-version: X.Y.Z -->`; registry records sha256; reports embed prompt name/version/hash in `ReportProvenance`.
- Roadmap renumbered to 13 phases: 9 = AI analyst layer (done), 10 = API, 11 = backtesting, 12 = polish (+PostgreSQL/Redis), 13 = release.

## Conventions Phase 4+ MUST follow (established in Phases 1–3)

- Module contract: pure `(CandleSeries, EngineConfig) -> AnalysisResult[T]`; no wall-clock, no I/O, no unseeded randomness; `generated_from` from series bounds.
- Detected objects subclass `AnalysisObject` (models/base.py) with `ID_PREFIX` → deterministic content-hash IDs; attach `VisualStyle` preset at detection time.
- Float compares via `FLOAT_REL_TOL`/`FLOAT_ABS_TOL`; thresholds are EngineConfig fields with defaults + docstrings; ATR may be `None` before `atr_period-1` — guard.
- `StructureScanner(...).run(series)` gives swings/breaks/atr_values in one pass — reuse, never recompute structure (see `analysis/liquidity/liquidity.py` template).
- New models: schema version slot in `core/versioning.py`, register in `EXPORTED_MODELS`, re-export via `python -m contexttrading.schemas.export`.
- Errors: `AnalysisError` CT-3000, `InsufficientDataError` CT-3001, `DataGapError`, always with `context={...}`.
- Docs per module in `docs/modules/`: Purpose/Responsibilities/Inputs/Outputs/Dependencies/Examples/Testing/Limitations; update `docs/roadmap.md`.
- Note: `PoolStatus` includes `BROKEN` (deviation from MP02 list, deliberate); MTF context moved to Phase 6 with sessions.

## User preferences observed

- Wants fully autonomous continuation ("continue automatically until production-ready"); interrupted once to pause for the night — resume tomorrow by continuing Phase 4 without re-asking.
- GitHub push: offer only at milestones; requires explicit confirmation.
