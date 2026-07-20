# API Reference (Outline)

> Filled in Phase 9 when the FastAPI service lands. Endpoints are planned,
> not implemented.

## Planned surface

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness/readiness |
| `/v1/schemas` | GET | List exported JSON schemas + versions |
| `/v1/analyze/{module}` | POST | Run one engine module on supplied OHLCV |
| `/v1/analyze/batch` | POST | Run several modules; returns envelopes |
| `/v1/narrative` | POST | AI explanation of an `AnalysisResult` payload |
| `/v1/backtest` | POST | Submit deterministic backtest (Phase 10) |

## Conventions

- All responses are `AnalysisResult[T]` envelopes or error envelopes
  (`{"error": {"code", "message", "context"}}` mirroring `core.errors`).
- Auth via API key header; rate limits per key.
- Versioned paths (`/v1`); schema versions live inside payloads.
