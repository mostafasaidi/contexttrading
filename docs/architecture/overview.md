# Architecture Overview

ContextTrading is a layered system with one invariant:

> **The Python engine calculates every market-structure component. The AI
> layer calculates nothing — it explains structured, versioned engine output.**

## The 9 layers

| # | Layer | Package | Responsibility |
|---|-------|---------|----------------|
| 1 | Data | `contexttrading.data` | Ingest, validate, store, and serve OHLCV. Gap detection, timezone normalization, provider adapters. |
| 2 | Analysis | `contexttrading.analysis` | Deterministic SMC engine: structure, liquidity, FVG, order blocks, supply/demand, premium/discount, sessions, confluence, MTF. |
| 3 | Trading Logic | (confluence + signal composition inside `analysis`/`backtesting`) | Combines engine outputs into deterministic signal/state objects. No discretion, no AI. |
| 4 | Visualization | `contexttrading.visualization` | Renders engine outputs (zones, breaks, swings) to Plotly figures and Lightweight-Charts-ready style payloads. |
| 5 | AI | `contexttrading.ai` | Explain-only layer. Consumes `AnalysisResult` JSON; emits structured narrative/risk JSON. Never computes market values. |
| 6 | Backtesting | `contexttrading.backtesting` | Event-driven replay of engine outputs with deterministic fills and cost models. |
| 7 | API | `contexttrading.api` | FastAPI surface exposing engine runs, schemas, and (later) streaming. Thin: no business logic. |
| 8 | Testing | `tests/` | Unit, integration, regression (golden-file), and performance suites guarding determinism. |
| 9 | Documentation | `docs/` | Architecture, module references, guides, exported JSON schemas. |

## Cross-cutting core

`contexttrading.core` and `contexttrading.models` sit beneath every layer:

- **core** — configuration, logging, error taxonomy, deterministic ID
  generation, schema versioning, shared constants/enums.
- **models** — Pydantic v2 domain models (`Candle`, `CandleSeries`,
  `VisualStyle`, `AnalysisResult[T]`) and the `VersionedModel` contract.

Every layer may depend on `core` and `models`. No other upward or lateral
dependencies are allowed except as listed below.

## Dependency rules

Allowed dependency direction (a layer may import anything below it in this
list, never above):

```text
API ──▶ Visualization / AI / Backtesting ──▶ Analysis ──▶ Data ──▶ Models ──▶ Core
```

Hard rules enforced by convention and review (import-linter wiring planned):

1. **AI depends on models and engine *outputs* only.** It must not import
   from `contexttrading.analysis` internals; it receives `AnalysisResult`
   payloads. This keeps the engine swappable and the AI honest.
2. **Analysis never imports visualization, AI, backtesting, or API.** The
   engine is pure compute: data in, versioned JSON out.
3. **Visualization renders outputs; it does not recompute them.** If a value
   is needed on a chart, the engine must emit it.
4. **API is a thin adapter.** Request parsing, auth, and serialization only.
5. **Models are dependency-free** except for `core` constants/versioning and
   Pydantic itself.

## Module output contract

Every analysis module returns `AnalysisResult[T]` (see
`contexttrading.models.outputs`):

- `schema_version` — version of the payload schema (`VersionedModel`).
- `engine_version` — version of the engine that produced it.
- `symbol`, `timeframe`, `generated_from` — the exact input data window.
- `payload` — the module-specific, typed result.

No module returns free text. No module returns raw dicts. If it isn't typed
and versioned, it doesn't ship.

## Why this shape

- **Reproducibility** — golden-file regression tests can assert byte-level
  equality of engine output for a fixed dataset and engine version.
- **Auditability** — every number an AI or chart shows traces back to an
  engine artifact with a content-hash ID.
- **Replaceability** — swap data providers, renderers, or AI providers behind
  stable interfaces without touching the engine.
