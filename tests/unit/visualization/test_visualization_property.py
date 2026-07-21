"""Property tests: primitives stay traceable to their source objects.

For every mapper, each emitted primitive's ``source_id`` must be the id of
an object in the input result (or a documented synthetic id for aggregate
geometry like range bands and HTF levels), and every time coordinate must
fall inside the input series, in UNIX seconds.
"""

from __future__ import annotations

from collections.abc import Iterable

from contexttrading.visualization.primitives import RenderPrimitive, to_unix_seconds
from tests.fixtures import (
    engine_config,
    five_day_15m_series,
    full_stack_results,
    uptrend_series,
)

#: Aggregate primitives that have no single backing object id.
_SYNTHETIC_PREFIXES = ("range:", "mtf:")


def _object_ids(results) -> set[str]:
    ids: set[str] = set()

    def add(items: Iterable) -> None:
        for item in items:
            if hasattr(item, "id"):
                ids.add(item.id)

    structure = results["structure"].payload
    add(structure.swings)
    add(structure.breaks)
    liquidity = results["liquidity"].payload
    add(liquidity.equal_levels)
    add(liquidity.pools)
    add(liquidity.sweeps)
    add(results["fvg"].payload.fvgs)
    orderblocks = results["orderblocks"].payload
    add(orderblocks.order_blocks)
    add(orderblocks.breaker_blocks)
    add(orderblocks.mitigation_blocks)
    add(results["supplydemand"].payload.zones)
    sessions = results["sessions"].payload
    add(sessions.sessions)
    add(sessions.pools)
    add(sessions.session_sweeps)
    add(results["confluence"].payload.zones)
    return ids


def _all_times(prim: RenderPrimitive) -> list[int]:
    return [
        value
        for key, value in prim.model_dump().items()
        if key.endswith("time") and isinstance(value, int)
    ]


def test_primitives_traceable_and_bounded() -> None:
    series = five_day_15m_series()
    results = full_stack_results(series, engine_config())
    ids = _object_ids(results)
    from contexttrading.visualization import build_chart_payload

    chart = build_chart_payload(series, results).payload
    first = to_unix_seconds(series.candles[0].timestamp)
    last = to_unix_seconds(series.candles[-1].timestamp)
    total = 0
    for layer in chart.layers:
        for prim in layer.primitives:
            total += 1
            assert prim.source_id in ids or prim.source_id.startswith(
                _SYNTHETIC_PREFIXES
            ), f"untraceable source_id {prim.source_id!r} on layer {layer.name}"
            for value in _all_times(prim):
                assert first <= value <= last
                assert value < 10**12
    assert total > 0, "full stack must produce primitives"


def test_uptrend_subset_traceable() -> None:
    series = uptrend_series()
    results = full_stack_results(series, engine_config())
    ids = _object_ids(results)
    from contexttrading.visualization import build_chart_payload

    chart = build_chart_payload(series, results).payload
    for layer in chart.layers:
        for prim in layer.primitives:
            assert prim.source_id in ids or prim.source_id.startswith(_SYNTHETIC_PREFIXES)
