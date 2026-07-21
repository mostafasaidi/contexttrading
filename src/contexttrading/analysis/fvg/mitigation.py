"""FVG mitigation lifecycle and deterministic strength scoring.

Lifecycle (chronological, per candle, per active FVG)
------------------------------------------------------
Zone ``[bottom, top]``; for **bullish** FVGs price mitigates from above, for
**bearish** from below (mirrored rules):

- **entry**: any trade into the zone (bullish: ``low <= top``; wicks count).
- **fill fraction** for a candle: how deep it traded into the zone —
  bullish: ``(top - max(low, bottom)) / (top - bottom)``, clamped to [0, 1].
- **FILLED** (``MITIGATED``): trade *through* the far side
  (bullish: ``low <= bottom``).
- **INVERSE** (``VIOLATED``): *close* through the far side
  (bullish: ``close < bottom``). Implies filled; terminal.
- ``age``: candles from ``formation_end_index`` to the fill candle (or the
  last candle when unresolved).

Strength score (all weights in :class:`EngineConfig`)
------------------------------------------------------
::

    strength = clamp01(
        w_gap    * min(gap_atr / fvg_gap_atr_cap, 1)     # 0.5 when ATR warmup
      + w_disp   * disp_score      # BOS: strong 1.0 / weak 0.5 / false 0.25 / none 0
      + w_fresh  * fresh_score     # untouched 1 / partial 0.5 / filled 0.1 / violated 0
      + w_age    * 0.5 ** (age / fvg_strength_half_life)
      + w_struct * struct_bonus    # nested 0.5 + stacked 0.5, capped at 1.0
    )

Ranking: strength desc, tie-break by ``formation_end_index`` asc — fully
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from contexttrading.analysis.fvg.detection import RawFVG
from contexttrading.analysis.fvg.inversion import (
    closes_through_far_side,
    trades_through_far_side,
)
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BreakStrength,
    MitigationStatus,
    TrendDirection,
)
from contexttrading.models.candle import Candle
from contexttrading.models.structure import StructureBreak

_DISPLACEMENT_SCORE = {
    BreakStrength.STRONG: 1.0,
    BreakStrength.WEAK: 0.5,
    BreakStrength.FALSE: 0.25,
}
_FRESHNESS_SCORE = {
    MitigationStatus.UNMITIGATED: 1.0,
    MitigationStatus.PARTIALLY_MITIGATED: 0.5,
    MitigationStatus.MITIGATED: 0.1,
    MitigationStatus.VIOLATED: 0.0,
}


@dataclass
class LifecycleState:
    """Mutable per-FVG scan state (finalized into the FVG model afterwards)."""

    status: MitigationStatus = MitigationStatus.UNMITIGATED
    first_touch_index: int | None = None
    filled_index: int | None = None
    max_fill_fraction: float = 0.0
    touches: int = 0
    is_inverse: bool = False
    inversion_index: int | None = None

    @property
    def active(self) -> bool:
        """Still eligible for nested parenting / further transitions."""
        return self.status in (
            MitigationStatus.UNMITIGATED,
            MitigationStatus.PARTIALLY_MITIGATED,
        )


def update_state(state: LifecycleState, raw: RawFVG, candle: Candle, index: int) -> None:
    """Advance one FVG's lifecycle by one candle (in place).

    Order: entry/fill bookkeeping first (wick semantics), then inversion
    (close semantics). Transitions are monotonic
    (UNMITIGATED → PARTIALLY_MITIGATED → MITIGATED → VIOLATED); a
    wick-filled (MITIGATED) zone can still invert on a later close-through.
    """
    if state.status is MitigationStatus.VIOLATED:
        return
    if state.status is MitigationStatus.MITIGATED:
        # Already filled by a wick; only a close-through can still invert it.
        if closes_through_far_side(raw.direction, raw.zone_bottom, raw.zone_top, candle):
            state.is_inverse = True
            state.inversion_index = index
            state.status = MitigationStatus.VIOLATED
        return
    bullish = raw.direction is TrendDirection.BULLISH
    entered = candle.low <= raw.zone_top if bullish else candle.high >= raw.zone_bottom
    if not entered:
        return

    state.touches += 1
    if state.first_touch_index is None:
        state.first_touch_index = index

    size = raw.zone_top - raw.zone_bottom
    if bullish:
        depth = raw.zone_top - max(candle.low, raw.zone_bottom)
    else:
        depth = min(candle.high, raw.zone_top) - raw.zone_bottom
    fraction = min(max(depth / size, 0.0), 1.0)
    state.max_fill_fraction = max(state.max_fill_fraction, fraction)

    if trades_through_far_side(raw.direction, raw.zone_bottom, raw.zone_top, candle):
        state.max_fill_fraction = 1.0
        state.filled_index = index
        state.status = MitigationStatus.MITIGATED
        if closes_through_far_side(raw.direction, raw.zone_bottom, raw.zone_top, candle):
            state.is_inverse = True
            state.inversion_index = index
            state.status = MitigationStatus.VIOLATED
    elif state.status is MitigationStatus.UNMITIGATED:
        state.status = MitigationStatus.PARTIALLY_MITIGATED


def displacement_score(linked: StructureBreak | None) -> float:
    """Displacement component from a linked structure break."""
    if linked is None:
        return 0.0
    return _DISPLACEMENT_SCORE[linked.strength]


def freshness_score(status: MitigationStatus) -> float:
    """Freshness component from the final mitigation status."""
    return _FRESHNESS_SCORE[status]


def age_score(age: int, half_life: int) -> float:
    """Exponential age decay: 0.5 ** (age / half_life)."""
    return 0.5 ** (age / half_life)


def structure_bonus(is_nested: bool, is_stacked: bool) -> float:
    """Nested/stacked bonus, capped at 1.0 (0.5 each)."""
    return min(0.5 * int(is_nested) + 0.5 * int(is_stacked), 1.0)


def strength_score(
    *,
    gap_atr: float | None,
    linked: StructureBreak | None,
    status: MitigationStatus,
    age: int,
    is_nested: bool,
    is_stacked: bool,
    config: EngineConfig,
) -> float:
    """Deterministic FVG strength in [0, 1] (formula in module docstring)."""
    gap_component = min(gap_atr / config.fvg_gap_atr_cap, 1.0) if gap_atr is not None else 0.5
    score = (
        config.fvg_weight_gap * gap_component
        + config.fvg_weight_displacement * displacement_score(linked)
        + config.fvg_weight_freshness * freshness_score(status)
        + config.fvg_weight_age * age_score(age, config.fvg_strength_half_life)
        + config.fvg_weight_structure * structure_bonus(is_nested, is_stacked)
    )
    return min(max(score, 0.0), 1.0)
