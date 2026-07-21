"""Supply/demand module orchestrator: OB-derived + pattern zones → lifecycle.

Pipeline
--------
1. ``OrderBlockEngine`` output provides OB-derived zones (and internally the
   structure scan, FVG overlaps, and sweeps — never recomputed here).
2. ``detect_pattern_zones`` finds rally-base-drop / drop-base-rally bases.
3. ``mark_duplicates`` flags pattern zones ~identical to an OB zone.
4. Each zone's lifecycle is scanned chronologically; strength is scored and
   zones ranked (strength desc, base_end asc).
"""

from __future__ import annotations

from contexttrading.analysis.orderblocks.orderblocks import OrderBlockEngine
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.analysis.supplydemand.zones import (
    ZoneState,
    detect_pattern_zones,
    mark_duplicates,
    strength_score,
    trend_aligned,
    update_zone_state,
    zones_from_order_blocks,
)
from contexttrading.core.config import EngineConfig
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.models.supplydemand import SupplyDemandResult, SupplyDemandZone, sd_style


class SupplyDemandEngine:
    """Runs the full supply/demand pipeline over a series."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def run(self, series: CandleSeries) -> SupplyDemandResult:
        """Detect, track, and score all supply/demand zones.

        Raises:
            InsufficientDataError: Below ``config.min_candles``.
        """
        config = self._config
        candles = series.candles
        if len(candles) < config.min_candles:
            raise InsufficientDataError(
                "Series too short for supply/demand analysis",
                context={"candles": len(candles), "min_candles": config.min_candles},
            )

        scan = StructureScanner(config).run(series)
        ob_result = OrderBlockEngine(config).run(series)

        ob_zones = zones_from_order_blocks(ob_result.order_blocks, scan)
        pattern_zones = detect_pattern_zones(series, scan, config)
        mark_duplicates(pattern_zones, ob_result.order_blocks, config)

        zones: list[SupplyDemandZone] = []
        for raw in (*ob_zones, *pattern_zones):
            state = ZoneState()
            update_zone_state(state, raw, series)
            end = state.broken_index or state.mitigated_index or len(candles) - 1
            age = max(end - raw.actionable_from_index, 0)
            aligned = trend_aligned(raw.kind, scan.external_trend)
            zones.append(
                SupplyDemandZone(
                    kind=raw.kind,
                    zone_bottom=raw.zone_bottom,
                    zone_top=raw.zone_top,
                    base_start_index=raw.base_start_index,
                    base_end_index=raw.base_end_index,
                    formed_at=candles[raw.base_end_index].timestamp,
                    actionable_from_index=raw.actionable_from_index,
                    departure_leg_id=raw.departure_leg_id,
                    departure_atr_multiple=raw.departure_atr_multiple,
                    mean_base_body_atr=raw.mean_base_body_atr,
                    trend_aligned=aligned,
                    status=state.status,
                    tests=state.tests,
                    first_touch_index=state.first_touch_index,
                    mitigated_index=state.mitigated_index,
                    broken_index=state.broken_index,
                    age=age,
                    linked_order_block_id=raw.linked_order_block_id,
                    is_duplicate=raw.is_duplicate,
                    strength=strength_score(
                        departure_atr_multiple=raw.departure_atr_multiple,
                        mean_base_body_atr=raw.mean_base_body_atr,
                        status=state.status,
                        tests=state.tests,
                        aligned=aligned,
                        age=age,
                        config=config,
                    ),
                    style=sd_style(raw.kind, state.status),
                )
            )

        zones.sort(key=lambda z: (-z.strength, z.base_end_index))
        zones = [z.model_copy(update={"rank": rank}) for rank, z in enumerate(zones, start=1)]

        counts_by_status: dict[str, int] = {}
        counts_by_kind: dict[str, int] = {}
        for zone in zones:
            counts_by_status[zone.status.value] = counts_by_status.get(zone.status.value, 0) + 1
            counts_by_kind[zone.kind.value] = counts_by_kind.get(zone.kind.value, 0) + 1
        return SupplyDemandResult(
            zones=zones,
            total_count=len(zones),
            counts_by_status=counts_by_status,
            counts_by_kind=counts_by_kind,
        )


def analyze_supplydemand(
    series: CandleSeries,
    config: EngineConfig | None = None,
) -> AnalysisResult[SupplyDemandResult]:
    """Run the supply/demand engine over a series.

    Args:
        series: Input candles.
        config: Engine thresholds (defaults when None).

    Returns:
        Envelope with ranked supply/demand zones and summary counts.
    """
    config = config or EngineConfig()
    payload = SupplyDemandEngine(config).run(series)
    return AnalysisResult[SupplyDemandResult](
        module="supplydemand",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
