"""Replay-loop unit tests: ordering, warmup, staleness, expiry, validation."""

from __future__ import annotations

import pytest

from contexttrading.backtesting.replay import run_backtest
from contexttrading.core.config import BacktestConfig
from contexttrading.core.errors import BacktestError
from contexttrading.models.backtest import OrderIntent
from contexttrading.models.candle import CandleSeries
from tests.fixtures import engine_config
from tests.unit.backtesting.conftest import ScriptStrategy, ramp_records


def buy(sl: float, tp: float | None = None, **kw) -> OrderIntent:
    return OrderIntent(
        kind=kw.pop("kind", "market"),
        direction="bullish",
        stop_loss=sl,
        take_profit=tp,
        created_index=0,  # ScriptStrategy re-stamps with the decision bar
        **kw,
    )


class TestFillTiming:
    def test_decision_at_close_fills_next_bar_open(self, ramp_series, free_config) -> None:
        # decide at bar 3 close; bar 4 opens at 103.0 (ramp: open_i = 100 + i)
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=120.0)]})
        result = run_backtest(ramp_series, strategy, backtest_config=free_config)
        assert len(result.trades) == 1
        trade = result.trades[0]
        assert trade.entry_index == 4
        assert trade.entry_price == 104.0  # zero-cost config: fill == open (100 + bar index)

    def test_no_fill_on_decision_bar(self, ramp_series, free_config) -> None:
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=120.0)]})
        result = run_backtest(ramp_series, strategy, backtest_config=free_config)
        assert result.trades[0].entry_index > 3

    def test_signal_close_fills_next_open(self, ramp_series, free_config) -> None:
        close_intent = OrderIntent(kind="close", direction="ranging", created_index=0)
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=200.0)], 10: [close_intent]})
        result = run_backtest(ramp_series, strategy, backtest_config=free_config)
        trade = result.trades[0]
        assert trade.exit_reason == "signal"
        assert trade.exit_index == 11
        assert trade.exit_price == 111.0

    def test_limit_expires_after_one_bar(self, ramp_series, free_config) -> None:
        # limit far below any later bar low: never fills, expires silently
        strategy = ScriptStrategy({3: [buy(sl=95.0, kind="limit", price=50.0)]})
        result = run_backtest(ramp_series, strategy, backtest_config=free_config)
        assert result.trades == []

    def test_one_position_at_a_time(self, ramp_series, free_config) -> None:
        # second entry intent while the first position is open is ignored
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=200.0)], 6: [buy(sl=95.0, tp=300.0)]})
        result = run_backtest(ramp_series, strategy, backtest_config=free_config)
        assert len(result.trades) == 1
        assert result.trades[0].entry_index == 4


class TestEndOfData:
    def test_open_position_closed_at_final_close(self, ramp_series, free_config) -> None:
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=10_000.0)]})
        result = run_backtest(ramp_series, strategy, backtest_config=free_config)
        trade = result.trades[0]
        assert trade.exit_reason == "end_of_data"
        assert trade.exit_index == len(ramp_series.candles) - 1
        assert trade.exit_price == ramp_series.candles[-1].close
        assert result.equity_curve[-1].in_position is False

    def test_eod_close_disabled_leaves_trade_unrecorded(self, ramp_series) -> None:
        cfg = BacktestConfig(
            warmup_bars=2, min_trades=1, spread_bps=0, slippage_bps=0, commission_bps=0,
            eod_close=False,
        )
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=10_000.0)]})
        result = run_backtest(ramp_series, strategy, backtest_config=cfg)
        assert result.trades == []
        assert result.equity_curve[-1].in_position is True


class TestWarmupAndRecompute:
    def test_no_decisions_before_warmup(self, ramp_series) -> None:
        cfg = BacktestConfig(warmup_bars=10, min_trades=1)
        strategy = ScriptStrategy()
        run_backtest(ramp_series, strategy, backtest_config=cfg)
        assert strategy.calls[0] == 10
        assert strategy.calls == list(range(10, len(ramp_series.candles)))

    def test_recompute_interval_staleness(self, ramp_series) -> None:
        class Probe(ScriptStrategy):
            modules = ("trend",)

        cfg = BacktestConfig(warmup_bars=10, recompute_interval=5, min_trades=1)
        strategy = Probe()
        run_backtest(ramp_series, strategy, engine_config(), backtest_config=cfg)
        seen = strategy.results_seen
        # recompute at bars 10, 15, 20, ... : results object changes only there;
        # the first call already sees recompute #1, so transitions = recomputes - 1
        changes = sum(1 for prev, curr in zip(seen, seen[1:]) if prev is not curr)
        expected = len(range(10, len(ramp_series.candles), 5)) - 1
        assert changes == expected
        # the recompute at bar 10 covers exactly bars 0..10
        first = seen[0]
        assert first["trend"].generated_from.candle_count == 11

    def test_window_bars_caps_engine_input(self, ramp_series) -> None:
        class Probe(ScriptStrategy):
            modules = ("trend",)

        cfg = BacktestConfig(warmup_bars=10, window_bars=20, min_trades=1)
        strategy = Probe()
        run_backtest(ramp_series, strategy, engine_config(), backtest_config=cfg)
        assert max(strategy.window_sizes) == 20
        # at bar 10 the window has only 11 candles (cap not yet reached)
        assert strategy.results_seen[0]["trend"].generated_from.candle_count == 11


class TestValidation:
    def test_entry_without_stop_rejected(self, ramp_series, free_config) -> None:
        class Bad(ScriptStrategy):
            def on_bar(self, bar_index, series, results, position, equity):
                if bar_index == 3:
                    return [OrderIntent(kind="market", direction="bullish", created_index=3)]
                return []

        with pytest.raises(BacktestError, match="stop_loss"):
            run_backtest(ramp_series, Bad(), backtest_config=free_config)

    def test_stale_created_index_rejected(self, ramp_series, free_config) -> None:
        class Bad(ScriptStrategy):
            def on_bar(self, bar_index, series, results, position, equity):
                if bar_index == 3:
                    return [OrderIntent(kind="market", direction="bullish",
                                        stop_loss=90.0, created_index=1)]
                return []

        with pytest.raises(BacktestError, match="decision bar"):
            run_backtest(ramp_series, Bad(), backtest_config=free_config)

    def test_unknown_module_rejected(self, ramp_series, free_config) -> None:
        class Bad(ScriptStrategy):
            modules = ("astrology",)

        with pytest.raises(BacktestError, match="unknown modules"):
            run_backtest(ramp_series, Bad(), backtest_config=free_config)


class TestDeterminism:
    def test_byte_identical_rerun(self, ramp_series, free_config) -> None:
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=108.0)], 20: [buy(sl=100.0, tp=140.0)]})
        first = run_backtest(ramp_series, strategy, backtest_config=free_config)
        second = run_backtest(ramp_series, strategy, backtest_config=free_config)
        assert first.model_dump_json() == second.model_dump_json()


class TestAccounting:
    def test_equity_identity(self, ramp_series, free_config) -> None:
        strategy = ScriptStrategy({3: [buy(sl=95.0, tp=108.0)], 20: [buy(sl=100.0, tp=140.0)]})
        result = run_backtest(ramp_series, strategy, backtest_config=free_config)
        total_pnl = sum(t.net_pnl for t in result.trades)
        assert result.equity_curve[-1].closed_equity == pytest.approx(
            free_config.initial_equity + total_pnl
        )
