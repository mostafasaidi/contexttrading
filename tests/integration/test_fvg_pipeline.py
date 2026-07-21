"""Integration: FVG engine over the 2,000-candle synthetic dataset.

Cross-module invariants (not exact values): FVG↔structure linkage integrity,
lifecycle bounds, finiteness, and byte-level determinism.
"""

from __future__ import annotations

import math

import pytest

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.structure import analyze_structure
from contexttrading.core.config import EngineConfig
from contexttrading.core.constants import MitigationStatus
from contexttrading.models.candle import CandleSeries
from tests.integration.test_pipeline import _dataset, _walk_numbers


@pytest.fixture(scope="module")
def dataset() -> CandleSeries:
    return _dataset()


@pytest.fixture(scope="module")
def config() -> EngineConfig:
    return EngineConfig()


class TestFvgPipeline:
    def test_detects_fvgs(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_fvg(dataset, config)
        assert result.payload.total_count > 0
        assert result.payload.total_count == len(result.payload.fvgs)

    def test_linked_breaks_exist_in_structure_output(
        self, dataset: CandleSeries, config: EngineConfig
    ) -> None:
        fvg_result = analyze_fvg(dataset, config)
        scan = analyze_structure(dataset, config)
        break_ids = {b.id for b in scan.payload.breaks}
        margins = {b.id: b.margin_atr for b in scan.payload.breaks}
        linked = [f for f in fvg_result.payload.fvgs if f.linked_break_id is not None]
        assert linked, "expected some displacement-linked FVGs on 2000 candles"
        for fvg in linked:
            assert fvg.linked_break_id in break_ids
            # margin mirrored from the source break (None during ATR warmup)
            assert fvg.displacement_margin_atr == margins[fvg.linked_break_id]

    def test_parent_references_resolve(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_fvg(dataset, config)
        ids = {f.id for f in result.payload.fvgs}
        for fvg in result.payload.fvgs:
            if fvg.parent_fvg_id is not None:
                assert fvg.is_nested
                assert fvg.parent_fvg_id in ids
            if fvg.stack_group_id is not None:
                members = [f for f in result.payload.fvgs if f.stack_group_id == fvg.stack_group_id]
                assert len(members) >= 2  # groups of one are never emitted

    def test_lifecycle_bounds(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_fvg(dataset, config)
        n = len(dataset.candles)
        for fvg in result.payload.fvgs:
            assert 0.0 <= fvg.max_fill_fraction <= 1.0
            assert 0 <= fvg.age < n
            assert fvg.formation_end_index < n
            if fvg.is_inverse:
                assert fvg.status is MitigationStatus.VIOLATED
                assert fvg.inversion_index is not None and fvg.inversion_index < n
            ranks = sorted(f.rank for f in result.payload.fvgs)
            assert ranks == list(range(1, len(ranks) + 1))

    def test_no_nan_or_inf_anywhere(self, dataset: CandleSeries, config: EngineConfig) -> None:
        result = analyze_fvg(dataset, config)
        for value in _walk_numbers(result.model_dump()):
            assert math.isfinite(value)

    def test_byte_identical_across_runs(self, dataset: CandleSeries, config: EngineConfig) -> None:
        a = analyze_fvg(dataset, config).model_dump_json()
        b = analyze_fvg(dataset, config).model_dump_json()
        assert a == b
