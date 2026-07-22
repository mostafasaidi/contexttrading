# ContextTrading

> Deterministic Smart Money Concepts (SMC) analysis engine — **Python calculates, AI explains.**

<!-- Badges (enabled once the repo is public) -->
<!-- ![CI](https://github.com/contexttrading/contexttrading/actions/workflows/ci.yml/badge.svg) -->
<!-- [![PyPI](https://img.shields.io/pypi/v/contexttrading)](https://pypi.org/project/contexttrading/) -->
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## The philosophy: deterministic first

Most "AI trading" tools let a language model eyeball a chart and hallucinate
structure. ContextTrading inverts that relationship:

- **The Python engine calculates everything.** Swing points, BOS/CHoCH, fair
  value gaps, order blocks, liquidity pools, session windows, trend state,
  premium/discount zones, confluence scores — all computed deterministically
  from OHLCV data.
- **The AI layer calculates nothing.** It receives structured, versioned JSON
  from the engine and produces explanation, narrative, and risk commentary —
  also as structured JSON. It never sees raw price series, and it can never
  invent a number the engine did not produce.
- **Everything is reproducible.** Identical input data + identical engine
  version ⇒ byte-identical output. No wall-clock timestamps, no hidden
  randomness, deterministic content-hash IDs.

This makes the system auditable, testable, backtestable, and safe to put an
LLM in front of.

## Features

| Area | Status | Highlights |
| --- | --- | --- |
| Core foundation | ✅ Phase 2 | Strict typed config, structured logging, error taxonomy, deterministic IDs, schema versioning |
| Data models | ✅ Phase 2 | Validated `Candle`, immutable `CandleSeries`, versioned output envelopes |
| Market structure | ✅ Phase 3 | Swings, legs, BOS/CHoCH (internal/external, major/minor, strong/weak/false), protected levels, TrendEngine |
| Liquidity | ✅ Phase 3 | Equal highs/lows, pools, sweep/grab/stop-hunt with monotonic pool status |
| FVG | ✅ Phase 4 | 3-candle imbalance, nested/stacked, inverse FVG, mitigation lifecycle, strength ranking |
| Order blocks | ✅ Phase 5 | Displacement-anchored OBs, breaker blocks, mitigation blocks, refinement |
| Supply/demand | ✅ Phase 5 | RBD/DBR zones, OB-derived zones, dedupe, deterministic strength |
| Premium/discount | ✅ Phase 3 | Dealing range, equilibrium, OTE zone, price location |
| Sessions | ✅ Phase 6 | Configurable windows + killzones, session high/low/PDH/PDL pools, Judas swings, day-extreme stats |
| MTF context | ✅ Phase 6 | Deterministic resampling (epoch/Monday/month anchors), weighted multi-timeframe bias |
| Confluence | ✅ Phase 7 | Explainable weighted scores, directional bias, spatial confluence zones |
| Visualization | ✅ Phase 8 | Lightweight-Charts payloads, 23-layer serializer, reference frontend, result store (SQLite + PostgreSQL) |
| AI narrative | ✅ Phase 9 | Evidence-bound structured analyst reports, citation enforcement, mock + HTTP providers |
| REST API | ✅ Phase 10 | FastAPI service, key auth, versioned error envelopes, NDJSON streaming, golden-tested OpenAPI |
| Backtesting | ✅ Phase 11 | No-lookahead event replay, costs/fills, statistics, grid + walk-forward optimization |
| Examples & performance | ✅ Phase 12 | Runnable example suite, timing tripwires, confluence payload-sharing (−51% full stack), edge-case matrix |

**v1.0.0 — all 13 roadmap phases complete.** 885 tests + 14 performance
benchmarks green; schemas frozen at 1.0.0
([versioning policy](docs/architecture/versioning-policy.md)).

## Architecture

```text
            ┌────────────────────────────────────────────────────┐
            │                     API (FastAPI)                   │
            └──────────────▲──────────────────────▲──────────────┘
                           │                      │
                 ┌─────────┴─────────┐   ┌────────┴────────┐
                 │  Visualization    │   │   AI (explain-  │
                 │  (Plotly/LWC)     │   │   only layer)   │
                 └─────────▲─────────┘   └────────▲────────┘
                           │                      │
            ┌──────────────┴──────────────────────┴─────────────┐
            │        AnalysisResult[T] — versioned JSON          │
            └──────────────▲──────────────────────▲─────────────┘
                           │                      │
                 ┌─────────┴─────────┐   ┌────────┴────────┐
                 │  Analysis engine  │   │   Backtesting   │
                 │  (SMC modules)    │   │   (event-driven)│
                 └─────────▲─────────┘   └────────▲────────┘
                           │                      │
            ┌──────────────┴──────────────────────┴─────────────┐
            │   Models (Candle, CandleSeries, envelopes, IDs)    │
            ├───────────────────────────────────────────────────┤
            │   Data (ingestion, validation, storage)            │
            └───────────────────────────────────────────────────┘
```

Dependency rule: layers point **downward only**. The AI layer depends on
`models` and engine *outputs* — never on engine internals.

## Quickstart

```bash
git clone https://github.com/contexttrading/contexttrading.git
cd contexttrading
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

```python
from contexttrading.core.constants import Timeframe
from contexttrading.models.candle import Candle, CandleSeries

candles = CandleSeries.from_records(
    [
        {"timestamp": "2024-01-01T09:30:00Z", "open": 100, "high": 101, "low": 99.5, "close": 100.5, "volume": 1200},
        {"timestamp": "2024-01-01T09:31:00Z", "open": 100.5, "high": 102, "low": 100.2, "close": 101.8, "volume": 980},
    ],
    timeframe=Timeframe.M1,
    symbol="ES",
)
print(candles.timeframe, len(candles))
```

Export the JSON schemas every module speaks:

```bash
python -m contexttrading.schemas.export        # writes docs/schemas/json/*.json
```

Run the REST API (engine + AI analyst over HTTP, API-key auth):

```bash
export CT_API__API_KEYS=dev-key
uvicorn contexttrading.api.app:create_app --factory --port 8000
curl -X POST localhost:8000/v1/analysis/full \
  -H "X-API-Key: dev-key" -H "Content-Type: application/json" -d @candles.json
```

See [docs/api/README.md](docs/api/README.md) for endpoints, the error
envelope, streaming, and Docker Compose.

## Examples

Runnable, deterministic scripts on seeded data (no network, no
credentials) live in [examples/](examples/README.md): basic module
analysis, the full-stack pipeline, chart-payload export, the mock-provider
AI narrative, and an SMC pullback backtest. Each doubles as documentation
and is smoke-tested in `tests/integration/test_examples.py`.

```bash
cd examples && PYTHONPATH="../src;.." python full_stack.py   # Windows Git Bash
```

Performance tripwires (plain timing, no extra deps) live in
`tests/performance/` — run with `pytest -m benchmark`.

## Backtesting

Deterministic, no-lookahead backtesting over any CandleSeries. Strategies
decide at bar close on engine output only; fills happen on the next bar
with configurable spread/slippage/commission:

```python
from contexttrading.backtesting import SMCPullbackStrategy, run_backtest
from contexttrading.core.config import BacktestConfig

result = run_backtest(series, SMCPullbackStrategy(), backtest_config=BacktestConfig())
print(result.statistics.net_pnl, result.statistics.sharpe)
for trade in result.trades:
    print(trade.exit_reason, trade.r_multiple, trade.evidence_ids)
```

Grid search and anchored walk-forward optimization live in
`backtesting.optimize`; the reference SMC pullback strategy demonstrates
evidence-bound entries (every trade links to the engine objects behind
it). HTTP: `POST /v1/backtest`. Full contract:
[docs/modules/backtesting.md](docs/modules/backtesting.md).

## Documentation

Tutorials (start here):

- [Quickstart](docs/guides/quickstart.md) — install to first analysis in 5 minutes
- [Engine tutorial](docs/guides/engine-tutorial.md) — every module and its output
- [AI analyst tutorial](docs/guides/ai-analyst-tutorial.md) — evidence-bound reports
- [Backtesting tutorial](docs/guides/backtesting-tutorial.md) — run + optimize the SMC strategy
- [API tutorial](docs/guides/api-tutorial.md) — launch, auth, call, stream

Reference:

- [Architecture overview](docs/architecture/overview.md) — the 9 layers and their boundaries
- [Determinism contract](docs/architecture/determinism.md) — reproducibility rules every module obeys
- [Versioning policy](docs/architecture/versioning-policy.md) — schema freeze, bump rules, golden protocol
- [Module contracts](docs/modules/) — one doc per engine module
- [REST API reference](docs/api/README.md) — endpoints, error codes, streaming
- [Security guide](docs/guides/security.md) — trust boundaries, secrets, deployment checklist
- [Roadmap](docs/roadmap.md) — the 13-phase build plan (complete)
- [Developer guide](docs/guides/developer-guide.md) — setup, style, testing, commits

## Contributing

See the [developer guide](docs/guides/developer-guide.md). Conventional
commits, `ruff` + `black`, 100% typed public APIs, and tests for every module
are required. PRs welcome.

## License

[MIT](LICENSE) © ContextTrading Contributors
