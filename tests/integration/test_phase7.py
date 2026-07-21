"""Integration: confluence over the 2,000-candle seeded dataset.

Assertions: referential integrity of factor/zone IDs against the real
module outputs, score bounds, and byte-identical reruns.
"""

from __future__ import annotations

import pytest

from contexttrading.analysis.confluence import analyze_confluence
from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.sessions import analyze_sessions
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.config import EngineConfig, SessionConfig
from contexttrading.core.constants import TrendDirection
from contexttrading.models.candle import CandleSeries
from tests.integration.test_pipeline import _dataset


@pytest.fixture(scope="module")
def dataset() -> CandleSeries:
    return _dataset()


@pytest.fixture(scope="module")
def config() -> EngineConfig:
    return EngineConfig()


class TestConfluenceIntegration:
    def test_scores_bounded_and_bias_consistent(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        p = analyze_confluence(dataset, config).payload
        assert 0.0 <= p.bullish_score <= 1.0
        assert 0.0 <= p.bearish_score <= 1.0
        assert p.score == max(p.bullish_score, p.bearish_score)
        if p.bullish_score > p.bearish_score:
            assert p.bias is TrendDirection.BULLISH
        elif p.bearish_score > p.bullish_score:
            assert p.bias is TrendDirection.BEARISH
        else:
            assert p.bias is TrendDirection.RANGING

    def test_all_factor_kinds_evaluated(self, dataset: CandleSeries, config: EngineConfig) -> None:
        p = analyze_confluence(dataset, config).payload
        kinds = {f.factor for f in p.factors}
        # Aggregate factors are always emitted; object factors appear when
        # the dataset produces nearby evidence.
        assert {"trend", "mtf"} <= kinds
        assert kinds <= {
            "trend",
            "mtf",
            "structure",
            "liquidity",
            "premium_discount",
            "fvg",
            "orderblock",
            "supplydemand",
            "session",
        }

    def test_factor_ids_reference_real_objects(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        p = analyze_confluence(dataset, config).payload
        fvg_ids = {f.id for f in analyze_fvg(dataset, config).payload.fvgs}
        ob = analyze_orderblocks(dataset, config).payload
        block_ids = {b.id for b in ob.order_blocks}
        block_ids |= {b.id for b in ob.breaker_blocks}
        block_ids |= {b.id for b in ob.mitigation_blocks}
        sd_ids = {z.id for z in analyze_supplydemand(dataset, config).payload.zones}
        judas_ids = {
            s.id for s in analyze_sessions(dataset, config, SessionConfig()).payload.session_sweeps
        }
        for factor in p.factors:
            if factor.factor == "fvg":
                assert factor.source_id in fvg_ids
            elif factor.factor == "orderblock":
                assert factor.source_id in block_ids
            elif factor.factor == "supplydemand":
                assert factor.source_id in sd_ids
            elif factor.factor == "session":
                assert factor.source_id in judas_ids
            else:
                assert factor.source_id is None

    def test_zone_members_reference_real_objects(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        p = analyze_confluence(dataset, config).payload
        fvg_ids = {f.id for f in analyze_fvg(dataset, config).payload.fvgs}
        ob = analyze_orderblocks(dataset, config).payload
        block_ids = {b.id for b in ob.order_blocks}
        block_ids |= {b.id for b in ob.breaker_blocks}
        block_ids |= {b.id for b in ob.mitigation_blocks}
        sd_ids = {z.id for z in analyze_supplydemand(dataset, config).payload.zones}
        known = fvg_ids | block_ids | sd_ids | {"premium_discount"}
        for zone in p.zones:
            assert 0.0 <= zone.score <= 1.0
            assert len(zone.member_ids) >= 2
            assert set(zone.member_ids) <= known

    def test_deterministic_on_dataset(self, dataset: CandleSeries, config: EngineConfig) -> None:
        a = analyze_confluence(dataset, config)
        b = analyze_confluence(dataset, config)
        assert a.model_dump_json() == b.model_dump_json()
