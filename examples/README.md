# Examples

Runnable, deterministic examples against the real engine. Each script uses
seeded synthetic data from `_data.py` (no network, no credentials) and prints
its key results, so the output doubles as documentation.

Run any example from this directory:

```bash
cd examples
PYTHONPATH="../src;.." python basic_analysis.py      # Windows Git Bash
PYTHONPATH="../src:.."  python basic_analysis.py     # POSIX
```

| Script | Demonstrates |
| --- | --- |
| `basic_analysis.py` | Loading a seeded `CandleSeries` and running individual modules (structure, liquidity, FVG). |
| `full_stack.py` | `run_full_stack` — all ten modules in canonical order plus the confluence bias. |
| `chart_payload.py` | Rendering engine results to chart layers/primitives; writes `output/chart_payload.json`. |
| `ai_analysis_mock.py` | The explain-only AI layer with a mock provider (payload in → structured report out, no API key). |
| `backtest_smc.py` | The reference SMC pullback strategy under deterministic event replay. |

Notes:

- Datasets are seeded (`regime_series(regime, count, seed)` with regimes
  `trend_up | range | volatile | low_liquidity`), so output is reproducible.
- `backtest_smc.py` uses `recompute_interval=4` to stay at a few seconds;
  the freshness trade-off is documented in `docs/modules/backtesting.md`.
- Generated files land in `output/` (gitignored).
- Smoke tests in `tests/integration/test_examples.py` run every example and
  assert its key output markers.
