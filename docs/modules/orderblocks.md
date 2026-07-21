# analysis.orderblocks

Order block engine: displacement-anchored order blocks, breaker blocks
(role-flipped violated OBs), and mitigation blocks (failed-move origins).

## Purpose

Locate the institutional origin candles of structure-breaking moves, track
how price revisits them, and flip consumed blocks into breakers when market
structure confirms the role change.

## Responsibilities

| Module | Responsibility |
|---|---|
| `detection.py` | Anchor OBs to confirmed structure breaks; zone/body geometry; refinement; origin tagging; dedupe. |
| `lifecycle.py` | Shared chronological first-touch lifecycle (`BlockState`, `update_block_state`). |
| `breakers.py` | Emit breaker blocks for violated OBs with a confirming counter-direction break. |
| `mitigation_blocks.py` | Emit mitigation blocks for liquidity sweeps without a structure break. |
| `orderblocks.py` | `OrderBlockEngine` / `analyze_orderblocks` orchestrator. |

## Inputs

- `CandleSeries` plus a structure scan (swings, breaks, ATR — via
  `StructureScanner`, never recomputed), FVG output (overlap confluence),
  liquidity internals (equal levels → pools → sweeps over the same scan),
  and volume z-scores (`volume_lookback`).
- `EngineConfig`: `ob_max_lookback` (30), `ob_refine_atr_multiple` (2.0),
  `ob_refine_wick_fraction` (0.5), `breaker_confirm_lookback` (20).

## Outputs

`AnalysisResult[OrderBlockResult]` (schema `OrderBlock-v1.json`,
`BreakerBlock-v1.json`, `MitigationBlock-v1.json`, `OrderBlockResult-v1.json`,
version 1.0.0):

- `order_blocks`: zone/body geometry, refined zone when oversized, `origin`
  (continuation/reversal), `linked_break_id`, `displacement_margin_atr`,
  `volume_zscore`, `overlapping_fvg_ids`, full lifecycle fields.
- `breaker_blocks`: flipped zone with `source_order_block_id`, `flip_index`,
  `confirming_break_id`, own lifecycle.
- `mitigation_blocks`: origin zone with `linked_sweep_id`, `failed_swing_id`.

## Deterministic rules

**Detection.** Every confirmed break (STRONG/WEAK; FALSE breaks are sweep
material) anchors at most one OB: the last opposite-close candle strictly
before `break_index` (down-close for a bullish break), searched up to
`ob_max_lookback` candles back. Single-candle anchor — cluster merging was
considered and dropped because every trend leg is a contiguous same-sign
run (see Deviations). Zone = candle `[low, high]`; body = `[min(o,c),
max(o,c)]`. Origin = REVERSAL when the linked break is a CHoCH, else
CONTINUATION. Dedupe: same candle+direction keeps the strongest break
(STRONG > WEAK, then MAJOR > MINOR, then earliest).

**Refinement.** When the zone height exceeds `ob_refine_atr_multiple` × ATR
at the anchor (strict `>`), the refined zone is the extreme
`ob_refine_wick_fraction` of the range (bullish: lowest part; bearish:
highest). Both zones are emitted; mitigation uses the refined midpoint.

**Lifecycle** (bullish shown; bearish mirrored; scan starts at the candle
*after* the break candle — the break candle belongs to the departure):

```
UNMITIGATED → PARTIALLY_MITIGATED → MITIGATED → VIOLATED
 (valid)        (entered zone)     (threshold)  (close-through)
```

- Entry: any trade into the zone (wick counts); penetration fraction
  tracked against the full zone.
- MITIGATED: traded through the mitigation level — far boundary for
  unrefined zones, refined-zone midpoint (50% rule) when refined.
- VIOLATED: a candle *closed* through the far side. Wick-through is NOT a
  violation. Terminal.
- `is_valid` = status is UNMITIGATED (literal reading of "unmitigated &
  unviolated"); `is_consumed` = MITIGATED and a later close departed the
  zone on the origin side (sticky).

**Breaker.** A VIOLATED OB flips when a confirmed break in the violation
direction occurs at the violation candle or within
`breaker_confirm_lookback` candles after it. The breaker inherits the OB
zone, runs the standard lifecycle from `flip_index + 1`, and renders
purple.

**Mitigation block.** Eligible sweeps: STOP_HUNT or GRAB (deep or
structure-linked stop runs without a real break). A BUYSIDE sweep yields a
bullish block on the candle at the most recent external swing low before
the sweep (the failed leg's origin; bearish mirrored). `failed_swing_id` =
the first member swing of the swept pool. Unrefined mitigation semantics.

## Testing

Unit fixtures cover geometry, origin tagging, the strict refinement
boundary, partial/mitigated/violated stories (wick vs close), breaker
confirmation (with and without a confirming break), sweep-driven mitigation
blocks, and FVG overlap links; hypothesis properties cover geometry,
lifecycle monotonicity, and ID stability; 2 regression goldens
(`orderblocks_trending`, `orderblocks_sweep`); integration over the seeded
2,000-candle dataset checks referential integrity and determinism.

## Limitations / deviations

- **Single-candle anchors** (deviation from the "cluster" wording in the
  spec): contiguous same-sign runs merge entire trend legs into oversized
  zones, so clusters are not merged; oversized candles are handled by
  refinement instead. `cluster_start_index` is kept in the schema (==
  `candle_index`).
- `is_valid` is deliberately literal: a partially mitigated OB is not
  "valid" — use `status` for finer granularity.
