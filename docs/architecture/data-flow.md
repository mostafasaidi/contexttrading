# Data Flow

## End-to-end pipeline

```text
OHLCV source (CSV / exchange API)
        │
        ▼
┌──────────────────┐   validation, dedupe, gap-check, UTC normalize
│   data adapters  │ ──────────────────────────────────────────────▶
└──────────────────┘
        │  CandleSeries (immutable, ordered, gap-aware, tz-aware)
        ▼
┌──────────────────────────────────────────────────────────────────┐
│                        Analysis engine                            │
│  structure ─┐                                                     │
│  liquidity  │                                                     │
│  fvg        ├── each: (CandleSeries, Config) ─▶ AnalysisResult[T] │
│  orderblocks│                                                     │
│  sessions ──┘                                                     │
│        │                                                          │
│        ▼                                                          │
│  confluence (cross-module, weighted, deterministic)               │
│  mtf (multi-timeframe alignment)                                  │
└──────────────────────────────────────────────────────────────────┘
        │  AnalysisResult[T] — versioned JSON, content-hash IDs
        ▼
   ┌────────────┬────────────────┬─────────────┐
   ▼            ▼                ▼             ▼
Visualization   AI layer      Backtesting     API
(Plotly / LWC   (explain-only (event replay)  (FastAPI
 style payloads) narrative)                    responses)
```

## The envelope

Every arrow out of the engine carries `AnalysisResult[T]`:

```json
{
  "schema_version": "1.0.0",
  "engine_version": "0.1.0",
  "module": "fvg",
  "symbol": "ES",
  "timeframe": "15m",
  "generated_from": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-02-01T00:00:00Z",
    "candle_count": 2976
  },
  "payload": { "...": "module-specific, typed, versioned" }
}
```

Consumers key off `module`, `schema_version`, and `engine_version`. Unknown
versions are rejected loudly, never guessed at.

## Where the AI sits

The AI layer is a *downstream consumer*, symmetric with visualization:

1. Engine emits `AnalysisResult` payloads.
2. AI adapter serializes selected payloads into a prompt (JSON in, JSON out
   via structured outputs / function calling).
3. The response is validated into `NarrativeResult` / `RiskAssessment`
   models — also `VersionedModel`s referencing the input IDs.
4. Validation failure ⇒ retry with schema reminder, then a typed
   `AIProviderError`. Never silently pass through free text.

## Storage (later phases)

Phase 8 adds a result store keyed by `(module, symbol, timeframe,
generated_from, engine_version)` — deterministic IDs make runs naturally
idempotent and cacheable.
