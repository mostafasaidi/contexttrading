# core.constants

Shared enums and numeric constants. This module is the single source of
truth for cross-layer vocabulary.

- **`Timeframe`** — `M1, M3, M5, M15, M30, H1, H2, H4, H6, H8, H12, D1, W1, MN1`.
  - `Timeframe.parse("15m" | "4h" | "1d" | "1w" | "1M")` (case-insensitive).
  - `.seconds` / `.minutes` / `.to_timedelta()`; total ordering by duration
    (`M1 < M5 < H1 < D1 < W1 < MN1`, where `MN1` is conventional 30 days for
    ordering only — never for arithmetic on real calendars).
- **`SessionName`** — `ASIA, LONDON, NEW_YORK, LONDON_CLOSE, ASIA_SYDNEY,
  ASIA_TOKYO` plus killzone aliases.
- **`TrendDirection`** — `BULLISH, BEARISH, RANGING, UNKNOWN` with `.sign`.
- **`StructureBreakType`** — `BOS, CHOCH`; **`StructureBreakClass`** —
  `INTERNAL, EXTERNAL`; **`StructureBreakSignificance`** — `MINOR, MAJOR`.
- **`SwingType`** — `HIGH, LOW`; **`ZoneType`** — `ORDER_BLOCK, BREAKER_BLOCK,
  FAIR_VALUE_GAP, SUPPLY, DEMAND, LIQUIDITY_POOL, PREMIUM, DISCOUNT, EQUILIBRIUM`.
- **`MitigationStatus`** — `UNMITIGATED, PARTIALLY_MITIGATED, MITIGATED, VIOLATED`.
- **`LiquiditySide`** — `BUYSIDE, SELLSIDE`; **`LiquidityPoolKind`** —
  `EQUAL_HIGHS, EQUAL_LOWS, SWING_HIGH/LOW, SESSION_HIGH/LOW,
  PREVIOUS_DAY_HIGH/LOW`.
- **Float tolerances:** `FLOAT_REL_TOL = 1e-9`, `FLOAT_ABS_TOL = 1e-12`.

Migration history: v1.0.0 (Phase 2) — initial.
