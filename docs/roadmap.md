# Roadmap — 12 Phases

| Phase | Name | Deliverables | Status |
|---|---|---|---|
| 1 | Repository & documentation foundation | Packaging, CI, docs skeleton, architecture docs | ✅ Done |
| 2 | Core foundation | Config, logging, errors, IDs, versioning, constants, candle models, output envelopes, schema export | ✅ Done |
| 3 | Market structure engine + liquidity + premium/discount | Swings, legs, BOS/CHoCH state machine, TrendEngine, equal levels/pools/sweeps, dealing range/OTE, ATR/volume primitives, goldens | ✅ Done |
| 4 | FVG engine | Fair value gaps, imbalance, inversion FVG (liquidity landed in Phase 3) | ✅ Done |
| 5 | Order blocks & supply/demand | OB detection, breaker blocks, mitigation status, zone strength | ✅ Done |
| 6 | Sessions & MTF | Killzones, session high/low, multi-timeframe trend alignment (premium/discount landed in Phase 3) | ⬜ Next |
| 7 | Confluence engine | Weighted deterministic scoring, signal composition (trading logic) | ⬜ |
| 8 | Visualization & storage | Plotly renderer, Lightweight-Charts payloads, SQLite/PostgreSQL/Redis result store | ⬜ |
| 9 | AI layer & API | Provider adapters, structured narrative/risk outputs, FastAPI service, schema endpoints, `docs/api/` | ⬜ |
| 10 | Backtesting | Event-driven replay, fills/costs, equity + reports, seeded determinism | ⬜ |
| 11 | Examples, polish, performance | `examples/`, benchmarks, docs completion, DX polish | ⬜ |
| 12 | Release hardening | Packaging to PyPI, Docker images, security review, v1.0 schema freeze | ⬜ |

## Principles governing the roadmap

- **Engine before consumers.** No visualization/AI/API work starts before
  the engine modules it renders/explains/serves exist and are regression-tested.
- **Golden files from Phase 3 onward.** Every engine module lands with
  regression fixtures; output changes require version bumps.
- **Schemas are a public API.** From Phase 2 on, `docs/schemas/json/` is a
  supported artifact; breaking changes follow semver.
