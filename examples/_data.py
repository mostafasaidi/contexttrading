"""Deterministic example datasets (seeded; no network, no files).

Regimes (all start at 100.0, 15m bars from 2024-01-01 UTC):

- ``trend_up``: persistent drift up with shallow pullbacks — the SMC
  pullback strategy's home turf (structure breaks, active OBs).
- ``range``: mean-reverting noise around 100 — liquidity sweeps at the
  range edges, few confirmed breaks.
- ``volatile``: calm baseline with periodic news-style spikes (large
  wicks, volume bursts) — stress-tests lifecycle rules.
- ``low_liquidity``: tiny bodies, sparse volume, flat stretches — engines
  must stay quiet and NaN-free.

Every series is a pure function of (regime, count, seed).
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

from contexttrading.models.candle import CandleSeries

REGIMES: tuple[str, ...] = ("trend_up", "range", "volatile", "low_liquidity")

_START = datetime(2024, 1, 1, tzinfo=UTC)


def regime_records(regime: str = "trend_up", count: int = 300, seed: int = 11) -> list[dict]:
    """Generate OHLCV records for one documented market regime."""
    if regime not in REGIMES:
        raise ValueError(f"unknown regime {regime!r}; choose from {REGIMES}")
    rng = random.Random(f"{seed}:{regime}")
    records: list[dict] = []
    price = 100.0
    for i in range(count):
        wave = math.sin(i / 17.0)
        if regime == "trend_up":
            drift, vol = 0.11 + 0.05 * wave, 0.35
            volume = 900 + 300 * wave
        elif regime == "range":
            drift, vol = 0.35 * wave, 0.25
            volume = 800.0
        elif regime == "volatile":
            spike = i % 89 == 44  # news spike every ~day on 15m
            drift, vol = (rng.choice((-1, 1)) * 1.8, 1.6) if spike else (0.03 * wave, 0.3)
            volume = 4000.0 if spike else 600.0
        else:  # low_liquidity
            drift, vol = 0.005 * wave, 0.06
            volume = 40 + 20 * (i % 7 == 0)
        open_ = price
        close = price + drift + rng.uniform(-vol, vol)
        close = max(close, 1.0)  # never non-positive
        high = max(open_, close) + rng.uniform(0.02, vol)
        low = min(open_, close) - rng.uniform(0.02, vol)
        low = max(low, 0.5)
        records.append(
            {
                "timestamp": (_START + timedelta(minutes=15 * i)).isoformat(),
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": round(volume + rng.uniform(0, 50), 1),
            }
        )
        price = close
    return records


def regime_series(
    regime: str = "trend_up", count: int = 300, seed: int = 11, symbol: str = "EXAMPLE"
) -> CandleSeries:
    """CandleSeries for one regime (15m timeframe)."""
    return CandleSeries.from_records(
        regime_records(regime, count, seed), symbol=symbol, timeframe="15m"
    )
