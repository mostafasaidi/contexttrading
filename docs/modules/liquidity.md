# analysis.liquidity

Liquidity engine: equal highs/lows, pools, and sweep/stop-hunt detection.

## Purpose

Locate where resting stop liquidity sits and detect when it gets run —
distinguishing genuine sweeps from true breaks.

## Responsibilities

| Module | Responsibility |
|---|---|
| `equal_levels.py` | Greedy ordered clustering of swing extremes within ATR tolerance into equal highs/lows. |
| `pools.py` | Pool construction from equal levels and standalone swings. |
| `sweeps.py` | Chronological sweep scan, classification (sweep/grab/stop_hunt), monotonic pool status resolution. |
| `liquidity.py` | `analyze_liquidity` orchestrator over a structure scan. |

## Inputs

- `CandleSeries` plus a structure scan (external swings, FALSE breaks, ATR).
- `EngineConfig`: `equal_level_atr_fraction` (0.1),
  `equal_level_min_separation` (3), `sweep_grab_atr_fraction` (0.5).

## Outputs

`AnalysisResult[LiquidityResult]` with:

- `equal_levels`: price (member mean), side, member swing IDs, count.
- `pools`: side, kind (`equal_highs`/`equal_lows`/`swing_high`/`swing_low`),
  `pool_class`, `source_ids`, `status` (`untapped`/`swept`/`broken`).
- `sweeps`: pool ref, candle, wick extreme, penetration in ATR,
  `close_back_inside`, classification, `linked_break_id` for stop hunts.

## Key rules

- Cluster tolerance: `equal_level_atr_fraction * ATR[swing_index]`; boundary
  is inclusive (`<=`); consecutive members need `>= equal_level_min_separation`
  candles between them.
- Pools activate at `formed_at_index + 1`; only the **first** touch resolves
  a pool: close-back-inside → SWEPT; close-through → BROKEN unless a FALSE
  structure break links the level at that candle → SWEPT with
  classification STOP_HUNT.
- GRAB when wick penetration `>= sweep_grab_atr_fraction * ATR`, else SWEEP.

## Example (excerpt)

```json
{
  "module": "liquidity",
  "payload": {
    "sweeps": [{
      "pool_price": 16.05,
      "candle_index": 20,
      "wick_extreme": 16.3,
      "close_back_inside": true,
      "classification": "stop_hunt"
    }]
  }
}
```

## Testing

`tests/unit/analysis/test_liquidity.py` — tolerance boundary (inclusive),
separation enforcement, classification matrix (unit-level pools), fakeout
pipeline stop-hunt, status resolution; golden
`tests/regression/goldens/liquidity_fakeout.json`.

## Limitations

- Only external swings source pools in Phase 3; internal liquidity arrives
  with confluence (Phase 7).
- Session/PDH-PDL pool kinds are declared in `LiquidityPoolKind` but produced
  from Phase 6 (sessions).

Migration history: v1.0.0 (Phase 3) — initial.
