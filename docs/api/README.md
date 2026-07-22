# ContextTrading REST API

FastAPI service exposing the deterministic engine, chart payloads, and the
evidence-bound AI analyst over HTTP. App factory:
`contexttrading.api.app:create_app`.

## Running

```bash
uvicorn contexttrading.api.app:create_app --factory --host 0.0.0.0 --port 8000
# or
docker compose -f docker/docker-compose.yml up api
```

Interactive docs at `/docs` (Swagger UI) and `/redoc`; the raw spec at
`/openapi.json` is golden-tested (`tests/regression/goldens/openapi_v1.json`).

## Authentication

API-key auth via the `X-API-Key` header, constant-time compared against
`CT_API__API_KEYS` (comma-separated). Health endpoints are always open.

```bash
curl -H "X-API-Key: $KEY" ...
```

- `CT_API__AUTH_ENABLED=false` — auth off entirely (dev).
- `CT_API__ALLOW_ANONYMOUS=true` — auth on but missing keys pass (bad keys
  still 401).

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/healthz` | GET | Liveness (always open) |
| `/readyz` | GET | Readiness: store ping, AI provider, auth state |
| `/v1/analysis/full` | POST | All 10 engine modules in canonical order |
| `/v1/analysis/{module}` | POST | One module (`structure`, `trend`, `liquidity`, `premium-discount`, `fvg`, `orderblocks`, `supplydemand`, `sessions`, `confluence`, `mtf`) |
| `/v1/charts/payload` | POST | Full stack -> renderer-ready `ChartPayload`; `persist=true` stores it |
| `/v1/results/{symbol}/{timeframe}/{module}?series_hash=` | GET | Fetch a persisted result (404 envelope when absent) |
| `/v1/ai/market-analysis` | POST | Bias/narrative report from posted candles |
| `/v1/ai/trade-evaluation` | POST | Evaluate a proposed setup against engine evidence |
| `/v1/ai/journal-review` | POST | Review posted journal trades |
| `/v1/ai/weekly-review` | POST | Review posted performance statistics |
| `/v1/stream/analysis` | POST | NDJSON stream: one line per module + a `done` line |
| `/v1/backtest` | POST | Deterministic no-lookahead backtest (`smc_pullback` registry) |

Request bodies share the same shape: `{"series": {"symbol", "timeframe",
"candles": [...]}}` plus optional `config_overrides` (merged onto the
server `EngineConfig`; unknown keys -> 422 CT-2000) and
`mtf_timeframes` on analysis endpoints. Candle cap:
`CT_API__MAX_CANDLES_PER_REQUEST` (default 20000) -> 413 CT-7002.

## Error envelope

Every failure — including 404s and unexpected 500s — returns the same
versioned envelope:

```json
{
  "schema_version": "1.0.0",
  "error": {
    "code": "CT-7001",
    "message": "Missing or invalid API key",
    "context": {},
    "request_id": "..."
  }
}
```

| HTTP | Codes | Meaning |
|---|---|---|
| 400 | CT-1xxx | Malformed candle data, unknown module |
| 401 | CT-7001 | Missing/invalid API key |
| 404 | CT-7003 | Stored result not found |
| 413 | CT-7002 | Candle count over the cap |
| 422 | CT-2xxx, CT-3001 | Schema validation; not enough candles |
| 500 | CT-4xxx, CT-3xxx, CT-0000 | Configuration, engine, unexpected |
| 502/504 | CT-5xxx | AI provider failure / timeout |

Every response echoes `X-Request-ID` (supply your own for tracing).

## Streaming protocol

`POST /v1/stream/analysis` returns `application/x-ndjson`: one JSON object
per line, modules in canonical order, then a terminal line:

```
{"module": "structure", "result": {...}}
...
{"module": "mtf", "result": {...}}
{"module": "done", "modules": [...], "candle_count": 2000}
```

NDJSON (not SSE) was chosen for simple programmatic consumption with any
HTTP client. Errors before streaming starts return the standard envelope.

## Examples

```bash
# Full stack
curl -X POST localhost:8000/v1/analysis/full \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d @candles.json

# Chart payload, persisted
curl -X POST localhost:8000/v1/charts/payload \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"series": ..., "persist": true, "theme": "dark"}'

# Stream
curl -N -X POST localhost:8000/v1/stream/analysis \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d @candles.json
```

## Configuration

All settings via `CT_` env vars (nested with `__`):
`CT_API__AUTH_ENABLED`, `CT_API__API_KEYS`, `CT_API__CORS_ORIGINS`,
`CT_API__MAX_CANDLES_PER_REQUEST`, `CT_STORAGE__BACKEND` (`sqlite`
default / `postgresql` — needs the `postgres` extra),
`CT_STORAGE__URL` (SQLite path or postgres DSN),
`CT_AI__PROVIDER` (`mock` / `openai` / `anthropic` / `none`).

Rate limiting and TLS are deployment concerns — put the service behind a
reverse proxy (nginx, Caddy, Traefik) for both.
