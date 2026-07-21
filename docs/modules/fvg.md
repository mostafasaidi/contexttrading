# analysis.fvg

Fair Value Gap (FVG) engine: 3-candle imbalance detection, nested/stacked
classification, displacement linkage, inversion, and a full mitigation
lifecycle with deterministic strength scoring.

## Purpose

Locate price imbalances left by displacement moves, classify them
(nested/stacked/inverse), link them to the structure breaks that caused
them, and track how price later mitigates each zone.

## Responsibilities

| Module | Responsibility |
|---|---|
| `detection.py` | Raw 3-candle gap detection, min-size filter, nested parenting, stack grouping, displacement linkage. |
| `inversion.py` | Far-side primitives: `trades_through_far_side` (wick) vs `closes_through_far_side` (close). |
| `mitigation.py` | Chronological lifecycle state machine and the deterministic strength formula. |
| `fvg.py` | `FVGEngine` / `analyze_fvg` orchestrator over a `StructureScanner` run. |

## Inputs

- `CandleSeries` plus a structure scan (ATR, structure breaks) — the engine
  runs `StructureScanner` internally and never recomputes swings/ATR.
- `EngineConfig`: `fvg_min_atr_fraction` (0.05), `fvg_stacked_lookback` (5),
  `fvg_strength_half_life` (50), `fvg_gap_atr_cap` (3.0), and the five
  strength weights (`fvg_weight_gap` 0.35, `fvg_weight_displacement` 0.25,
  `fvg_weight_freshness` 0.15, `fvg_weight_age` 0.15,
  `fvg_weight_structure` 0.10).

## Outputs

`AnalysisResult[FVGResult]` (schema `FVG-v1.json` / `FVGResult-v1.json`,
version 1.0.0) with FVGs sorted by strength (rank 1 first):

- geometry: `zone_bottom`/`zone_top`, formation indices, `gap_size`,
  `gap_atr` (None during ATR warmup), `gap_percent`.
- classification: `is_nested` + `parent_fvg_id`, `stack_group_id`,
  `linked_break_id` + `displacement_margin_atr`, `is_inverse` +
  `inversion_index`.
- lifecycle: `status`, `first_touch_index`, `filled_index`,
  `max_fill_fraction`, `touches`, `age`.
- scoring: `strength` ∈ [0, 1], `rank`.

## Detection rules

- **Bullish FVG** at middle candle `i`: `low[i+1] > high[i-1]`; zone
  `[high[i-1], low[i+1]]`. Bearish mirrored: `high[i+1] < low[i-1]`.
- **Min-size filter**: `gap >= fvg_min_atr_fraction * ATR[i]`, inclusive
  boundary. During ATR warmup (`ATR[i] is None`) the filter is skipped and
  the gap is kept with `gap_atr=None` (conservative, mirrors structure).
- **Nested**: at registration (the confirmation candle `i+1`), a new FVG
  links the smallest still-active same-direction FVG whose zone fully
  contains it. "Active" means UNMITIGATED or PARTIALLY_MITIGATED at that
  moment — a chronological snapshot, not final-state geometry.
- **Stacked**: pure geometry — same-direction FVGs whose zones touch or
  overlap, chained transitively, each link within `fvg_stacked_lookback`
  candles (inclusive). Groups of one are never emitted; the group id is a
  content hash of the root member.
- **Displacement**: the middle candle's structure breaks are linked,
  preferring STRONG > WEAK > FALSE, then MAJOR > MINOR.

## Lifecycle

Zone `[bottom, top]`; bullish zones mitigate from above, bearish from below
(mirrored). Wicks count for entry/fill; **only a close can invert**.

```
UNMITIGATED → PARTIALLY_MITIGATED → MITIGATED → VIOLATED
 (untouched)   (entered zone)      (wick fill)  (close-through = inverse)
```

- Entry: any trade into the zone (bullish: `low <= top`).
- Fill fraction per candle: depth traded into the zone, clamped to [0, 1].
- MITIGATED (filled): traded *through* the far side (wick suffices).
- VIOLATED (inverse): a candle *closed* through the far side; terminal.
  A wick-filled zone can still invert later — MITIGATED is not terminal
  for inversion.
- `age`: candles from `formation_end_index` to the fill candle, or to the
  last candle when unresolved.

The lifecycle reuses the shared `MitigationStatus` enum:
`UNMITIGATED`=untouched, `PARTIALLY_MITIGATED`=partial, `MITIGATED`=filled,
`VIOLATED`=inverted — no new enum, no schema break.

## Strength formula

```
strength = clamp01(
    w_gap    * min(gap_atr / fvg_gap_atr_cap, 1)   # 0.5 when ATR warmup
  + w_disp   * disp_score    # linked BOS: strong 1.0 / weak 0.5 / false 0.25 / none 0
  + w_fresh  * fresh_score   # untouched 1 / partial 0.5 / filled 0.1 / violated 0
  + w_age    * 0.5 ** (age / fvg_strength_half_life)
  + w_struct * struct_bonus  # nested 0.5 + stacked 0.5, capped at 1.0
)
```

Ranking: strength descending, tie-break by `formation_end_index` ascending —
fully deterministic.

## Determinism notes

- Single chronological pass: states update candle-by-candle; FVGs register
  at their confirmation candle; models finalize in registration order so
  `parent_fvg_id` always resolves to an already-built parent.
- FVG identity hashes all detection + lifecycle fields but excludes
  presentation/derived scoring (`id`, `label`, `rank`, `strength`).
- No wall-clock, no randomness; byte-identical output across runs (covered
  by integration tests and regression goldens).
