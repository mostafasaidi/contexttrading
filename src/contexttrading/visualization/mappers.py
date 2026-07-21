"""Per-module mappers: analysis objects -> render primitives.

Pure translation: every primitive copies color/opacity/line style from the
source object's ``VisualStyle`` preset — nothing is recomputed or
re-styled here. Tooltips are structured key/value pairs (all values
pre-formatted strings, deterministic).

Index-to-time rule: primitives anchor on candle indices, converted through
``series.candles[i].timestamp`` to UNIX seconds; open-ended zones extend to
the last candle of the series.
"""

from __future__ import annotations

from contexttrading.core.constants import (
    LiquiditySide,
    SwingClass,
    SwingType,
    TrendDirection,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.confluence import ConfluenceResult
from contexttrading.models.fvg import FVGResult
from contexttrading.models.liquidity import LiquidityResult
from contexttrading.models.mtf import MTFResult
from contexttrading.models.orderblock import OrderBlockResult
from contexttrading.models.range import DealingRangeResult
from contexttrading.models.session import SessionResult
from contexttrading.models.structure import MarketStructureResult
from contexttrading.models.supplydemand import SupplyDemandResult
from contexttrading.models.visualization import LineStyle
from contexttrading.visualization.primitives import (
    AreaBand,
    Box,
    Marker,
    PriceLine,
    RenderPrimitive,
    Segment,
    to_unix_seconds,
)

_BULL = "#22ab94"
_BEAR = "#f23645"
_NEUTRAL = "#787b86"


def _time_at(series: CandleSeries, index: int) -> int:
    """Candle index -> UNIX seconds, clamped into the series."""
    clamped = max(0, min(index, len(series) - 1))
    return to_unix_seconds(series.candles[clamped].timestamp)


def _last_time(series: CandleSeries) -> int:
    return to_unix_seconds(series.candles[-1].timestamp)


def map_structure(result: MarketStructureResult, series: CandleSeries) -> list[RenderPrimitive]:
    """Swings -> markers, breaks -> segments, protected levels -> price lines."""
    primitives: list[RenderPrimitive] = []
    for swing in result.swings:
        external = swing.swing_class is SwingClass.EXTERNAL
        primitives.append(
            Marker(
                source_id=swing.id,
                layer=swing.style.layer,
                priority=swing.style.priority,
                tooltip={
                    "type": f"{swing.swing_class.value} swing {swing.swing_type.value}",
                    "price": f"{swing.price:g}",
                    "index": str(swing.index),
                },
                color=swing.style.color,
                time=_time_at(series, swing.index),
                price=swing.price,
                position=("aboveBar" if swing.swing_type is SwingType.HIGH else "belowBar"),
                shape="diamond" if external else "circle",
                text="H" if swing.swing_type is SwingType.HIGH else "L",
            )
        )
    swings_by_id = {s.id: s for s in result.swings}
    for brk in result.breaks:
        origin = swings_by_id.get(brk.broken_swing_id)
        start_time = (
            to_unix_seconds(origin.timestamp)
            if origin is not None
            else _time_at(series, brk.break_index)
        )
        primitives.append(
            Segment(
                source_id=brk.id,
                layer=brk.style.layer,
                priority=brk.style.priority,
                tooltip={
                    "type": f"{brk.break_type.value} {brk.direction.value}",
                    "strength": brk.strength.value,
                    "level": f"{brk.broken_swing_price:g}",
                    "break_price": f"{brk.break_price:g}",
                    "broken_swing_id": brk.broken_swing_id,
                },
                color=brk.style.color,
                start_time=start_time,
                start_price=brk.broken_swing_price,
                end_time=to_unix_seconds(brk.break_timestamp),
                end_price=brk.break_price,
                line_style=brk.style.line_style,
                line_width=brk.style.line_width,
            )
        )
    for label, protected in (
        ("protected high", result.protected_high),
        ("protected low", result.protected_low),
    ):
        if protected is not None:
            primitives.append(
                PriceLine(
                    source_id=protected.id,
                    layer="structure.protected",
                    priority=18,
                    tooltip={"type": label, "price": f"{protected.price:g}"},
                    color=protected.style.color,
                    price=protected.price,
                    line_style=protected.style.line_style,
                    title=label,
                )
            )
    return primitives


def map_liquidity(result: LiquidityResult, series: CandleSeries) -> list[RenderPrimitive]:
    """Equal levels and pools -> price lines, sweeps -> markers."""
    primitives: list[RenderPrimitive] = []
    for level in result.equal_levels:
        primitives.append(
            PriceLine(
                source_id=level.id,
                layer=level.style.layer,
                priority=level.style.priority,
                tooltip={
                    "type": f"equal {'highs' if level.side is LiquiditySide.BUYSIDE else 'lows'}",
                    "price": f"{level.price:g}",
                    "count": str(level.count),
                },
                color=level.style.color,
                price=level.price,
                line_style=level.style.line_style,
                title=f"EQ{'H' if level.side is LiquiditySide.BUYSIDE else 'L'} x{level.count}",
            )
        )
    for pool in result.pools:
        primitives.append(
            PriceLine(
                source_id=pool.id,
                layer=pool.style.layer,
                priority=pool.style.priority,
                tooltip={
                    "type": f"{pool.side.value} liquidity",
                    "kind": pool.kind.value,
                    "price": f"{pool.price:g}",
                    "status": pool.status.value,
                },
                color=pool.style.color,
                price=pool.price,
                line_style=pool.style.line_style,
                title=f"{pool.kind.value} ({pool.status.value})",
            )
        )
    for sweep in result.sweeps:
        buyside = sweep.side is LiquiditySide.BUYSIDE
        primitives.append(
            Marker(
                source_id=sweep.id,
                layer=sweep.style.layer,
                priority=sweep.style.priority,
                tooltip={
                    "type": sweep.classification.value.replace("_", " "),
                    "side": sweep.side.value,
                    "pool_price": f"{sweep.pool_price:g}",
                    "wick_extreme": f"{sweep.wick_extreme:g}",
                    "pool_id": sweep.pool_id,
                },
                color=sweep.style.color,
                time=to_unix_seconds(sweep.timestamp),
                price=sweep.wick_extreme,
                position="aboveBar" if buyside else "belowBar",
                shape="arrowDown" if buyside else "arrowUp",
                text=sweep.classification.value[0].upper(),
            )
        )
    return primitives


def map_fvg(result: FVGResult, series: CandleSeries) -> list[RenderPrimitive]:
    """FVGs -> zone boxes (formation start to fill or series end)."""
    primitives: list[RenderPrimitive] = []
    for gap in result.fvgs:
        end = gap.filled_index if gap.filled_index is not None else len(series) - 1
        primitives.append(
            Box(
                source_id=gap.id,
                layer=gap.style.layer,
                priority=gap.style.priority,
                tooltip={
                    "type": f"{'inverse ' if gap.is_inverse else ''}" f"{gap.direction.value} fvg",
                    "status": gap.status.value,
                    "gap_size": f"{gap.gap_size:g}",
                    "gap_atr": (f"{gap.gap_atr:.3f}" if gap.gap_atr is not None else "n/a"),
                    "strength": f"{gap.strength:.3f}",
                    "rank": str(gap.rank),
                },
                color=gap.style.color,
                start_time=_time_at(series, gap.formation_start_index),
                end_time=_time_at(series, end),
                bottom=gap.zone_bottom,
                top=gap.zone_top,
                opacity=gap.style.opacity,
                line_style=gap.style.line_style,
                fill=gap.style.fill,
            )
        )
    return primitives


def map_orderblocks(result: OrderBlockResult, series: CandleSeries) -> list[RenderPrimitive]:
    """Order/breaker/mitigation blocks -> zone boxes."""
    primitives: list[RenderPrimitive] = []
    groups = (
        ("order block", result.order_blocks),
        ("breaker", result.breaker_blocks),
        ("mitigation block", result.mitigation_blocks),
    )
    for name, blocks in groups:
        for block in blocks:
            end_idx = block.violation_index or block.mitigation_index or len(series) - 1
            primitives.append(
                Box(
                    source_id=block.id,
                    layer=block.style.layer,
                    priority=block.style.priority,
                    tooltip={
                        "type": f"{block.direction.value} {name}",
                        "status": block.status.value,
                        "touches": str(block.touches),
                        "zone": f"{block.zone_bottom:g} - {block.zone_top:g}",
                    },
                    color=block.style.color,
                    start_time=_time_at(series, block.candle_index),
                    end_time=_time_at(series, end_idx),
                    bottom=block.zone_bottom,
                    top=block.zone_top,
                    opacity=block.style.opacity,
                    line_style=block.style.line_style,
                    fill=block.style.fill,
                )
            )
    return primitives


def map_supplydemand(result: SupplyDemandResult, series: CandleSeries) -> list[RenderPrimitive]:
    """Supply/demand zones -> zone boxes."""
    primitives: list[RenderPrimitive] = []
    for zone in result.zones:
        end_idx = zone.broken_index or zone.mitigated_index or len(series) - 1
        primitives.append(
            Box(
                source_id=zone.id,
                layer=zone.style.layer,
                priority=zone.style.priority,
                tooltip={
                    "type": f"{zone.kind.value} zone",
                    "status": zone.status.value,
                    "tests": str(zone.tests),
                    "strength": f"{zone.strength:.3f}",
                    "trend_aligned": str(zone.trend_aligned).lower(),
                },
                color=zone.style.color,
                start_time=_time_at(series, zone.base_start_index),
                end_time=_time_at(series, end_idx),
                bottom=zone.zone_bottom,
                top=zone.zone_top,
                opacity=zone.style.opacity,
                line_style=zone.style.line_style,
                fill=zone.style.fill,
            )
        )
    return primitives


def map_range(result: DealingRangeResult, series: CandleSeries) -> list[RenderPrimitive]:
    """Dealing range -> premium/discount/OTE bands + equilibrium line."""
    dr = result.dealing_range
    if dr is None:
        return []
    start = _time_at(series, 0)
    end = _last_time(series)
    primitives: list[RenderPrimitive] = []
    for style, bottom, top, kind in (
        (dr.premium_style, dr.equilibrium, dr.high, "premium"),
        (dr.discount_style, dr.low, dr.equilibrium, "discount"),
        (dr.ote_style, dr.ote_low, dr.ote_high, "ote"),
    ):
        primitives.append(
            Box(
                source_id=f"range:{kind}",
                layer=style.layer,
                priority=style.priority,
                tooltip={
                    "type": f"{kind} zone",
                    "direction": dr.direction.value,
                    "zone": f"{bottom:g} - {top:g}",
                    "price_location": dr.price_location.value,
                },
                color=style.color,
                start_time=start,
                end_time=end,
                bottom=bottom,
                top=top,
                opacity=style.opacity,
                line_style=style.line_style,
                fill=style.fill,
            )
        )
    primitives.append(
        PriceLine(
            source_id="range:equilibrium",
            layer=dr.equilibrium_style.layer,
            priority=dr.equilibrium_style.priority,
            tooltip={"type": "equilibrium (50%)", "price": f"{dr.equilibrium:g}"},
            color=dr.equilibrium_style.color,
            price=dr.equilibrium,
            line_style=dr.equilibrium_style.line_style,
            title="EQ 50%",
        )
    )
    return primitives


def map_sessions(result: SessionResult, series: CandleSeries) -> list[RenderPrimitive]:
    """Session instances -> area bands, levels -> price lines, Judas -> markers."""
    primitives: list[RenderPrimitive] = []
    for stats in result.sessions:
        primitives.append(
            AreaBand(
                source_id=stats.id,
                layer=stats.style.layer,
                priority=stats.style.priority,
                tooltip={
                    "type": f"{stats.session}{' killzone' if stats.is_killzone else ''}",
                    "date": stats.trading_date.isoformat(),
                    "open": f"{stats.open:g}",
                    "high": f"{stats.high:g}",
                    "low": f"{stats.low:g}",
                    "close": f"{stats.close:g}",
                    "direction": stats.direction.value,
                    "forms_day_high": str(stats.forms_day_high).lower(),
                    "forms_day_low": str(stats.forms_day_low).lower(),
                },
                color=stats.style.color,
                start_time=to_unix_seconds(stats.start_time),
                end_time=to_unix_seconds(stats.end_time),
                opacity=stats.style.opacity,
            )
        )
    for pool in result.pools:
        primitives.append(
            PriceLine(
                source_id=pool.id,
                layer="sessions.levels",
                priority=pool.style.priority,
                tooltip={
                    "type": pool.kind.value.replace("_", " "),
                    "price": f"{pool.price:g}",
                    "status": pool.status.value,
                },
                color=pool.style.color,
                price=pool.price,
                line_style=pool.style.line_style,
                title=pool.kind.value.replace("_", " "),
            )
        )
    for event in result.session_sweeps:
        buyside = event.side is LiquiditySide.BUYSIDE
        primitives.append(
            Marker(
                source_id=event.id,
                layer=event.style.layer,
                priority=event.style.priority,
                tooltip={
                    "type": "judas swing",
                    "swept_group": event.swept_group,
                    "swept_price": f"{event.swept_price:g}",
                    "killzone": event.sweeping_window,
                    "linked_sweep_id": event.linked_sweep_id,
                },
                color=event.style.color,
                time=to_unix_seconds(event.timestamp),
                price=event.swept_price,
                position="aboveBar" if buyside else "belowBar",
                shape="diamond",
                text="J",
            )
        )
    return primitives


def map_confluence(result: ConfluenceResult, series: CandleSeries) -> list[RenderPrimitive]:
    """Confluence zones -> score-scaled boxes."""
    primitives: list[RenderPrimitive] = []
    for zone in result.zones:
        primitives.append(
            Box(
                source_id=zone.id,
                layer=zone.style.layer,
                priority=zone.style.priority,
                tooltip={
                    "type": f"{zone.direction.value} confluence zone",
                    "score": f"{zone.score:.3f}",
                    "kinds": ", ".join(zone.member_kinds),
                    "members": str(len(zone.member_ids)),
                },
                color=zone.style.color,
                start_time=_time_at(series, 0),
                end_time=_last_time(series),
                bottom=zone.zone_bottom,
                top=zone.zone_top,
                opacity=zone.style.opacity,
                line_style=zone.style.line_style,
                fill=zone.style.fill,
            )
        )
    return primitives


def map_mtf(result: MTFResult, series: CandleSeries) -> list[RenderPrimitive]:
    """HTF dealing ranges -> labeled price lines on the mtf.levels layer."""
    primitives: list[RenderPrimitive] = []
    for context in result.contexts[1:]:  # contexts[0] is the base timeframe
        dr = context.dealing_range
        if dr is None:
            continue
        color = (
            _BULL
            if context.direction is TrendDirection.BULLISH
            else (_BEAR if context.direction is TrendDirection.BEARISH else _NEUTRAL)
        )
        tf = str(context.timeframe)
        for kind, price, line_style in (
            ("high", dr.high, LineStyle.DOTTED),
            ("EQ", dr.equilibrium, LineStyle.DASHED),
            ("low", dr.low, LineStyle.DOTTED),
        ):
            primitives.append(
                PriceLine(
                    source_id=f"mtf:{tf}:{kind}",
                    layer="mtf.levels",
                    priority=4,
                    tooltip={
                        "type": f"{tf} dealing range {kind}",
                        "price": f"{price:g}",
                        "direction": context.direction.value,
                        "weight": f"{context.weight:g}",
                    },
                    color=color,
                    price=price,
                    line_style=line_style,
                    title=f"{tf} {kind}",
                )
            )
    return primitives
