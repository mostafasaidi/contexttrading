"""Shared fixtures for the ContextTrading test suite."""

from __future__ import annotations

from datetime import UTC
from typing import Any

import pytest

from contexttrading.models.candle import CandleSeries


def make_records(
    count: int = 10,
    *,
    start: str = "2024-01-01T00:00:00Z",
    step_seconds: int = 60,
    base_price: float = 100.0,
) -> list[dict[str, Any]]:
    """Deterministic zig-zag candle records for tests."""
    from datetime import datetime, timedelta

    t0 = datetime.fromisoformat(start.replace("Z", "+00:00")).astimezone(UTC)
    records: list[dict[str, Any]] = []
    price = base_price
    for i in range(count):
        drift = 1.0 if i % 2 == 0 else -0.8
        open_ = price
        close = price + drift
        high = max(open_, close) + 0.5
        low = min(open_, close) - 0.5
        records.append(
            {
                "timestamp": (t0 + timedelta(seconds=step_seconds * i)).isoformat(),
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": 1000.0 + i,
            }
        )
        price = close
    return records


@pytest.fixture()
def candle_records() -> list[dict[str, Any]]:
    """Ten deterministic 1-minute candle records."""
    return make_records(10)


@pytest.fixture()
def series(candle_records: list[dict[str, Any]]) -> CandleSeries:
    """A 10-candle 1m series for symbol TEST."""
    return CandleSeries.from_records(candle_records, symbol="TEST", timeframe="1m")
