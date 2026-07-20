"""BOS / CHoCH market-structure state machine.

State machine (deterministic, per ``docs/architecture/determinism.md``)
----------------------------------------------------------------------
Swings become **actionable** at candle ``index + lookback`` (confirmation
lag) and are evaluated *before* that candle's own break checks, so a swing
can be broken on its confirmation candle but never earlier.

Per swing class (internal, external) the scanner tracks an independent
:class:`_ClassTracker` with:

- ``highs`` / ``lows``: prices of actionable swings, in order.
- ``sequence_trend``: HH+HL → BULLISH, LH+LL → BEARISH, otherwise RANGING
  (needs >= 2 of each), UNKNOWN before that.
- ``trend`` (active): starts UNKNOWN; the **first** close through the most
  recent actionable swing extreme establishes it (that break is the initial
  BOS). Afterwards the active trend flips **only** on a CHoCH — sequence
  drift alone never flips it.
- ``protected_high`` / ``protected_low``: in a bullish trend the protected
  low is the most recent swing low known when a bullish BOS fires (the low
  that "caused" the break); it updates **only** on BOS events and on initial
  trend establishment — not on every new swing low. Bearish mirror.

Break evaluation at candle ``i`` (per tracker):

- **BOS**: close beyond the most recent same-trend extreme (bullish: last
  swing high). ``margin = close - level`` (in break direction);
  ``STRONG`` when ``margin >= strength_atr_fraction * ATR[i]``, else ``WEAK``.
  When ATR is unavailable the break is conservatively ``WEAK``.
  A confirmed BOS consumes the level: a new swing extreme must form before
  the next BOS in that direction.
- **CHoCH**: close beyond the protected counter-level against the active
  trend; flips the trend and re-anchors protection to the most recent
  opposite extreme.
- **FALSE** (sweep candidate): wick beyond a tracked level without close
  confirmation. Emitted once per level until the level is confirmed-broken
  or replaced; never mutates trend state.

Significance: external breaks are ``MAJOR``, internal breaks ``MINOR``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from contexttrading.analysis.indicators import atr
from contexttrading.analysis.structure.legs import classify_legs
from contexttrading.analysis.structure.swings import detect_swing_sets
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BreakStrength,
    StructureBreakClass,
    StructureBreakSignificance,
    StructureBreakType,
    SwingClass,
    SwingType,
    TrendDirection,
)
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import Candle, CandleSeries
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.models.structure import (
    Leg,
    MarketStructureResult,
    StructureBreak,
    SwingPoint,
    break_style,
)


def sequence_trend(highs: Sequence[float], lows: Sequence[float]) -> TrendDirection:
    """HH+HL → BULLISH, LH+LL → BEARISH, mixed → RANGING, thin → UNKNOWN."""
    if len(highs) < 2 or len(lows) < 2:
        return TrendDirection.UNKNOWN
    hh = highs[-1] > highs[-2]
    hl = lows[-1] > lows[-2]
    lh = highs[-1] < highs[-2]
    ll = lows[-1] < lows[-2]
    if hh and hl:
        return TrendDirection.BULLISH
    if lh and ll:
        return TrendDirection.BEARISH
    return TrendDirection.RANGING


@dataclass
class _ClassTracker:
    """Break-tracking state for one swing class (internal or external)."""

    swing_class: SwingClass
    break_class: StructureBreakClass
    significance: StructureBreakSignificance
    lookback: int
    trend: TrendDirection = TrendDirection.UNKNOWN
    highs: list[float] = field(default_factory=list)
    lows: list[float] = field(default_factory=list)
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None
    protected_high: SwingPoint | None = None
    protected_low: SwingPoint | None = None
    false_emitted_high: bool = False
    false_emitted_low: bool = False

    @property
    def seq_trend(self) -> TrendDirection:
        """Trend implied by the raw swing sequence."""
        return sequence_trend(self.highs, self.lows)

    def absorb(self, swing: SwingPoint) -> None:
        """Register a newly actionable swing."""
        if swing.swing_type is SwingType.HIGH:
            self.highs.append(swing.price)
            self.last_high = swing
            self.false_emitted_high = False
        else:
            self.lows.append(swing.price)
            self.last_low = swing
            self.false_emitted_low = False


@dataclass
class StructureScan:
    """Full internal result of a structure scan (module-internal)."""

    internal_swings: list[SwingPoint]
    external_swings: list[SwingPoint]
    breaks: list[StructureBreak]
    legs: list[Leg]
    protected_high: SwingPoint | None
    protected_low: SwingPoint | None
    external_trend: TrendDirection
    internal_trend: TrendDirection
    external_sequence_trend: TrendDirection
    internal_sequence_trend: TrendDirection
    atr_values: tuple[float | None, ...]


def _classify_margin(
    margin: float, atr_value: float | None, threshold: float
) -> tuple[BreakStrength, float | None]:
    """Strength from close margin vs ATR threshold."""
    if atr_value is None or atr_value <= 0:
        return BreakStrength.WEAK, None
    margin_atr = margin / atr_value
    return (BreakStrength.STRONG if margin_atr >= threshold else BreakStrength.WEAK), margin_atr


class StructureScanner:
    """Runs the BOS/CHoCH state machine over a series."""

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def run(self, series: CandleSeries) -> StructureScan:
        """Scan the series and return the full structure state.

        Raises:
            InsufficientDataError: Below ``config.min_candles``.
        """
        config = self._config
        candles = series.candles
        if len(candles) < config.min_candles:
            raise InsufficientDataError(
                "Series too short for structure analysis",
                context={"candles": len(candles), "min_candles": config.min_candles},
            )
        atr_values = atr(candles, config.atr_period)
        internal_swings, external_swings = detect_swing_sets(series, config)

        trackers = {
            SwingClass.INTERNAL: _ClassTracker(
                swing_class=SwingClass.INTERNAL,
                break_class=StructureBreakClass.INTERNAL,
                significance=StructureBreakSignificance.MINOR,
                lookback=config.internal_swing_lookback,
            ),
            SwingClass.EXTERNAL: _ClassTracker(
                swing_class=SwingClass.EXTERNAL,
                break_class=StructureBreakClass.EXTERNAL,
                significance=StructureBreakSignificance.MAJOR,
                lookback=config.external_swing_lookback,
            ),
        }
        # Swings become actionable at index + lookback; process chronologically.
        pending = sorted(
            internal_swings + external_swings,
            key=lambda s: (s.index + s.lookback, s.index, s.swing_class.value),
        )
        breaks: list[StructureBreak] = []
        cursor = 0
        for i, candle in enumerate(candles):
            while cursor < len(pending) and pending[cursor].index + pending[cursor].lookback <= i:
                swing = pending[cursor]
                trackers[swing.swing_class].absorb(swing)
                cursor += 1
            for tracker in trackers.values():
                breaks.extend(self._evaluate_candle(tracker, i, candle, atr_values[i]))

        external = trackers[SwingClass.EXTERNAL]
        internal = trackers[SwingClass.INTERNAL]
        legs = classify_legs(external_swings, atr_values)
        return StructureScan(
            internal_swings=internal_swings,
            external_swings=external_swings,
            breaks=breaks,
            legs=legs,
            protected_high=external.protected_high,
            protected_low=external.protected_low,
            external_trend=external.trend,
            internal_trend=internal.trend,
            external_sequence_trend=external.seq_trend,
            internal_sequence_trend=internal.seq_trend,
            atr_values=atr_values,
        )

    # -- per-candle evaluation -------------------------------------------------

    def _evaluate_candle(
        self,
        tracker: _ClassTracker,
        index: int,
        candle: Candle,
        atr_value: float | None,
    ) -> list[StructureBreak]:
        out: list[StructureBreak] = []
        # 1. Same-trend extreme: BOS (or FALSE attempt).
        if tracker.last_high is not None and tracker.trend is not TrendDirection.BEARISH:
            brk = self._try_break(
                tracker,
                tracker.last_high,
                index,
                candle,
                atr_value,
                upward=True,
                establishing=tracker.trend is TrendDirection.UNKNOWN,
            )
            if brk is not None:
                out.append(brk)
                if brk.strength is not BreakStrength.FALSE:
                    self._on_bos(tracker, tracker.last_high, upward=True)
        if tracker.last_low is not None and tracker.trend is not TrendDirection.BULLISH:
            brk = self._try_break(
                tracker,
                tracker.last_low,
                index,
                candle,
                atr_value,
                upward=False,
                establishing=tracker.trend is TrendDirection.UNKNOWN,
            )
            if brk is not None:
                out.append(brk)
                if brk.strength is not BreakStrength.FALSE:
                    self._on_bos(tracker, tracker.last_low, upward=False)
        # 2. Protected counter-level: CHoCH against the active trend.
        if tracker.trend is TrendDirection.BULLISH and tracker.protected_low is not None:
            brk = self._try_break(
                tracker, tracker.protected_low, index, candle, atr_value, upward=False, choch=True
            )
            if brk is not None:
                out.append(brk)
                if brk.strength is not BreakStrength.FALSE:
                    self._on_choch(tracker, tracker.protected_low, upward=False)
        elif tracker.trend is TrendDirection.BEARISH and tracker.protected_high is not None:
            brk = self._try_break(
                tracker, tracker.protected_high, index, candle, atr_value, upward=True, choch=True
            )
            if brk is not None:
                out.append(brk)
                if brk.strength is not BreakStrength.FALSE:
                    self._on_choch(tracker, tracker.protected_high, upward=True)
        return out

    # -- event constructors ------------------------------------------------------

    def _try_break(
        self,
        tracker: _ClassTracker,
        level: SwingPoint,
        index: int,
        candle: Candle,
        atr_value: float | None,
        *,
        upward: bool,
        choch: bool = False,
        establishing: bool = False,
    ) -> StructureBreak | None:
        """Build a break event for one level/candle, or None if untouched."""
        if upward:
            wick_breach = candle.high > level.price
            confirmed = candle.close > level.price
            wick_extreme = candle.high
            margin = candle.close - level.price
        else:
            wick_breach = candle.low < level.price
            confirmed = candle.close < level.price
            wick_extreme = candle.low
            margin = level.price - candle.close
        if not wick_breach:
            return None

        direction = TrendDirection.BULLISH if upward else TrendDirection.BEARISH
        if choch:
            break_type = StructureBreakType.CHOCH
        elif establishing and tracker.trend is TrendDirection.UNKNOWN:
            break_type = StructureBreakType.BOS  # initial trend-establishing break
        elif tracker.trend is TrendDirection.UNKNOWN:
            return None  # no trend context and not an extreme break — ignore
        else:
            break_type = StructureBreakType.BOS

        if confirmed:
            strength, margin_atr = _classify_margin(
                margin, atr_value, self._config.strength_atr_fraction
            )
            return StructureBreak(
                broken_swing_id=level.id,
                broken_swing_price=level.price,
                broken_swing_class=level.swing_class,
                break_index=index,
                break_timestamp=candle.timestamp,
                break_price=candle.close,
                direction=direction,
                break_type=break_type,
                break_class=tracker.break_class,
                significance=tracker.significance,
                strength=strength,
                margin_atr=margin_atr,
                is_sweep_candidate=False,
                style=break_style(break_type, direction, strength),
            )
        # Wick-only breach → FALSE, once per level.
        if (upward and tracker.false_emitted_high) or (not upward and tracker.false_emitted_low):
            return None
        if upward:
            tracker.false_emitted_high = True
        else:
            tracker.false_emitted_low = True
        return StructureBreak(
            broken_swing_id=level.id,
            broken_swing_price=level.price,
            broken_swing_class=level.swing_class,
            break_index=index,
            break_timestamp=candle.timestamp,
            break_price=wick_extreme,
            direction=direction,
            break_type=break_type,
            break_class=tracker.break_class,
            significance=tracker.significance,
            strength=BreakStrength.FALSE,
            margin_atr=None,
            is_sweep_candidate=True,
            style=break_style(break_type, direction, BreakStrength.FALSE),
        )

    def _on_bos(self, tracker: _ClassTracker, level: SwingPoint, *, upward: bool) -> None:
        """State transition after a confirmed BOS (or initial establishment)."""
        if upward:
            tracker.trend = TrendDirection.BULLISH
            tracker.last_high = None  # level consumed
            # Protect the most recent swing low (the cause of the break).
            if tracker.last_low is not None:
                tracker.protected_low = tracker.last_low
        else:
            tracker.trend = TrendDirection.BEARISH
            tracker.last_low = None
            if tracker.last_high is not None:
                tracker.protected_high = tracker.last_high

    def _on_choch(self, tracker: _ClassTracker, level: SwingPoint, *, upward: bool) -> None:
        """State transition after a confirmed CHoCH (trend flip)."""
        if upward:  # was bearish, now bullish
            tracker.trend = TrendDirection.BULLISH
            tracker.protected_high = None
            if tracker.last_low is not None:
                tracker.protected_low = tracker.last_low
        else:  # was bullish, now bearish
            tracker.trend = TrendDirection.BEARISH
            tracker.protected_low = None
            if tracker.last_high is not None:
                tracker.protected_high = tracker.last_high


def analyze_structure(
    series: CandleSeries,
    config: EngineConfig | None = None,
) -> AnalysisResult[MarketStructureResult]:
    """Run the full structure engine over a series.

    Args:
        series: Input candles.
        config: Engine thresholds (defaults when None).

    Returns:
        Envelope with swings, breaks, legs, and protected levels.
    """
    config = config or EngineConfig()
    scan = StructureScanner(config).run(series)
    payload = MarketStructureResult(
        swings=sorted(
            scan.internal_swings + scan.external_swings,
            key=lambda s: (s.index, s.swing_class.value, s.swing_type.value),
        ),
        breaks=scan.breaks,
        legs=scan.legs,
        protected_high=scan.protected_high,
        protected_low=scan.protected_low,
    )
    return AnalysisResult[MarketStructureResult](
        module="structure",
        symbol=series.symbol,
        timeframe=series.timeframe,
        generated_from=DataWindow(
            start=series.start, end=series.end, candle_count=len(series)  # type: ignore[arg-type]
        ),
        payload=payload,
    )
