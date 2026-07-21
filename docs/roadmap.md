# Roadmap — 13 Phases

| Phase | Name | Deliverables | Status |
|---|---|---|---|
| 1 | Repository & documentation foundation | Packaging, CI, docs skeleton, architecture docs | ✅ Done |
| 2 | Core foundation | Config, logging, errors, IDs, versioning, constants, candle models, output envelopes, schema export | ✅ Done |
| 3 | Market structure engine + liquidity + premium/discount | Swings, legs, BOS/CHoCH state machine, TrendEngine, equal levels/pools/sweeps, dealing range/OTE, ATR/volume primitives, goldens | ✅ Done |
| 4 | FVG engine | Fair value gaps, imbalance, inversion FVG (liquidity landed in Phase 3) | ✅ Done |
| 5 | Order blocks & supply/demand | OB detection, breaker blocks, mitigation status, zone strength | ✅ Done |
| 6 | Sessions & MTF | Killzones, session high/low, Judas swings, deterministic resampling, multi-timeframe trend alignment (premium/discount landed in Phase 3) | ✅ Done |
| 7 | Confluence engine | Weighted deterministic scoring, explainable factor breakdown, confluence zones | ✅ Done |
| 8 | Visualization & storage | Lightweight-Charts chart payloads + reference frontend, SQLite result store (Plotly renderer dropped — payload is renderer-agnostic; PostgreSQL/Redis deferred to Phase 12) | ✅ Done |
| 9 | AI analyst layer | Versioned prompts, deterministic context builder, provider abstraction, citation enforcement, evidence-bound structured reports | ✅ Done |
| 10 | API service | FastAPI service, analyze/AI endpoints, schema endpoints, `docs/api/` | ⬜ Next |
| 11 | Backtesting | Event-driven replay, fills/costs, equity + reports, seeded determinism | ⬜ |
| 12 | Examples, polish, performance | `examples/`, benchmarks, docs completion, DX polish, PostgreSQL/Redis store adapters | ⬜ |
| 13 | Release hardening | Packaging to PyPI, Docker images, security review, v1.0 schema freeze | ⬜ |

## Principles governing the roadmap

- **Engine before consumers.** No visualization/AI/API work starts before
  the engine modules it renders/explains/serves exist and are regression-tested.
- **Golden files from Phase 3 onward.** Every engine module lands with
  regression fixtures; output changes require version bumps.
- **Schemas are a public API.** From Phase 2 on, `docs/schemas/json/` is a
  supported artifact; breaking changes follow semver.
