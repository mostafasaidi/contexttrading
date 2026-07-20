"""Deterministic volatility & volume primitives.

These are the ONLY indicator-style computations in the engine. They are pure
functions over candle sequences with fixed iteration order — no wall-clock,
no randomness, no lookahead: rolling statistics at index ``i`` use only data
from indices ``< i`` (documented per function).

Conventions
-----------
- Functions return tuples aligned 1:1 with the input candles; positions
  without enough history carry ``None``.
- ATR uses Wilder smoothing: the first value sits at index ``period - 1``
  and equals the simple mean of ``TR[0..period-1]``; afterwards
  ``ATR[i] = (ATR[i-1] * (period - 1) + TR[i]) / period``.
- Standard deviations are population std (ddof=0) computed with a two-pass
  algorithm in index order.
"""

from __future__ import annotations

from collections.abc import Sequence

from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import Candle


def true_ranges(candles: Sequence[Candle]) -> tuple[float, ...]:
    """True range per candle.

    ``TR[0] = high - low``; afterwards
    ``TR[i] = max(high-low, |high - prev_close|, |low - prev_close|)``.
    """
    if not candles:
        return ()
    out = [candles[0].high - candles[0].low]
    for prev, cur in zip(candles, candles[1:], strict=False):
        out.append(
            max(
                cur.high - cur.low,
                abs(cur.high - prev.close),
                abs(cur.low - prev.close),
            )
        )
    return tuple(out)


def atr(candles: Sequence[Candle], period: int) -> tuple[float | None, ...]:
    """Wilder ATR aligned with ``candles``.

    Args:
        candles: Ordered candles.
        period: Smoothing period (>= 1).

    Returns:
        Tuple of ATR values; ``None`` for indices ``< period - 1``.

    Raises:
        ValueError: If ``period < 1``.
    """
    if period < 1:
        raise ValueError("ATR period must be >= 1")
    trs = true_ranges(candles)
    n = len(trs)
    out: list[float | None] = [None] * n
    if n < period:
        return tuple(out)
    first = sum(trs[:period]) / period
    out[period - 1] = first
    value = first
    for i in range(period, n):
        value = (value * (period - 1) + trs[i]) / period
        out[i] = value
    return tuple(out)


def latest_atr(candles: Sequence[Candle], period: int, *, min_candles: int = 1) -> float:
    """Most recent ATR value, or raise when unavailable.

    Args:
        candles: Ordered candles.
        period: ATR period.
        min_candles: Minimum series length required before computing.

    Raises:
        InsufficientDataError: If the series is too short for a value.
    """
    if len(candles) < max(min_candles, period):
        raise InsufficientDataError(
            "Not enough candles for ATR",
            context={"candles": len(candles), "period": period, "min_candles": min_candles},
        )
    values = atr(candles, period)
    for value in reversed(values):
        if value is not None:
            return value
    raise InsufficientDataError(  # pragma: no cover - guarded above
        "ATR unavailable", context={"candles": len(candles), "period": period}
    )


def rolling_mean(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    """Rolling simple mean including the current element.

    ``None`` for indices ``< window - 1``. Computed with a running sum in
    index order (fixed float-addition sequence ⇒ deterministic).
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= window:
            running -= values[i - window]
        if i >= window - 1:
            out[i] = running / window
    return tuple(out)


def prior_rolling_mean(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    """Rolling mean of the ``window`` elements strictly before index ``i``.

    No lookahead: ``out[i]`` uses ``values[i-window : i]`` only.
    ``None`` for ``i < window``.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    out: list[float | None] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        if i >= window:
            out[i] = running / window
        running += v
        if i >= window - 1:
            running -= values[i - window + 1]
    return tuple(out)


def prior_rolling_std(values: Sequence[float], window: int) -> tuple[float | None, ...]:
    """Population std of the ``window`` elements strictly before index ``i``.

    Two-pass over each window in index order. ``None`` for ``i < window``.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    out: list[float | None] = [None] * len(values)
    means = prior_rolling_mean(values, window)
    for i in range(window, len(values)):
        mean = means[i]
        assert mean is not None  # guaranteed for i >= window
        segment = values[i - window : i]
        variance = sum((v - mean) ** 2 for v in segment) / window
        out[i] = variance**0.5
    return tuple(out)


def relative_volumes(candles: Sequence[Candle], window: int) -> tuple[float | None, ...]:
    """Volume divided by the prior-window mean volume (no lookahead).

    ``None`` when history is insufficient or the prior mean is zero.
    """
    volumes = [c.volume for c in candles]
    means = prior_rolling_mean(volumes, window)
    out: list[float | None] = []
    for c, mean in zip(candles, means, strict=False):
        if mean is None or mean == 0.0:
            out.append(None)
        else:
            out.append(c.volume / mean)
    return tuple(out)


def volume_zscores(candles: Sequence[Candle], window: int) -> tuple[float | None, ...]:
    """Z-score of each candle's volume vs the prior window (no lookahead).

    ``None`` when history is insufficient or the prior std is zero (flat
    volume ⇒ no meaningful z-score).
    """
    volumes = [c.volume for c in candles]
    means = prior_rolling_mean(volumes, window)
    stds = prior_rolling_std(volumes, window)
    out: list[float | None] = []
    for v, mean, std in zip(volumes, means, stds, strict=False):
        if mean is None or std is None or std == 0.0:
            out.append(None)
        else:
            out.append((v - mean) / std)
    return tuple(out)


def volume_imbalance_flags(
    candles: Sequence[Candle], window: int, threshold: float
) -> tuple[bool, ...]:
    """True where ``|volume z-score| >= threshold``.

    Candles without a valid z-score (insufficient history / flat volume) are
    flagged ``False``.
    """
    if threshold <= 0:
        raise ValueError("threshold must be > 0")
    return tuple(z is not None and abs(z) >= threshold for z in volume_zscores(candles, window))
