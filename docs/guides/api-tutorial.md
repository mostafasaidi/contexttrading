# API tutorial: launch, authenticate, call, stream

The REST API exposes the full engine, chart payloads, the evidence-bound
AI analyst, and backtesting over HTTP. Every response is versioned JSON;
every error is the same `ErrorEnvelope`.

## 1. Launch

```bash
pip install "contexttrading[api]"       # fastapi + uvicorn

export CT_API__API_KEYS="dev-key"       # comma-separated for several keys
uvicorn contexttrading.api.app:create_app --factory --port 8000
```

Or with Docker (non-root, healthchecked, SQLite on a named volume):

```bash
docker compose -f docker/docker-compose.yml up api           # SQLite store
docker compose -f docker/docker-compose.yml --profile db up  # + postgres service
```

Interactive docs at `http://localhost:8000/docs`; the raw spec is
golden-tested (`tests/regression/goldens/openapi_v1.json`). Health:

```bash
curl localhost:8000/healthz    # always open
curl localhost:8000/readyz     # store ping + AI provider + auth state
```

## 2. Authenticate

Every `/v1/*` call needs the `X-API-Key` header (constant-time compare):

```bash
KEY=dev-key
curl -H "X-API-Key: $KEY" localhost:8000/v1/results/ES/15m/structure?series_hash=...
```

- Missing/bad key → 401 with `CT-7001` envelope.
- `CT_API__AUTH_ENABLED=false` disables auth entirely (local dev only).
- `CT_API__ALLOW_ANONYMOUS=true` lets *missing* keys pass; bad keys
  still 401.

## 3. Run an analysis

Bodies share one shape — a series wrapper plus optional overrides:

```json
{
  "series": {"symbol": "ES", "timeframe": "15m", "candles": [
    {"timestamp": "2024-01-01T09:30:00Z", "open": 100, "high": 101,
     "low": 99.5, "close": 100.5, "volume": 1200}
  ]},
  "config_overrides": {"atr_period": 21},
  "mtf_timeframes": ["1h", "4h"]
}
```

```bash
curl -X POST localhost:8000/v1/analysis/full \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d @candles.json

curl -X POST localhost:8000/v1/analysis/confluence \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d @candles.json
```

Module slugs: `structure`, `trend`, `liquidity`, `premium-discount`,
`fvg`, `orderblocks`, `supplydemand`, `sessions`, `confluence`, `mtf`
(note the dash in `premium-discount`). Unknown `config_overrides` keys
→ 422 CT-2000; over 20,000 candles → 413 CT-7002
(`CT_API__MAX_CANDLES_PER_REQUEST`).

## 4. Charts and persistence

```bash
curl -X POST "localhost:8000/v1/charts/payload?persist=true" \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d @candles.json
```

`persist=true` stores the payload in the result store (SQLite by
default; `CT_STORAGE__BACKEND=postgresql` + `CT_STORAGE__URL` for the
postgres backend). Retrieval needs the series hash:

```bash
curl -H "X-API-Key: $KEY" \
  "localhost:8000/v1/results/ES/15m/chart?series_hash=<sha256>"
```

The payload is what the bundled reference frontend renders — serve
`src/contexttrading/visualization/frontend/` over HTTP and load it.

## 5. AI endpoints

```bash
export CT_AI__PROVIDER=mock              # or openai/anthropic with keys set
curl -X POST localhost:8000/v1/ai/market-analysis \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d @candles.json
```

Also: `/v1/ai/trade-evaluation`, `/v1/ai/journal-review`,
`/v1/ai/weekly-review`. Provider not configured → 500 CT-4000; provider
failure → 502 (504 on timeout). See the
[AI analyst tutorial](ai-analyst-tutorial.md) for the citation contract.

## 6. Backtest

```bash
curl -X POST localhost:8000/v1/backtest \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{
    "series": {"symbol": "ES", "timeframe": "15m", "candles": [...]},
    "strategy": "smc_pullback",
    "strategy_params": {"min_confluence_score": 0.35},
    "backtest_overrides": {"recompute_interval": 4, "min_trades": 1}
  }'
```

Unknown strategy name → 422. Full semantics in the
[backtesting tutorial](backtesting-tutorial.md).

## 7. Stream the full stack

```bash
curl -N -X POST localhost:8000/v1/stream/analysis \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d @candles.json
```

NDJSON — one line per module in canonical order, then a terminal
`{"module": "done", ...}` line. Streamed results are identical to
`/v1/analysis/full` (tested). NDJSON over SSE deliberately: finite
responses any HTTP client can parse line by line.

## 8. Errors

One envelope everywhere — including 404s and 500s:

```json
{"schema_version": "1.0.0",
 "error": {"code": "CT-3001", "message": "Series too short for structure analysis",
           "context": {"candles": 12, "min_candles": 50}, "request_id": "..."}}
```

Every response echoes `X-Request-ID` (supply your own for tracing). The
full code table lives in [docs/api/README.md](../api/README.md); TLS and
rate limiting are reverse-proxy concerns.
