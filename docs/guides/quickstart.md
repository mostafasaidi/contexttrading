# Quickstart: install to first analysis in 5 minutes

This gets you from a clean checkout to a full ten-module Smart Money
Concepts analysis with real, runnable commands. No data feeds, no API
keys, no network after install — everything runs on bundled seeded data.

## 1. Install

```bash
git clone https://github.com/contexttrading/contexttrading.git
cd contexttrading
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q -m "not benchmark"                          # optional: prove the install (~3 min)
```

Core engine dependencies are just pydantic, pydantic-settings, and
PyYAML. The REST API (`api`), HTTP AI providers (`ai`), and the
PostgreSQL store (`postgres`) are extras — see
[the packaging metadata](../../pyproject.toml).

## 2. Your first analysis (60 seconds)

Run the full-stack example — all ten modules over a seeded 300-bar
series, exactly what a first integration would do:

```bash
cd examples
PYTHONPATH="../src;.." python full_stack.py      # Windows Git Bash
PYTHONPATH="../src:.."  python full_stack.py     # POSIX
```

Expected output (deterministic — the data is seeded):

```
full stack over 300 bars (EXAMPLE 15m)
  structure         MarketStructureResult
  ...
bias: bullish (bull 0.355 / bear 0.273)
```

## 3. The same thing in your own code

```python
from contexttrading.analysis.pipeline import run_full_stack
from contexttrading.models.candle import CandleSeries

series = CandleSeries.from_records(
    [
        {"timestamp": "2024-01-01T09:30:00+00:00", "open": 100, "high": 101,
         "low": 99.5, "close": 100.5, "volume": 1200},
        # ... at least 50 candles (config.min_candles) for structure analysis
    ],
    symbol="ES",
    timeframe="15m",
)

results = run_full_stack(series)          # dict[str, AnalysisResult], 10 modules
print(results["confluence"].payload.bias)          # TrendDirection.BULLISH / ...
print(results["structure"].payload.breaks[-1])     # latest BOS/CHoCH
```

Three rules that make every result trustworthy:

1. **Deterministic** — identical input, identical output (byte-exact;
   proven by 26 regression goldens).
2. **Versioned** — every envelope carries `schema_version` (contract)
   and `engine_version` (computation). Check both before interpreting.
3. **Typed errors** — too little data raises `InsufficientDataError`
   (CT-3001), invalid data `ValidationError` (CT-2000). No silent
   fallbacks, no NaN leaks.

## 4. Where to go next

| Goal | Guide |
| --- | --- |
| Understand each module's output | [Engine tutorial](engine-tutorial.md) |
| Chart the results | `examples/chart_payload.py` → [visualization docs](../modules/visualization.md) |
| AI narrative over the engine JSON | [AI analyst tutorial](ai-analyst-tutorial.md) |
| Backtest a strategy | [Backtesting tutorial](backtesting-tutorial.md) |
| Serve it over HTTP | [API tutorial](api-tutorial.md) |

All five `examples/` scripts are smoke-tested
(`tests/integration/test_examples.py`), so what you read is what runs.
