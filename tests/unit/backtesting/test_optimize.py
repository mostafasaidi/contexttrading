"""Optimization unit tests: grid order, leaderboard, walk-forward, errors."""

from __future__ import annotations

from typing import ClassVar

import pytest

from contexttrading.backtesting.optimize import _combos, grid_search, walk_forward
from contexttrading.core.config import BacktestConfig
from contexttrading.core.errors import BacktestError, ValidationError
from tests.unit.backtesting.conftest import ParamToyStrategy

FREE = BacktestConfig(warmup_bars=2, min_trades=1, spread_bps=0, slippage_bps=0, commission_bps=0)


def factory(params: dict) -> ParamToyStrategy:
    return ParamToyStrategy(**params)


class TestCombos:
    def test_cartesian_order_last_key_varies_fastest(self) -> None:
        space = {"strategy.a": [1, 2], "strategy.b": ["x", "y", "z"]}
        combos = _combos(space)
        assert combos == [
            {"strategy.a": 1, "strategy.b": "x"},
            {"strategy.a": 1, "strategy.b": "y"},
            {"strategy.a": 1, "strategy.b": "z"},
            {"strategy.a": 2, "strategy.b": "x"},
            {"strategy.a": 2, "strategy.b": "y"},
            {"strategy.a": 2, "strategy.b": "z"},
        ]

    def test_empty_space_single_default_combo(self) -> None:
        assert _combos({}) == [{}]

    def test_empty_values_rejected(self) -> None:
        with pytest.raises(BacktestError):
            _combos({"strategy.a": []})

    def test_bad_prefix_rejected(self) -> None:
        with pytest.raises(BacktestError, match=r"engine\./backtest\./strategy"):
            _combos({"nope.a": [1]})


class TestGridSearch:
    SPACE: ClassVar = {"strategy.enter_bar": [5, 10], "strategy.tp_r": [1.0, 2.0]}

    def test_leaderboard_ranked_by_objective(self, ramp_series) -> None:
        result = grid_search(ramp_series, factory, self.SPACE, backtest_config=FREE)
        assert result.combos_evaluated == 4
        values = [e.objective_value for e in result.leaderboard]
        assert values == sorted(values, reverse=True)
        assert [e.rank for e in result.leaderboard] == [1, 2, 3, 4]
        # tp_r=2.0 combos win on a rising ramp; ties keep declaration order
        assert result.leaderboard[0].params["strategy.tp_r"] == 2.0
        assert result.leaderboard[0].params["strategy.enter_bar"] == 5
        assert result.leaderboard[1].params["strategy.enter_bar"] == 10

    def test_deterministic_rerun(self, ramp_series) -> None:
        first = grid_search(ramp_series, factory, self.SPACE, backtest_config=FREE)
        second = grid_search(ramp_series, factory, self.SPACE, backtest_config=FREE)
        assert first.model_dump_json() == second.model_dump_json()

    def test_none_objective_ranks_last(self, ramp_series) -> None:
        # sharpe needs >= 2 non-flat returns; a single EOD-closed trade keeps
        # equity flat until the last bar -> zero-variance returns -> None
        space = {"strategy.enter_bar": [5, 30]}
        result = grid_search(ramp_series, factory, space, objective="sharpe", backtest_config=FREE)
        assert result.leaderboard[-1].objective_value is None or all(
            e.objective_value is not None for e in result.leaderboard
        )
        # ranks remain a clean 1..N permutation regardless
        assert [e.rank for e in result.leaderboard] == [1, 2]

    def test_unknown_objective_rejected(self, ramp_series) -> None:
        with pytest.raises(BacktestError, match="Unknown objective"):
            grid_search(ramp_series, factory, self.SPACE, objective="magic")

    def test_engine_param_path_applies(self, ramp_series) -> None:
        # engine.min_candles is a real EngineConfig field; the combo must apply
        result = grid_search(
            ramp_series,
            factory,
            {"engine.min_candles": [5], "strategy.enter_bar": [5]},
            backtest_config=FREE,
        )
        assert result.combos_evaluated == 1
        assert result.leaderboard[0].params["engine.min_candles"] == 5

    def test_unknown_engine_field_rejected(self, ramp_series) -> None:
        with pytest.raises(ValidationError):
            grid_search(ramp_series, factory, {"engine.not_a_field": [1]}, backtest_config=FREE)


class TestWalkForward:
    def test_contiguous_expanding_folds(self, ramp_series) -> None:
        result = walk_forward(
            ramp_series, 4, factory, {"strategy.enter_bar": [3, 6]}, backtest_config=FREE
        )
        assert len(result.folds) == 3
        total = len(ramp_series.candles)
        assert result.folds[0].train_bars + result.folds[0].test_bars <= total
        # anchored expansion: train windows grow
        trains = [f.train_bars for f in result.folds]
        assert trains == sorted(trains)
        assert result.folds[-1].train_bars + result.folds[-1].test_bars == total

    def test_deterministic_rerun(self, ramp_series) -> None:
        first = walk_forward(
            ramp_series, 4, factory, {"strategy.enter_bar": [3, 6]}, backtest_config=FREE
        )
        second = walk_forward(
            ramp_series, 4, factory, {"strategy.enter_bar": [3, 6]}, backtest_config=FREE
        )
        assert first.model_dump_json() == second.model_dump_json()

    def test_overfit_flag_counts(self, ramp_series) -> None:
        result = walk_forward(
            ramp_series, 4, factory, {"strategy.enter_bar": [3, 6]}, backtest_config=FREE
        )
        assert result.overfit_folds == sum(1 for f in result.folds if f.overfit)
        for fold in result.folds:
            assert isinstance(fold.overfit, bool)

    def test_requires_two_folds(self, ramp_series) -> None:
        with pytest.raises(BacktestError):
            walk_forward(ramp_series, 1, factory, {}, backtest_config=FREE)
