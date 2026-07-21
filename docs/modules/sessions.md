# analysis.sessions

Session engine: configurable session/killzone windows, per-instance
statistics, session-derived liquidity pools, and Judas-swing detection.

## Purpose

Turn wall-clock session definitions (Sydney, Tokyo, London, New York and
the kill zones) into deterministic, candle-derived objects: what each
session did (range, direction, volume), which session forms the day's
high/low, and where session liquidity gets swept — including the classic
Judas swing (Asian range swept in the London kill zone, London levels
swept in the New York kill zones).

## Responsibilities

| Module | Responsibility |
|---|---|
| `definitions.py` | `SessionWindow` resolution from `SessionConfig`, midnight-wrap membership, instance assignment, calendar helpers. |
| `tracker.py` | Instance statistics, calendar-day levels, Asian-range accumulation, session/PDH/PDL pool synthesis, Judas classification. |
| `sessions.py` | `analyze_sessions` orchestrator: stats → pools → sweep scan → Judas → day-extreme summary. |

## Inputs

- A `CandleSeries` (UTC timestamps; any timeframe).
- `SessionConfig`: `default_timezone` plus `sessions` / `killzones` window
  maps (`HH:MM`, may wrap midnight). Defaults (UTC): Sydney 21:00–06:00,
  Tokyo 00:00–09:00, London 07:00–16:00, New York 12:00–21:00; kill zones
  London 07:00–10:00, New York AM 12:00–15:00, London close 15:00–17:00,
  New York PM 18:00–20:00.
- `EngineConfig`: `session_doji_body_fraction` (0.2), plus the shared
  ATR / sweep thresholds used by the liquidity scan.
- A structure scan (ATR values, FALSE breaks) — reused, never recomputed.

Deviation from the strict one-config module contract: session windows live
in `SessionConfig` (a separate settings section), so the entrypoint takes
it as a second optional parameter defaulting to the documented UTC windows.

## Outputs

`AnalysisResult[SessionResult]` (schema `SessionStats-v1.json`,
`SessionSweep-v1.json`, `SessionResult-v1.json`, version 1.0.0):

- `sessions`: `SessionStats` per instance (window × trading date) — OHLCV,
  high/low candle indices, direction (RANGING when body <
  `session_doji_body_fraction` × range), `range_atr`, `forms_day_high/low`,
  box style (`sessions.boxes` / `sessions.killzones` layers).
- `pools` / `sweeps`: session-derived `LiquidityPool`s (kinds
  `SESSION_HIGH/LOW`, `PREVIOUS_DAY_HIGH/LOW`) with final statuses and the
  `LiquiditySweep`s against them — the standard sweep machinery, no
  parallel lifecycle.
- `session_sweeps`: `SessionSweep` Judas events (swept group/level/price,
  sweeping killzone, candle, `linked_sweep_id`).
- `day_high_counts` / `day_low_counts` / `dominant_*_session`: which
  window most often prints the calendar-day extremes.

## Deterministic rules

**Instances.** Candles are assigned to windows by local (session-timezone)
minute-of-day; membership is half-open `[start, end)`. A wrapped window
(end ≤ start) matches `minute >= start or minute < end`, and its instance
belongs to the calendar date of its START bar.

**Asian range.** For each calendar day `D` with a configured London
session: candles inside the Sydney or Tokyo windows with local timestamps
in `[london_open(D) - 12h, london_open(D))`. Accumulated high/low becomes
the `"asia"` level group.

**Pools.** Session high/low pools form at the instance's last candle
(active from the next one) — the level is known only once the instance is
complete. Previous-day pools form at the last candle of the previous day
and activate with the new day's first candle.

**Judas swing.** A `LiquiditySweep` against a session-derived pool where
the sweeping candle sits in a kill zone: `asia` levels during the London
kill zone, or `london` levels during the New York kill zones
(`new_york_am`, `new_york_pm`). Day-level (PDH/PDL) sweeps are reported as
normal sweeps, not Judas events.

**Day extremes.** `forms_day_high/low` compares the instance extreme with
the calendar-day extreme of the date on which that extreme candle printed
(exact float equality — both values come from the same candles). Counts
exclude kill zones; dominant-session ties break alphabetically.

## Testing

Unit tests cover window membership/wrap, instance dating, OHLCV stats and
doji direction, day-extreme flags and counts, pool kinds/levels/statuses,
the Judas classifier (both patterns plus negative cases) end-to-end on a
hand-built 2-day fixture, custom-window configs, and determinism; 2
regression goldens (`sessions_five_day`, `sessions_judas`); integration
over the seeded 2,000-candle dataset checks coverage, PDH/PDL presence,
sweep linkage, count invariants, and determinism.

## Limitations / deviations

- A candle may belong to several overlapping windows (e.g. Tokyo and
  Sydney 00:00–06:00); each window is tracked independently, so day-extreme
  counts can exceed the number of days.
- The final, still-open instance at series end is tracked and pooled like
  any other; its pools simply activate too late to be swept.
- Kill zones double as session instances for statistics; they never create
  pools and are excluded from day-extreme counts.
