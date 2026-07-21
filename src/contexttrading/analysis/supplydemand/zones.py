"""Supply & demand zones: detection, lifecycle, and deterministic strength.

Zone sources
------------
- **OB-derived**: every order block maps to a zone (bullish OB → DEMAND,
  bearish OB → SUPPLY) over the OB's *active* zone (refined when refined).
- **Pattern (rally-base-drop / drop-base-rally)**: at an external swing where
  the leg direction reverses, a **base** = the run of 1-``sd_max_base_candles``
  consecutive candles ending at the swing whose bodies are all below
  ``sd_base_body_atr_fraction`` x ATR (runs longer than the max are ranges,
  not bases, and are skipped). The departure leg must be an IMPULSE leg with
  magnitude >= ``sd_departure_atr_multiple`` x ATR. Drop after rally → SUPPLY;
  rally after drop → DEMAND. Zones are actionable once the departure leg's
  end swing is confirmed (``end_index + external_swing_lookback``); zones
  whose departure is unconfirmed at series end are skipped.

Duplicate rule
--------------
A pattern zone is ``is_duplicate`` when a same-kind order block's active zone
overlaps it by ``intersection / min(heights) >= sd_duplicate_overlap_fraction``
— the OB is preferred and linked via ``linked_order_block_id``.

Lifecycle (chronological, first-touch)
--------------------------------------
``FRESH`` → ``TESTED`` (distinct re-entry that neither mitigates nor breaks;
``tests`` counts such visits) → terminal ``MITIGATED`` (traded through the
base, wick suffices) or ``BROKEN`` (closed through the base; takes precedence
when both happen on one candle).

Strength
--------
::

    strength = clamp01(
        w_dep    * min(departure_atr / sd_departure_atr_cap, 1)   # 0.5 in warmup
      + w_tight  * (1 - min(mean_base_body_atr / sd_base_body_atr_fraction, 1))
      + w_fresh  * (FRESH 1.0 / TESTED 0.5 / MITIGATED 0.1 / BROKEN 0.0)
      + w_tests  * 0.5 ** tests
      + w_trend  * (1.0 if aligned with external trend else 0.0)
      + w_age    * 0.5 ** (age / sd_strength_half_life)
    )

Ranking: strength desc, tie-break by ``base_end_index`` asc — deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from contexttrading.analysis.structure.structure import StructureScan
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    LegKind,
    SDZoneStatus,
    TrendDirection,
    ZoneType,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.orderblock import OrderBlock

_FRESHNESS_SCORE = {
    SDZoneStatus.FRESH: 1.0,
    SDZoneStatus.TESTED: 0.5,
    SDZoneStatus.MITIGATED: 0.1,
    SDZoneStatus.BROKEN: 0.0,
}


@dataclass
class RawZone:
    """Pre-lifecycle supply/demand zone (detection output)."""

    kind: ZoneType
    zone_bottom: float
    zone_top: float
    base_start_index: int
    base_end_index: int
    actionable_from_index: int
    departure_leg_id: str | None
    departure_atr_multiple: float | None
    mean_base_body_atr: float | None
    linked_order_block_id: str | None = None
    is_duplicate: bool = False


@dataclass
class ZoneState:
    """Mutable per-zone lifecycle scan state."""

    status: SDZoneStatus = SDZoneStatus.FRESH
    tests: int = 0
    first_touch_index: int | None = None
    mitigated_index: int | None = None
    broken_index: int | None = None


def detect_pattern_zones(
    series: CandleSeries,
    scan: StructureScan,
    config: EngineConfig,
) -> list[RawZone]:
    """Detect rally-base-drop / drop-base-rally zones at reversal swings."""
    candles = series.candles
    n = len(candles)
    legs_by_end = {leg.end_index: leg for leg in scan.legs}
    out: list[RawZone] = []

    for leg in scan.legs:
        if leg.kind is not LegKind.IMPULSE:
            continue
        if leg.atr_multiple is None or leg.atr_multiple < config.sd_departure_atr_multiple:
            continue
        prior = legs_by_end.get(leg.start_index)
        if prior is None or prior.direction is leg.direction:
            continue  # need a reversal shape (rally-base-drop / drop-base-rally)
        actionable = leg.end_index + config.external_swing_lookback
        if actionable > n - 1:
            continue  # departure swing unconfirmed at series end (no lookahead)

        # Base: candles ending at the shared swing, all small-body.
        swing = leg.start_index
        bodies: list[float] = []
        start = swing
        while start >= 0:
            atr_at = scan.atr_values[start]
            if atr_at is None or atr_at <= 0:
                break
            body = abs(candles[start].close - candles[start].open)
            if body >= config.sd_base_body_atr_fraction * atr_at:
                break
            bodies.append(body / atr_at)
            start -= 1
        base_len = swing - start
        if base_len == 0 or base_len > config.sd_max_base_candles:
            continue
        base = candles[start + 1 : swing + 1]
        zone_bottom = min(c.low for c in base)
        zone_top = max(c.high for c in base)
        if zone_top <= zone_bottom:
            continue

        kind = ZoneType.SUPPLY if leg.direction is TrendDirection.BEARISH else ZoneType.DEMAND
        out.append(
            RawZone(
                kind=kind,
                zone_bottom=zone_bottom,
                zone_top=zone_top,
                base_start_index=start + 1,
                base_end_index=swing,
                actionable_from_index=actionable,
                departure_leg_id=leg.id,
                departure_atr_multiple=leg.atr_multiple,
                mean_base_body_atr=sum(bodies) / len(bodies),
            )
        )
    return out


def zones_from_order_blocks(
    order_blocks: list[OrderBlock],
    scan: StructureScan,
) -> list[RawZone]:
    """Map every order block to a supply/demand zone over its active zone."""
    out: list[RawZone] = []
    for ob in order_blocks:
        kind = ZoneType.DEMAND if ob.direction is TrendDirection.BULLISH else ZoneType.SUPPLY
        if ob.is_refined and ob.refined_bottom is not None and ob.refined_top is not None:
            bottom, top = ob.refined_bottom, ob.refined_top
        else:
            bottom, top = ob.zone_bottom, ob.zone_top
        atr_at = scan.atr_values[ob.candle_index]
        body = ob.body_top - ob.body_bottom
        mean_body_atr = body / atr_at if atr_at else None
        out.append(
            RawZone(
                kind=kind,
                zone_bottom=bottom,
                zone_top=top,
                base_start_index=ob.cluster_start_index,
                base_end_index=ob.candle_index,
                actionable_from_index=ob.actionable_from_index,
                departure_leg_id=None,
                departure_atr_multiple=ob.displacement_margin_atr,
                mean_base_body_atr=mean_body_atr,
                linked_order_block_id=ob.id,
            )
        )
    return out


def mark_duplicates(
    pattern_zones: list[RawZone],
    order_blocks: list[OrderBlock],
    config: EngineConfig,
) -> None:
    """Flag pattern zones ~identical to an order block zone (in place)."""
    for zone in pattern_zones:
        if zone.linked_order_block_id is not None:
            continue
        height = zone.zone_top - zone.zone_bottom
        for ob in order_blocks:
            ob_kind = ZoneType.DEMAND if ob.direction is TrendDirection.BULLISH else ZoneType.SUPPLY
            if ob_kind is not zone.kind:
                continue
            if ob.is_refined and ob.refined_bottom is not None and ob.refined_top is not None:
                ob_bottom, ob_top = ob.refined_bottom, ob.refined_top
            else:
                ob_bottom, ob_top = ob.zone_bottom, ob.zone_top
            overlap = min(zone.zone_top, ob_top) - max(zone.zone_bottom, ob_bottom)
            smaller = min(height, ob_top - ob_bottom)
            if smaller > 0 and overlap / smaller >= config.sd_duplicate_overlap_fraction:
                zone.is_duplicate = True
                zone.linked_order_block_id = ob.id
                break


def update_zone_state(
    state: ZoneState,
    raw: RawZone,
    series: CandleSeries,
) -> None:
    """Chronological lifecycle scan from the actionable candle onward."""
    candles = series.candles
    supply = raw.kind is ZoneType.SUPPLY
    prev_entered = False
    for i in range(raw.actionable_from_index, len(candles)):
        candle = candles[i]
        entered = candle.high >= raw.zone_bottom if supply else candle.low <= raw.zone_top
        if not entered:
            prev_entered = False
            continue
        if state.first_touch_index is None:
            state.first_touch_index = i
        traded_through = candle.high >= raw.zone_top if supply else candle.low <= raw.zone_bottom
        closed_through = candle.close > raw.zone_top if supply else candle.close < raw.zone_bottom
        if closed_through:
            state.status = SDZoneStatus.BROKEN
            state.broken_index = i
            if state.mitigated_index is None:
                state.mitigated_index = i
            return
        if traded_through:
            state.status = SDZoneStatus.MITIGATED
            state.mitigated_index = i
            return
        if not prev_entered:
            state.tests += 1  # distinct visit that neither mitigates nor breaks
        state.status = SDZoneStatus.TESTED
        prev_entered = True


def trend_aligned(kind: ZoneType, external_trend: TrendDirection) -> bool:
    """Demand aligns with a bullish external trend; supply with bearish."""
    return (kind is ZoneType.DEMAND and external_trend is TrendDirection.BULLISH) or (
        kind is ZoneType.SUPPLY and external_trend is TrendDirection.BEARISH
    )


def strength_score(
    *,
    departure_atr_multiple: float | None,
    mean_base_body_atr: float | None,
    status: SDZoneStatus,
    tests: int,
    aligned: bool,
    age: int,
    config: EngineConfig,
) -> float:
    """Deterministic zone strength in [0, 1] (formula in module docstring)."""
    departure = (
        min(departure_atr_multiple / config.sd_departure_atr_cap, 1.0)
        if departure_atr_multiple is not None
        else 0.5
    )
    tightness = (
        1.0 - min(mean_base_body_atr / config.sd_base_body_atr_fraction, 1.0)
        if mean_base_body_atr is not None and config.sd_base_body_atr_fraction > 0
        else 0.5
    )
    score = (
        config.sd_weight_departure * departure
        + config.sd_weight_tightness * tightness
        + config.sd_weight_freshness * _FRESHNESS_SCORE[status]
        + config.sd_weight_tests * 0.5**tests
        + config.sd_weight_trend * (1.0 if aligned else 0.0)
        + config.sd_weight_age * 0.5 ** (age / config.sd_strength_half_life)
    )
    return min(max(score, 0.0), 1.0)
