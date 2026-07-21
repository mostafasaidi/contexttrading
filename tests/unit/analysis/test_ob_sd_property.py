"""Property-based tests (hypothesis) for the OB and supply/demand engines."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.constants import MitigationStatus, SDZoneStatus
from tests.fixtures import engine_config
from tests.unit.analysis.test_swings_property import _ohlc, _to_series

_BLOCKS_TERMINAL = (MitigationStatus.MITIGATED, MitigationStatus.VIOLATED)


@given(rows=_ohlc)
@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_block_geometry_and_lifecycle_invariants(rows) -> None:
    """Every block has a positive zone and monotonic lifecycle bookkeeping."""
    result = analyze_orderblocks(_to_series(rows), engine_config())
    payload = result.payload
    blocks = (*payload.order_blocks, *payload.breaker_blocks, *payload.mitigation_blocks)
    for block in blocks:
        assert block.zone_top > block.zone_bottom
        assert 0.0 <= block.max_penetration_fraction <= 1.0
        assert block.age >= 0
        if block.status is MitigationStatus.UNMITIGATED:
            assert block.first_touch_index is None
            assert block.is_valid
        else:
            assert block.first_touch_index is not None
        if block.status in _BLOCKS_TERMINAL:
            assert block.mitigation_index is not None
            assert block.first_touch_index <= block.mitigation_index
        if block.status is MitigationStatus.VIOLATED:
            assert block.violation_index is not None
            assert block.mitigation_index <= block.violation_index
        assert block.is_valid == (block.status is MitigationStatus.UNMITIGATED)


@given(rows=_ohlc)
@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_breaker_links_resolve(rows) -> None:
    """Breakers always reference an existing, violated source OB."""
    result = analyze_orderblocks(_to_series(rows), engine_config())
    obs = {b.id: b for b in result.payload.order_blocks}
    for brk in result.payload.breaker_blocks:
        assert brk.source_order_block_id in obs
        assert obs[brk.source_order_block_id].status is MitigationStatus.VIOLATED
        assert brk.direction is not obs[brk.source_order_block_id].direction


@given(rows=_ohlc)
@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_zone_geometry_and_lifecycle_invariants(rows) -> None:
    """Every SD zone has a positive zone and consistent lifecycle fields."""
    result = analyze_supplydemand(_to_series(rows), engine_config())
    for zone in result.payload.zones:
        assert zone.zone_top > zone.zone_bottom
        assert 0.0 <= zone.strength <= 1.0
        assert zone.tests >= 0 and zone.age >= 0
        if zone.status is SDZoneStatus.FRESH:
            assert zone.first_touch_index is None
            assert zone.tests == 0
        else:
            assert zone.first_touch_index is not None
        if zone.status is SDZoneStatus.MITIGATED:
            assert zone.mitigated_index is not None
        if zone.status is SDZoneStatus.BROKEN:
            assert zone.broken_index is not None


@given(rows=_ohlc)
@settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_ids_stable_across_reruns(rows) -> None:
    """Two runs over the same series produce identical payloads."""
    series = _to_series(rows)
    a = analyze_orderblocks(series, engine_config()).payload.model_dump_json()
    b = analyze_orderblocks(series, engine_config()).payload.model_dump_json()
    assert a == b
    c = analyze_supplydemand(series, engine_config()).payload.model_dump_json()
    d = analyze_supplydemand(series, engine_config()).payload.model_dump_json()
    assert c == d
