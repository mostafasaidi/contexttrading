"""Scratch smoke test for the structure engine (not part of the test suite)."""

import random
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "src")

from contexttrading.analysis.structure import analyze_structure, analyze_trend
from contexttrading.core.config import EngineConfig
from contexttrading.models.candle import CandleSeries

random.seed(42)
t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
records, price = [], 100.0
for i in range(120):
    drift = 0.6 if (i // 10) % 3 != 2 else -0.9
    noise = random.uniform(-0.2, 0.2)
    o = price
    c = price + drift + noise
    h = max(o, c) + random.uniform(0.1, 0.4)
    lo = min(o, c) - random.uniform(0.1, 0.4)
    records.append(
        {
            "timestamp": (t0 + timedelta(minutes=i)).isoformat(),
            "open": round(o, 4),
            "high": round(h, 4),
            "low": round(lo, 4),
            "close": round(c, 4),
            "volume": 1000 + random.uniform(-100, 100),
        }
    )
    price = c

s = CandleSeries.from_records(records, symbol="TEST", timeframe="1m")
cfg = EngineConfig(min_candles=50)
res = analyze_structure(s, cfg)
p = res.payload
print("swings:", len(p.swings), "external:", sum(1 for x in p.swings if x.swing_class == "external"))
print("breaks:", [(b.break_type, b.direction, b.strength, b.break_index) for b in p.breaks][:8])
print("legs:", [(leg.direction, leg.kind) for leg in p.legs][:6])
print("protected_low:", p.protected_low.price if p.protected_low else None)
t = analyze_trend(s, cfg)
print("trend:", t.payload.state.direction, t.payload.state.strength, t.payload.state.market_phase)
print("basis:", t.payload.state.confidence_basis)
