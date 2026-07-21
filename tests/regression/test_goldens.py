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

from contexttrading.analysis.confluence import analyze_confluence
from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.liquidity import analyze_liquidity
from contexttrading.analysis.mtf import analyze_mtf
from contexttrading.analysis.orderblocks import analyze_orderblocks
from contexttrading.analysis.premium_discount import analyze_dealing_range
from contexttrading.analysis.sessions import analyze_sessions
from contexttrading.analysis.structure import analyze_structure, analyze_trend
from contexttrading.analysis.supplydemand import analyze_supplydemand
from contexttrading.core.config import SessionConfig
from contexttrading.visualization import build_chart_payload
from tests.fixtures import (
    MTF_UPTREND_PIVOTS,
    downtrend_series,
    engine_config,
    fakeout_records,
    five_day_15m_series,
    full_stack_results,
    judas_15m_series,
    to_series,
    uptrend_series,
    v_reversal_series,
    zigzag_series,
)
from tests.fvg_fixtures import inversion_series, nested_fvg_records
from tests.ob_fixtures import mb_sweep_records, rbd_records

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


class TestOrderBlockGoldens:
    def test_v_reversal_orderblocks(self) -> None:
        # continuation OBs + a reversal OB + a breaker at the CHoCH
        result = analyze_orderblocks(v_reversal_series(), engine_config())
        _assert_golden("orderblocks_trending.json", result.model_dump_json())

    def test_sweep_mitigation_blocks(self) -> None:
        result = analyze_orderblocks(to_series(mb_sweep_records(), symbol="MB"), engine_config())
        _assert_golden("orderblocks_sweep.json", result.model_dump_json())


class TestSupplyDemandGoldens:
    def test_rbd_supply_zone(self) -> None:
        result = analyze_supplydemand(to_series(rbd_records(), symbol="RBD"), engine_config())
        _assert_golden("supplydemand_rbd.json", result.model_dump_json())


class TestSessionGoldens:
    def test_five_day_sessions(self) -> None:
        result = analyze_sessions(five_day_15m_series(), engine_config(), SessionConfig())
        _assert_golden("sessions_five_day.json", result.model_dump_json())

    def test_judas_sessions(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        _assert_golden("sessions_judas.json", result.model_dump_json())


class TestMtfGoldens:
    def test_aligned_uptrend_mtf(self) -> None:
        config = engine_config(internal_swing_lookback=1, external_swing_lookback=2)
        series = zigzag_series(MTF_UPTREND_PIVOTS, leg_bars=16, symbol="UP", bar_minutes=15)
        result = analyze_mtf(series, ["1h", "4h"], config)
        _assert_golden("mtf_uptrend.json", result.model_dump_json())

    def test_five_day_mtf(self) -> None:
        result = analyze_mtf(five_day_15m_series(), ["1h", "4h", "1d"], engine_config())
        _assert_golden("mtf_five_day.json", result.model_dump_json())


class TestConfluenceGoldens:
    def test_five_day_confluence(self) -> None:
        result = analyze_confluence(five_day_15m_series(), engine_config())
        _assert_golden("confluence_five_day.json", result.model_dump_json())

    def test_judas_confluence(self) -> None:
        result = analyze_confluence(judas_15m_series(), engine_config())
        _assert_golden("confluence_judas.json", result.model_dump_json())

    def test_uptrend_confluence(self) -> None:
        result = analyze_confluence(uptrend_series(), engine_config())
        _assert_golden("confluence_uptrend.json", result.model_dump_json())


class TestChartGoldens:
    def test_five_day_chart_full_stack(self) -> None:
        series = five_day_15m_series()
        results = full_stack_results(series, engine_config())
        chart = build_chart_payload(series, results)
        _assert_golden("chart_five_day.json", chart.model_dump_json())

    def test_uptrend_chart_subset(self) -> None:
        series = uptrend_series()
        config = engine_config()
        results = {
            "structure": analyze_structure(series, config),
            "liquidity": analyze_liquidity(series, config),
            "fvg": analyze_fvg(series, config),
            "premium_discount": analyze_dealing_range(series, config),
        }
        chart = build_chart_payload(series, results)
        _assert_golden("chart_uptrend.json", chart.model_dump_json())


class TestAiGoldens:
    def test_five_day_analysis_context(self) -> None:
        from contexttrading.ai import build_analysis_context

        series = five_day_15m_series()
        context = build_analysis_context(series, full_stack_results(series, engine_config()))
        _assert_golden("ai_context_five_day.json", context.model_dump_json())

    def test_five_day_mock_market_report(self) -> None:
        from contexttrading.ai import InstitutionalAnalyst, MockProvider

        series = five_day_15m_series()
        results = full_stack_results(series, engine_config())
        report = InstitutionalAnalyst(MockProvider()).analyze_market(series, results)
        _assert_golden("ai_report_five_day.json", report.model_dump_json())
