# analysis.supplydemand

Supply & demand engine: OB-derived zones plus rally-base-drop /
drop-base-rally pattern zones, with lifecycle and deterministic strength.

## Purpose

Consolidate order blocks and standalone base patterns into one ranked
supply/demand map: where unfilled institutional interest likely remains,
how fresh each zone is, and how strong.

## Responsibilities

| Module | Responsibility |
|---|---|
| `zones.py` | Pattern detection (RBD/DBR), OB-derived zone mapping, duplicate marking, lifecycle scan, strength scoring. |
| `supplydemand.py` | `SupplyDemandEngine` / `analyze_supplydemand` orchestrator. |

## Inputs

- `OrderBlockEngine` output (OB-derived zones; internally structure, FVG,
  and liquidity — never recomputed here).
- A structure scan (external swings, legs, ATR, external trend).
- `EngineConfig`: `sd_base_body_atr_fraction` (0.5), `sd_max_base_candles`
  (3), `sd_departure_atr_multiple` (1.5), `sd_departure_atr_cap` (3.0),
  `sd_duplicate_overlap_fraction` (0.8), `sd_strength_half_life` (50), and
  the six `sd_weight_*` fields (0.30/0.20/0.20/0.10/0.10/0.10).

## Outputs

`AnalysisResult[SupplyDemandResult]` (schema `SupplyDemandZone-v1.json`,
`SupplyDemandResult-v1.json`, version 1.0.0): zones sorted by strength
(rank 1 first) with kind, geometry, base span, departure data, lifecycle
(`status`, `tests`, touch/mitigated/broken indices, age), cross-links
(`linked_order_block_id`, `is_duplicate`), `trend_aligned`, `strength`,
`rank`.

## Deterministic rules

**Zone sources.**

- *OB-derived*: every order block maps to a zone (bullish → DEMAND,
  bearish → SUPPLY) over its *active* zone (refined when refined);
  departure = the OB's displacement margin.
- *Pattern*: at an external swing where leg direction reverses, the base is
  the run of 1–`sd_max_base_candles` candles ending at the swing whose
  bodies are all < `sd_base_body_atr_fraction` × ATR (longer runs are
  ranges, not bases — skipped). The departure leg must be an IMPULSE leg
  with magnitude ≥ `sd_departure_atr_multiple` × ATR. Rally-base-drop →
  SUPPLY; drop-base-rally → DEMAND. Actionable once the departure leg's end
  swing is confirmed (`end_index + external_swing_lookback`); zones with an
  unconfirmed departure at series end are skipped (no lookahead).

**Duplicate rule.** A pattern zone overlapping a same-kind order block
zone by `intersection / min(heights) >= sd_duplicate_overlap_fraction` is
`is_duplicate=True` — the OB is preferred and linked.

**Lifecycle** (chronological first-touch; supply shown, demand mirrored):

```
FRESH → TESTED → MITIGATED (wick through base)   [terminal]
              ↘ BROKEN    (close through base)   [terminal]
```

- A *test* is a distinct re-entry that neither mitigates nor breaks;
  consecutive candles inside the zone count once.
- BROKEN wins over MITIGATED when one candle does both.

**Strength.**

```
strength = clamp01(
    w_dep    * min(departure_atr / sd_departure_atr_cap, 1)      # 0.5 in warmup
  + w_tight  * (1 - min(mean_base_body_atr / sd_base_body_atr_fraction, 1))
  + w_fresh  * (FRESH 1.0 / TESTED 0.5 / MITIGATED 0.1 / BROKEN 0.0)
  + w_tests  * 0.5 ** tests
  + w_trend  * (1.0 if aligned with external trend else 0.0)
  + w_age    * 0.5 ** (age / sd_strength_half_life)
)
```

Ranking: strength desc, tie-break by `base_end_index` asc.

## Testing

Unit fixtures cover RBD/DBR geometry, fresh/tested/mitigated/broken
transitions (incl. distinct-visit counting and broken-wins precedence),
the duplicate threshold boundary (rbd duplicates, dbr does not), OB-link
integrity, strength determinism/ordering/warmup, and validators; hypothesis
properties cover geometry, lifecycle monotonicity, and ID stability; 1
regression golden (`supplydemand_rbd`); integration over the seeded
2,000-candle dataset checks referential integrity and determinism.

## Limitations / deviations

- Trend alignment uses `StructureScan.external_trend` (the same value
  `TrendEngine` derives its direction from) rather than a separate
  TrendEngine run.
- Bodies exactly at the base threshold are excluded (`<` is strict), so the
  boundary candle always ends the base run.
