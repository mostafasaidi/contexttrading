"""Backtest property tests (hypothesis): accounting + timing invariants."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from contexttrading.backtesting.replay import run_backtest
from contexttrading.core.config import BacktestConfig
from contexttrading.models.backtest import OrderIntent
from contexttrading.models.candle import CandleSeries
from tests.unit.backtesting.conftest import ScriptStrategy


def _series_from_steps(steps: list[float]) -> CandleSeries:
    price = 100.0
    records = []
    for i, step in enumerate(steps):
        open_ = price
        close = price + step
        high = max(open_, close) + 0.3
        low = min(open_, close) - 0.3
        records.append(
            {
                "timestamp": f"2024-01-02T{i // 60:02d}:{i % 60:02d}:00Z",
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": 100,
            }
        )
        price = close
    return CandleSeries.from_records(records, symbol="P", timeframe="1m")


_CFG = BacktestConfig(
    warmup_bars=2, min_trades=1, spread_bps=2.0, slippage_bps=1.0, commission_bps=1.0
)


@given(
    steps=st.lists(
        st.floats(min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False),
        min_size=20,
        max_size=40,
    ),
    entry_bar=st.integers(min_value=3, max_value=15),
    sl_offset=st.floats(min_value=0.5, max_value=3.0, allow_nan=False, allow_infinity=False),
)
@hyp_settings(max_examples=30, deadline=None)
def test_backtest_invariants(steps, entry_bar, sl_offset) -> None:
    series = _series_from_steps(steps)

    class OneShot(ScriptStrategy):
        def on_bar(self, bar_index, series, results, position, equity):
            if bar_index == entry_bar and position is None:
                close = series.candles[-1].close
                return [
                    OrderIntent(
                        kind="market",
                        direction="bullish",
                        stop_loss=close - sl_offset,
                        created_index=bar_index,
                    )
                ]
            return []

    result = run_backtest(series, OneShot(), backtest_config=_CFG)
    candles = series.candles

    # Accounting identity: realized equity == initial + sum(net PnL).
    assert result.equity_curve[-1].closed_equity == pytest.approx(
        _CFG.initial_equity + sum(t.net_pnl for t in result.trades), rel=1e-9
    )

    for trade in result.trades:
        # No fill before the next bar's open: entry always after the
        # decision bar, at that bar's open +/- bounded costs (<= 10 bps).
        assert trade.entry_index >= entry_bar + 1
        entry_open = candles[trade.entry_index].open
        assert trade.entry_price == pytest.approx(entry_open, rel=1e-3)
        # SL exits never fill better than the stop (long): fill <= stop.
        if trade.exit_reason == "stop_loss":
            assert trade.exit_price <= trade.stop_loss
        # MAE/MFE bounds and consistency.
        assert trade.mae_price >= 0.0
        assert trade.mfe_price >= 0.0
        assert trade.holding_bars == trade.exit_index - trade.entry_index

    stats = result.statistics
    assert 0.0 <= stats.win_rate <= 1.0
    assert 0.0 <= stats.exposure_pct <= 1.0
    assert stats.drawdown.max_drawdown_abs >= 0.0
    assert stats.wins + stats.losses == stats.total_trades
