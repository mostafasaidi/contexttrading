# Engine tutorial: every module, and how to read its output

The engine is ten pure modules behind one contract:

```python
AnalysisResult[T] = analyze_<module>(series: CandleSeries, config: EngineConfig)  # per module
```

No wall-clock, no I/O, no hidden state — the same candles always produce
the same bytes. This tutorial runs each one and explains what to look
at. Everything below works against the seeded example data:

```bash
cd examples
PYTHONPATH="../src;.." python basic_analysis.py    # structure + liquidity + fvg
```

Or in Python, using the example data helper:

```python
from _data import regime_series                    # from the examples/ dir
from contexttrading.core.config import EngineConfig

series = regime_series("trend_up", count=300)      # seeded, deterministic
config = EngineConfig()
```

## structure — swings, legs, BOS/CHoCH

```python
from contexttrading.analysis.structure import analyze_structure, analyze_trend

structure = analyze_structure(series, config).payload
print(len(structure.swings), len(structure.breaks))
```

The foundation everything else builds on. `swings` are classified
`internal`/`external` pivots; `breaks` are BOS (trend continuation) or
CHoCH (character change) events with a strength grade. `analyze_trend`
derives the current `TrendState` (direction, leg quality) from the same
scan — always read trend from here, never re-derive it.

## liquidity — pools, equal levels, sweeps

```python
from contexttrading.analysis.liquidity import analyze_liquidity

liq = analyze_liquidity(series, config).payload
print(len(liq.pools), len(liq.sweeps))
```

`pools` are resting-liquidity zones (equal highs/lows, session extremes);
`sweeps` are stop-hunt events classified by type (e.g. STOP_HUNT/GRAB).
A sell-side sweep is bullish evidence downstream — the confluence engine
applies that mapping for you.

## premium_discount — the dealing range

```python
from contexttrading.analysis.premium_discount import analyze_dealing_range

dr = analyze_dealing_range(series, config).payload.dealing_range
print(dr.equilibrium)
```

The confirmed range, its equilibrium, and premium/discount bands.
DISCOUNT = bullish zone-in-value territory (used by the reference
strategy), premium the mirror.

## fvg / orderblocks / supplydemand — zones

```python
from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.supplydemand import analyze_supplydemand

gaps = analyze_fvg(series, config).payload.fvgs
ob = analyze_orderblocks(series, config).payload
blocks = ob.order_blocks  # plus ob.breaker_blocks, ob.mitigation_blocks
zones = analyze_supplydemand(series, config).payload.zones
```

Three zone families with different semantics: FVGs are imbalance gaps
(incl. inverse FVGs and mitigation state), order blocks anchor on the
last opposite candle before a confirmed break (breakers = violated OBs
with a counter-break), supply/demand adds RBD/DBR pattern zones. Every
zone carries a lifecycle status (FRESH → TESTED → MITIGATED/BROKEN) and
a deterministic `id` you can cite.

## sessions — kill zones and Judas swings

```python
from contexttrading.analysis.sessions import analyze_sessions

sess = analyze_sessions(series, config).payload
```

UTC-anchored session windows (Sydney/Tokyo/London/New York + kill
zones), per-session stats, day extremes, and Judas-swing detection
(Asian-range sweep during London, London sweep during NY).

## mtf — multi-timeframe context

```python
from contexttrading.analysis.mtf import analyze_mtf

mtf = analyze_mtf(series, ("1h", "4h"), config).payload
print(mtf.bias.direction, mtf.bias.strength)
```

Resamples deterministically (epoch floor; 1w = Monday 00:00 UTC; 1M =
calendar month), evaluates structure per timeframe, and aggregates a
weighted-majority bias. A too-short resampled series degrades to an
UNKNOWN context — never an exception.

## confluence — the weighted verdict

```python
from contexttrading.analysis.confluence import analyze_confluence

conf = analyze_confluence(series, config).payload
print(conf.bias, conf.score, len(conf.factors), len(conf.zones))
```

Pure orchestration: it runs the engines above (or reuses `precomputed`
payloads), maps each piece of evidence to a directional
`FactorContribution` (weight × raw, normalized), and emits bull/bear
scores, the winning bias, and spatial confluence zones where ≥2 distinct
kinds of evidence overlap with unanimous direction. Non-evaluable
factors are omitted rather than diluted to zero — read `conf.factors`
for the full audit trail.

## Reading an envelope

Every result shares the same envelope:

```python
result.schema_version   # contract version ("1.0.0") — check before interpreting
result.engine_version   # which computation produced it
result.generated_from   # DataWindow: start/end/candle_count of the input
result.payload          # the module-specific model above
```

## Performance notes

Measured on the seeded 2,000-bar integration dataset (see
`tests/performance/`): structure 61 ms, FVG 203 ms, order blocks 383 ms,
full stack ≈ 1.7 s. `run_full_stack` shares precomputed payloads with
confluence — always prefer it over calling ten analyzers yourself when
you want everything.

## Going deeper

Each module has a full contract doc in `docs/modules/` (purpose, inputs,
outputs, config fields, limitations). The edge-case contract — typed
`InsufficientDataError` on short series, strict-JSON payloads on
degenerate ones — is enforced by `tests/unit/analysis/test_edge_cases.py`.
