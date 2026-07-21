"""Order block detection: anchor candles before displacement structure breaks.

Deterministic rules
-------------------
- Every **confirmed** structure break (strength STRONG or WEAK; FALSE breaks
  are sweep material, not displacement) anchors at most one order block.
- **Bullish OB**: the last down-close candle (``close < open``) strictly
  before ``break_index``. **Bearish OB**: mirrored (last up-close candle).
- Search bound: up to ``ob_max_lookback`` candles back from the break — the
  first opposite-close candle found walking backwards is, by definition, the
  last one before the displacement move.
- **Cluster**: not merged. Contiguous same-sign runs (every trend leg) would
  produce oversized zones, so the anchor is always the single last
  opposite-close candle; oversized candles are handled by refinement.
- **Zone** = cluster range ``[low, high]``; **body** = anchor candle body.
- **Refinement**: when the zone height exceeds ``ob_refine_atr_multiple`` x
  ATR at the anchor candle, emit a *refined zone* = the extreme
  ``ob_refine_wick_fraction`` of the range (bullish: lowest part; bearish:
  highest part). During ATR warmup no refinement is applied.
- **Origin**: ``REVERSAL`` when the linked break is a CHoCH, else
  ``CONTINUATION``.
- **Dedupe**: several breaks may anchor the same candle+direction; keep the
  one linked to the strongest break (STRONG > WEAK), then MAJOR > MINOR,
  then the earliest break.
- Degenerate zero-height zones (flat candles) are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from contexttrading.analysis.structure.structure import StructureScan
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BlockOrigin,
    BreakStrength,
    StructureBreakSignificance,
    StructureBreakType,
    TrendDirection,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.fvg import FVG
from contexttrading.models.structure import StructureBreak


@dataclass
class RawOrderBlock:
    """Pre-lifecycle order block (detection output)."""

    direction: TrendDirection
    zone_bottom: float
    zone_top: float
    body_bottom: float
    body_top: float
    candle_index: int
    cluster_start_index: int
    is_refined: bool
    refined_bottom: float | None
    refined_top: float | None
    origin: BlockOrigin
    linked_break: StructureBreak
    volume_zscore: float | None
    overlapping_fvg_ids: list[str] = field(default_factory=list)

    @property
    def actionable_from_index(self) -> int:
        """Lifecycle starts at the candle AFTER the linked break candle —
        the break candle belongs to the departure, not to a revisit."""
        return self.linked_break.break_index + 1

    @property
    def mitigation_level(self) -> float:
        """Price that, when traded through, marks the block MITIGATED.

        Unrefined: the far boundary. Refined: the midpoint of the refined
        zone (50% rule).
        """
        if self.is_refined and self.refined_bottom is not None and self.refined_top is not None:
            return (self.refined_bottom + self.refined_top) / 2
        return self.zone_bottom if self.direction is TrendDirection.BULLISH else self.zone_top


def _break_rank(brk: StructureBreak) -> tuple[int, int, int]:
    """Dedupe preference: STRONG > WEAK, MAJOR > MINOR, earliest break."""
    strength_rank = 1 if brk.strength is BreakStrength.STRONG else 0
    significance_rank = 1 if brk.significance is StructureBreakSignificance.MAJOR else 0
    return (strength_rank, significance_rank, -brk.break_index)


def detect_raw_order_blocks(
    series: CandleSeries,
    scan: StructureScan,
    volume_zs: tuple[float | None, ...],
    config: EngineConfig,
) -> list[RawOrderBlock]:
    """Detect raw order blocks anchored to confirmed structure breaks."""
    candles = series.candles
    best: dict[tuple[int, TrendDirection], RawOrderBlock] = {}
    confirmed = [b for b in scan.breaks if b.strength is not BreakStrength.FALSE]

    for brk in confirmed:
        bullish = brk.direction is TrendDirection.BULLISH
        bound = max(brk.break_index - config.ob_max_lookback, 0)
        anchor = None
        for i in range(brk.break_index - 1, bound - 1, -1):
            candle = candles[i]
            opposite_close = candle.close < candle.open if bullish else candle.close > candle.open
            if opposite_close:
                anchor = i
                break
        if anchor is None:
            continue

        # Single-candle anchor. Cluster merging (contiguous same-sign candles)
        # was considered and dropped: every trend leg is a contiguous same-sign
        # run, so merging produced oversized, useless zones; oversized single
        # candles are handled by the refinement rule below instead.
        start = anchor
        anchor_candle = candles[anchor]
        zone_bottom = anchor_candle.low
        zone_top = anchor_candle.high
        if zone_top <= zone_bottom:
            continue  # degenerate flat candle
        body_bottom = min(anchor_candle.open, anchor_candle.close)
        body_top = max(anchor_candle.open, anchor_candle.close)

        is_refined = False
        refined_bottom = refined_top = None
        atr_at = scan.atr_values[anchor]
        height = zone_top - zone_bottom
        if atr_at is not None and height > config.ob_refine_atr_multiple * atr_at:
            is_refined = True
            refined_height = config.ob_refine_wick_fraction * height
            if bullish:
                refined_bottom, refined_top = zone_bottom, zone_bottom + refined_height
            else:
                refined_bottom, refined_top = zone_top - refined_height, zone_top

        origin = (
            BlockOrigin.REVERSAL
            if brk.break_type is StructureBreakType.CHOCH
            else BlockOrigin.CONTINUATION
        )
        raw = RawOrderBlock(
            direction=brk.direction,
            zone_bottom=zone_bottom,
            zone_top=zone_top,
            body_bottom=body_bottom,
            body_top=body_top,
            candle_index=anchor,
            cluster_start_index=start,
            is_refined=is_refined,
            refined_bottom=refined_bottom,
            refined_top=refined_top,
            origin=origin,
            linked_break=brk,
            volume_zscore=volume_zs[anchor] if anchor < len(volume_zs) else None,
        )
        key = (anchor, brk.direction)
        existing = best.get(key)
        if existing is None or _break_rank(brk) > _break_rank(existing.linked_break):
            best[key] = raw

    return sorted(best.values(), key=lambda r: (r.linked_break.break_index, r.candle_index))


def attach_fvg_overlaps(raws: list[RawOrderBlock], fvgs: list[FVG]) -> None:
    """Link every FVG whose zone geometrically intersects the OB zone (in place).

    IDs are collected in FVG result order (deterministic rank order).
    """
    for raw in raws:
        raw.overlapping_fvg_ids = [
            fvg.id
            for fvg in fvgs
            if fvg.zone_bottom < raw.zone_top and fvg.zone_top > raw.zone_bottom
        ]
