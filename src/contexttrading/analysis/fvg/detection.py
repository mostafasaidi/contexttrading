"""FVG detection: 3-candle imbalance, size filter, grouping, displacement.

Pattern
-------
- **Bullish FVG** at middle candle ``i``: ``low[i+1] > high[i-1]``;
  zone ``[high[i-1], low[i+1]]`` (bottom = high[i-1], top = low[i+1]).
- **Bearish FVG** at middle candle ``i``: ``high[i+1] < low[i-1]``;
  zone ``[high[i+1], low[i-1]]`` (bottom = high[i+1], top = low[i-1]).

An FVG is **confirmed at the close of candle i+1** and becomes trackable
from candle ``i+2`` onward (no lookahead).

Size filter: ``gap >= fvg_min_atr_fraction * ATR[i]`` (inclusive boundary).
During ATR warmup (``ATR[i] is None``) the filter is **skipped** — the FVG is
kept with ``gap_atr=None`` (documented conservative choice, mirroring the
Phase-3 strength fallback).

Grouping (evaluated at registration time by the lifecycle engine, since
"still-unfilled" is a chronological property):
- **Nested**: zone fully contained (inclusive) in an older, still-unfilled,
  same-direction FVG → ``parent`` = the *smallest* containing zone
  (deterministic tie-break: smaller size, then earlier formation).
- **Stacked**: per direction, FVGs sorted by formation index; consecutive
  FVGs within ``fvg_stacked_lookback`` candles whose zones overlap or are
  adjacent (inclusive interval intersection) chain into one group.
  ``stack_group_id`` is a content hash of the group's root (oldest member).

Displacement: ``link_displacement`` maps structure breaks by candle index;
the break at the FVG's middle candle wins, preferring confirmed STRONG over
WEAK over FALSE and MAJOR over MINOR (deterministic ordering).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BreakStrength,
    StructureBreakSignificance,
    TrendDirection,
)
from contexttrading.core.ids import deterministic_id
from contexttrading.models.candle import Candle, CandleSeries
from contexttrading.models.structure import StructureBreak


@dataclass
class RawFVG:
    """Pre-lifecycle FVG detection record (module-internal)."""

    direction: TrendDirection
    zone_bottom: float
    zone_top: float
    formation_start_index: int
    middle_index: int
    formation_end_index: int
    gap_size: float
    gap_atr: float | None
    gap_percent: float

    def contains(self, other: RawFVG) -> bool:
        """True when ``other``'s zone is fully (inclusively) contained."""
        return self.zone_bottom <= other.zone_bottom and other.zone_top <= self.zone_top

    def intersects(self, other: RawFVG) -> bool:
        """True when zones overlap or are adjacent (inclusive)."""
        return self.zone_bottom <= other.zone_top and other.zone_bottom <= self.zone_top


def detect_raw_fvgs(
    series: CandleSeries,
    atr_values: Sequence[float | None],
    config: EngineConfig,
) -> list[RawFVG]:
    """Detect raw 3-candle imbalances in chronological order.

    Args:
        series: Input candles.
        atr_values: ATR series aligned with candle indices (None in warmup).
        config: Thresholds (``fvg_min_atr_fraction``).

    Returns:
        Raw FVGs sorted by middle index.
    """
    candles = series.candles
    out: list[RawFVG] = []
    for i in range(1, len(candles) - 1):
        prev_, nxt = candles[i - 1], candles[i + 1]
        atr_at = atr_values[i] if i < len(atr_values) else None
        if nxt.low > prev_.high:  # bullish imbalance
            raw = _build(
                candles, i, TrendDirection.BULLISH, zone_bottom=prev_.high, zone_top=nxt.low
            )
        elif nxt.high < prev_.low:  # bearish imbalance
            raw = _build(
                candles, i, TrendDirection.BEARISH, zone_bottom=nxt.high, zone_top=prev_.low
            )
        else:
            continue
        if atr_at is not None and raw.gap_size < config.fvg_min_atr_fraction * atr_at:
            continue  # below minimum size (ATR available)
        out.append(raw)
    return out


def _build(
    candles: Sequence[Candle],
    i: int,
    direction: TrendDirection,
    *,
    zone_bottom: float,
    zone_top: float,
) -> RawFVG:
    gap = zone_top - zone_bottom
    mid_price = (zone_top + zone_bottom) / 2
    return RawFVG(
        direction=direction,
        zone_bottom=zone_bottom,
        zone_top=zone_top,
        formation_start_index=i - 1,
        middle_index=i,
        formation_end_index=i + 1,
        gap_size=gap,
        gap_atr=None,  # filled by caller context when ATR exists
        gap_percent=gap / mid_price,
    )


def with_atr(raw: RawFVG, atr_value: float | None) -> RawFVG:
    """Return a copy of ``raw`` with ``gap_atr`` set when ATR exists."""
    raw.gap_atr = raw.gap_size / atr_value if atr_value else None
    return raw


def find_parent(candidate: RawFVG, actives: Sequence[RawFVG]) -> RawFVG | None:
    """Smallest still-active same-direction FVG containing ``candidate``.

    Args:
        candidate: Newly registered FVG.
        actives: Older FVGs still unfilled/unviolated at registration time.

    Returns:
        The parent record, or None.
    """
    containers = [
        other
        for other in actives
        if other.direction is candidate.direction
        and other is not candidate
        and other.contains(candidate)
        and (other.zone_bottom, other.zone_top) != (candidate.zone_bottom, candidate.zone_top)
    ]
    if not containers:
        return None
    return min(
        containers,
        key=lambda o: (o.zone_top - o.zone_bottom, o.formation_end_index),
    )


def assign_stack_groups(fvgs: Sequence[RawFVG], lookback: int) -> dict[int, str]:
    """Chain same-direction FVGs into stacked groups.

    Args:
        fvgs: Raw FVGs (any order).
        lookback: Max candles between formation ends of consecutive members.

    Returns:
        Mapping ``id(raw) -> stack_group_id`` for grouped FVGs only
        (groups of one are not stacked).
    """
    groups: dict[int, str] = {}
    for direction in (TrendDirection.BULLISH, TrendDirection.BEARISH):
        ordered = sorted(
            (f for f in fvgs if f.direction is direction),
            key=lambda f: (f.formation_end_index, f.zone_bottom),
        )
        current: list[RawFVG] = []
        for raw in ordered:
            if (
                current
                and raw.formation_end_index - current[-1].formation_end_index <= lookback
                and raw.intersects(current[-1])
            ):
                current.append(raw)
            else:
                _flush_stack(current, groups)
                current = [raw]
        _flush_stack(current, groups)
    return groups


def _flush_stack(members: list[RawFVG], groups: dict[int, str]) -> None:
    if len(members) < 2:
        return
    root = members[0]
    group_id = deterministic_id(
        {
            "direction": root.direction.value,
            "formation_end_index": root.formation_end_index,
            "zone": [root.zone_bottom, root.zone_top],
        },
        prefix="fvgstack",
    )
    for member in members:
        groups[id(member)] = group_id


def link_displacement(
    raw: RawFVG, breaks_by_index: dict[int, list[StructureBreak]]
) -> StructureBreak | None:
    """Best structure break at the FVG's middle candle, if any.

    Preference order (deterministic): STRONG > WEAK > FALSE, then
    MAJOR > MINOR, then by break ID.
    """
    candidates = breaks_by_index.get(raw.middle_index, [])
    if not candidates:
        return None
    strength_rank = {
        BreakStrength.STRONG: 0,
        BreakStrength.WEAK: 1,
        BreakStrength.FALSE: 2,
    }
    significance_rank = {
        StructureBreakSignificance.MAJOR: 0,
        StructureBreakSignificance.MINOR: 1,
    }
    return min(
        candidates,
        key=lambda b: (strength_rank[b.strength], significance_rank[b.significance], b.id),
    )
