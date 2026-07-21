# api (REST service)

FastAPI surface for the engine, chart payloads, and the AI analyst. Pure
transport layer: it orchestrates existing modules, detects nothing itself,
and keeps the determinism contract — identical request body, identical
response body.

## Invariants

1. **No analysis logic in the API layer.** Routes call
   `analysis.pipeline.run_module` / `run_full_stack`,
   `visualization.build_chart_payload`, and `InstitutionalAnalyst` — the
   same entrypoints tests use. HTTP == in-process, byte for byte
   (integration-tested on 2,000 candles).
2. **Every error is an envelope.** `ErrorEnvelope{error: {code, message,
   context, request_id}}` for all failures, including 404/422/500; no
   FastAPI default error bodies leak.
3. **Versioned wire models only.** Request/response models live in
   `api/models.py` (`SCHEMA_VERSION_API = "1.0.0"`), registered in
   `core/versioning.py`, exported by `schemas.export`. No ad-hoc dicts.
4. **Orchestration has one source.** `MODULE_ORDER` in
   `analysis/pipeline.py` defines module order for `/analysis/full`, the
   NDJSON stream, and test fixtures.

## Responsibilities

| Module | Responsibility |
|---|---|
| `api/app.py` | `create_app(settings)` factory: lifespan (ResultStore, analyst), request-id middleware, exception handlers, health routes, router wiring, OpenAPI metadata. |
| `api/auth.py` | `require_api_key` dependency — `X-API-Key` header, `hmac.compare_digest`, honors `auth_enabled` / `allow_anonymous`. |
| `api/deps.py` | DI helpers: settings access, candle-cap enforcement, `EngineConfig` merge for `config_overrides`, analyst lookup. |
| `api/models.py` | Wire models: `CandlesInput`, `AnalysisRequest`, `ChartRequest/Response`, AI request models, `StoredResultResponse`, `ErrorEnvelope`. |
| `api/routes/analysis.py` | `POST /v1/analysis/full`, `POST /v1/analysis/{module}` (full registered first so "full" never matches `{module}`). |
| `api/routes/charts.py` | `POST /v1/charts/payload` — full stack + chart payload, optional persist. |
| `api/routes/results.py` | `GET /v1/results/{symbol}/{timeframe}/{module}?series_hash=` from the ResultStore. |
| `api/routes/ai.py` | Four AI analyst endpoints (market analysis, trade evaluation, journal review, weekly review). |
| `api/routes/stream.py` | `POST /v1/stream/analysis` — NDJSON, one line per module + `done`. |
| `analysis/pipeline.py` | Shared orchestration (`MODULE_ORDER`, `MODULE_SLUGS`, `run_module`, `run_full_stack`) used by routes AND test fixtures. |

## Error mapping

`ContextTradingError` subclasses map to HTTP status in `app._status_for`:

| Exception | Code | HTTP |
|---|---|---|
| `AuthenticationError` | CT-7001 | 401 |
| `NotFoundError` | CT-7003 | 404 |
| `RequestTooLargeError` | CT-7002 | 413 |
| `InsufficientDataError` | CT-3001 | 422 |
| `DataError` | CT-1xxx | 400 |
| `ValidationError` (core + FastAPI request validation) | CT-2xxx | 422 |
| `ConfigurationError` | CT-4xxx | 500 |
| `AIProviderError` | CT-5xxx | 502 (504 when the message says "timeout") |
| other `AnalysisError` | CT-3xxx | 500 |
| anything else | CT-0000 | 500 |

Deviation note: `InsufficientDataError` is CT-3xxx but returns 422, not
500 — too-few-candles is a client-supplied data problem, not a server
fault. Documented in `app.py`.

## Streaming

NDJSON (`application/x-ndjson`), chosen over SSE because programmatic
clients parse line-delimited JSON with any HTTP library; no event
framing, no reconnect semantics needed for a finite response. Line order
is exactly `MODULE_ORDER` followed by
`{"module": "done", "modules": [...], "candle_count": N}`. Streamed
per-module results equal `/v1/analysis/full` results (tested).

## Configuration

`APIConfig` (env prefix `CT_API__`): `auth_enabled` (true),
`allow_anonymous` (false), `api_keys` (comma-separated string or JSON
array), `cors_origins`, `max_candles_per_request` (20000). The store path
comes from `CT_STORAGE__URL` (`sqlite:///...`); the analyst is built when
`CT_AI__PROVIDER != "none"`.

## Determinism

- Same request body -> same response bytes (integration-tested).
- `run_full_stack` results depend only on the series + EngineConfig.
- `X-Request-ID` echoes the client's header or a fresh UUID; it appears
  in every error envelope.

## Limitations

- No rate limiting or byte-size body cap (candle-count cap only) — put a
  reverse proxy in front for both.
- SQLite ResultStore is single-writer; fine for the compose deployment,
  swap for Postgres (Phase 12) for multi-replica setups.
- `/v1/results/...` serves only what was persisted via
  `charts/payload?persist=true`; analysis endpoints do not persist.
- Streaming sends the terminal `done` line only on success; mid-stream
  engine failures abort the connection (envelope errors are only possible
  before the first line).

## Testing

`tests/unit/api/` (TestClient, MockProvider, no network): auth matrix,
module smoke (parametrized), error-envelope shape per failure class,
persist round-trip, stream-vs-full equality, OpenAPI contract.
`tests/regression/goldens/openapi_v1.json`: spec snapshot (regenerate
with `CT_UPDATE_GOLDENS=1` + version bump).
`tests/integration/test_phase9_api.py`: 2,000-candle parity — HTTP ==
direct `run_full_stack`, stream == direct, chart persist round-trip.
