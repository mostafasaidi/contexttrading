# analysis.mtf

Multi-timeframe context: deterministic resampling plus a weighted
cross-timeframe trend bias.

## Purpose

Answer "what is the higher-timeframe context of this chart?" without
leaving the deterministic engine: aggregate a base series into higher
timeframes, run the same structure/trend/dealing-range engines on each,
and align the results into one bias with an execution-timeframe hint.

## Responsibilities

| Module | Responsibility |
|---|---|
| `resample.py` | Anchored, gap-tolerant downsampling (`bucket_start` / `bucket_end` / `resample_series`). |
| `context.py` | `analyze_mtf` orchestrator and `aggregate_bias` weighted voting. |

## Inputs

- A base `CandleSeries` and a list of strictly higher timeframes.
- `EngineConfig`: `mtf_include_incomplete_bar` (True),
  `mtf_tf_weight_base` (2.0), `mtf_moderate_share` (2/3), plus the shared
  structure/trend thresholds reused per timeframe.

## Outputs

`AnalysisResult[MTFResult]` (schema `TimeframeContext-v1.json`,
`MTFBias-v1.json`, `MTFResult-v1.json`, version 1.0.0):

- `contexts`: one `TimeframeContext` per timeframe (base first, then
  ascending) — timeframe, `TrendState` (None when the resampled series is
  too short; direction UNKNOWN), dealing range, weight, candle count.
- `bias`: `MTFBias` — direction, strength, `agreement_share`,
  `htf_influence`, `recommended_execution_timeframe`, `conflict_notes`.

## Deterministic rules

**Anchoring** (all UTC, no lookahead):

- Up to `1d`: bars align to the Unix epoch
  (`start = floor(ts / tf_seconds) * tf_seconds`).
- `1w`: bars start Monday 00:00 UTC (epoch day 4 = 1970-01-05).
- `1M`: bars start on the calendar month's first day (month length uses
  the real calendar, never the conventional 30-day constant).

**Aggregation.** OHLCV = first/max/min/last/sum over each bucket; empty
buckets emit no bar (no phantom candles). Only the LAST bucket may be
incomplete: when the series ends before the bucket's end its bar carries
`is_closed=False` and is dropped when `mtf_include_incomplete_bar=False`.
Upsampling (target ≤ source) raises `DataError`.
`CandleSeries.resample(...)` delegates here (lazy import — the models
layer stays dependency-free).

**Weights.** Rank 0 = base timeframe; each requested timeframe's weight is
`mtf_tf_weight_base ** rank`, so with the default base of 2.0 the
influence doubles per rank (1, 2, 4, 8, ...).

**Bias.** Weighted majority over contexts with a known (BULLISH/BEARISH)
direction; ties vote RANGING. `agreement_share` = aligned weight / total
weight (UNKNOWN contexts dilute the share). Strength:

- STRONG: at least two contexts, all known, all agreeing;
- MODERATE: `agreement_share >= mtf_moderate_share`;
- WEAK: otherwise.

`htf_influence` = weighted share of higher-timeframe contexts opposing the
base-timeframe trend (0 when the base trend is unknown or no HTF trend is
known). `recommended_execution_timeframe` = the base timeframe when it
agrees with the bias, else None. `conflict_notes` lists adjacent
disagreeing pairs as `conflict: <tf_a> <dir_a> vs <tf_b> <dir_b>`.

**Robustness.** A resampled series too short for structure analysis
(`InsufficientDataError` anywhere in the scan) yields an UNKNOWN context
instead of failing the pass.

## Testing

Unit tests cover epoch/Monday/month anchoring, OHLCV aggregation, empty
buckets, incomplete-bar handling and exclusion, upsampling errors, bias
aggregation (strong/moderate/weak/tie/unknown, conflict notes,
htf_influence, recommendation), context ordering/weights, short-HTF
robustness, and determinism; hypothesis properties cover exact
aggregation, bucket alignment/ordering, and the only-last-bar-incomplete
invariant; 2 regression goldens (`mtf_uptrend`, `mtf_five_day`);
integration over the seeded 2,000-candle dataset checks context
counts/weights, bias coherence, `CandleSeries.resample` roundtrip, and
determinism.

## Limitations / deviations

- Mid-series buckets with partial coverage (gaps in the source series) are
  still marked complete — gap handling remains a series-level concern
  (`CandleSeries.gaps()`); only the final bar tracks completeness.
- `agreement_share` and the strength rule weight by rank, not by candle
  count, so a thin monthly context can outweigh a rich hourly one by
  design.
