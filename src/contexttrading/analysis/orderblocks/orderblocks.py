"""Order block module orchestrator: detection → lifecycle → breakers/MBs.

Pipeline
--------
1. ``StructureScanner`` provides swings, breaks, and ATR (never recomputed).
2. ``FVGEngine`` provides FVGs for overlap confluence links.
3. Liquidity internals (equal levels → pools → sweeps) reuse the same scan —
   no second structure pass.
4. ``detect_raw_order_blocks`` anchors OBs to confirmed breaks.
5. Each block's lifecycle is scanned chronologically from its actionable
   candle; violated OBs with confirming counter-breaks flip into breaker
   blocks; eligible sweeps (stop hunts / grabs) yield mitigation blocks.
"""

from __future__ import annotations

from contexttrading.analysis.fvg.fvg import FVGEngine
from contexttrading.analysis.indicators import volume_zscores
from contexttrading.analysis.liquidity.equal_levels import detect_equal_levels
from contexttrading.analysis.liquidity.pools import build_pools
from contexttrading.analysis.liquidity.sweeps import scan_sweeps
from contexttrading.analysis.orderblocks.breakers import build_breakers
from contexttrading.analysis.orderblocks.detection import (
    RawOrderBlock,
    attach_fvg_overlaps,
    detect_raw_order_blocks,
)
from contexttrading.analysis.orderblocks.lifecycle import (
    BlockState,
    resolve_age,
    update_block_state,
)
from contexttrading.analysis.orderblocks.mitigation_blocks import build_mitigation_blocks
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import MitigationStatus
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import CandleSeries
from contexttrading.models.orderblock import (
    OrderBlock,
    OrderBlockResult,
    block_style,
)
from contexttrading.models.outputs import AnalysisResult, DataWindow


def _finalize_order_block(raw: RawOrderBlock, series: CandleSeries) -> OrderBlock:
    """Run the lifecycle scan and build the immutable model."""
    candles = series.candles
    state = BlockState()
    actionable = raw.actionable_from_index
    for i in range(actionable, len(candles)):
        update_block_state(
            state,
            direction=raw.direction,
            zone_bottom=raw.zone_bottom,
            zone_top=raw.zone_top,
            mitigation_level=raw.mitigation_level,
            candle=candles[i],
            index=i,
        )
    return OrderBlock(
        direction=raw.direction,
        zone_bottom=raw.zone_bottom,
        zone_top=raw.zone_top,
        body_bottom=raw.body_bottom,
        body_top=raw.body_top,
        candle_index=raw.candle_index,
        cluster_start_index=raw.cluster_start_index,
        formed_at=candles[raw.candle_index].timestamp,
        actionable_from_index=actionable,
        is_refined=raw.is_refined,
        refined_bottom=raw.refined_bottom,
        refined_top=raw.refined_top,
        origin=raw.origin,
        linked_break_id=raw.linked_break.id,
        displacement_margin_atr=raw.linked_break.margin_atr,
        volume_zscore=raw.volume_zscore,
        overlapping_fvg_ids=raw.overlapping_fvg_ids,
        status=state.status,
        first_touch_index=state.first_touch_index,
        mitigation_index=state.mitigation_index,
        violation_index=state.violation_index,
        max_penetration_fraction=state.max_penetration_fraction,
        touches=state.touches,
        age=resolve_age(state, actionable, len(candles) - 1),
        is_consumed=state.is_consumed,
        is_valid=state.status is MitigationStatus.UNMITIGATED,
        style=block_style("ob", raw.direction, state.status),
    )


class OrderBlockEngine:
    """Runs the full order block pipeline over a series."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def run(self, series: CandleSeries) -> OrderBlockResult:
        """Detect, track, and classify all block types in the series.

        Raises:
            InsufficientDataError: Below ``config.min_candles``.
        """
        config = self._config
        candles = series.candles
        if len(candles) < config.min_candles:
            raise InsufficientDataError(
                "Series too short for order block analysis",
                context={"candles": len(candles), "min_candles": config.min_candles},
            )

        scan = StructureScanner(config).run(series)
        fvg_result = FVGEngine(config).run(series)
        volume_zs = volume_zscores(candles, config.volume_lookback)

        # Liquidity internals over the same scan (no second structure pass).
        equal_levels = detect_equal_levels(scan.external_swings, scan.atr_values, config)
        pools = build_pools(scan.external_swings, equal_levels)
        _, sweeps = scan_sweeps(series, pools, scan.breaks, scan.atr_values, config)

        raws = detect_raw_order_blocks(series, scan, volume_zs, config)
        attach_fvg_overlaps(raws, fvg_result.fvgs)
        order_blocks = [_finalize_order_block(raw, series) for raw in raws]

        breaker_blocks = build_breakers(order_blocks, series, scan.breaks, config)
        mitigation_blocks = build_mitigation_blocks(sweeps, pools, scan.external_swings, series)

        counts_by_status: dict[str, int] = {}
        counts_by_direction: dict[str, int] = {}
        for block in (*order_blocks, *breaker_blocks, *mitigation_blocks):
            counts_by_status[block.status.value] = counts_by_status.get(block.status.value, 0) + 1
            counts_by_direction[block.direction.value] = (
                counts_by_direction.get(block.direction.value, 0) + 1
            )
        return OrderBlockResult(
            order_blocks=order_blocks,
            breaker_blocks=breaker_blocks,
            mitigation_blocks=mitigation_blocks,
            total_count=len(order_blocks) + len(breaker_blocks) + len(mitigation_blocks),
            counts_by_status=counts_by_status,
            counts_by_direction=counts_by_direction,
        )


def analyze_orderblocks(
    series: CandleSeries,
    config: EngineConfig | None = None,
) -> AnalysisResult[OrderBlockResult]:
    """Run the order block engine over a series.

    Args:
        series: Input candles.
        config: Engine thresholds (defaults when None).

    Returns:
        Envelope with order blocks, breaker blocks, and mitigation blocks.
    """
    config = config or EngineConfig()
    payload = OrderBlockEngine(config).run(series)
    return AnalysisResult[OrderBlockResult](
        module="orderblocks",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
