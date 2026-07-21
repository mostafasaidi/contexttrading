"""Deterministic timeframe resampling (downsampling only).

Anchoring (all UTC, no lookahead):
    - Up to ``1d``: bars align to the Unix epoch —
      ``start = floor(ts / tf_seconds) * tf_seconds``.
    - ``1w``: bars start Monday 00:00 UTC (1970-01-05, epoch day 4).
    - ``1M``: bars start on the calendar month's first day, 00:00 UTC.

Aggregation is first/max/min/last/sum for O/H/L/C/V. Empty buckets emit no
bar (no phantom candles). Only the LAST bucket may be incomplete: when the
source series ends before the bucket's end, its bar carries
``is_closed=False`` and can be dropped via ``include_incomplete=False``.
Upsampling (target <= source) raises :class:`DataError`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from contexttrading.core.constants import Timeframe
from contexttrading.core.errors import DataError
from contexttrading.models.candle import Candle, CandleSeries

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
#: Epoch day index of the first Monday (1970-01-05).
_MONDAY_EPOCH_DAY = 4


def bucket_start(ts: datetime, target: Timeframe) -> datetime:
    """Anchored UTC start of the bucket containing ``ts``."""
    if target is Timeframe.MN1:
        return datetime(ts.year, ts.month, 1, tzinfo=UTC)
    if target is Timeframe.W1:
        days = (ts - _EPOCH).days
        week = (days - _MONDAY_EPOCH_DAY) // 7
        return _EPOCH + timedelta(days=_MONDAY_EPOCH_DAY + 7 * week)
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % target.seconds), UTC)


def bucket_end(start: datetime, target: Timeframe) -> datetime:
    """Exclusive UTC end of the bucket starting at ``start``."""
    if target is Timeframe.MN1:
        if start.month == 12:
            return datetime(start.year + 1, 1, 1, tzinfo=UTC)
        return datetime(start.year, start.month + 1, 1, tzinfo=UTC)
    return start + timedelta(seconds=target.seconds)


def resample_series(
    series: CandleSeries,
    target: Timeframe | str,
    *,
    include_incomplete: bool = True,
) -> CandleSeries:
    """Aggregate a series into a higher timeframe.

    Args:
        series: Source candles (chronological, UTC).
        target: Target timeframe (strictly larger than the source).
        include_incomplete: Keep the still-forming last bar
            (``is_closed=False``) when the final bucket is not fully covered.

    Returns:
        A new :class:`CandleSeries` at the target timeframe, preserving
        symbol and timezone metadata.

    Raises:
        DataError: On upsampling or same-timeframe requests.
    """
    tf = Timeframe.parse(target) if isinstance(target, str) else target
    source = series.timeframe
    if tf.seconds <= source.seconds:
        raise DataError(
            "Resampling requires a strictly higher timeframe",
            context={"source": str(source), "target": str(tf)},
        )
    if len(series) == 0:
        return CandleSeries(
            [], symbol=series.symbol, timeframe=tf, timezone_name=series.timezone_name
        )

    buckets: list[tuple[datetime, list[Candle]]] = []
    for candle in series:
        start = bucket_start(candle.timestamp, tf)
        if buckets and buckets[-1][0] == start:
            buckets[-1][1].append(candle)
        else:
            buckets.append((start, [candle]))

    last_candle_ts = series.candles[-1].timestamp
    out: list[Candle] = []
    for start, members in buckets:
        end = bucket_end(start, tf)
        complete = last_candle_ts >= end - timedelta(seconds=source.seconds)
        if not complete and not include_incomplete:
            continue
        tick_counts = [m.tick_count for m in members]
        ticks = (
            sum(t for t in tick_counts if t is not None)
            if all(t is not None for t in tick_counts)
            else None
        )
        out.append(
            Candle(
                timestamp=start,
                open=members[0].open,
                high=max(m.high for m in members),
                low=min(m.low for m in members),
                close=members[-1].close,
                volume=sum(m.volume for m in members),
                tick_count=ticks,
                is_closed=complete,
            )
        )
    return CandleSeries(out, symbol=series.symbol, timeframe=tf, timezone_name=series.timezone_name)
