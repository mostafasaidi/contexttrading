"""Directional factor extraction for the confluence engine.

Every factor is a :class:`FactorContribution`: factor kind, backing object
ID, supported direction, configured weight, raw evidence in [0, 1], and
``contribution = weight * raw``. Factors with no directional evidence
(RANGING, raw 0) are still emitted when the factor was evaluable — they
dilute the normalized scores, which is the intended confidence semantics.

Qualitative-to-raw mappings are documented module constants (not config):
    - trend strength: STRONG 1.0 / MODERATE 0.6 / WEAK 0.3;
    - sweep class: STOP_HUNT 1.0 / GRAB 0.8 / SWEEP 0.6;
    - block kind: order block 1.0 / breaker 0.8 / mitigation block 0.7.
"""

from __future__ import annotations

from contexttrading.analysis.structure.structure import StructureScan
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BreakStrength,
    LiquiditySide,
    MitigationStatus,
    PriceLocation,
    SDZoneStatus,
    SweepClassification,
    TrendDirection,
    TrendStrength,
    ZoneType,
)
from contexttrading.models.confluence import FactorContribution
from contexttrading.models.fvg import FVGResult
from contexttrading.models.liquidity import LiquidityResult
from contexttrading.models.mtf import MTFResult
from contexttrading.models.orderblock import OrderBlockResult
from contexttrading.models.range import DealingRange
from contexttrading.models.session import SessionResult
from contexttrading.models.structure import TrendState
from contexttrading.models.supplydemand import SupplyDemandResult

TREND_STRENGTH_RAW: dict[TrendStrength, float] = {
    TrendStrength.STRONG: 1.0,
    TrendStrength.MODERATE: 0.6,
    TrendStrength.WEAK: 0.3,
}
SWEEP_CLASS_RAW: dict[SweepClassification, float] = {
    SweepClassification.STOP_HUNT: 1.0,
    SweepClassification.GRAB: 0.8,
    SweepClassification.SWEEP: 0.6,
}
BLOCK_KIND_RAW: dict[str, float] = {"ob": 1.0, "brk": 0.8, "mb": 0.7}

_ACTIVE_FVG = (MitigationStatus.UNMITIGATED, MitigationStatus.PARTIALLY_MITIGATED)
_ACTIVE_SD = (SDZoneStatus.FRESH, SDZoneStatus.TESTED)


def _nearby(bottom: float, top: float, price: float, limit: float) -> bool:
    """True when ``price`` is inside [bottom, top] or within ``limit`` of it."""
    if bottom <= price <= top:
        return True
    distance = bottom - price if price < bottom else price - top
    return distance <= limit


def _proximity_limit(config: EngineConfig, atr_last: float | None) -> float:
    """Proximity threshold in price units (0 during ATR warmup)."""
    return config.conf_proximity_atr * atr_last if atr_last else 0.0


def trend_factor(trend: TrendState, config: EngineConfig) -> FactorContribution:
    """External trend direction, scaled by qualitative strength."""
    known = trend.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
    raw = TREND_STRENGTH_RAW[trend.strength] if known else 0.0
    return FactorContribution(
        factor="trend",
        source_id=None,
        direction=trend.direction if known else TrendDirection.RANGING,
        weight=config.conf_weight_trend,
        raw=raw,
        contribution=config.conf_weight_trend * raw,
        detail=f"external trend {trend.direction.value} ({trend.strength.value})",
    )


def mtf_factor(mtf: MTFResult, config: EngineConfig) -> FactorContribution:
    """MTF bias direction, scaled by its weighted agreement share."""
    bias = mtf.bias
    known = bias.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
    raw = bias.agreement_share if known else 0.0
    return FactorContribution(
        factor="mtf",
        source_id=None,
        direction=bias.direction if known else TrendDirection.RANGING,
        weight=config.conf_weight_mtf,
        raw=raw,
        contribution=config.conf_weight_mtf * raw,
        detail=(
            f"mtf bias {bias.direction.value} ({bias.strength.value}, "
            f"share {bias.agreement_share:.3f})"
        ),
    )


def structure_factor(scan: StructureScan, config: EngineConfig) -> FactorContribution | None:
    """Majority direction of the last ``conf_structure_lookback`` confirmed breaks."""
    confirmed = [b for b in scan.breaks if b.strength is not BreakStrength.FALSE]
    window = confirmed[-config.conf_structure_lookback :]
    if not window:
        return None
    bull = sum(1 for b in window if b.direction is TrendDirection.BULLISH)
    bear = len(window) - bull
    total = len(window)
    if bull == bear:
        direction, raw = TrendDirection.RANGING, 0.0
    elif bull > bear:
        direction, raw = TrendDirection.BULLISH, bull / total
    else:
        direction, raw = TrendDirection.BEARISH, bear / total
    return FactorContribution(
        factor="structure",
        source_id=None,
        direction=direction,
        weight=config.conf_weight_structure,
        raw=raw,
        contribution=config.conf_weight_structure * raw,
        detail=f"recent breaks {bull} bullish / {bear} bearish of {total}",
    )


def liquidity_factor(liquidity: LiquidityResult, config: EngineConfig) -> FactorContribution | None:
    """Majority direction of recent sweeps (sellside sweep = bullish evidence)."""
    window = liquidity.sweeps[-config.conf_sweep_lookback :]
    if not window:
        return None
    bull = sum(
        SWEEP_CLASS_RAW[s.classification] for s in window if s.side is LiquiditySide.SELLSIDE
    )
    bear = sum(SWEEP_CLASS_RAW[s.classification] for s in window if s.side is LiquiditySide.BUYSIDE)
    total = bull + bear
    if bull == bear:
        direction, raw = TrendDirection.RANGING, 0.0
    elif bull > bear:
        direction, raw = TrendDirection.BULLISH, bull / total
    else:
        direction, raw = TrendDirection.BEARISH, bear / total
    return FactorContribution(
        factor="liquidity",
        source_id=None,
        direction=direction,
        weight=config.conf_weight_liquidity,
        raw=raw,
        contribution=config.conf_weight_liquidity * raw,
        detail=f"recent sweeps {bull:.2f} bullish / {bear:.2f} bearish (class-weighted)",
    )


def premium_discount_factor(
    dealing_range: DealingRange | None, config: EngineConfig
) -> FactorContribution | None:
    """Price location: DISCOUNT is bullish evidence, PREMIUM bearish."""
    if dealing_range is None:
        return None
    half = (dealing_range.high - dealing_range.low) / 2
    raw = min(abs(dealing_range.reference_price - dealing_range.equilibrium) / half, 1.0)
    direction = {
        PriceLocation.DISCOUNT: TrendDirection.BULLISH,
        PriceLocation.PREMIUM: TrendDirection.BEARISH,
        PriceLocation.EQUILIBRIUM: TrendDirection.RANGING,
    }[dealing_range.price_location]
    if direction is TrendDirection.RANGING:
        raw = 0.0
    return FactorContribution(
        factor="premium_discount",
        source_id=None,
        direction=direction,
        weight=config.conf_weight_premium_discount,
        raw=raw,
        contribution=config.conf_weight_premium_discount * raw,
        detail=f"price in {dealing_range.price_location.value} of the dealing range",
    )


def fvg_factors(
    fvg: FVGResult, price: float, limit: float, config: EngineConfig
) -> list[FactorContribution]:
    """Nearby active FVGs (UNMITIGATED / PARTIALLY_MITIGATED), strength-ranked."""
    factors = []
    for gap in fvg.fvgs:
        if gap.status not in _ACTIVE_FVG:
            continue
        if not _nearby(gap.zone_bottom, gap.zone_top, price, limit):
            continue
        factors.append(
            FactorContribution(
                factor="fvg",
                source_id=gap.id,
                direction=gap.direction,
                weight=config.conf_weight_fvg,
                raw=gap.strength,
                contribution=config.conf_weight_fvg * gap.strength,
                detail=f"{gap.direction.value} fvg {gap.id} (strength {gap.strength:.3f})",
            )
        )
    return factors


def orderblock_factors(
    ob: OrderBlockResult, price: float, limit: float, config: EngineConfig
) -> list[FactorContribution]:
    """Nearby valid blocks (order blocks, breakers, mitigation blocks)."""
    factors = []
    groups = (
        ("ob", "order block", ob.order_blocks),
        ("brk", "breaker", ob.breaker_blocks),
        ("mb", "mitigation block", ob.mitigation_blocks),
    )
    for kind, name, blocks in groups:
        for block in blocks:
            if not block.is_valid:
                continue
            if not _nearby(block.zone_bottom, block.zone_top, price, limit):
                continue
            raw = BLOCK_KIND_RAW[kind]
            factors.append(
                FactorContribution(
                    factor="orderblock",
                    source_id=block.id,
                    direction=block.direction,
                    weight=config.conf_weight_orderblock,
                    raw=raw,
                    contribution=config.conf_weight_orderblock * raw,
                    detail=f"{block.direction.value} {name} {block.id} (valid, near price)",
                )
            )
    return factors


def supplydemand_factors(
    sd: SupplyDemandResult, price: float, limit: float, config: EngineConfig
) -> list[FactorContribution]:
    """Nearby fresh/tested supply/demand zones (duplicates excluded)."""
    factors = []
    for zone in sd.zones:
        if zone.status not in _ACTIVE_SD or zone.is_duplicate:
            continue
        if not _nearby(zone.zone_bottom, zone.zone_top, price, limit):
            continue
        direction = (
            TrendDirection.BULLISH if zone.kind is ZoneType.DEMAND else TrendDirection.BEARISH
        )
        factors.append(
            FactorContribution(
                factor="supplydemand",
                source_id=zone.id,
                direction=direction,
                weight=config.conf_weight_supplydemand,
                raw=zone.strength,
                contribution=config.conf_weight_supplydemand * zone.strength,
                detail=f"{zone.kind.value} zone {zone.id} (strength {zone.strength:.3f})",
            )
        )
    return factors


def session_factors(sessions: SessionResult, config: EngineConfig) -> list[FactorContribution]:
    """Recent Judas swings (buyside sweep = bearish evidence, and mirrored)."""
    factors = []
    for event in sessions.session_sweeps[-config.conf_sweep_lookback :]:
        direction = (
            TrendDirection.BEARISH
            if event.side is LiquiditySide.BUYSIDE
            else TrendDirection.BULLISH
        )
        factors.append(
            FactorContribution(
                factor="session",
                source_id=event.id,
                direction=direction,
                weight=config.conf_weight_session,
                raw=1.0,
                contribution=config.conf_weight_session,
                detail=(
                    f"judas swing: {event.swept_group} "
                    f"{'high' if event.side is LiquiditySide.BUYSIDE else 'low'} swept "
                    f"in {event.sweeping_window} killzone"
                ),
            )
        )
    return factors


def collect_factors(
    trend: TrendState,
    mtf: MTFResult,
    scan: StructureScan,
    liquidity: LiquidityResult,
    dealing_range: DealingRange | None,
    fvg: FVGResult,
    ob: OrderBlockResult,
    sd: SupplyDemandResult,
    sessions: SessionResult,
    price: float,
    atr_last: float | None,
    config: EngineConfig,
) -> list[FactorContribution]:
    """Assemble all directional factors in a fixed, documented order."""
    limit = _proximity_limit(config, atr_last)
    factors: list[FactorContribution] = [trend_factor(trend, config), mtf_factor(mtf, config)]
    for optional in (
        structure_factor(scan, config),
        liquidity_factor(liquidity, config),
        premium_discount_factor(dealing_range, config),
    ):
        if optional is not None:
            factors.append(optional)
    factors.extend(fvg_factors(fvg, price, limit, config))
    factors.extend(orderblock_factors(ob, price, limit, config))
    factors.extend(supplydemand_factors(sd, price, limit, config))
    factors.extend(session_factors(sessions, config))
    return factors
