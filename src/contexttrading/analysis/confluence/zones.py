"""Spatial confluence zones: clusters where several factor kinds overlap.

Active zones from FVG, order blocks, supply/demand, and the dealing
range's premium/discount band are clustered by interval overlap. A cluster
becomes a :class:`ConfluenceZone` only when it contains at least
``conf_zone_min_factors`` distinct factor kinds AND all members agree in
direction. Zone score:

    score = sum(best_member_raw(kind) * kind_weight for each present kind)
            / sum(kind_weight over ALL zone-eligible kinds)

so a zone with every kind at full strength scores exactly 1.0.
"""

from __future__ import annotations

from dataclasses import dataclass

from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    MitigationStatus,
    SDZoneStatus,
    TrendDirection,
    ZoneType,
)
from contexttrading.models.confluence import ConfluenceZone, confluence_zone_style
from contexttrading.models.fvg import FVGResult
from contexttrading.models.orderblock import OrderBlockResult
from contexttrading.models.range import DealingRange
from contexttrading.models.supplydemand import SupplyDemandResult

_ACTIVE_FVG = (MitigationStatus.UNMITIGATED, MitigationStatus.PARTIALLY_MITIGATED)
_ACTIVE_SD = (SDZoneStatus.FRESH, SDZoneStatus.TESTED)

#: Factor kinds eligible for zone membership (weights come from config).
ZONE_KINDS: tuple[str, ...] = ("fvg", "orderblock", "supplydemand", "premium_discount")


@dataclass(frozen=True)
class ZoneMember:
    """One active zone eligible for spatial clustering."""

    kind: str
    source_id: str
    direction: TrendDirection
    bottom: float
    top: float
    raw: float


def collect_zone_members(
    fvg: FVGResult,
    ob: OrderBlockResult,
    sd: SupplyDemandResult,
    dealing_range: DealingRange | None,
    block_kind_raw: dict[str, float],
) -> list[ZoneMember]:
    """Collect all active zones (no proximity filter — zones are levels)."""
    members: list[ZoneMember] = []
    for gap in fvg.fvgs:
        if gap.status in _ACTIVE_FVG:
            members.append(
                ZoneMember(
                    "fvg", gap.id, gap.direction, gap.zone_bottom, gap.zone_top, gap.strength
                )
            )
    for kind, blocks in (
        ("ob", ob.order_blocks),
        ("brk", ob.breaker_blocks),
        ("mb", ob.mitigation_blocks),
    ):
        for block in blocks:
            if block.is_valid:
                members.append(
                    ZoneMember(
                        "orderblock",
                        block.id,
                        block.direction,
                        block.zone_bottom,
                        block.zone_top,
                        block_kind_raw[kind],
                    )
                )
    for zone in sd.zones:
        if zone.status in _ACTIVE_SD and not zone.is_duplicate:
            direction = (
                TrendDirection.BULLISH if zone.kind is ZoneType.DEMAND else TrendDirection.BEARISH
            )
            members.append(
                ZoneMember(
                    "supplydemand",
                    zone.id,
                    direction,
                    zone.zone_bottom,
                    zone.zone_top,
                    zone.strength,
                )
            )
    if dealing_range is not None:
        if dealing_range.direction is TrendDirection.BULLISH:
            members.append(
                ZoneMember(
                    "premium_discount",
                    "premium_discount",
                    TrendDirection.BULLISH,
                    dealing_range.low,
                    dealing_range.equilibrium,
                    1.0,
                )
            )
        elif dealing_range.direction is TrendDirection.BEARISH:
            members.append(
                ZoneMember(
                    "premium_discount",
                    "premium_discount",
                    TrendDirection.BEARISH,
                    dealing_range.equilibrium,
                    dealing_range.high,
                    1.0,
                )
            )
    return members


def _kind_weights(config: EngineConfig) -> dict[str, float]:
    return {
        "fvg": config.conf_weight_fvg,
        "orderblock": config.conf_weight_orderblock,
        "supplydemand": config.conf_weight_supplydemand,
        "premium_discount": config.conf_weight_premium_discount,
    }


def build_confluence_zones(members: list[ZoneMember], config: EngineConfig) -> list[ConfluenceZone]:
    """Cluster overlapping members and score unanimous multi-kind clusters."""
    weights = _kind_weights(config)
    total_weight = sum(weights.values())
    if not members or total_weight <= 0:
        return []

    ordered = sorted(members, key=lambda m: (m.bottom, m.top, m.kind, m.source_id))
    clusters: list[list[ZoneMember]] = []
    for member in ordered:
        if clusters and member.bottom <= max(m.top for m in clusters[-1]):
            clusters[-1].append(member)
        else:
            clusters.append([member])

    zones: list[ConfluenceZone] = []
    for cluster in clusters:
        kinds = sorted({m.kind for m in cluster})
        if len(kinds) < config.conf_zone_min_factors:
            continue
        directions = {m.direction for m in cluster}
        if len(directions) != 1:
            continue  # conflicted cluster: no zone
        direction = next(iter(directions))
        best_raw = {kind: max(m.raw for m in cluster if m.kind == kind) for kind in kinds}
        score = sum(weights[kind] * best_raw[kind] for kind in kinds) / total_weight
        zones.append(
            ConfluenceZone(
                direction=direction,
                zone_bottom=min(m.bottom for m in cluster),
                zone_top=max(m.top for m in cluster),
                member_ids=[m.source_id for m in cluster],
                member_kinds=kinds,
                score=score,
                style=confluence_zone_style(direction, score),
            )
        )
    zones.sort(key=lambda z: (-z.score, z.zone_bottom, z.zone_top))
    return zones
