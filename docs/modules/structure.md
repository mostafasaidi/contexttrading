# analysis.structure

Market-structure engine: fractal swings, leg classification, BOS/CHoCH state
machine, and the composite TrendEngine.

## Purpose

Convert raw OHLCV into the institutional SMC skeleton — swings, structure
breaks, trend state — with full determinism.

## Responsibilities

| Module | Responsibility |
|---|---|
| `swings.py` | Fractal swing high/low detection (strict inequality, tie = no swing), internal vs external classes. |
| `legs.py` | Alternating-swing reduction; impulse/correction leg classification with ATR multiples and retracement ratios. |
| `structure.py` | `StructureScanner` state machine: BOS/CHoCH, internal/external, major/minor, strong/weak/false, protected levels. |
| `trend.py` | `TrendEngine`: direction, strength, market phase, evidence basis. |

## Inputs

- `CandleSeries` (>= `engine.min_candles` → else `InsufficientDataError` CT-3001)
- `EngineConfig`: `internal_swing_lookback` (2), `external_swing_lookback` (5),
  `atr_period` (14), `strength_atr_fraction` (0.25), `phase_lookback` (20),
  `consolidation_range_atr_multiple` (3.0), `strong_impulse_ratio` (1.5),
  `swing_overlap_fraction` (0.5)

## Outputs

- `analyze_structure` → `AnalysisResult[MarketStructureResult]`
  (swings, breaks, legs, `protected_high`/`protected_low`)
- `analyze_trend` → `AnalysisResult[TrendResult]` (`TrendState`)

`StructureBreak` fields: `broken_swing_id`, `broken_swing_price`,
`broken_swing_class`, `break_index`, `break_timestamp`, `break_price`,
`direction`, `break_type` (BOS/CHoCH), `break_class` (internal/external),
`significance` (major/minor), `strength` (strong/weak/false), `margin_atr`,
`is_sweep_candidate`, `style`.

## Key rules (state machine)

- Swings are actionable at `index + lookback`, evaluated before that candle's
  break checks.
- Active trend starts UNKNOWN; the first close through an actionable extreme
  establishes it (initial BOS). Afterwards it flips **only** on CHoCH.
- BOS consumes its level; a new swing must form before the next same-side BOS.
- Protected low/high updates only on BOS events (and initial establishment).
- FALSE = wick-only breach, emitted once per level, no state change, flagged
  `is_sweep_candidate` for the liquidity module.
- Strength: `margin = close - level`; STRONG when
  `margin >= strength_atr_fraction * ATR[i]`; WEAK otherwise (also when ATR
  is unavailable).

## Example (excerpt)

```json
{
  "module": "structure",
  "payload": {
    "breaks": [{
      "broken_swing_price": 17.05,
      "break_index": 19,
      "direction": "bullish",
      "break_type": "bos",
      "significance": "major",
      "strength": "strong",
      "margin_atr": 0.52
    }]
  }
}
```

## Testing

`tests/unit/analysis/test_{swings,legs,structure,trend}.py` (hand-crafted
fixtures: trending, ranging, V-reversal, fakeout, flat), property tests in
`test_swings_property.py`, goldens in `tests/regression/goldens/structure_*.json`.

## Limitations

- Equal-priced neighbors are never swings (by design); use the liquidity
  module for equal levels.
- `retracement_ratio`/`atr_multiple` are None when the prior leg or ATR is
  unavailable.
- Weekend/holiday gaps are not modeled; gap handling is a data-layer concern.

Migration history: v1.0.0 (Phase 3) — initial.
