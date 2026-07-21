"""Session tracking: instance statistics, session-derived pools, Judas sweeps.

Pipeline (all chronological, all derived from candle timestamps only):

1. Resolve configured windows and assign candles to session instances.
2. Accumulate OHLCV statistics per instance; mark which instance printed
   each calendar day's high/low.
3. Synthesize liquidity pools from completed instances (session high/low),
   the Asian range (Sydney + Tokyo before the London open), and previous
   day high/low — then let the existing sweep machinery resolve them.
4. Classify sweeps of Asian levels during the London killzone and of
   London levels during the New York killzones as Judas swings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise

from contexttrading.analysis.sessions.definitions import (
    SessionWindow,
    window_instances,
)
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    LiquidityPoolKind,
    LiquiditySide,
    SwingClass,
    TrendDirection,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.liquidity import LiquidityPool, LiquiditySweep
from contexttrading.models.session import (
    SessionStats,
    SessionSweep,
    judas_style,
    session_style,
)

#: Session names (in SessionConfig.sessions) that accumulate the Asian range.
ASIA_SESSION_NAMES: tuple[str, ...] = ("sydney", "tokyo")
#: Session whose open bounds the Asian range, and its sweep killzone.
LONDON_SESSION_NAME = "london"
LONDON_KILLZONE_NAME = "london"
#: Killzones during which a London-level sweep is a Judas swing.
NEW_YORK_KILLZONE_NAMES: tuple[str, ...] = ("new_york_am", "new_york_pm")


@dataclass
class _Instance:
    """Internal accumulator for one session instance."""

    window: SessionWindow
    trading_date: date
    start_index: int
    end_index: int
    open: float
    high: float
    low: float
    close: float
    high_index: int
    low_index: int
    volume: float


def _track_instances(series: CandleSeries, window: SessionWindow, tz) -> list[_Instance]:
    candles = series.candles
    timestamps = [c.timestamp for c in candles]
    instances: list[_Instance] = []
    for trading_date, first, last in window_instances(timestamps, window, tz):
        segment = candles[first : last + 1]
        high = max(c.high for c in segment)
        low = min(c.low for c in segment)
        high_index = next(first + k for k, c in enumerate(segment) if c.high == high)
        low_index = next(first + k for k, c in enumerate(segment) if c.low == low)
        instances.append(
            _Instance(
                window=window,
                trading_date=trading_date,
                start_index=first,
                end_index=last,
                open=segment[0].open,
                high=high,
                low=low,
                close=segment[-1].close,
                high_index=high_index,
                low_index=low_index,
                volume=sum(c.volume for c in segment),
            )
        )
    return instances


def _direction(inst: _Instance, doji_fraction: float) -> TrendDirection:
    span = inst.high - inst.low
    body = inst.close - inst.open
    if span > 0 and abs(body) < doji_fraction * span:
        return TrendDirection.RANGING
    if body > 0:
        return TrendDirection.BULLISH
    if body < 0:
        return TrendDirection.BEARISH
    return TrendDirection.RANGING


@dataclass(frozen=True)
class DayLevels:
    """Calendar-day extremes in the session timezone."""

    day: date
    high: float
    low: float
    first_index: int
    last_index: int


def compute_day_levels(series: CandleSeries, tz) -> list[DayLevels]:
    """Per-calendar-day high/low with candle-index bounds (chronological)."""
    candles = series.candles
    days: dict[date, list[int]] = {}
    for i, c in enumerate(candles):
        days.setdefault(c.timestamp.astimezone(tz).date(), []).append(i)
    levels: list[DayLevels] = []
    for day in sorted(days):
        idx = days[day]
        levels.append(
            DayLevels(
                day=day,
                high=max(candles[i].high for i in idx),
                low=min(candles[i].low for i in idx),
                first_index=idx[0],
                last_index=idx[-1],
            )
        )
    return levels


def compute_asian_ranges(
    series: CandleSeries,
    windows: list[SessionWindow],
    tz,
) -> list[_Instance]:
    """Asian range per trading day: Sydney + Tokyo before the London open.

    For each calendar day ``D`` with a configured London session, the range
    spans candles inside the Sydney or Tokyo windows with local timestamps
    in ``[london_open(D) - 12h, london_open(D))``. No range is emitted when
    the contributing sessions are not configured or no candles qualify.
    """
    asia_windows = [w for w in windows if not w.is_killzone and w.name in ASIA_SESSION_NAMES]
    london = next((w for w in windows if not w.is_killzone and w.name == LONDON_SESSION_NAME), None)
    if not asia_windows or london is None:
        return []
    candles = series.candles
    days = sorted({c.timestamp.astimezone(tz).date() for c in candles})
    ranges: list[_Instance] = []
    asia_window = SessionWindow(
        name="asia",
        start_minute=asia_windows[0].start_minute,
        end_minute=asia_windows[0].end_minute,
        is_killzone=False,
    )
    for day in days:
        london_open = datetime.combine(
            day, time(london.start_minute // 60, london.start_minute % 60), tzinfo=tz
        )
        span_start = (london_open - timedelta(hours=12)).astimezone(UTC)
        span_end = london_open.astimezone(UTC)
        indices = [
            i
            for i, c in enumerate(candles)
            if span_start <= c.timestamp < span_end
            and any(
                w.contains((local := c.timestamp.astimezone(tz)).hour * 60 + local.minute)
                for w in asia_windows
            )
        ]
        if not indices:
            continue
        segment = [candles[i] for i in indices]
        high = max(c.high for c in segment)
        low = min(c.low for c in segment)
        ranges.append(
            _Instance(
                window=asia_window,
                trading_date=day,
                start_index=indices[0],
                end_index=indices[-1],
                open=segment[0].open,
                high=high,
                low=low,
                close=segment[-1].close,
                high_index=next(i for i in indices if candles[i].high == high),
                low_index=next(i for i in indices if candles[i].low == low),
                volume=sum(c.volume for c in segment),
            )
        )
    return ranges


def build_session_stats(
    instances: list[_Instance],
    series: CandleSeries,
    day_levels: list[DayLevels],
    atr_values: tuple[float | None, ...],
    config: EngineConfig,
    tz,
) -> list[SessionStats]:
    """Materialize instances as SessionStats with day-extreme flags.

    ``forms_day_high``/``forms_day_low`` compare the instance extreme with
    the calendar-day extreme (in the session timezone) of the date on which
    that extreme candle printed — exact float equality is safe because both
    values come from the same candles.
    """
    candles = series.candles
    by_day = {d.day: d for d in day_levels}
    stats: list[SessionStats] = []
    for inst in instances:
        atr_at = atr_values[inst.end_index] if inst.end_index < len(atr_values) else None
        span = inst.high - inst.low
        high_day = by_day.get(candles[inst.high_index].timestamp.astimezone(tz).date())
        low_day = by_day.get(candles[inst.low_index].timestamp.astimezone(tz).date())
        stats.append(
            SessionStats(
                session=inst.window.name,
                is_killzone=inst.window.is_killzone,
                trading_date=inst.trading_date,
                start_time=candles[inst.start_index].timestamp,
                end_time=candles[inst.end_index].timestamp,
                open=inst.open,
                high=inst.high,
                low=inst.low,
                close=inst.close,
                high_index=inst.high_index,
                low_index=inst.low_index,
                candle_count=inst.end_index - inst.start_index + 1,
                volume=inst.volume,
                direction=_direction(inst, config.session_doji_body_fraction),
                range_atr=(span / atr_at) if atr_at else None,
                forms_day_high=high_day is not None and inst.high == high_day.high,
                forms_day_low=low_day is not None and inst.low == low_day.low,
                style=session_style(inst.window.name, inst.window.is_killzone),
            )
        )
    return stats


def build_session_pools(
    instances: list[_Instance],
    asian_ranges: list[_Instance],
    day_levels: list[DayLevels],
    stats_ids: dict[tuple[str, date, int], str],
) -> tuple[list[LiquidityPool], dict[str, str]]:
    """Synthesize liquidity pools from session levels.

    Returns:
        ``(pools, groups)`` where ``groups`` maps pool id to its origin
        group (``"asia"``, a session name, or ``"day"``) used by the Judas
        classifier. Pools activate at ``formed_at_index + 1``: the level is
        known only once its instance/day is complete.
    """
    pools: list[LiquidityPool] = []
    groups: dict[str, str] = {}

    def add(
        price: float,
        side: LiquiditySide,
        kind: LiquidityPoolKind,
        source_ids: list[str],
        formed: int,
        group: str,
    ) -> None:
        pool = LiquidityPool(
            price=price,
            side=side,
            kind=kind,
            pool_class=SwingClass.EXTERNAL,
            source_ids=source_ids,
            formed_at_index=formed,
        )
        pools.append(pool)
        groups[pool.id] = group

    for inst in [*instances, *asian_ranges]:
        if inst.window.is_killzone:
            continue
        source = [stats_ids[(inst.window.name, inst.trading_date, inst.start_index)]]
        group = "asia" if inst.window.name == "asia" else inst.window.name
        add(
            inst.high,
            LiquiditySide.BUYSIDE,
            LiquidityPoolKind.SESSION_HIGH,
            source,
            inst.end_index,
            group,
        )
        add(
            inst.low,
            LiquiditySide.SELLSIDE,
            LiquidityPoolKind.SESSION_LOW,
            source,
            inst.end_index,
            group,
        )

    for prev_day, day in pairwise(day_levels):
        source = [f"day:{prev_day.day.isoformat()}"]
        formed = day.first_index - 1
        add(
            prev_day.high,
            LiquiditySide.BUYSIDE,
            LiquidityPoolKind.PREVIOUS_DAY_HIGH,
            source,
            formed,
            "day",
        )
        add(
            prev_day.low,
            LiquiditySide.SELLSIDE,
            LiquidityPoolKind.PREVIOUS_DAY_LOW,
            source,
            formed,
            "day",
        )
    return pools, groups


def killzone_at(timestamp: datetime, killzones: list[SessionWindow], tz) -> str | None:
    """Name of the first killzone containing the timestamp, else None."""
    local = timestamp.astimezone(tz)
    minute = local.hour * 60 + local.minute
    for kz in killzones:
        if kz.contains(minute):
            return kz.name
    return None


def detect_judas_swings(
    sweeps: list[LiquiditySweep],
    pool_groups: dict[str, str],
    killzones: list[SessionWindow],
    tz,
) -> list[SessionSweep]:
    """Classify Judas swings from sweeps of session-derived pools.

    Patterns:
        - ``asia`` level swept during the London killzone;
        - ``london`` level swept during the New York killzones.
    """
    found: list[SessionSweep] = []
    for sweep in sweeps:
        group = pool_groups.get(sweep.pool_id)
        if group not in ("asia", LONDON_SESSION_NAME):
            continue
        kz = killzone_at(sweep.timestamp, killzones, tz)
        if kz is None:
            continue
        judas = (group == "asia" and kz == LONDON_KILLZONE_NAME) or (
            group == LONDON_SESSION_NAME and kz in NEW_YORK_KILLZONE_NAMES
        )
        if not judas:
            continue
        # Recover the pool kind from the sweep's side: buyside sweeps hit
        # highs, sellside sweeps hit lows. Day pools keep their own kinds.
        kind = (
            LiquidityPoolKind.SESSION_HIGH
            if sweep.side is LiquiditySide.BUYSIDE
            else LiquidityPoolKind.SESSION_LOW
        )
        found.append(
            SessionSweep(
                swept_group=group,
                swept_level_kind=kind,
                swept_price=sweep.pool_price,
                side=sweep.side,
                sweeping_window=kz,
                candle_index=sweep.candle_index,
                timestamp=sweep.timestamp,
                linked_sweep_id=sweep.id,
                style=judas_style(),
            )
        )
    return found
