"""Integration: full Phase-3 pipeline over a 2,000-candle synthetic dataset.

Dataset: seeded (deterministic) random walk with regime shifts — trending
legs alternating with ranges — plus occasional volume spikes. Assertions are
cross-module consistency invariants, not exact values.
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

import pytest

from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.premium_discount import analyze_dealing_range
from contexttrading.analysis.structure import analyze_structure, analyze_trend
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import (
    BreakStrength,
    PoolStatus,
    StructureBreakType,
)
from contexttrading.models.candle import CandleSeries

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _dataset(count: int = 2000, seed: int = 7) -> CandleSeries:
    rng = random.Random(seed)
    records = []
    price = 100.0
    i = 0
    while i < count:
        regime_len = rng.randint(80, 200)
        drift = rng.choice([-0.15, -0.08, 0.0, 0.08, 0.15])
        for _ in range(regime_len):
            if i >= count:
                break
            shock = rng.gauss(0, 0.35)
            if rng.random() < 0.01:  # news-style spike
                shock *= 6
            o = price
            c = price + drift + shock
            h = max(o, c) + abs(rng.gauss(0, 0.15))
            lo = min(o, c) - abs(rng.gauss(0, 0.15))
            v = max(1.0, 1000 + rng.gauss(0, 150) + (4000 if abs(shock) > 1.5 else 0))
            records.append(
                {
                    "timestamp": (T0 + timedelta(minutes=i)).isoformat(),
                    "open": round(o, 4),
                    "high": round(h, 4),
                    "low": round(lo, 4),
                    "close": round(c, 4),
                    "volume": round(v, 2),
                }
            )
            price = c
            i += 1
    return CandleSeries.from_records(records, symbol="SYNTH", timeframe="1m")


@pytest.fixture(scope="module")
def dataset() -> CandleSeries:
    return _dataset()


@pytest.fixture(scope="module")
def config() -> EngineConfig:
    return EngineConfig()


class TestFullPipeline:
    def test_structure_runs(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_structure(dataset, config)
        assert result.payload.swings
        assert result.generated_from.candle_count == 2000

    def test_every_break_references_existing_swing(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        result = analyze_structure(dataset, config)
        swing_ids = {s.id for s in result.payload.swings}
        assert result.payload.breaks
        for b in result.payload.breaks:
            assert b.broken_swing_id in swing_ids

    def test_confirmed_breaks_close_beyond_level(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        result = analyze_structure(dataset, config)
        closes = {i: c.close for i, c in enumerate(dataset.candles)}
        for b in result.payload.breaks:
            if b.strength is BreakStrength.FALSE:
                continue
            close = closes[b.break_index]
            if b.direction == "bullish":
                assert close > b.broken_swing_price
            else:
                assert close < b.broken_swing_price

    def test_no_nan_or_inf_anywhere(self, dataset: CandleSeries, config: EngineConfig) -> None:
        for result in (
            analyze_structure(dataset, config),
            analyze_trend(dataset, config),
            analyze_liquidity(dataset, config),
            analyze_dealing_range(dataset, config),
        ):
            for value in _walk_numbers(result.model_dump()):
                assert not math.isnan(value) and not math.isinf(value)

    def test_pool_statuses_monotonic(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_liquidity(dataset, config)
        swept_ids = {s.pool_id for s in result.payload.sweeps}
        for pool in result.payload.pools:
            if pool.status is PoolStatus.SWEPT:
                assert pool.id in swept_ids
            # BROKEN pools must not also have a sweep event.
            if pool.status is PoolStatus.BROKEN:
                assert pool.id not in swept_ids

    def test_choch_implies_prior_trend(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_structure(dataset, config)
        bos_or_establishing = [
            b for b in result.payload.breaks if b.break_type is StructureBreakType.BOS
        ]
        choch = [b for b in result.payload.breaks if b.break_type is StructureBreakType.CHOCH]
        if choch:
            assert bos_or_establishing  # a trend existed before any flip

    def test_dealing_range_consistency(self, dataset: CandleSeries, config: EngineConfig) -> None:
        structure = analyze_structure(dataset, config)
        result = analyze_dealing_range(dataset, config)
        dr = result.payload.dealing_range
        if dr is None:
            assert not structure.payload.swings
            return
        swing_ids = {s.id for s in structure.payload.swings}
        assert dr.high_swing_id in swing_ids
        assert dr.low_swing_id in swing_ids
        assert dr.low < dr.equilibrium < dr.high
        assert dr.low <= dr.ote_low <= dr.ote_high <= dr.high

    def test_full_pipeline_deterministic(self, dataset: CandleSeries, config: EngineConfig) -> None:
        first = analyze_liquidity(dataset, config).model_dump_json()
        second = analyze_liquidity(dataset, config).model_dump_json()
        assert first == second


def _walk_numbers(node: object) -> list[float]:
    out: list[float] = []
    if isinstance(node, float):
        out.append(node)
    elif isinstance(node, dict):
        for v in node.values():
            out.extend(_walk_numbers(v))
    elif isinstance(node, (list, tuple)):
        for v in node:
            out.extend(_walk_numbers(v))
    return out
