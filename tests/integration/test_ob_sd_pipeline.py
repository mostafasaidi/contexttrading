"""Integration: order block + supply/demand engines on the seeded dataset.

Cross-module invariants (not exact values): referential integrity of every
linked id (structure breaks, FVGs, sweeps, swings, OBs, legs), lifecycle
bounds, finiteness, and byte-level determinism.
"""

from __future__ import annotations

import math

import pytest

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.structure import analyze_structure
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import MitigationStatus, SDZoneStatus
from contexttrading.models.candle import CandleSeries
from tests.integration.test_pipeline import _dataset, _walk_numbers


@pytest.fixture(scope="module")
def dataset() -> CandleSeries:
    return _dataset()


@pytest.fixture(scope="module")
def config() -> EngineConfig:
    return EngineConfig()


class TestOrderBlockPipeline:
    def test_detects_blocks(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_orderblocks(dataset, config)
        assert result.payload.total_count > 0
        assert result.payload.order_blocks, "expected order blocks on 2000 candles"
        assert result.payload.breaker_blocks, "expected breaker blocks on 2000 candles"

    def test_break_and_fvg_links_resolve(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_orderblocks(dataset, config)
        scan = analyze_structure(dataset, config)
        fvg_ids = {f.id for f in analyze_fvg(dataset, config).payload.fvgs}
        break_ids = {b.id for b in scan.payload.breaks}
        for ob in result.payload.order_blocks:
            assert ob.linked_break_id in break_ids
            assert set(ob.overlapping_fvg_ids) <= fvg_ids

    def test_breaker_and_mb_links_resolve(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        result = analyze_orderblocks(dataset, config)
        scan = analyze_structure(dataset, config)
        sweeps = analyze_liquidity(dataset, config).payload.sweeps
        ob_ids = {b.id for b in result.payload.order_blocks}
        break_ids = {b.id for b in scan.payload.breaks}
        swing_ids = {s.id for s in scan.payload.swings}
        for brk in result.payload.breaker_blocks:
            assert brk.source_order_block_id in ob_ids
            assert brk.confirming_break_id in break_ids
        for mb in result.payload.mitigation_blocks:
            assert mb.linked_sweep_id in {s.id for s in sweeps}
            assert mb.failed_swing_id in swing_ids

    def test_lifecycle_bounds(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_orderblocks(dataset, config)
        n = len(dataset.candles)
        blocks = (
            *result.payload.order_blocks,
            *result.payload.breaker_blocks,
            *result.payload.mitigation_blocks,
        )
        for block in blocks:
            assert 0.0 <= block.max_penetration_fraction <= 1.0
            assert 0 <= block.age < n
            assert block.actionable_from_index <= n
            if block.status is MitigationStatus.VIOLATED:
                assert block.violation_index is not None and block.violation_index < n

    def test_no_nan_or_inf_anywhere(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_orderblocks(dataset, config)
        for value in _walk_numbers(result.model_dump()):
            assert math.isfinite(value)


class TestSupplyDemandPipeline:
    def test_detects_zones(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_supplydemand(dataset, config)
        assert result.payload.total_count > 0
        kinds = {z.kind for z in result.payload.zones}
        assert len(kinds) == 2, "expected both supply and demand zones"

    def test_ob_and_leg_links_resolve(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_supplydemand(dataset, config)
        obs = analyze_orderblocks(dataset, config).payload.order_blocks
        scan = analyze_structure(dataset, config)
        ob_ids = {b.id for b in obs}
        leg_ids = {leg.id for leg in scan.payload.legs}
        linked_ob = [z for z in result.payload.zones if z.linked_order_block_id is not None]
        assert linked_ob, "expected OB-linked zones on 2000 candles"
        for zone in linked_ob:
            assert zone.linked_order_block_id in ob_ids
        for zone in result.payload.zones:
            if zone.departure_leg_id is not None:
                assert zone.departure_leg_id in leg_ids
            if zone.is_duplicate:
                assert zone.linked_order_block_id is not None

    def test_lifecycle_bounds(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_supplydemand(dataset, config)
        n = len(dataset.candles)
        for zone in result.payload.zones:
            assert 0 <= zone.age < n
            assert zone.base_start_index <= zone.base_end_index < zone.actionable_from_index
            if zone.status is SDZoneStatus.BROKEN:
                assert zone.broken_index is not None and zone.broken_index < n
            if zone.status is SDZoneStatus.MITIGATED:
                assert zone.mitigated_index is not None and zone.mitigated_index < n
        ranks = sorted(z.rank for z in result.payload.zones)
        assert ranks == list(range(1, len(ranks) + 1))

    def test_no_nan_or_inf_anywhere(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_supplydemand(dataset, config)
        for value in _walk_numbers(result.model_dump()):
            assert math.isfinite(value)

    def test_byte_identical_across_runs(self, dataset: CandleSeries, config: EngineConfig) -> None:
        a = analyze_orderblocks(dataset, config).model_dump_json()
        b = analyze_orderblocks(dataset, config).model_dump_json()
        assert a == b
        c = analyze_supplydemand(dataset, config).model_dump_json()
        d = analyze_supplydemand(dataset, config).model_dump_json()
        assert c == d
