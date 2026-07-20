"""TrendEngine: composite trend state from structure, swings, and legs.

Deterministic heuristics (all thresholds in :class:`EngineConfig`)
------------------------------------------------------------------
- ``direction``: the active external trend from the structure state machine
  (UNKNOWN when nothing established yet).
- ``internal_trend``: sequence trend of internal swings.
- ``strength``: combines
    - ``impulse_correction_ratio`` = mean impulse ATR-magnitude / mean
      correction ATR-magnitude over classified legs, and
    - ``bos_follow_through`` = fraction of confirmed external BOS events
      that were STRONG.
  ``STRONG`` when ratio >= ``strong_impulse_ratio`` and follow-through >= 0.5;
  ``WEAK`` when ratio < 1.0 or follow-through < 0.25 (with data present);
  otherwise ``MODERATE``.
- ``market_phase``: evaluated over the last ``phase_lookback`` candles:
    1. ``CONSOLIDATION`` when (max high - min low) <
       ``consolidation_range_atr_multiple * ATR_latest``;
    2. else ``EXPANSION`` when a confirmed BOS in the active trend direction
       fired within the lookback window;
    3. else, when the last two legs overlap by >= ``swing_overlap_fraction``
       of the shorter leg: ``DISTRIBUTION`` in a bullish trend,
       ``ACCUMULATION`` in a bearish trend;
    4. fallback: ``EXPANSION`` when trending, else ``CONSOLIDATION``.
- ``confidence_basis``: deterministic evidence tags with values taken from
  the data (fixed-precision formatting), never free-form text.
"""

from __future__ import annotations

from collections.abc import Sequence

from contexttrading.analysis.structure.structure import StructureScan, StructureScanner
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BreakStrength,
    LegKind,
    MarketPhase,
    StructureBreakType,
    TrendDirection,
    TrendStrength,
)
from contexttrading.models.candle import CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.models.structure import Leg, StructureBreak, TrendResult, TrendState


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def impulse_correction_ratio(legs: Sequence[Leg]) -> float | None:
    """Mean impulse ATR-magnitude / mean correction ATR-magnitude."""
    impulses = [
        leg.atr_multiple for leg in legs if leg.kind is LegKind.IMPULSE and leg.atr_multiple
    ]
    corrections = [
        leg.atr_multiple for leg in legs if leg.kind is LegKind.CORRECTION and leg.atr_multiple
    ]
    if not impulses or not corrections:
        return None
    mean_impulse = _mean(impulses)
    mean_correction = _mean(corrections)
    if not mean_impulse or not mean_correction:
        return None
    return mean_impulse / mean_correction


def bos_follow_through(breaks: Sequence[StructureBreak]) -> float | None:
    """Fraction of confirmed external BOS events classified STRONG."""
    confirmed = [
        b
        for b in breaks
        if b.break_type is StructureBreakType.BOS and b.strength is not BreakStrength.FALSE
    ]
    if not confirmed:
        return None
    strong = sum(1 for b in confirmed if b.strength is BreakStrength.STRONG)
    return strong / len(confirmed)


def leg_overlap_fraction(legs: Sequence[Leg]) -> float | None:
    """Price-interval overlap of the last two legs / shorter leg length."""
    if len(legs) < 2:
        return None
    a, b = legs[-2], legs[-1]
    lo = max(min(a.start_price, a.end_price), min(b.start_price, b.end_price))
    hi = min(max(a.start_price, a.end_price), max(b.start_price, b.end_price))
    shorter = min(a.magnitude, b.magnitude)
    if shorter <= 0 or hi <= lo:
        return 0.0
    return (hi - lo) / shorter


class TrendEngine:
    """Derives :class:`TrendState` from a structure scan."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def evaluate(self, series: CandleSeries, scan: StructureScan) -> TrendState:
        """Compute the composite trend state."""
        direction = scan.external_trend
        ratio = impulse_correction_ratio(scan.legs)
        follow = bos_follow_through(scan.breaks)
        strength = self._strength(ratio, follow)
        phase, phase_basis = self._market_phase(series, scan, direction)
        basis = self._basis(scan, ratio, follow) + phase_basis
        return TrendState(
            direction=direction,
            external_trend=scan.external_trend,
            internal_trend=(
                scan.internal_trend
                if scan.internal_trend is not TrendDirection.UNKNOWN
                else scan.internal_sequence_trend
            ),
            strength=strength,
            market_phase=phase,
            impulse_correction_ratio=ratio,
            bos_follow_through=follow,
            confidence_basis=basis,
        )

    # -- internals ------------------------------------------------------------

    def _strength(self, ratio: float | None, follow: float | None) -> TrendStrength:
        if ratio is None and follow is None:
            return TrendStrength.MODERATE
        if ratio is not None and ratio < 1.0:
            return TrendStrength.WEAK
        if follow is not None and follow < 0.25:
            return TrendStrength.WEAK
        ratio_ok = ratio is not None and ratio >= self._config.strong_impulse_ratio
        follow_ok = follow is not None and follow >= 0.5
        if ratio_ok and follow_ok:
            return TrendStrength.STRONG
        return TrendStrength.MODERATE

    def _market_phase(
        self,
        series: CandleSeries,
        scan: StructureScan,
        direction: TrendDirection,
    ) -> tuple[MarketPhase, list[str]]:
        config = self._config
        candles = series.candles
        window = candles[-config.phase_lookback :]
        basis: list[str] = []
        atr_latest = next((v for v in reversed(scan.atr_values) if v is not None), None)

        if atr_latest and window:
            span = max(c.high for c in window) - min(c.low for c in window)
            if span < config.consolidation_range_atr_multiple * atr_latest:
                basis.append(f"range_compression:{span / atr_latest:.2f}atr")
                return MarketPhase.CONSOLIDATION, basis

        cutoff = len(candles) - config.phase_lookback
        recent_bos = [
            b
            for b in scan.breaks
            if b.break_index >= cutoff
            and b.break_type is StructureBreakType.BOS
            and b.strength is not BreakStrength.FALSE
            and b.direction is direction
        ]
        if recent_bos and direction in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            basis.append(f"recent_bos_in_trend:{len(recent_bos)}")
            return MarketPhase.EXPANSION, basis

        overlap = leg_overlap_fraction(scan.legs)
        if overlap is not None and overlap >= config.swing_overlap_fraction:
            basis.append(f"leg_overlap:{overlap:.2f}")
            if direction is TrendDirection.BULLISH:
                return MarketPhase.DISTRIBUTION, basis
            if direction is TrendDirection.BEARISH:
                return MarketPhase.ACCUMULATION, basis

        if direction in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            basis.append("trend_active_no_compression")
            return MarketPhase.EXPANSION, basis
        basis.append("no_trend_no_expansion")
        return MarketPhase.CONSOLIDATION, basis

    def _basis(
        self,
        scan: StructureScan,
        ratio: float | None,
        follow: float | None,
    ) -> list[str]:
        basis: list[str] = []
        seq = scan.external_sequence_trend
        if seq is TrendDirection.BULLISH:
            basis.append("hh_hl_sequence")
        elif seq is TrendDirection.BEARISH:
            basis.append("lh_ll_sequence")
        elif seq is TrendDirection.RANGING:
            basis.append("mixed_sequence")
        else:
            basis.append("sequence_undetermined")
        if follow is not None:
            confirmed = sum(
                1
                for b in scan.breaks
                if b.break_type is StructureBreakType.BOS and b.strength is not BreakStrength.FALSE
            )
            strong = sum(
                1
                for b in scan.breaks
                if b.break_type is StructureBreakType.BOS and b.strength is BreakStrength.STRONG
            )
            basis.append(f"strong_bos:{strong}/{confirmed}")
        if ratio is not None:
            basis.append(f"impulse_correction_ratio:{ratio:.2f}")
        return basis


def analyze_trend(
    series: CandleSeries,
    config: EngineConfig | None = None,
) -> AnalysisResult[TrendResult]:
    """Run the trend engine (structure scan + composite state)."""
    config = config or EngineConfig()
    scan = StructureScanner(config).run(series)
    state = TrendEngine(config).evaluate(series, scan)
    return AnalysisResult[TrendResult](
        module="trend",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=TrendResult(state=state),
    )
