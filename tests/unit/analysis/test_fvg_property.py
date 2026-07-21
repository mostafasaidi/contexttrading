"""Property-based tests (hypothesis) for the FVG engine invariants."""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.core.constants import MitigationStatus
from tests.fixtures import engine_config
from tests.unit.analysis.test_swings_property import _ohlc, _to_series


@given(rows=_ohlc)
@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_fvg_geometry_and_indices_always_valid(rows) -> None:
    """Every detected FVG has a positive zone and ordered formation indices."""
    result = analyze_fvg(_to_series(rows), engine_config())
    for fvg in result.payload.fvgs:
        assert fvg.zone_top > fvg.zone_bottom
        assert fvg.formation_start_index < fvg.middle_index < fvg.formation_end_index
        assert 0.0 <= fvg.strength <= 1.0


@given(rows=_ohlc)
@settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_lifecycle_invariants(rows) -> None:
    """Monotonic lifecycle bookkeeping holds for arbitrary series."""
    result = analyze_fvg(_to_series(rows), engine_config())
    n = len(rows)
    for fvg in result.payload.fvgs:
        assert 0.0 <= fvg.max_fill_fraction <= 1.0
        assert fvg.age >= 0
        if fvg.status is MitigationStatus.UNMITIGATED:
            assert fvg.first_touch_index is None
            assert fvg.filled_index is None
            assert fvg.max_fill_fraction == 0.0
        else:
            assert fvg.first_touch_index is not None
        if fvg.status in (MitigationStatus.MITIGATED, MitigationStatus.VIOLATED):
            assert fvg.filled_index is not None
            assert fvg.max_fill_fraction == 1.0
            assert fvg.first_touch_index <= fvg.filled_index
        if fvg.is_inverse:
            assert fvg.status is MitigationStatus.VIOLATED
            assert fvg.inversion_index is not None
            assert fvg.filled_index <= fvg.inversion_index < n
        assert fvg.touches >= (fvg.first_touch_index is not None)


@given(rows=_ohlc)
@settings(max_examples=15, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_ids_stable_across_reruns(rows) -> None:
    """Two runs over the same series produce identical IDs and ranks."""
    series = _to_series(rows)
    a = analyze_fvg(series, engine_config())
    b = analyze_fvg(series, engine_config())
    assert [f.model_dump() for f in a.payload.fvgs] == [f.model_dump() for f in b.payload.fvgs]
