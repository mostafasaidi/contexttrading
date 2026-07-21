# analysis.confluence

Confluence engine: deterministic, explainable confidence scores composed
from every other module's outputs.

## Purpose

Answer "how much evidence supports long vs short right now?" as structured
data: directional scores in [0, 1] with a complete per-factor breakdown,
plus spatial *confluence zones* where several factor kinds overlap. The
engine detects nothing itself — it orchestrates the configured engines and
scores their versioned outputs. Every factor is self-describing so the
Phase-8 AI layer can narrate without recomputing anything.

## Responsibilities

| Module | Responsibility |
|---|---|
| `factors.py` | Directional evidence extraction (one `FactorContribution` per piece of evidence). |
| `zones.py` | Spatial overlap clustering and zone scoring. |
| `confluence.py` | `analyze_confluence` orchestrator: engines → factors → normalized scores → zones. |

## Inputs

- A `CandleSeries`; `EngineConfig` (`conf_*` fields below); optional
  `SessionConfig` (forwarded to the sessions engine); optional
  `mtf_timeframes` (defaults to the next two standard timeframes above the
  base — e.g. 15m → 30m, 1h).
- Module outputs: structure scan + `TrendState`, liquidity,
  premium/discount, FVG, order blocks, supply/demand, sessions, MTF —
  obtained by running the configured engines, never reimplemented.

## Outputs

`AnalysisResult[ConfluenceResult]` (schema `FactorContribution-v1.json`,
`ConfluenceZone-v1.json`, `ConfluenceResult-v1.json`, version 1.0.0):
`bias`, `score`, `bullish_score`, `bearish_score`, `reference_price`,
`factors` (full breakdown), `agreeing_factors`, `conflicting_factors`,
`zones`.

## Scoring formula

Each factor emits `weight` (config), `raw` in [0, 1], and
`contribution = weight * raw` toward one direction (RANGING = no side):

```
bullish_score = sum(contribution of bullish factors) / total emitted weight
bearish_score = mirrored                    (both in [0,1], sum <= 1)
score = max(bullish_score, bearish_score);  bias = its side (ties RANGING)
```

Factors with no directional evidence (e.g. ranging trend) are emitted with
`raw = 0` — they count in the total weight and therefore *dilute* the
scores: missing agreement lowers confidence by design. Factors that cannot
be evaluated at all (no confirmed breaks, no sweeps, no dealing range) are
omitted and do not dilute.

## Factors (assembly order, direction mapping, raw value)

| Factor | Weight field | Direction rule | Raw |
|---|---|---|---|
| `trend` | `conf_weight_trend` (1.0) | external trend | STRONG 1.0 / MODERATE 0.6 / WEAK 0.3 (documented constant) |
| `mtf` | `conf_weight_mtf` (1.5) | MTF bias | `bias.agreement_share` |
| `structure` | `conf_weight_structure` (1.0) | majority of last `conf_structure_lookback` (5) confirmed breaks | majority / window size |
| `liquidity` | `conf_weight_liquidity` (1.0) | majority of last `conf_sweep_lookback` (5) sweeps; sellside sweep = bullish | class-weighted majority share (STOP_HUNT 1.0 / GRAB 0.8 / SWEEP 0.6) |
| `premium_discount` | `conf_weight_premium_discount` (0.5) | DISCOUNT bullish / PREMIUM bearish | distance from equilibrium / half-range, clamped |
| `fvg` | `conf_weight_fvg` (1.0) | per nearby active FVG (unmitigated/partial) | FVG strength |
| `orderblock` | `conf_weight_orderblock` (1.0) | per nearby valid block | OB 1.0 / breaker 0.8 / mitigation block 0.7 |
| `supplydemand` | `conf_weight_supplydemand` (1.0) | per nearby fresh/tested zone (duplicates excluded); DEMAND bullish | zone strength |
| `session` | `conf_weight_session` (0.5) | per recent Judas swing; buyside sweep = bearish | 1.0 |

"Nearby" = last close inside the zone or within `conf_proximity_atr` (1.0)
× ATR of it (0 during ATR warmup: price must be inside).

## Confluence zones

Active zones (same filters as the object factors, *without* the proximity
limit — zones are levels to watch) plus the dealing range's discount band
(bullish range) or premium band (bearish range) are clustered by interval
overlap (chain-merged). A cluster becomes a `ConfluenceZone` when it has
>= `conf_zone_min_factors` (2) distinct kinds AND unanimous direction:

```
zone score = sum(best_member_raw(kind) * kind_weight for present kinds)
             / sum(kind_weight over all four zone kinds)
```

Zones render as boxes (`confluence.zones` layer, opacity scales with
score) and are sorted by score desc.

## Testing

Unit tests cover factor boundaries (strength maps, majority/tie rules,
lookback windows, premium/discount scaling), weight normalization against
the emitted factor list, zone overlap/min-kinds/conflict/chain rules,
score formula, ID referential integrity, and determinism; hypothesis
properties cover score bounds, bias consistency, exact contributions, and
zone well-formedness (degenerate walks that violate structure-engine leg
contracts are excluded via `assume`); 3 regression goldens
(`confluence_five_day`, `confluence_judas`, `confluence_uptrend`);
integration over the seeded 2,000-candle dataset checks factor-kind
coverage, ID references into real module outputs, and byte-identical
reruns.

## Limitations / deviations

- Weights are not required to sum to 1 — normalization divides by the
  total emitted weight, so configs only express relative importance.
- Object factors (fvg/orderblock/supplydemand/session) contribute one
  entry per backing object, so object-rich charts shift weight toward
  those factors; this is intentional (more confluent evidence = higher
  confidence) and fully visible in the factor list.
- MTF timeframes default to the next two enum timeframes above the base;
  pass `mtf_timeframes` explicitly for a specific ladder.
