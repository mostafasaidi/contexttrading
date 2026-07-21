"""Reference strategy: SMC pullback entries driven purely by engine output.

Entry rules (long; short is the exact mirror):

1. Trend filter: ``trend.state.direction`` agrees with the trade side.
2. Trigger: the most recent confirmed BOS (strength STRONG or WEAK, type
   BOS) in the trend direction, at most ``max_bars_since_break`` old.
3. Zone: the current bar trades into a still-open zone originating from
   that BOS — a bullish/bearish OrderBlock with ``linked_break_id`` equal
   to the BOS id and status UNMITIGATED/PARTIALLY_MITIGATED (preferred),
   else an unmitigated FVG in the trade direction. "Trades into" means
   ``bar.low <= zone_top`` and ``bar.close >= zone_bottom`` for longs
   (mirrored for shorts) — a touch, not a close-through.
4. Location: the zone sits in DISCOUNT (long) / PREMIUM (short) of the
   confirmed dealing range — or, when the zone formed above/below the
   confirmed range during the fresh BOS leg, it qualifies by construction
   (the confirmed range lags active legs; see ``_zone_in_value``).
5. Confluence: the confluence module's score for the trade side is at
   least ``min_confluence_score``.

Order construction:

- Entry: market order at the NEXT bar open (replay contract).
- Stop: zone extreme minus/plus ``sl_atr_buffer`` x ATR (Wilder ATR from
  ``analysis.indicators`` over the decision window; engine entrypoint,
  not a strategy-side calculation). Trades are skipped while ATR is None.
- Target: the nearest untapped opposing liquidity pool beyond price;
  when none exists, ``tp_r_multiple`` x the initial risk from the
  decision close (documented approximation — the actual fill is the next
  bar's open).
- Evidence: the BOS id, zone id, pool id (when used), and the source ids
  of same-side confluence factors, in engine assembly order.

Exits: SL/TP only (plus end-of-data close). One position at a time; the
strategy never emits intents while a position is open.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from contexttrading.analysis.indicators import atr
from contexttrading.backtesting.execution import PositionState
from contexttrading.core.constants import (
    BreakStrength,
    LiquiditySide,
    MitigationStatus,
    PoolStatus,
    StructureBreakType,
    TrendDirection,
)
from contexttrading.models.backtest import OrderIntent
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult

_OPEN_STATUSES = (MitigationStatus.UNMITIGATED, MitigationStatus.PARTIALLY_MITIGATED)


class SMCPullbackParams(BaseModel):
    """Tunable parameters of the SMC pullback strategy."""

    model_config = ConfigDict(extra="forbid")

    min_confluence_score: float = Field(
        default=0.5, ge=0, le=1, description="Minimum same-side confluence score."
    )
    sl_atr_buffer: float = Field(
        default=0.5, ge=0, description="Stop buffer beyond the zone extreme, in ATRs."
    )
    tp_r_multiple: float = Field(
        default=2.0, gt=0, description="Fallback target when no liquidity pool exists."
    )
    max_bars_since_break: int = Field(
        default=40, ge=1, description="BOS older than this many bars is stale."
    )
    atr_period: int = Field(default=14, ge=1, description="Wilder ATR period for the stop.")
    allow_long: bool = True
    allow_short: bool = True


class SMCPullbackStrategy:
    """Pullback-into-zone entries after a confirmed BOS (see module docstring)."""

    name: ClassVar[str] = "smc_pullback"
    modules: ClassVar[tuple[str, ...]] = (
        "structure",
        "trend",
        "orderblocks",
        "fvg",
        "liquidity",
        "premium_discount",
        "confluence",
    )

    def __init__(self, params: SMCPullbackParams | None = None) -> None:
        self.params = params or SMCPullbackParams()

    def on_bar(
        self,
        bar_index: int,
        series: CandleSeries,
        results: dict[str, AnalysisResult] | None,  # type: ignore[type-arg]
        position: PositionState | None,
        equity: float,
    ) -> list[OrderIntent]:
        if position is not None or results is None:
            return []
        trend = results["trend"].payload.state  # type: ignore[attr-defined]
        for direction in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            if direction is TrendDirection.BULLISH and not self.params.allow_long:
                continue
            if direction is TrendDirection.BEARISH and not self.params.allow_short:
                continue
            intent = self._try_side(direction, bar_index, series, results, trend.direction)
            if intent is not None:
                return [intent]
        return []

    def _try_side(
        self,
        direction: TrendDirection,
        bar_index: int,
        series: CandleSeries,
        results: dict[str, AnalysisResult],  # type: ignore[type-arg]
        trend_direction: TrendDirection,
    ) -> OrderIntent | None:
        if trend_direction is not direction:
            return None
        bar = series.candles[-1]
        sign = direction.sign

        bos = self._latest_bos(results, direction, bar_index)
        if bos is None:
            return None

        zone_id, zone_bottom, zone_top = self._entry_zone(results, direction, bos.id, bar)
        if zone_id is None:
            return None

        if not self._zone_in_value(results, direction, zone_bottom, zone_top):
            return None

        confluence = results["confluence"].payload  # type: ignore[attr-defined]
        score = confluence.bullish_score if sign > 0 else confluence.bearish_score
        if score < self.params.min_confluence_score:
            return None

        atr_value = atr(series.candles, self.params.atr_period)[-1]
        if atr_value is None:
            return None
        buffer = self.params.sl_atr_buffer * atr_value
        stop = zone_bottom - buffer if sign > 0 else zone_top + buffer
        risk = (bar.close - stop) * sign
        if risk <= 0:
            return None

        tp, pool_id = self._target_pool(results, direction, bar.close)
        if tp is None:
            tp = bar.close + sign * self.params.tp_r_multiple * risk
        if (tp - bar.close) * sign <= 0:
            return None

        evidence = [bos.id, zone_id]
        if pool_id is not None:
            evidence.append(pool_id)
        evidence.extend(
            factor.source_id
            for factor in confluence.factors
            if factor.direction is direction and factor.source_id is not None
        )
        return OrderIntent(
            kind="market",
            direction=direction,
            stop_loss=stop,
            take_profit=tp,
            evidence_ids=evidence,
            tag="smc_pullback",
            created_index=bar_index,
        )

    def _latest_bos(
        self,
        results: dict[str, AnalysisResult],  # type: ignore[type-arg]
        direction: TrendDirection,
        bar_index: int,
    ):
        breaks = results["structure"].payload.breaks  # type: ignore[attr-defined]
        candidates = [
            b
            for b in breaks
            if b.direction is direction
            and b.break_type is StructureBreakType.BOS
            and b.strength in (BreakStrength.STRONG, BreakStrength.WEAK)
            and bar_index - b.break_index <= self.params.max_bars_since_break
        ]
        return candidates[-1] if candidates else None

    def _entry_zone(
        self,
        results: dict[str, AnalysisResult],  # type: ignore[type-arg]
        direction: TrendDirection,
        bos_id: str,
        bar,
    ) -> tuple[str | None, float, float]:
        sign = direction.sign

        def touched(bottom: float, top: float) -> bool:
            if sign > 0:
                return bar.low <= top and bar.close >= bottom
            return bar.high >= bottom and bar.close <= top

        blocks = results["orderblocks"].payload.order_blocks  # type: ignore[attr-defined]
        for ob in blocks:
            if (
                ob.direction is direction
                and ob.status in _OPEN_STATUSES
                and ob.linked_break_id == bos_id
                and touched(ob.zone_bottom, ob.zone_top)
            ):
                return ob.id, ob.zone_bottom, ob.zone_top
        fvgs = results["fvg"].payload.fvgs  # type: ignore[attr-defined]
        for fvg in fvgs:
            if (
                fvg.direction is direction
                and fvg.status is MitigationStatus.UNMITIGATED
                and touched(fvg.zone_bottom, fvg.zone_top)
            ):
                return fvg.id, fvg.zone_bottom, fvg.zone_top
        return None, 0.0, 0.0

    def _zone_in_value(
        self,
        results: dict[str, AnalysisResult],  # type: ignore[type-arg]
        direction: TrendDirection,
        zone_bottom: float,
        zone_top: float,
    ) -> bool:
        """Premium/discount check on the ZONE against the confirmed dealing range.

        The engine's dealing range only spans CONFIRMED external swings, so
        it lags during an active leg. Rule (long; mirrored for shorts):

        - zone inside the confirmed range (``zone_top <= range.high``):
          require the zone to sit in DISCOUNT (``zone_top <= equilibrium``).
        - zone above the confirmed range high: it formed within the fresh,
          not-yet-confirmed BOS leg and is therefore near that leg's origin
          by construction (the OB's ``linked_break_id`` ties it to the BOS)
          — the check passes. No lookahead: this uses only confirmed
          structure plus the zone's own geometry.
        - no dealing range yet: reject (location unverifiable).
        """
        dealing_range = results["premium_discount"].payload.dealing_range  # type: ignore[attr-defined]
        if dealing_range is None:
            return False
        if direction.sign > 0:
            if zone_top > dealing_range.high:
                return True
            return zone_top <= dealing_range.equilibrium
        if zone_bottom < dealing_range.low:
            return True
        return zone_bottom >= dealing_range.equilibrium

    def _target_pool(
        self,
        results: dict[str, AnalysisResult],  # type: ignore[type-arg]
        direction: TrendDirection,
        close: float,
    ) -> tuple[float | None, str | None]:
        """Nearest untapped opposing pool beyond the close (longs target buyside)."""
        want_side = "buyside" if direction.sign > 0 else "sellside"
        pools = [
            pool
            for pool in results["liquidity"].payload.pools  # type: ignore[attr-defined]
            if pool.side is LiquiditySide(want_side)
            and pool.status is PoolStatus.UNTAPPED
            and (pool.price - close) * direction.sign > 0
        ]
        if not pools:
            return None, None
        nearest = min(pools, key=lambda pool: abs(pool.price - close))
        return nearest.price, nearest.id
