"""Order block / supply-demand test fixtures: hand-crafted candle scenarios.

All scenarios use ``engine_config()`` (internal lookback 2, external 3,
ATR period 3). Comments record the intended detection so failures are easy
to diagnose.
"""

from __future__ import annotations

from typing import Any

from tests.fixtures import make_candle


def bullish_ob_records() -> list[dict[str, Any]]:
    """Bullish OB at the BOS (c4), then partial → wick-mitigation → violation.

    - Swing high 10.8 at c2, swing low 10.05 at c5.
    - c6 closes 10.9 > 10.8 → bullish BOS @6; OB = c4 (last down-close),
      zone [10.1, 10.65], origin CONTINUATION.
    - c10 dips into the zone (partial), c11 wicks through 10.1 (MITIGATED,
      close inside), c12 closes 9.95 → VIOLATED + bearish CHoCH @12 →
      bearish breaker (confirmed at the same candle).
    """
    return [
        make_candle(0, 10.0, 10.2, 9.9, 10.1),
        make_candle(1, 10.1, 10.5, 10.0, 10.4),
        make_candle(2, 10.4, 10.8, 10.3, 10.7),  # swing high 10.8
        make_candle(3, 10.65, 10.75, 10.55, 10.7),  # up-close (keeps OB single-candle)
        make_candle(4, 10.6, 10.65, 10.1, 10.15),  # OB candle (down-close)
        make_candle(5, 10.15, 10.3, 10.05, 10.2),  # swing low 10.05
        make_candle(6, 10.2, 11.0, 10.15, 10.9),  # displacement → BOS @6
        make_candle(7, 10.9, 11.2, 10.85, 11.1),
        make_candle(8, 11.1, 11.4, 11.0, 11.3),
        make_candle(9, 11.3, 11.5, 11.2, 11.4),  # swing high 11.5
        make_candle(10, 11.3, 11.35, 10.3, 10.5),  # enters OB zone (partial)
        make_candle(11, 10.5, 10.7, 10.05, 10.4),  # wick through 10.1 → MITIGATED
        make_candle(12, 10.4, 10.45, 9.9, 9.95),  # close-through → VIOLATED + CHoCH
        make_candle(13, 9.95, 10.2, 9.8, 10.0),  # returns into breaker zone
        make_candle(14, 10.0, 10.15, 9.85, 9.9),
    ]


def ob_violation_no_break_records() -> list[dict[str, Any]]:
    """Bullish OB violated by a close-through that does NOT break structure.

    Same shape as ``bullish_ob_records`` but c12 closes 10.08 — through the
    OB zone bottom (10.1) yet above the c5 swing low (10.05) → the OB is
    VIOLATED without any bearish CHoCH/BOS → no breaker block may be emitted.
    """
    records = bullish_ob_records()
    records[12] = make_candle(12, 10.4, 10.45, 10.05, 10.08)  # close-through OB only
    records[13] = make_candle(13, 10.08, 10.2, 10.06, 10.15)  # stays above the swing low
    records[14] = make_candle(14, 10.15, 10.25, 10.06, 10.2)  # stays above the swing low
    return records


def bearish_ob_records() -> list[dict[str, Any]]:
    """Bearish OB at the BOS (c4), partial then wick-mitigation, no violation.

    - Swing low 9.9 at c2, swing high 10.25 at c5.
    - c6 closes 9.75 < 9.9 → bearish BOS @6; OB = c4 (last up-close),
      zone [9.95, 10.15], origin CONTINUATION.
    - c9 enters the zone (partial), c10 wicks through 10.15 (MITIGATED,
      close back inside → never VIOLATED).
    """
    return [
        make_candle(0, 10.5, 10.6, 10.3, 10.4),
        make_candle(1, 10.4, 10.45, 10.06, 10.15),
        make_candle(2, 10.15, 10.2, 9.9, 9.95),  # swing low 9.9
        make_candle(3, 10.0, 10.05, 9.92, 9.97),  # down-close (keeps OB single-candle)
        make_candle(4, 9.97, 10.15, 9.95, 10.1),  # OB candle (up-close)
        make_candle(5, 10.2, 10.25, 10.0, 10.05),  # swing high 10.25, down-close
        make_candle(6, 10.05, 10.1, 9.7, 9.75),  # displacement → BOS @6
        make_candle(7, 9.75, 9.8, 9.4, 9.45),
        make_candle(8, 9.45, 9.6, 9.3, 9.5),
        make_candle(9, 9.5, 10.0, 9.45, 9.9),  # enters OB zone (partial)
        make_candle(10, 9.9, 10.2, 9.85, 10.1),  # wick through 10.15 → MITIGATED
        make_candle(11, 10.1, 10.12, 9.8, 9.9),
    ]


def refined_ob_records() -> list[dict[str, Any]]:
    """Bullish OB whose candle range exceeds 2 x ATR → refined zone emitted.

    - Swing high 10.5 at c2; c4 is a huge down-close candle
      (range 0.99 > 2 x ATR[4] ~ 0.96) and the swing low.
    - c6 closes 10.7 > 10.5 → bullish BOS @6; OB = c4, zone [9.5, 10.49],
      refined zone [9.5, 9.995] (lowest 50% of the range).
    """
    return [
        make_candle(0, 10.0, 10.1, 9.95, 10.05),
        make_candle(1, 10.05, 10.3, 10.0, 10.25),
        make_candle(2, 10.25, 10.5, 10.2, 10.45),  # swing high 10.5
        make_candle(3, 10.4, 10.48, 10.3, 10.45),  # up-close (keeps OB single-candle)
        make_candle(4, 10.45, 10.49, 9.5, 9.7),  # huge OB candle + swing low
        make_candle(5, 9.7, 10.28, 9.65, 10.26),  # up-close
        make_candle(6, 10.26, 10.8, 10.05, 10.7),  # displacement → BOS @6
        make_candle(7, 10.7, 10.9, 10.6, 10.8),
        make_candle(8, 10.8, 11.0, 10.7, 10.9),
    ]


def mb_sweep_records() -> list[dict[str, Any]]:
    """Mitigation block: equal highs swept (GRAB/stop-hunt) without a BOS.

    - Swing high 10.5 at c2 and 10.49 at c8 → equal highs; swing low 10.0 at
      c5 (the failed-leg origin).
    - c12 wicks 10.75 through the pool, closes back inside → sweep without a
      structure break → bullish mitigation block on the c5 candle, zone
      [10.0, 10.15].
    - c14 enters the zone, c15 wicks through 10.0 → MITIGATED (close inside).
    """
    return [
        make_candle(0, 10.0, 10.15, 9.95, 10.1),
        make_candle(1, 10.1, 10.3, 10.05, 10.25),
        make_candle(2, 10.25, 10.5, 10.2, 10.45),  # swing high 10.5
        make_candle(3, 10.44, 10.44, 10.15, 10.2),
        make_candle(4, 10.2, 10.3, 10.05, 10.1),
        make_candle(5, 10.05, 10.15, 10.0, 10.1),  # swing low 10.0 (MB origin)
        make_candle(6, 10.1, 10.3, 10.1, 10.25),
        make_candle(7, 10.15, 10.3, 10.1, 10.25),
        make_candle(8, 10.28, 10.49, 10.2, 10.45),  # swing high 10.49 (equal highs)
        make_candle(9, 10.42, 10.44, 10.2, 10.3),
        make_candle(10, 10.3, 10.35, 10.15, 10.25),
        make_candle(11, 10.25, 10.3, 10.1, 10.2),
        make_candle(12, 10.25, 10.75, 10.2, 10.35),  # sweep: wick 10.75, close inside
        make_candle(13, 10.35, 10.4, 10.15, 10.2),
        make_candle(14, 10.2, 10.25, 10.05, 10.1),  # enters MB zone
        make_candle(15, 10.1, 10.12, 9.95, 10.02),  # wick through 10.0 → MITIGATED
    ]


def rbd_records() -> list[dict[str, Any]]:
    """Rally-base-drop: supply zone at the c7 doji, tested once on revisit.

    - Rally c3→c7, one-candle base (doji body 0.02) at swing high 10.62,
      strong drop to 9.6 (impulse) → SUPPLY zone [10.52, 10.62].
    - Actionable at c14 (swing c11 confirmed); c14 wicks 10.55 into the zone
      → TESTED, tests=1. The drop also breaks the c3 swing low → bearish OB
      whose zone overlaps the supply zone (duplicate link).
    """
    return [
        make_candle(0, 10.6, 10.65, 10.45, 10.5),
        make_candle(1, 10.5, 10.55, 10.3, 10.35),
        make_candle(2, 10.35, 10.4, 10.15, 10.2),
        make_candle(3, 10.2, 10.25, 10.0, 10.05),  # swing low 10.0
        make_candle(4, 10.05, 10.2, 10.05, 10.18),  # rally
        make_candle(5, 10.18, 10.4, 10.15, 10.38),
        make_candle(6, 10.38, 10.6, 10.35, 10.58),
        make_candle(7, 10.58, 10.62, 10.52, 10.56),  # base doji, swing high 10.62
        make_candle(8, 10.56, 10.58, 10.3, 10.32),  # drop
        make_candle(9, 10.32, 10.35, 10.05, 10.08),
        make_candle(10, 10.08, 10.1, 9.8, 9.85),
        make_candle(11, 9.85, 9.9, 9.6, 9.65),  # swing low 9.6
        make_candle(12, 9.65, 9.95, 9.65, 9.9),
        make_candle(13, 9.9, 10.1, 9.9, 10.05),
        make_candle(14, 10.05, 10.55, 10.05, 10.3),  # wick into zone → TESTED
        make_candle(15, 10.3, 10.35, 10.1, 10.15),
    ]


def dbr_records() -> list[dict[str, Any]]:
    """Drop-base-rally: demand zone at the c7 doji, tested once on revisit.

    - Drop c3→c7, one-candle base (doji body 0.02) at swing low 9.85, strong
      rally to 10.65 (impulse) → DEMAND zone [9.85, 9.95].
    - Actionable at c14; c14 dips 9.9 into the zone → TESTED, tests=1; c15
      stays inside without breaking (no second test).
    """
    return [
        make_candle(0, 9.9, 10.05, 9.85, 10.0),
        make_candle(1, 10.0, 10.2, 9.95, 10.15),
        make_candle(2, 10.15, 10.35, 10.1, 10.3),
        make_candle(3, 10.3, 10.5, 10.25, 10.45),  # swing high 10.5
        make_candle(4, 10.45, 10.45, 10.2, 10.25),  # drop
        make_candle(5, 10.25, 10.28, 10.0, 10.05),
        make_candle(6, 10.05, 10.1, 9.88, 9.9),
        make_candle(7, 9.9, 9.95, 9.85, 9.92),  # base doji, swing low 9.85
        make_candle(8, 9.92, 10.1, 9.9, 10.05),  # rally
        make_candle(9, 10.05, 10.3, 10.0, 10.25),
        make_candle(10, 10.25, 10.5, 10.2, 10.45),
        make_candle(11, 10.45, 10.65, 10.4, 10.6),  # swing high 10.65
        make_candle(12, 10.6, 10.62, 10.3, 10.35),
        make_candle(13, 10.35, 10.4, 10.1, 10.15),
        make_candle(14, 10.15, 10.2, 9.9, 9.95),  # dips into zone → TESTED
        make_candle(15, 9.95, 10.05, 9.87, 10.0),  # inside zone, no break
    ]
