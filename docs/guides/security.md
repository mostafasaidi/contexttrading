# Security Guide

ContextTrading's security posture in one page: what the trust boundaries
are, how secrets are handled, and how to audit dependencies.

## Trust boundaries

| Boundary | Handling |
| --- | --- |
| Candle / request input | All external input is validated by pydantic models (`Candle`, `CandleSeries`, API wire models). Invalid data raises typed errors (`ValidationError` CT-2000 → 422), never partial state. |
| API authentication | `X-API-Key` header compared with `hmac.compare_digest` (constant-time). Keys come ONLY from `CT_API__API_KEYS` (comma-separated or JSON array). `auth_enabled=False` is a deliberate local-dev switch — never set it in a shared deployment. |
| AI provider keys | Read exclusively from the environment variable named by `AIConfig.api_key_env` (default per provider). Keys are never logged, never serialized into reports, and never sent anywhere but the configured provider endpoint. |
| Result store | SQLite/PostgreSQL payloads are validated against the current schema version on load (`SchemaVersionError` on mismatch); a tampered or stale row fails closed instead of being misinterpreted. |
| Error responses | Every error is an `ErrorEnvelope` (code/message/context/request-id). Stack traces and internals never leak to clients. |

## Hard-coded secret policy

There are **no hard-coded secrets** in the repository. The only literal
credentials are documented local-development defaults, both overridable
by environment variables:

- `docker-compose.yml`: `CT_API__API_KEYS:-dev-key` (API) and
  `contexttrading:contexttrading` (postgres service, local `db` profile).

A grep audit (`api_key|secret|password|token` assignments) is part of
every release review.

## Dependency auditing

Runtime dependencies are intentionally few (core: pydantic,
pydantic-settings, PyYAML; extras: fastapi/uvicorn, httpx, psycopg).
Audit them in CI with [pip-audit](https://pypi.org/project/pip-audit/):

```bash
pip install pip-audit
pip-audit --desc
```

The CI workflow runs pip-audit as a **non-blocking** job
(`continue-on-error`) so advisories surface without red-flagging
unrelated work; release sign-off requires a clean or explicitly waived
report. To audit exactly what ships:

```bash
pip-audit --requirement <(python -m pip show contexttrading | ...)
# or, inside the release venv:
pip-audit --local
```

## Deployment checklist

- [ ] Real API keys via `CT_API__API_KEYS` (not the compose default).
- [ ] `auth_enabled` left at its default `True`.
- [ ] HTTPS terminated at a reverse proxy; rate limiting is a proxy
      concern (documented in `docs/modules/api.md`).
- [ ] Container runs as the non-root `app` user (default in
      `docker/Dockerfile`).
- [ ] PostgreSQL backend (`CT_STORAGE__BACKEND=postgresql`) for any
      multi-instance deployment; SQLite is single-writer.
- [ ] pip-audit report reviewed for the release dependency set.
