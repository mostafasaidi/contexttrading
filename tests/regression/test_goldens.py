"""Regression goldens: byte-exact engine outputs for fixed datasets.

Golden files live in ``tests/regression/goldens/``. Regenerate intentionally
(with a version bump + migration note) via::

    CT_UPDATE_GOLDENS=1 python -m pytest tests/regression -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.premium_discount import analyze_dealing_range
from contexttrading.analysis.structure import analyze_structure, analyze_trend
from tests.fixtures import (
    downtrend_series,
    engine_config,
    fakeout_records,
    to_series,
    uptrend_series,
    v_reversal_series,
)
from tests.fvg_fixtures import inversion_series, nested_fvg_records

GOLDENS_DIR = Path(__file__).parent / "goldens"
UPDATE = os.environ.get("CT_UPDATE_GOLDENS") == "1"


def _assert_golden(name: str, payload_json: str) -> None:
    path = GOLDENS_DIR / name
    # Canonicalize: parse and re-dump with stable formatting for comparison.
    actual = json.dumps(json.loads(payload_json), indent=2, sort_keys=True) + "\n"
    if UPDATE:
        path.write_text(actual, encoding="utf-8")
    if not path.exists():
        pytest.fail(f"Golden missing: {path}. Run with CT_UPDATE_GOLDENS=1 to create it.")
    expected = path.read_text(encoding="utf-8")
    assert (
        actual == expected
    ), f"Golden mismatch: {name} (intentional change? bump version + regenerate)"


class TestStructureGoldens:
    def test_uptrend_structure(self) -> None:
        result = analyze_structure(uptrend_series(), engine_config())
        _assert_golden("structure_uptrend.json", result.model_dump_json())

    def test_downtrend_structure(self) -> None:
        result = analyze_structure(downtrend_series(), engine_config())
        _assert_golden("structure_downtrend.json", result.model_dump_json())

    def test_v_reversal_structure(self) -> None:
        result = analyze_structure(v_reversal_series(), engine_config())
        _assert_golden("structure_v_reversal.json", result.model_dump_json())

    def test_uptrend_trend_state(self) -> None:
        result = analyze_trend(uptrend_series(), engine_config())
        _assert_golden("trend_uptrend.json", result.model_dump_json())


class TestLiquidityGoldens:
    def test_fakeout_liquidity(self) -> None:
        result = analyze_liquidity(to_series(fakeout_records(), symbol="FAKE"), engine_config())
        _assert_golden("liquidity_fakeout.json", result.model_dump_json())


class TestDealingRangeGoldens:
    def test_uptrend_dealing_range(self) -> None:
        result = analyze_dealing_range(uptrend_series(), engine_config())
        _assert_golden("dealing_range_uptrend.json", result.model_dump_json())


class TestFvgGoldens:
    def test_uptrend_fvg(self) -> None:
        result = analyze_fvg(uptrend_series(), engine_config())
        _assert_golden("fvg_uptrend.json", result.model_dump_json())

    def test_nested_fvg(self) -> None:
        result = analyze_fvg(to_series(nested_fvg_records(), symbol="NEST"), engine_config())
        _assert_golden("fvg_nested.json", result.model_dump_json())

    def test_inversion_fvg(self) -> None:
        result = analyze_fvg(inversion_series(), engine_config())
        _assert_golden("fvg_inversion.json", result.model_dump_json())
