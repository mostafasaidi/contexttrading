"""Statistics unit tests: hand-computed metrics, edge cases, formulas."""

from __future__ import annotations

import math
import statistics as stats

import pytest

from contexttrading.backtesting.statistics import (
    annualization_factor,
    bar_returns,
    compute_statistics,
    max_drawdown,
)
from contexttrading.core.config import BacktestConfig
from contexttrading.core.constants import Timeframe
from contexttrading.models.backtest import EquityPoint, TradeRecord
from tests.unit.backtesting.conftest import make_candle


def trade(net: float, r: float, seq: int) -> TradeRecord:
    candle = make_candle(seq, 100, 100, 100, 100)
    return TradeRecord(
        sequence=seq,
        direction="bullish",
        entry_index=seq,
        entry_timestamp=candle.timestamp,
        entry_price=100.0,
        exit_index=seq + 1,
        exit_timestamp=candle.timestamp,
        exit_price=100.0 + net / 10.0,
        size_units=10.0,
        stop_loss=99.0,
        take_profit=None,
        initial_risk_distance=1.0,
        exit_reason="signal",
        gross_pnl=net,
        commission_paid=0.0,
        net_pnl=net,
        r_multiple=r,
        mae_price=0.0,
        mfe_price=abs(r),
        mae_r=0.0,
        mfe_r=abs(r),
        holding_bars=1,
    )


def curve(equities: list[float], in_position_from: int | None = None) -> list[EquityPoint]:
    points = []
    for i, eq in enumerate(equities):
        candle = make_candle(i, 100, 100, 100, 100)
        in_pos = in_position_from is not None and i >= in_position_from
        points.append(
            EquityPoint(
                bar_index=i,
                timestamp=candle.timestamp,
                equity=eq,
                closed_equity=eq,
                open_pnl=0.0,
                in_position=in_pos,
            )
        )
    return points


CFG = BacktestConfig(min_trades=3)
TRADES = [trade(200.0, 2.0, 0), trade(-100.0, -1.0, 1), trade(300.0, 3.0, 2), trade(-50.0, -0.5, 3)]
CURVE = curve([100_000.0, 100_200.0, 100_100.0, 100_400.0, 100_350.0])


class TestTradeMetrics:
    def test_counts_and_rates(self) -> None:
        result = compute_statistics(TRADES, CURVE, CFG, Timeframe.M1)
        assert (result.total_trades, result.wins, result.losses) == (4, 2, 2)
        assert result.win_rate == pytest.approx(0.5)

    def test_profit_factor_and_expectancy(self) -> None:
        result = compute_statistics(TRADES, CURVE, CFG, Timeframe.M1)
        assert result.gross_profit == pytest.approx(500.0)
        assert result.gross_loss == pytest.approx(150.0)
        assert result.profit_factor == pytest.approx(500.0 / 150.0)
        assert result.net_pnl == pytest.approx(350.0)
        assert result.expectancy_currency == pytest.approx(87.5)
        assert result.expectancy_r == pytest.approx((2.0 - 1.0 + 3.0 - 0.5) / 4)

    def test_averages_and_payoff(self) -> None:
        result = compute_statistics(TRADES, CURVE, CFG, Timeframe.M1)
        assert result.avg_win == pytest.approx(250.0)
        assert result.avg_loss == pytest.approx(75.0)
        assert result.payoff_ratio == pytest.approx(250.0 / 75.0)

    def test_streaks(self) -> None:
        result = compute_statistics(TRADES, CURVE, CFG, Timeframe.M1)
        assert result.max_consecutive_wins == 1
        assert result.max_consecutive_losses == 1
        streaked = [trade(10, 1, 0), trade(20, 1, 1), trade(-5, -1, 2), trade(5, 1, 3)]
        result = compute_statistics(streaked, CURVE, CFG, Timeframe.M1)
        assert result.max_consecutive_wins == 2

    def test_profit_factor_none_without_losses(self) -> None:
        result = compute_statistics([trade(10, 1, 0)], CURVE, CFG, Timeframe.M1)
        assert result.profit_factor is None
        assert result.avg_loss is None
        assert result.payoff_ratio is None

    def test_empty_trades(self) -> None:
        result = compute_statistics([], CURVE, CFG, Timeframe.M1)
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.expectancy_r == 0.0

    def test_reliability_flag(self) -> None:
        assert compute_statistics(TRADES, CURVE, CFG, Timeframe.M1).statistics_reliable is True
        strict = BacktestConfig(min_trades=30)
        assert compute_statistics(TRADES, CURVE, strict, Timeframe.M1).statistics_reliable is False


class TestDrawdown:
    def test_max_drawdown_hand_computed(self) -> None:
        points = curve([100.0, 120.0, 90.0, 110.0, 95.0])
        dd = max_drawdown(points)
        assert dd.max_drawdown_abs == pytest.approx(30.0)  # 120 -> 90
        assert dd.max_drawdown_pct == pytest.approx(30.0 / 120.0)
        assert dd.peak_index == 1
        assert dd.trough_index == 2

    def test_monotonic_curve_has_zero_drawdown(self) -> None:
        dd = max_drawdown(curve([1.0, 2.0, 3.0]))
        assert dd.max_drawdown_abs == 0.0


class TestReturnsAndRatios:
    def test_bar_returns(self) -> None:
        returns = bar_returns(curve([100.0, 110.0, 99.0]))
        assert returns == pytest.approx([0.1, -0.1])

    def test_annualization_from_timeframe(self) -> None:
        assert annualization_factor(Timeframe.M1) == pytest.approx(365.25 * 24 * 60)
        assert annualization_factor(Timeframe.D1) == pytest.approx(365.25)

    def test_sharpe_matches_manual_calc(self) -> None:
        points = curve([100.0, 110.0, 99.0, 108.9])
        result = compute_statistics([], points, CFG, Timeframe.D1)
        returns = [0.1, -0.1, 0.1]
        expected = stats.fmean(returns) / stats.stdev(returns) * math.sqrt(365.25)
        assert result.sharpe == pytest.approx(expected)

    def test_sortino_uses_downside_only(self) -> None:
        points = curve([100.0, 110.0, 99.0, 108.9])
        result = compute_statistics([], points, CFG, Timeframe.D1)
        returns = [0.1, -0.1, 0.1]
        dd = math.sqrt(stats.fmean(min(r, 0.0) ** 2 for r in returns))
        expected = stats.fmean(returns) / dd * math.sqrt(365.25)
        assert result.sortino == pytest.approx(expected)

    def test_sharpe_none_when_flat(self) -> None:
        result = compute_statistics([], curve([100.0, 100.0, 100.0]), CFG, Timeframe.M1)
        assert result.sharpe is None
        assert result.sortino is None

    def test_calmar_none_without_drawdown(self) -> None:
        result = compute_statistics([], curve([100.0, 101.0, 102.0]), CFG, Timeframe.D1)
        assert result.calmar is None

    def test_exposure(self) -> None:
        points = curve([1.0, 1.0, 1.0, 1.0], in_position_from=2)
        result = compute_statistics([], points, CFG, Timeframe.M1)
        assert result.exposure_pct == pytest.approx(0.5)
