# analysis.indicators

Deterministic volatility & volume primitives — the ONLY indicator-style
computations in the engine. Used internally by engines; never by the AI layer.

## Purpose

Provide ATR-based normalization (strength thresholds, tolerances) and volume
context (relative volume, z-scores, imbalance flags) with zero lookahead.

## API

| Function | Returns | Notes |
|---|---|---|
| `true_ranges(candles)` | `tuple[float, ...]` | TR[0] = high-low. |
| `atr(candles, period)` | `tuple[float \| None, ...]` | Wilder; first value at `period-1` = SMA of TR[0..period-1]. |
| `latest_atr(candles, period, min_candles)` | `float` | Raises CT-3001 when unavailable. |
| `rolling_mean(values, window)` | `tuple[float \| None, ...]` | Includes current element. |
| `prior_rolling_mean(values, window)` | `tuple[float \| None, ...]` | Strictly before `i` — no lookahead. |
| `prior_rolling_std(values, window)` | `tuple[float \| None, ...]` | Population std (ddof=0). |
| `relative_volumes(candles, window)` | `tuple[float \| None, ...]` | Volume / prior-window mean. |
| `volume_zscores(candles, window)` | `tuple[float \| None, ...]` | None when prior std = 0. |
| `volume_imbalance_flags(candles, window, threshold)` | `tuple[bool, ...]` | `|z| >= threshold`. |

Config: `atr_period` (14), `volume_lookback` (20), `volume_zscore_threshold` (2.0).

## Conventions

- Outputs align 1:1 with inputs; insufficient history → `None`/`False`.
- All rolling stats at index `i` use only indices `< i` unless documented
  otherwise (`rolling_mean` includes `i`).
- Fixed iteration order → identical float results across runs/platforms.

## Testing

`tests/unit/analysis/test_indicators.py` — hand-computed ATR/Wilder values,
no-lookahead checks, zero-std edges, spike detection.

## Limitations

- No EMA/RSI/etc. — engines must normalize through ATR or rolling stats only;
  new primitives require a determinism review.
- Volume semantics are feed-dependent (tick vs real volume); the engine treats
  volume as an opaque non-negative number.

Migration history: v1.0.0 (Phase 3) — initial.
