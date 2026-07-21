"""Unit tests for the session engine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contexttrading.analysis.sessions import analyze_sessions, resolve_windows
from contexttrading.analysis.sessions.definitions import SessionWindow, window_instances
from contexttrading.analysis.sessions.tracker import (
    NEW_YORK_KILLZONE_NAMES,
    detect_judas_swings,
)
from contexttrading.core.config import SessionConfig
from contexttrading.core.constants import (
    LiquidityPoolKind,
    LiquiditySide,
    PoolStatus,
    SweepClassification,
    TrendDirection,
)
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.liquidity import LiquiditySweep
from tests.fixtures import (
    engine_config,
    five_day_15m_series,
    judas_15m_series,
    to_series,
    zigzag_records,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)


class TestWindowDefinitions:
    def test_midnight_wrap_membership(self) -> None:
        sydney = SessionWindow("sydney", 21 * 60, 6 * 60, is_killzone=False)
        assert sydney.wraps_midnight
        assert sydney.contains(23 * 60)
        assert sydney.contains(5 * 60 + 59)
        assert not sydney.contains(6 * 60)
        assert not sydney.contains(12 * 60)

    def test_non_wrap_membership_is_half_open(self) -> None:
        london = SessionWindow("london", 7 * 60, 16 * 60, is_killzone=False)
        assert not london.wraps_midnight
        assert london.contains(7 * 60)
        assert london.contains(15 * 60 + 59)
        assert not london.contains(16 * 60)

    def test_resolve_windows_sessions_then_killzones(self) -> None:
        windows = resolve_windows(SessionConfig())
        names = [w.name for w in windows]
        assert names[:4] == ["sydney", "tokyo", "london", "new_york"]
        assert all(not w.is_killzone for w in windows[:4])
        assert all(w.is_killzone for w in windows[4:])

    def test_wrapped_instance_belongs_to_start_date(self) -> None:
        # Candles at 23:00 Jan 1 and 01:00 Jan 2: one Sydney instance dated Jan 1.
        sydney = SessionWindow("sydney", 21 * 60, 6 * 60, is_killzone=False)
        ts = [datetime(2024, 1, 1, 23, tzinfo=UTC), datetime(2024, 1, 2, 1, tzinfo=UTC)]
        instances = window_instances(ts, sydney, UTC)  # type: ignore[arg-type]
        assert len(instances) == 1
        trading_date, first, last = instances[0]
        assert trading_date.isoformat() == "2024-01-01"
        assert (first, last) == (0, 1)


class TestSessionStats:
    def test_instance_counts_on_five_day_series(self) -> None:
        result = analyze_sessions(five_day_15m_series(), engine_config(), SessionConfig())
        stats = result.payload.sessions
        sessions = [s for s in stats if not s.is_killzone]
        tokyo = [s for s in sessions if s.session == "tokyo"]
        london = [s for s in sessions if s.session == "london"]
        # Sydney wraps midnight: partial first instance + 4 full + 1 trailing.
        sydney = [s for s in sessions if s.session == "sydney"]
        assert len(tokyo) == 5
        assert len(london) == 5
        assert len(sydney) == 6
        # Every session also yields killzone instances and Asian ranges.
        assert any(s.is_killzone for s in stats)
        assert any(s.session == "asia" for s in stats)

    def test_stats_ohlc_and_geometry(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        stats = result.payload.sessions
        asia = next(
            s for s in stats if s.session == "asia" and s.trading_date.isoformat() == "2024-01-02"
        )
        assert asia.high == pytest.approx(104.6)
        assert asia.low == pytest.approx(100.85, abs=0.05)
        assert asia.high_index == 104
        # 12 candles from day-1 21:00-23:45 (Sydney) + 28 from day-2 00:00-06:45.
        assert asia.candle_count == 40
        london = next(
            s for s in stats if s.session == "london" and s.trading_date.isoformat() == "2024-01-02"
        )
        assert london.high == pytest.approx(105.2)
        assert london.direction is TrendDirection.BEARISH
        assert london.forms_day_high
        assert not london.forms_day_low

    def test_doji_session_is_ranging(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        tokyo_day2 = next(
            s
            for s in result.payload.sessions
            if s.session == "tokyo" and s.trading_date.isoformat() == "2024-01-02"
        )
        # Open 103.8, close ~103.9 over a 1.7 range: body fraction < 0.2.
        assert tokyo_day2.direction is TrendDirection.RANGING

    def test_day_extreme_counts_and_dominant(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        payload = result.payload
        assert payload.day_high_counts.get("london") == 1  # 105.2 on day 2
        assert payload.dominant_high_session in payload.day_high_counts
        assert payload.dominant_low_session in payload.day_low_counts

    def test_deterministic_repeat_runs(self) -> None:
        series = five_day_15m_series()
        a = analyze_sessions(series, engine_config(), SessionConfig())
        b = analyze_sessions(five_day_15m_series(), engine_config(), SessionConfig())
        assert a.model_dump_json() == b.model_dump_json()


class TestSessionPools:
    def test_pool_kinds_present(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        kinds = {p.kind for p in result.payload.pools}
        assert LiquidityPoolKind.SESSION_HIGH in kinds
        assert LiquidityPoolKind.SESSION_LOW in kinds
        assert LiquidityPoolKind.PREVIOUS_DAY_HIGH in kinds
        assert LiquidityPoolKind.PREVIOUS_DAY_LOW in kinds

    def test_session_pool_levels_match_stats(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        payload = result.payload
        session_highs = {p.price for p in payload.pools if p.kind is LiquidityPoolKind.SESSION_HIGH}
        stats_highs = {s.high for s in payload.sessions if not s.is_killzone}
        assert session_highs <= stats_highs

    def test_previous_day_pools_use_prior_day_levels(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        pdh = [p for p in result.payload.pools if p.kind is LiquidityPoolKind.PREVIOUS_DAY_HIGH]
        assert len(pdh) == 1  # two days -> one previous-day pair
        # Day-1 high (~101.5) is broken early on day 2 (close-through).
        assert pdh[0].status is PoolStatus.BROKEN


class TestJudasClassifier:
    def _sweep(self, pool_id: str, ts: datetime, side: LiquiditySide) -> LiquiditySweep:
        return LiquiditySweep(
            pool_id=pool_id,
            pool_price=100.0,
            side=side,
            candle_index=0,
            timestamp=ts,
            wick_extreme=100.5,
            penetration_atr=None,
            close_back_inside=True,
            classification=SweepClassification.SWEEP,
        )

    def test_asia_swept_in_london_killzone_is_judas(self) -> None:
        kz = [SessionWindow("london", 7 * 60, 10 * 60, is_killzone=True)]
        sweep = self._sweep("pool-a", datetime(2024, 1, 2, 8, tzinfo=UTC), LiquiditySide.BUYSIDE)
        found = detect_judas_swings([sweep], {"pool-a": "asia"}, kz, UTC)  # type: ignore[arg-type]
        assert len(found) == 1
        assert found[0].swept_group == "asia"
        assert found[0].sweeping_window == "london"
        assert found[0].swept_level_kind is LiquidityPoolKind.SESSION_HIGH
        assert found[0].linked_sweep_id == sweep.id

    def test_london_swept_in_new_york_killzone_is_judas(self) -> None:
        kz = [
            SessionWindow(name, 12 * 60, 15 * 60, is_killzone=True)
            for name in NEW_YORK_KILLZONE_NAMES
        ]
        sweep = self._sweep("pool-l", datetime(2024, 1, 2, 13, tzinfo=UTC), LiquiditySide.SELLSIDE)
        found = detect_judas_swings([sweep], {"pool-l": "london"}, kz, UTC)  # type: ignore[arg-type]
        assert len(found) == 1
        assert found[0].swept_level_kind is LiquidityPoolKind.SESSION_LOW

    def test_non_pattern_sweeps_ignored(self) -> None:
        kz = [SessionWindow("london", 7 * 60, 10 * 60, is_killzone=True)]
        # London level during the London killzone: not a Judas pattern.
        sweep = self._sweep("pool-l", datetime(2024, 1, 2, 8, tzinfo=UTC), LiquiditySide.BUYSIDE)
        assert detect_judas_swings([sweep], {"pool-l": "london"}, kz, UTC) == []  # type: ignore[arg-type]
        # Asia level outside every killzone.
        late = self._sweep("pool-a", datetime(2024, 1, 2, 11, tzinfo=UTC), LiquiditySide.BUYSIDE)
        assert detect_judas_swings([late], {"pool-a": "asia"}, kz, UTC) == []  # type: ignore[arg-type]


class TestJudasEndToEnd:
    def test_asian_high_swept_during_london_killzone(self) -> None:
        result = analyze_sessions(judas_15m_series(), engine_config(), SessionConfig())
        judas = [
            s for s in result.payload.session_sweeps if s.candle_index == 125  # 07:15 on day 2
        ]
        assert len(judas) == 1
        event = judas[0]
        assert event.swept_group == "asia"
        assert event.sweeping_window == "london"
        assert event.side is LiquiditySide.BUYSIDE
        assert event.swept_price == pytest.approx(104.6)
        sweep_ids = {s.id for s in result.payload.sweeps}
        assert event.linked_sweep_id in sweep_ids


class TestSessionEdgeCases:
    def test_insufficient_data_raises(self) -> None:
        series = to_series(zigzag_records([10, 11, 10.5], leg_bars=2))
        with pytest.raises(InsufficientDataError):
            analyze_sessions(series, engine_config(), SessionConfig())

    def test_custom_windows_without_asia_sessions(self) -> None:
        config = SessionConfig(
            sessions={"london": {"start": "08:00", "end": "12:00"}},
            killzones={},
        )
        result = analyze_sessions(five_day_15m_series(), engine_config(), config)
        payload = result.payload
        assert {s.session for s in payload.sessions} == {"london"}
        assert not any(s.session == "asia" for s in payload.sessions)
        # Previous-day pools are still synthesized.
        assert any(p.kind is LiquidityPoolKind.PREVIOUS_DAY_LOW for p in payload.pools)

    def test_envelope_metadata(self) -> None:
        series = judas_15m_series()
        result = analyze_sessions(series, engine_config(), SessionConfig())
        assert result.module == "sessions"
        assert result.symbol == series.symbol
        assert result.generated_from.candle_count == len(series)
