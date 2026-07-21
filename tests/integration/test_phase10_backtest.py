"""Phase 10 integration: SMC pullback backtest over 2,000 seeded candles.

Verifies the phase-level contracts:

- byte-identical reruns (determinism),
- zero lookahead BY CONSTRUCTION: a backtest truncated at bar T produces
  identical decisions and equity for every shared bar (engines only ever
  see prefixes; decisions fill on the next bar),
- every trade carries >= 1 evidence id that resolves to an engine object
  in the decision-bar window results.

Performance levers (documented in replay.py): recompute_interval + bounded
window keep the O(n^2) replay tractable for CI.
"""

from __future__ import annotations

import pytest

from contexttrading.analysis.pipeline import run_module
from contexttrading.backtesting import SMCPullbackStrategy, run_backtest
from contexttrading.core.config import BacktestConfig
from tests.fixtures import engine_config
from tests.integration.test_pipeline import _dataset

CONFIG = BacktestConfig(
    warmup_bars=100,
    min_trades=1,
    recompute_interval=20,
    window_bars=400,
)
TRUNCATE_AT = 1300


@pytest.fixture(scope="module")
def dataset():
    return _dataset()


@pytest.fixture(scope="module")
def result(dataset):
    return run_backtest(dataset, SMCPullbackStrategy(), engine_config(), CONFIG)


class TestDeterminism:
    def test_byte_identical_rerun(self, dataset, result) -> None:
        rerun = run_backtest(dataset, SMCPullbackStrategy(), engine_config(), CONFIG)
        assert result.model_dump_json() == rerun.model_dump_json()


class TestNoLookaheadByConstruction:
    """Truncated-at-T run == full run on every shared bar.

    Method: replay the series prefix [0, T). Because engines only see
    prefixes and fills happen on the bar after the decision, the truncated
    run must reproduce the full run's per-bar equity and trade entries for
    all bars < T. The only sanctioned differences are AT the truncation
    point itself (end-of-data close of a still-open position).
    """

    def test_truncated_decisions_match(self, dataset, result) -> None:
        truncated = run_backtest(
            dataset[:TRUNCATE_AT], SMCPullbackStrategy(), engine_config(), CONFIG
        )
        shared_curve = result.equity_curve[: TRUNCATE_AT - 1]
        truncated_curve = truncated.equity_curve[: TRUNCATE_AT - 1]
        assert [p.model_dump(mode="json") for p in shared_curve] == [
            p.model_dump(mode="json") for p in truncated_curve
        ]

        full_trades = {t.entry_index: t.model_dump(mode="json") for t in result.trades}
        for trade in truncated.trades:
            if trade.exit_reason == "end_of_data" and trade.exit_index == TRUNCATE_AT - 1:
                continue  # sanctioned: the full run had not exited yet at T
            match = full_trades.get(trade.entry_index)
            assert match is not None, f"phantom trade at {trade.entry_index}"
            assert match == trade.model_dump(mode="json")


class TestEvidence:
    def test_every_trade_has_evidence(self, result) -> None:
        for trade in result.trades:
            assert len(trade.evidence_ids) >= 1

    def test_evidence_ids_resolve_in_decision_window(self, dataset, result) -> None:
        strategy = SMCPullbackStrategy()
        for trade in result.trades:
            decision_bar = trade.entry_index - 1
            # The strategy saw the results of the latest RECOMPUTE point at
            # or before the decision bar (recompute_interval staleness is a
            # documented replay feature), so evidence must resolve there.
            recompute_bar = (
                CONFIG.warmup_bars
                + ((decision_bar - CONFIG.warmup_bars) // CONFIG.recompute_interval)
                * CONFIG.recompute_interval
            )
            start = max(0, recompute_bar + 1 - CONFIG.window_bars)
            window = dataset[start : recompute_bar + 1]
            blob = ""
            for module in strategy.modules:
                blob += run_module(module, window, engine_config()).model_dump_json()
            for evidence_id in trade.evidence_ids:
                assert f'"{evidence_id}"' in blob, (
                    f"trade {trade.sequence}: {evidence_id} not found "
                    f"in results window ending at bar {recompute_bar}"
                )


class TestSanity:
    def test_trades_and_accounting(self, result) -> None:
        stats = result.statistics
        assert stats.total_trades == len(result.trades)
        assert stats.total_trades >= 1
        final = result.equity_curve[-1]
        assert final.closed_equity == pytest.approx(CONFIG.initial_equity + stats.net_pnl, rel=1e-9)
        for trade in result.trades:
            # a position can be stopped on its own fill bar (holding_bars == 0)
            assert trade.exit_index >= trade.entry_index
