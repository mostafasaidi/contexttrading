# models.candle

Validated market-data primitives.

- **`Candle`** — `timestamp` (tz-aware UTC; naive rejected), `open`, `high`,
  `low`, `close`, `volume`, optional `tick_count` / `is_closed`. Validation:
  `high >= max(open, close)`, `low <= min(open, close)`, `high >= low`,
  `volume >= 0`, all prices finite and `> 0` where required. Frozen.
  Derived: `body`, `range`, `midpoint`, `direction` (`TrendDirection`).
- **`CandleSeries`** — immutable, ordered, gap-aware container with `symbol`,
  `timeframe`, `timezone` metadata. Built via `CandleSeries.from_records(...)`
  or from a sequence of `Candle`s; sorts by timestamp, rejects duplicates.
  Slicing by index and by time window (`between(start, end)`), `gaps()`
  returns missing-period windows, `resample(target)` declares the Phase-3+
  resampling contract. Iteration and `len()` supported.

Migration history: v1.0.0 (Phase 2) — initial.
