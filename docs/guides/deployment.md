# Deployment Guide — ContextTrading Server

Target: production server with domain **n8meme.eu**.

## 1. Server requirements

- Linux (Ubuntu 22.04+ recommended), Docker + Docker Compose plugin
- A DNS A record for `n8meme.eu` (and optionally `api.n8meme.eu`) pointing at the server
- Open ports 80/443 for the reverse proxy

## 2. Clone & configure

```bash
git clone https://github.com/mostafasaidi/ContextTrading.git
cd ContextTrading
cp .env.example .env   # if present, otherwise create per below
```

Minimum environment for the API service:

```bash
CT_API__AUTH_ENABLED=true
CT_API__API_KEYS=<generate-a-long-random-key>
CT_STORAGE__BACKEND=sqlite            # or postgres with the db compose profile
CT_AI__PROVIDER=openai                # or anthropic / mock
CT_AI__MODEL=gpt-4o-mini              # example
# API keys are read from env names configured in AIConfig (never hard-coded):
OPENAI_API_KEY=<your-key>
```

## 3. Run with Docker

```bash
docker compose -f docker/docker-compose.yml up -d api          # API only (SQLite volume)
docker compose -f docker/docker-compose.yml --profile db up -d # + PostgreSQL
```

The API listens on port 8000 inside the compose network and exposes `/healthz`.

## 4. Reverse proxy (Caddy — automatic HTTPS)

Caddy is the simplest option for the domain (automatic Let's Encrypt certificates):

```
# Caddyfile
n8meme.eu {
    reverse_proxy 127.0.0.1:8000
}
```

Subdomain split is also common once a web UI exists:

```
n8meme.eu       { reverse_proxy 127.0.0.1:3000 }   # web UI
api.n8meme.eu   { reverse_proxy 127.0.0.1:8000 }   # FastAPI
```

nginx works equally well; terminate TLS there and proxy_pass to the services.

## 5. Notes for the agent continuing this build on the server

- The repository is the single source of truth: read `README.md`, `docs/architecture/overview.md`, and `docs/roadmap.md` first.
- The web UI does not exist yet. Planned location: `web/` (React + TypeScript + Vite + Tailwind + shadcn/ui, dark institutional design). It must consume the FastAPI backend only — **no trading logic in JavaScript**.
- Key backend contracts for UI work: `POST /v1/analysis/full`, `POST /v1/analysis/{module}`, `POST /v1/charts/payload`, `POST /v1/stream/analysis` (NDJSON), `POST /v1/ai/*`, `POST /v1/backtest`. See `docs/api/README.md` and the OpenAPI snapshot golden.
- Determinism is the core invariant: never recompute market structure in the UI; render only what the engine returns. Every AI claim carries `evidence_ids` that map to engine objects — the UI should highlight cited objects on the chart.
- Verify before/after any change: `python -m pytest tests/ -q`, `python -m ruff check .`, `python -m black --check .` — all must stay green. See `docs/guides/developer-guide.md`.
- Schema versioning policy: `docs/architecture/versioning-policy.md`. Never silently change a frozen schema.
