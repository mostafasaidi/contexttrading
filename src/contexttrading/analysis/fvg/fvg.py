"""FVG module orchestrator: detection → lifecycle → scoring → envelope.

Pipeline
--------
1. ``StructureScanner`` provides ATR and structure breaks (never recomputed).
2. ``detect_raw_fvgs`` finds raw 3-candle imbalances (chronological).
3. ``assign_stack_groups`` links stacked FVGs (pure geometry).
4. A single chronological pass updates lifecycle states candle-by-candle and
   registers each FVG at its confirmation candle (``formation_end_index``);
   nested parenting snapshots the *still-active* containers at registration.
5. Final FVG models are built in registration order (parent IDs resolvable),
   scored, and ranked by strength desc / formation index asc.
"""

from __future__ import annotations

from contexttrading.analysis.fvg.detection import (
    RawFVG,
    assign_stack_groups,
    detect_raw_fvgs,
    find_parent,
    link_displacement,
    with_atr,
)
from contexttrading.analysis.fvg.mitigation import (
    LifecycleState,
    strength_score,
    update_state,
)
from contexttrading.analysis.structure.structure import StructureScanner
from contexttrading.core.config import EngineConfig
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import CandleSeries
from contexttrading.models.fvg import FVG, FVGResult, fvg_style
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.models.structure import StructureBreak


class FVGEngine:
    """Runs the full FVG pipeline over a series."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def run(self, series: CandleSeries) -> FVGResult:
        """Detect, track, and score all FVGs in the series.

        Raises:
            InsufficientDataError: Below ``config.min_candles``.
        """
        config = self._config
        candles = series.candles
        if len(candles) < config.min_candles:
            raise InsufficientDataError(
                "Series too short for FVG analysis",
                context={"candles": len(candles), "min_candles": config.min_candles},
            )

        scan = StructureScanner(config).run(series)
        raws = detect_raw_fvgs(series, scan.atr_values, config)
        for raw in raws:
            with_atr(raw, scan.atr_values[raw.middle_index])
        stack_groups = assign_stack_groups(raws, config.fvg_stacked_lookback)
        breaks_by_index: dict[int, list[StructureBreak]] = {}
        for brk in scan.breaks:
            breaks_by_index.setdefault(brk.break_index, []).append(brk)

        # -- chronological lifecycle pass --------------------------------------
        states: dict[int, LifecycleState] = {}
        parents: dict[int, RawFVG] = {}
        registered: list[RawFVG] = []
        pending = sorted(raws, key=lambda r: (r.formation_end_index, r.middle_index))
        cursor = 0
        for i, candle in enumerate(candles):
            for raw in registered:
                update_state(states[id(raw)], raw, candle, i)
            while cursor < len(pending) and pending[cursor].formation_end_index <= i:
                raw = pending[cursor]
                cursor += 1
                actives = [r for r in registered if states[id(r)].active]
                parent = find_parent(raw, actives)
                if parent is not None:
                    parents[id(raw)] = parent
                registered.append(raw)
                states[id(raw)] = LifecycleState()

        # -- finalize models (registration order: parents before children) -----
        models: list[FVG] = []
        raw_to_model: dict[int, FVG] = {}
        for raw in registered:
            state = states[id(raw)]
            linked = link_displacement(raw, breaks_by_index)
            age = (state.filled_index if state.filled_index is not None else len(candles) - 1) - (
                raw.formation_end_index
            )
            parent_model = raw_to_model.get(id(parents[id(raw)])) if id(raw) in parents else None
            stacked = id(raw) in stack_groups
            nested = parent_model is not None
            model = FVG(
                direction=raw.direction,
                zone_bottom=raw.zone_bottom,
                zone_top=raw.zone_top,
                formation_start_index=raw.formation_start_index,
                middle_index=raw.middle_index,
                formation_end_index=raw.formation_end_index,
                formed_at=candles[raw.middle_index].timestamp,
                gap_size=raw.gap_size,
                gap_atr=raw.gap_atr,
                gap_percent=raw.gap_percent,
                is_nested=nested,
                parent_fvg_id=parent_model.id if parent_model else None,
                stack_group_id=stack_groups.get(id(raw)),
                linked_break_id=linked.id if linked else None,
                displacement_margin_atr=linked.margin_atr if linked else None,
                is_inverse=state.is_inverse,
                inversion_index=state.inversion_index,
                status=state.status,
                first_touch_index=state.first_touch_index,
                filled_index=state.filled_index,
                max_fill_fraction=state.max_fill_fraction,
                age=age,
                touches=state.touches,
                strength=strength_score(
                    gap_atr=raw.gap_atr,
                    linked=linked,
                    status=state.status,
                    age=age,
                    is_nested=nested,
                    is_stacked=stacked,
                    config=config,
                ),
                style=fvg_style(raw.direction, state.is_inverse, state.status),
            )
            models.append(model)
            raw_to_model[id(raw)] = model

        # -- ranking -------------------------------------------------------------
        models.sort(key=lambda f: (-f.strength, f.formation_end_index))
        models = [m.model_copy(update={"rank": rank}) for rank, m in enumerate(models, start=1)]

        counts_by_status: dict[str, int] = {}
        counts_by_direction: dict[str, int] = {}
        for model in models:
            counts_by_status[model.status.value] = counts_by_status.get(model.status.value, 0) + 1
            counts_by_direction[model.direction.value] = (
                counts_by_direction.get(model.direction.value, 0) + 1
            )
        return FVGResult(
            fvgs=models,
            total_count=len(models),
            counts_by_status=counts_by_status,
            counts_by_direction=counts_by_direction,
        )


def analyze_fvg(
    series: CandleSeries,
    config: EngineConfig | None = None,
) -> AnalysisResult[FVGResult]:
    """Run the FVG engine over a series.

    Args:
        series: Input candles.
        config: Engine thresholds (defaults when None).

    Returns:
        Envelope with ranked FVGs and summary counts.
    """
    config = config or EngineConfig()
    payload = FVGEngine(config).run(series)
    return AnalysisResult[FVGResult](
        module="fvg",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
