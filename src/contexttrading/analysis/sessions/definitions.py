"""Session window definitions and calendar helpers.

Windows come from :class:`SessionConfig` as ``HH:MM`` strings in the
configured timezone. All matching converts candle timestamps (UTC) into
that timezone — determinism comes from candle timestamps only, never from
wall-clock.

A window may wrap midnight (e.g. Sydney 21:00-06:00). A session *instance*
belongs to the calendar date of its START bar, so a wrapped window that
starts at 21:00 on Monday and ends at 06:00 Tuesday is the Monday instance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from contexttrading.core.config import SessionConfig


@dataclass(frozen=True)
class SessionWindow:
    """A resolved session/killzone window in minutes-of-day."""

    name: str
    start_minute: int  # minutes after 00:00 in the session timezone
    end_minute: int  # exclusive; may be <= start_minute (wraps midnight)
    is_killzone: bool

    @property
    def wraps_midnight(self) -> bool:
        """True when the window crosses 00:00 in the session timezone."""
        return self.end_minute <= self.start_minute

    def contains(self, minute_of_day: int) -> bool:
        """Half-open membership test for a minute-of-day."""
        if self.wraps_midnight:
            return minute_of_day >= self.start_minute or minute_of_day < self.end_minute
        return self.start_minute <= minute_of_day < self.end_minute


def _parse_hhmm(raw: str) -> int:
    hour, minute = raw.split(":")
    return int(hour) * 60 + int(minute)


def resolve_windows(config: SessionConfig) -> list[SessionWindow]:
    """Resolve configured sessions and killzones into sorted windows.

    Sessions come first (config order), then killzones; within each group
    the configured insertion order is preserved for determinism.
    """
    windows = [
        SessionWindow(
            name=name,
            start_minute=_parse_hhmm(w["start"]),
            end_minute=_parse_hhmm(w["end"]),
            is_killzone=False,
        )
        for name, w in config.sessions.items()
    ]
    windows.extend(
        SessionWindow(
            name=name,
            start_minute=_parse_hhmm(w["start"]),
            end_minute=_parse_hhmm(w["end"]),
            is_killzone=True,
        )
        for name, w in config.killzones.items()
    )
    return windows


def window_instances(
    timestamps: list[datetime],
    window: SessionWindow,
    tz,
) -> list[tuple[date, int, int]]:
    """Assign candle indices to session instances of one window.

    Args:
        timestamps: UTC candle timestamps (chronological).
        window: The window to match.
        tz: Timezone the window is defined in.

    Returns:
        ``[(trading_date, first_index, last_index), ...]`` in chronological
        order. ``trading_date`` is the calendar date (in ``tz``) of the
        instance's start bar. An instance closes when a candle falls outside
        the window (or the series ends).
    """
    instances: list[tuple[date, int, int]] = []
    open_start: int | None = None
    open_date: date | None = None
    prev_in = False
    for i, ts in enumerate(timestamps):
        local = ts.astimezone(tz)
        minute = local.hour * 60 + local.minute
        inside = window.contains(minute)
        if inside and not prev_in:
            open_start = i
            # Wrapped windows: bars after midnight belong to the date of the
            # start bar, i.e. the PREVIOUS local calendar date.
            if window.wraps_midnight and minute < window.end_minute:
                open_date = local.date() - timedelta(days=1)
            else:
                open_date = local.date()
        elif not inside and prev_in and open_start is not None and open_date is not None:
            instances.append((open_date, open_start, i - 1))
            open_start = None
            open_date = None
        prev_in = inside
    if prev_in and open_start is not None and open_date is not None:
        instances.append((open_date, open_start, len(timestamps) - 1))
    return instances


def day_bounds(day: date, tz) -> tuple[datetime, datetime]:
    """UTC ``[start, end)`` bounds of a calendar date in the session timezone."""
    start = datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)
    end = start + timedelta(days=1)
    return start, end


def trading_days(timestamps: list[datetime], tz) -> list[date]:
    """Sorted calendar dates (in ``tz``) covered by the series."""
    return sorted({ts.astimezone(tz).date() for ts in timestamps})
