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
| Confluence | 🔜 Phase 7 | Weighted, deterministic confluence scoring |
| Visualization | 🔜 Phase 8 | Plotly + TradingView Lightweight Charts styles |
| AI narrative | 🔜 Phase 9 | Explain-only AI layer over versioned JSON |
| Backtesting & API | 🔜 Phases 10–11 | Event-driven backtester, FastAPI service |

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

## Documentation

- [Architecture overview](docs/architecture/overview.md) — the 9 layers and their boundaries
- [Determinism contract](docs/architecture/determinism.md) — reproducibility rules every module obeys
- [Data flow](docs/architecture/data-flow.md) — OHLCV in, versioned JSON out
- [Layer details](docs/architecture/layers.md) — responsibilities and dependency rules
- [Roadmap](docs/roadmap.md) — the 12-phase build plan
- [Developer guide](docs/guides/developer-guide.md) — setup, style, testing, commits

## Contributing

See the [developer guide](docs/guides/developer-guide.md). Conventional
commits, `ruff` + `black`, 100% typed public APIs, and tests for every module
are required. PRs welcome.

## License

[MIT](LICENSE) © ContextTrading Contributors
