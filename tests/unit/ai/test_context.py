"""Unit tests for the deterministic context builders."""

from __future__ import annotations

from contexttrading.ai.context import (
    build_analysis_context,
    build_journal_context,
    build_performance_context,
)
from contexttrading.core.config import AIConfig
from tests.fixtures import (
    engine_config,
    five_day_15m_series,
    full_stack_results,
    uptrend_series,
)


def _five_day():
    series = five_day_15m_series()
    return series, full_stack_results(series, engine_config())


class TestEvidenceIndex:
    def test_covers_every_detected_object(self) -> None:
        series, results = _five_day()
        ctx = build_analysis_context(series, results)
        expected: set[str] = set()
        structure = results["structure"].payload
        expected |= {s.id for s in structure.swings}
        expected |= {b.id for b in structure.breaks}
        expected |= {lg.id for lg in structure.legs}
        liquidity = results["liquidity"].payload
        expected |= {p.id for p in liquidity.pools}
        expected |= {s.id for s in liquidity.sweeps}
        expected |= {lv.id for lv in liquidity.equal_levels}
        expected |= {f.id for f in results["fvg"].payload.fvgs}
        ob = results["orderblocks"].payload
        expected |= {b.id for b in ob.order_blocks + ob.breaker_blocks + ob.mitigation_blocks}
        expected |= {z.id for z in results["supplydemand"].payload.zones}
        sessions = results["sessions"].payload
        expected |= {s.id for s in sessions.sessions}
        expected |= {p.id for p in sessions.pools}
        expected |= {e.id for e in sessions.session_sweeps}
        expected |= {z.id for z in results["confluence"].payload.zones}
        missing = expected - set(ctx.evidence_index)
        assert not missing, f"evidence index missing {len(missing)} object ids"

    def test_synthetic_keys_present(self) -> None:
        series, results = _five_day()
        ctx = build_analysis_context(series, results)
        for key in ("trend:state", "mtf:bias", "range:dealing"):
            assert key in ctx.evidence_index
        factor_keys = [k for k in ctx.evidence_index if k.startswith("factor:")]
        assert len(factor_keys) == len(results["confluence"].payload.factors)

    def test_index_never_truncated(self) -> None:
        series, results = _five_day()
        config = AIConfig(max_objects_per_category=2)
        ctx = build_analysis_context(series, results, ai_config=config)
        total_objects = len(results["structure"].payload.swings)
        assert total_objects > 2
        swing_entries = [k for k, e in ctx.evidence_index.items() if e.kind == "swing"]
        assert len(swing_entries) >= total_objects


class TestTruncation:
    def test_caps_respected_and_recorded(self) -> None:
        series, results = _five_day()
        config = AIConfig(max_objects_per_category=3)
        ctx = build_analysis_context(series, results, ai_config=config)
        assert len(ctx.structure["recent_swings"]) <= 3
        assert len(ctx.structure["recent_breaks"]) <= 3
        assert len(ctx.liquidity["pools"]) <= 3
        categories = {t.category for t in ctx.truncation}
        assert "structure.swings" in categories
        for entry in ctx.truncation:
            assert entry.shown < entry.total
            assert entry.keep_rule

    def test_factors_never_truncated(self) -> None:
        series, results = _five_day()
        config = AIConfig(max_objects_per_category=1)
        ctx = build_analysis_context(series, results, ai_config=config)
        assert len(ctx.confluence["factors"]) == len(results["confluence"].payload.factors)

    def test_deterministic(self) -> None:
        series, results = _five_day()
        first = build_analysis_context(series, results).model_dump_json()
        second = build_analysis_context(series, results).model_dump_json()
        assert first == second


class TestProximity:
    def test_tight_proximity_excludes_far_zones(self) -> None:
        series, results = _five_day()
        wide = build_analysis_context(series, results, ai_config=AIConfig(proximity_atr=100.0))
        tight = build_analysis_context(series, results, ai_config=AIConfig(proximity_atr=0.5))
        assert len(tight.zones_nearby) <= len(wide.zones_nearby)
        for zone in tight.zones_nearby:
            assert zone["distance_atr"] is None or zone["distance_atr"] <= 0.5

    def test_zones_sorted_by_distance(self) -> None:
        series, results = _five_day()
        ctx = build_analysis_context(series, results)
        distances = [z["distance_atr"] for z in ctx.zones_nearby if z["distance_atr"] is not None]
        assert distances == sorted(distances)


class TestDataQuality:
    def test_missing_modules_flagged(self) -> None:
        series = uptrend_series()
        results = full_stack_results(series, engine_config())
        del results["fvg"]
        del results["mtf"]
        ctx = build_analysis_context(series, results)
        assert "module_not_provided:fvg" in ctx.data_quality.flags
        assert "module_not_provided:mtf" in ctx.data_quality.flags

    def test_level_rules(self) -> None:
        series = uptrend_series()
        full = full_stack_results(series, engine_config())
        ctx_full = build_analysis_context(series, full)
        assert ctx_full.data_quality.level in ("good", "fair")
        # Three or more flags -> poor.
        subset = {k: v for k, v in full.items() if k in ("structure", "trend")}
        ctx_poor = build_analysis_context(series, subset)
        assert ctx_poor.data_quality.level == "poor"

    def test_stale_pools_flag_on_five_day(self) -> None:
        series, results = _five_day()
        ctx = build_analysis_context(series, results)
        # Deterministic rule: untapped pools formed in the first half of the series.
        assert "stale_untapped_pools:2" in ctx.data_quality.flags
        assert ctx.data_quality.level == "fair"


class TestJournalContext:
    def test_statistics_computed_in_python(self) -> None:
        trades = [
            {"id": "t1", "pnl": 10.0},
            {"id": "t2", "pnl": -5.0},
            {"id": "t3", "pnl": 20.0},
            {"id": "t4", "pnl": -10.0},
        ]
        ctx = build_journal_context(trades, period="2024-W01")
        stats = ctx.statistics
        assert stats["trade_count"] == 4
        assert stats["win_rate"] == 0.5
        assert stats["avg_win"] == 15.0
        assert stats["avg_loss"] == -7.5
        assert stats["profit_factor"] == 2.0
        assert stats["total_pnl"] == 15.0
        for key in stats:
            assert f"stat:{key}" in ctx.evidence_index
        for trade in trades:
            assert trade["id"] in ctx.evidence_index

    def test_small_sample_flagged(self) -> None:
        ctx = build_journal_context([{"id": "t1", "pnl": 1.0}])
        assert "small_sample:1" in ctx.data_quality.flags
        assert ctx.data_quality.level == "fair"

    def test_missing_ids_get_deterministic_ones(self) -> None:
        ctx = build_journal_context([{"pnl": 1.0}, {"pnl": -1.0}])
        assert "trade:000" in ctx.evidence_index
        assert "trade:001" in ctx.evidence_index

    def test_deterministic(self) -> None:
        trades = [{"id": "t1", "pnl": 1.0}, {"id": "t2", "pnl": -2.0}]
        assert (
            build_journal_context(trades).model_dump_json()
            == build_journal_context(trades).model_dump_json()
        )


class TestPerformanceContext:
    def test_stats_wrapped_as_is(self) -> None:
        stats = {"trade_count": 25, "win_rate": 0.52, "profit_factor": 1.4}
        ctx = build_performance_context(stats, period="2024-W01")
        assert ctx.kind == "performance"
        assert ctx.statistics == stats
        assert set(ctx.evidence_index) == {f"stat:{k}" for k in stats}
        assert ctx.data_quality.level == "good"

    def test_small_sample_flag(self) -> None:
        ctx = build_performance_context({"trade_count": 3}, period="2024-01")
        assert "small_sample:3" in ctx.data_quality.flags
