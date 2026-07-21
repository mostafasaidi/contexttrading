"""Execution-layer unit tests: fills, costs, sizing, SL/TP, MAE/MFE."""

from __future__ import annotations

import pytest

from contexttrading.backtesting.execution import (
    PositionState,
    close_trade,
    commission,
    manage_position,
    size_position,
    try_fill_intent,
)
from contexttrading.core.config import BacktestConfig
from contexttrading.core.constants import TrendDirection
from contexttrading.core.errors import BacktestError
from contexttrading.models.backtest import OrderIntent
from tests.unit.backtesting.conftest import make_candle

CFG = BacktestConfig(spread_bps=2.0, slippage_bps=4.0, commission_bps=1.0)
# half-spread = 1bp, slippage = 4bps
HALF = 0.0001
SLIP = 0.0004


def intent(kind: str, direction: str = "bullish", price: float | None = None, **kw) -> OrderIntent:
    return OrderIntent(
        kind=kind,
        direction=direction,
        price=price,
        stop_loss=kw.pop("stop_loss", 99.0),
        created_index=0,
        **kw,
    )


class TestMarketFills:
    def test_buy_market_pays_spread_and_slippage(self) -> None:
        bar = make_candle(0, 100.0, 101.0, 99.5, 100.5)
        fill = try_fill_intent(intent("market"), bar, CFG)
        assert fill == pytest.approx(100.0 * (1 + HALF + SLIP))

    def test_sell_market_receives_less(self) -> None:
        bar = make_candle(0, 100.0, 101.0, 99.5, 100.5)
        fill = try_fill_intent(intent("market", "bearish"), bar, CFG)
        assert fill == pytest.approx(100.0 * (1 - HALF - SLIP))

    def test_ranging_direction_rejected(self) -> None:
        bar = make_candle(0, 100.0, 101.0, 99.5, 100.5)
        with pytest.raises(BacktestError):
            try_fill_intent(intent("market", "ranging"), bar, CFG)


class TestLimitFills:
    def test_buy_limit_tie_counts_as_filled(self) -> None:
        # low touches the limit exactly -> filled at the limit + half-spread
        bar = make_candle(0, 100.5, 101.0, 100.0, 100.6)
        fill = try_fill_intent(intent("limit", price=100.0), bar, CFG)
        assert fill == pytest.approx(100.0 * (1 + HALF))

    def test_buy_limit_gap_fills_at_open(self) -> None:
        # open gaps below the limit -> buyer gets the better open price
        bar = make_candle(0, 99.5, 100.2, 99.0, 100.0)
        fill = try_fill_intent(intent("limit", price=100.0), bar, CFG)
        assert fill == pytest.approx(99.5 * (1 + HALF))

    def test_buy_limit_no_touch_expires_unfilled(self) -> None:
        bar = make_candle(0, 100.5, 101.0, 100.2, 100.6)
        assert try_fill_intent(intent("limit", price=100.0), bar, CFG) is None

    def test_sell_limit_tie_and_gap(self) -> None:
        tie = make_candle(0, 99.5, 100.0, 99.0, 99.6)
        assert try_fill_intent(intent("limit", "bearish", 100.0), tie, CFG) == pytest.approx(
            100.0 * (1 - HALF)
        )
        gap = make_candle(0, 100.5, 101.0, 100.2, 100.6)
        assert try_fill_intent(intent("limit", "bearish", 100.0), gap, CFG) == pytest.approx(
            100.5 * (1 - HALF)
        )

    def test_limit_requires_price(self) -> None:
        bar = make_candle(0, 100.0, 101.0, 99.5, 100.5)
        with pytest.raises(BacktestError):
            try_fill_intent(intent("limit"), bar, CFG)


class TestStopEntryFills:
    def test_buy_stop_touch_fills_at_trigger_with_slippage(self) -> None:
        bar = make_candle(0, 99.5, 100.0, 99.0, 99.8)
        fill = try_fill_intent(intent("stop", price=100.0), bar, CFG)
        assert fill == pytest.approx(100.0 * (1 + HALF + SLIP))

    def test_buy_stop_gap_fills_at_open(self) -> None:
        bar = make_candle(0, 100.5, 101.0, 100.3, 100.8)
        fill = try_fill_intent(intent("stop", price=100.0), bar, CFG)
        assert fill == pytest.approx(100.5 * (1 + HALF + SLIP))

    def test_sell_stop_no_touch(self) -> None:
        bar = make_candle(0, 100.5, 101.0, 100.2, 100.6)
        assert try_fill_intent(intent("stop", "bearish", 100.0), bar, CFG) is None


class TestCostsAndSizing:
    def test_commission_per_side(self) -> None:
        assert commission(100.0, 10.0, CFG) == pytest.approx(100.0 * 10.0 * 1e-4)

    def test_risk_percent_sizing(self) -> None:
        fill = 100.0
        order = intent("market", stop_loss=99.0)
        units = size_position(order, 100_000.0, fill, CFG)  # risk 1% = 1000 / 1.0 distance
        assert units == pytest.approx(1000.0)

    def test_risk_sizing_requires_stop(self) -> None:
        order = OrderIntent(kind="market", direction="bullish", created_index=0)
        with pytest.raises(BacktestError):
            size_position(order, 100_000.0, 100.0, CFG)

    def test_fixed_units_mode(self) -> None:
        cfg = BacktestConfig(position_sizing="fixed_units", fixed_units=7.5)
        order = OrderIntent(kind="market", direction="bullish", created_index=0)
        assert size_position(order, 100_000.0, 100.0, cfg) == 7.5

    def test_explicit_size_wins(self) -> None:
        order = intent("market", size_units=3.0)
        assert size_position(order, 100_000.0, 100.0, CFG) == 3.0


def position(
    direction: str = "bullish",
    entry: float = 100.0,
    sl: float = 99.0,
    tp: float | None = 102.0,
    size: float = 10.0,
) -> PositionState:
    sign = 1 if direction == "bullish" else -1
    return PositionState(
        direction=TrendDirection(direction),
        sign=sign,
        size_units=size,
        entry_index=1,
        entry_timestamp=make_candle(1, entry, entry, entry, entry).timestamp,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        initial_risk_distance=abs(entry - sl),
        commission_entry=commission(entry, size, CFG),
    )


class TestPositionManagement:
    def test_long_sl_hit_fills_at_stop_with_slippage(self) -> None:
        pos = position()
        bar = make_candle(2, 100.2, 100.4, 98.8, 99.2)  # low through SL, TP untouched
        fill, reason = manage_position(pos, bar, CFG)
        assert reason == "stop_loss"
        assert fill == pytest.approx(99.0 * (1 - HALF - SLIP))  # selling out

    def test_long_tp_hit_fills_at_target_without_slippage(self) -> None:
        pos = position()
        bar = make_candle(2, 100.5, 102.0, 100.2, 101.5)
        fill, reason = manage_position(pos, bar, CFG)
        assert reason == "take_profit"
        assert fill == pytest.approx(102.0 * (1 - HALF))

    def test_intrabar_ambiguity_assumes_sl_first(self) -> None:
        pos = position()
        bar = make_candle(2, 100.2, 102.5, 98.5, 101.0)  # both SL and TP in range
        fill, reason = manage_position(pos, bar, CFG)
        assert reason == "stop_loss"
        assert fill == pytest.approx(99.0 * (1 - HALF - SLIP))

    def test_gap_through_sl_fills_at_open(self) -> None:
        pos = position()
        bar = make_candle(2, 98.5, 99.0, 98.0, 98.4)  # opens below the stop
        fill, reason = manage_position(pos, bar, CFG)
        assert reason == "stop_loss"
        assert fill == pytest.approx(98.5 * (1 - HALF - SLIP))

    def test_gap_past_tp_fills_at_open(self) -> None:
        pos = position()
        bar = make_candle(2, 102.5, 103.0, 102.2, 102.8)  # opens above the target
        fill, reason = manage_position(pos, bar, CFG)
        assert reason == "take_profit"
        assert fill == pytest.approx(102.5 * (1 - HALF))

    def test_short_mirror_sl(self) -> None:
        pos = position("bearish", entry=100.0, sl=101.0, tp=98.0)
        bar = make_candle(2, 100.2, 101.3, 100.0, 100.5)
        fill, reason = manage_position(pos, bar, CFG)
        assert reason == "stop_loss"
        assert fill == pytest.approx(101.0 * (1 + HALF + SLIP))  # buying back

    def test_no_hit_returns_none(self) -> None:
        pos = position()
        bar = make_candle(2, 100.2, 101.0, 99.5, 100.6)
        assert manage_position(pos, bar, CFG) is None

    def test_breakeven_only_moves_forward(self) -> None:
        pos = position()
        pos.apply_breakeven()
        assert pos.stop_loss == 100.0
        pos.apply_breakeven()
        assert pos.stop_loss == 100.0  # idempotent
        short = position("bearish", entry=100.0, sl=101.0, tp=98.0)
        short.apply_breakeven()
        assert short.stop_loss == 100.0


class TestCloseTrade:
    def test_pnl_r_and_mae_mfe_math(self) -> None:
        pos = position(entry=100.0, sl=99.0, tp=None, size=10.0)
        pos.min_price = 98.0  # dipped 2 below entry while holding
        pos.max_price = 103.0  # rallied 3 above entry
        trade = close_trade(
            pos,
            exit_price=102.0,
            exit_index=5,
            exit_timestamp=make_candle(5, 102, 102, 102, 102).timestamp,
            reason="signal",
            sequence=0,
            config=CFG,
        )
        assert trade.gross_pnl == pytest.approx((102.0 - 100.0) * 10.0)
        expected_costs = commission(100.0, 10.0, CFG) + commission(102.0, 10.0, CFG)
        assert trade.commission_paid == pytest.approx(expected_costs)
        assert trade.net_pnl == pytest.approx(trade.gross_pnl - expected_costs)
        assert trade.r_multiple == pytest.approx(2.0)  # +2 over 1.0 initial risk
        assert trade.mae_price == pytest.approx(2.0)
        assert trade.mfe_price == pytest.approx(3.0)
        assert trade.mae_r == pytest.approx(2.0)
        assert trade.mfe_r == pytest.approx(3.0)
        assert trade.holding_bars == 4

    def test_short_mae_mfe_mirrored(self) -> None:
        pos = position("bearish", entry=100.0, sl=101.0, tp=None, size=5.0)
        pos.min_price = 97.0
        pos.max_price = 101.5
        trade = close_trade(
            pos,
            exit_price=99.0,
            exit_index=3,
            exit_timestamp=make_candle(3, 99, 99, 99, 99).timestamp,
            reason="signal",
            sequence=1,
            config=CFG,
        )
        assert trade.gross_pnl == pytest.approx((100.0 - 99.0) * 5.0)
        assert trade.mae_price == pytest.approx(1.5)
        assert trade.mfe_price == pytest.approx(3.0)
        assert trade.r_multiple == pytest.approx(1.0)
