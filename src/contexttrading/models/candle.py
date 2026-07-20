"""Market-data primitives: validated candles and immutable series.

Determinism notes:
    - ``Candle.timestamp`` must be timezone-aware and is normalized to UTC.
    - ``CandleSeries`` sorts by timestamp, rejects duplicates, and exposes
      gaps relative to its timeframe — never to wall-clock expectations.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime, timezone
from typing import Any, ClassVar, Self

from pydantic import AwareDatetime, Field, model_validator

from contexttrading.core.constants import Timeframe, TrendDirection
from contexttrading.core.errors import DataError, DataGapError
from contexttrading.core.versioning import SCHEMA_VERSION_CANDLE, SCHEMA_VERSION_GAP_WINDOW
from contexttrading.models.base import VersionedModel


class Candle(VersionedModel, frozen=True):
    """A single OHLCV candle.

    Validation guarantees: prices finite and > 0, ``volume >= 0``,
    ``high >= max(open, close)``, ``low <= min(open, close)``, and a
    timezone-aware timestamp normalized to UTC.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_CANDLE

    timestamp: AwareDatetime = Field(description="Candle open time (normalized to UTC).")
    open: float = Field(gt=0, description="Open price.")
    high: float = Field(gt=0, description="High price.")
    low: float = Field(gt=0, description="Low price.")
    close: float = Field(gt=0, description="Close price.")
    volume: float = Field(ge=0, description="Traded volume (0 allowed for illiquid feeds).")
    tick_count: int | None = Field(default=None, ge=0, description="Optional tick metadata.")
    is_closed: bool = Field(default=True, description="False for a still-forming candle.")

    @model_validator(mode="after")
    def _validate_ohlc(self) -> Candle:
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"high ({self.high}) must be >= max(open, close) "
                f"({max(self.open, self.close)}) at {self.timestamp.isoformat()}"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"low ({self.low}) must be <= min(open, close) "
                f"({min(self.open, self.close)}) at {self.timestamp.isoformat()}"
            )
        if self.high < self.low:
            raise ValueError(f"high ({self.high}) < low ({self.low})")
        return self

    @model_validator(mode="after")
    def _normalize_timestamp(self) -> Candle:
        # AwareDatetime guarantees tz-awareness; normalize to UTC.
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))
        return self

    # -- derived values -----------------------------------------------------

    @property
    def body(self) -> float:
        """Signed candle body (close - open)."""
        return self.close - self.open

    @property
    def range(self) -> float:
        """Total candle range (high - low)."""
        return self.high - self.low

    @property
    def midpoint(self) -> float:
        """Midpoint of the candle range."""
        return (self.high + self.low) / 2

    @property
    def is_bullish(self) -> bool:
        """True when close > open."""
        return self.close > self.open

    @property
    def direction(self) -> TrendDirection:
        """Candle direction: bullish, bearish, or ranging (doji)."""
        if self.close > self.open:
            return TrendDirection.BULLISH
        if self.close < self.open:
            return TrendDirection.BEARISH
        return TrendDirection.RANGING


class GapWindow(VersionedModel, frozen=True):
    """A window of missing candles inside a series."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_GAP_WINDOW

    start: AwareDatetime = Field(description="Timestamp of the last candle before the gap.")
    end: AwareDatetime = Field(description="Timestamp of the first candle after the gap.")
    missing_candles: int = Field(ge=1, description="Number of expected candles absent.")


class CandleSeries:
    """Immutable, ordered, gap-aware container of :class:`Candle` objects.

    Instances are built via the constructor (from candles) or
    :meth:`from_records` (from raw mappings). Candles are sorted by
    timestamp; duplicate timestamps are rejected. All timestamps are UTC.
    """

    __slots__ = ("_candles", "_symbol", "_timeframe", "_timezone_name")

    def __init__(
        self,
        candles: Sequence[Candle],
        *,
        symbol: str,
        timeframe: Timeframe | str,
        timezone_name: str = "UTC",
    ) -> None:
        if not symbol:
            raise DataError("CandleSeries requires a non-empty symbol")
        tf = Timeframe.parse(timeframe) if isinstance(timeframe, str) else timeframe
        ordered = tuple(sorted(candles, key=lambda c: c.timestamp))
        for prev, nxt in zip(ordered, ordered[1:], strict=False):
            if prev.timestamp == nxt.timestamp:
                raise DataError(
                    "Duplicate candle timestamps in series",
                    context={"symbol": symbol, "timestamp": nxt.timestamp.isoformat()},
                )
        self._candles = ordered
        self._symbol = symbol
        self._timeframe = tf
        self._timezone_name = timezone_name

    # -- constructors ---------------------------------------------------------

    @classmethod
    def from_records(
        cls,
        records: Sequence[dict[str, Any] | Candle],
        *,
        symbol: str,
        timeframe: Timeframe | str,
        timezone_name: str = "UTC",
    ) -> Self:
        """Build a series from raw OHLCV mappings or Candle instances.

        Args:
            records: Mappings with ``timestamp/open/high/low/close/volume``
                (plus optional metadata), or pre-built candles.
            symbol: Instrument symbol.
            timeframe: Series timeframe (code like ``"15m"`` or enum).
            timezone_name: Original feed timezone label (metadata only).

        Returns:
            A validated, ordered :class:`CandleSeries`.

        Raises:
            DataError: On duplicate timestamps or invalid records.
        """
        candles: list[Candle] = []
        for i, record in enumerate(records):
            try:
                candles.append(record if isinstance(record, Candle) else Candle(**record))
            except Exception as exc:
                raise DataError(
                    "Invalid candle record",
                    context={"symbol": symbol, "index": i, "error": str(exc)},
                ) from exc
        return cls(candles, symbol=symbol, timeframe=timeframe, timezone_name=timezone_name)

    # -- metadata -------------------------------------------------------------

    @property
    def symbol(self) -> str:
        """Instrument symbol."""
        return self._symbol

    @property
    def timeframe(self) -> Timeframe:
        """Series timeframe."""
        return self._timeframe

    @property
    def timezone_name(self) -> str:
        """Original feed timezone label (all timestamps are UTC regardless)."""
        return self._timezone_name

    @property
    def candles(self) -> tuple[Candle, ...]:
        """Ordered candles as an immutable tuple."""
        return self._candles

    @property
    def start(self) -> datetime | None:
        """Timestamp of the first candle, or None when empty."""
        return self._candles[0].timestamp if self._candles else None

    @property
    def end(self) -> datetime | None:
        """Timestamp of the last candle, or None when empty."""
        return self._candles[-1].timestamp if self._candles else None

    # -- container protocol ---------------------------------------------------

    def __len__(self) -> int:
        return len(self._candles)

    def __iter__(self) -> Iterator[Candle]:
        return iter(self._candles)

    def __getitem__(self, index: int | slice) -> Candle | CandleSeries:
        if isinstance(index, slice):
            return CandleSeries(
                self._candles[index],
                symbol=self._symbol,
                timeframe=self._timeframe,
                timezone_name=self._timezone_name,
            )
        return self._candles[index]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CandleSeries):
            return NotImplemented
        return (
            self._candles == other._candles
            and self._symbol == other._symbol
            and self._timeframe == other._timeframe
        )

    def __repr__(self) -> str:
        return (
            f"CandleSeries(symbol={self._symbol!r}, timeframe={self._timeframe}, "
            f"candles={len(self)})"
        )

    # -- slicing & windows ------------------------------------------------------

    def between(self, start: datetime | None = None, end: datetime | None = None) -> CandleSeries:
        """Return the sub-series with ``start <= timestamp <= end`` (UTC).

        Args:
            start: Inclusive lower bound (None = unbounded). Naive values are
                interpreted as UTC.
            end: Inclusive upper bound (None = unbounded).

        Returns:
            A new :class:`CandleSeries` sharing this series' metadata.
        """
        lo = _as_utc(start) if start is not None else None
        hi = _as_utc(end) if end is not None else None
        selected = tuple(
            c for c in self._candles if (lo is None or c.timestamp >= lo) and (hi is None or c.timestamp <= hi)
        )
        return CandleSeries(
            selected,
            symbol=self._symbol,
            timeframe=self._timeframe,
            timezone_name=self._timezone_name,
        )

    # -- gap awareness ----------------------------------------------------------

    def gaps(self, *, tolerance: float = 1.5) -> list[GapWindow]:
        """Detect missing-candle windows relative to the series timeframe.

        A gap exists when the delta between consecutive candles exceeds
        ``tolerance * timeframe``. Weekends/holidays in real calendars are
        out of scope here — this is a structural check, not a calendar.

        Args:
            tolerance: Multiplier of the expected period above which a delta
                counts as a gap (must be >= 1).

        Returns:
            List of :class:`GapWindow`, in time order.
        """
        if tolerance < 1:
            raise ValueError("tolerance must be >= 1")
        expected = self._timeframe.seconds
        windows: list[GapWindow] = []
        for prev, nxt in zip(self._candles, self._candles[1:], strict=False):
            delta = (nxt.timestamp - prev.timestamp).total_seconds()
            if delta > expected * tolerance:
                missing = int(round(delta / expected)) - 1
                if missing >= 1:
                    windows.append(
                        GapWindow(start=prev.timestamp, end=nxt.timestamp, missing_candles=missing)
                    )
        return windows

    def require_gap_free(self, *, tolerance: float = 1.5) -> None:
        """Raise :class:`DataGapError` if the series contains gaps."""
        found = self.gaps(tolerance=tolerance)
        if found:
            raise DataGapError(
                "Series contains gaps",
                context={
                    "symbol": self._symbol,
                    "timeframe": str(self._timeframe),
                    "gap_count": len(found),
                    "first_gap": found[0].model_dump(mode="json"),
                },
            )

    # -- resampling (contract for Phase 3+) -------------------------------------

    def resample(self, target: Timeframe | str) -> CandleSeries:
        """Resample to a higher timeframe.

        Only upsampling (target duration strictly greater than the current
        timeframe) will be supported. Implemented in Phase 3 alongside the
        structure engine; the signature is the stable contract.

        Args:
            target: Target timeframe (must be larger than the current one).

        Raises:
            NotImplementedError: Always, until Phase 3 lands.
        """
        _ = Timeframe.parse(target) if isinstance(target, str) else target
        raise NotImplementedError("CandleSeries.resample lands in Phase 3")

    # -- serialization ------------------------------------------------------------

    def to_records(self) -> list[dict[str, Any]]:
        """Serialize candles to JSON-ready mappings (stable field order)."""
        return [c.model_dump(mode="json") for c in self._candles]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
