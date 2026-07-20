# analysis.premium_discount

Dealing range, equilibrium, premium/discount location, and OTE zone.

## Purpose

Frame the active dealing range so later phases (confluence, trade logic) can
price entries in discount (buys) or premium (sells).

## Responsibilities

- `dealing_range.py`: `compute_dealing_range` (pure function over external
  swings) and `analyze_dealing_range` (envelope wrapper running a structure
  scan).

## Inputs

- `CandleSeries` plus structure scan (external swings, active trend).
- `EngineConfig`: `ote_fib_lower` (0.62), `ote_fib_upper` (0.79),
  `float_abs_tol`.

## Outputs

`AnalysisResult[DealingRangeResult]` → `DealingRange | None` with:
`high`/`low` (+ swing refs), `direction`, `equilibrium` (50%),
`ote_low`/`ote_high`, `ote_fibs`, `reference_price` (last close),
`price_location` (`premium`/`discount`/`equilibrium`), and four zone styles
(premium/discount/equilibrium/OTE) for direct rendering.

## Key rules

- Range = last alternating external swing high + low; requires
  `high.price > low.price`, else None.
- BULLISH OTE: `[high - 0.79R, high - 0.62R]` (buy zone in discount);
  BEARISH OTE: `[low + 0.62R, low + 0.79R]` (sell zone in premium).
  `R = high - low`; fibs sorted so custom values may be passed in any order.
- Undetermined trend falls back to swing recency (low-before-high ⇒ bullish).
- EQUILIBRIUM location requires |price - EQ| <= `float_abs_tol`.

## Example (excerpt)

```json
{
  "module": "premium_discount",
  "payload": {
    "dealing_range": {
      "high": 19.05, "low": 15.95, "equilibrium": 17.5,
      "ote_low": 16.601, "ote_high": 17.128,
      "direction": "bullish", "price_location": "premium"
    }
  }
}
```

## Testing

`tests/unit/analysis/test_dealing_range.py` — geometry, mirrored OTE, custom
fibs, location boundary, validation errors; golden
`tests/regression/goldens/dealing_range_uptrend.json`.

## Limitations

- The range tracks only the latest swing pair; nested/dealing-range history
  (multi-range) is a Phase 6 MTF concern.

Migration history: v1.0.0 (Phase 3) — initial.
