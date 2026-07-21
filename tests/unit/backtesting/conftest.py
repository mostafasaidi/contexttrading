"""Shared backtest test helpers: tiny series + scriptable toy strategies.

Toy strategies declare ``modules = ()`` so replays run NO engine modules —
unit tests stay fast and exercise the replay/execution layer only.
"""

from __future__ import annotations

import pytest

from contexttrading.core.config import BacktestConfig
from contexttrading.models.backtest import OrderIntent
from contexttrading.models.candle import Candle, CandleSeries


def ramp_records(count: int = 40, start: float = 100.0, step: float = 1.0) -> list[dict]:
    """Monotonic ramp: each bar opens at prev close, trends up by ``step``."""
    records = []
    price = start
    for i in range(count):
        records.append(
            {
                "timestamp": (
                    f"2024-01-01T00:{i % 60:02d}:00Z"
                    if i < 60
                    else f"2024-01-01T{i // 60:02d}:{i % 60:02d}:00Z"
                ),
                "open": price,
                "high": price + step,
                "low": price - 0.5 * step,
                "close": price + 0.5 * step,
                "volume": 100,
            }
        )
        price += step
    return records


@pytest.fixture()
def ramp_series() -> CandleSeries:
    return CandleSeries.from_records(ramp_records(), symbol="T", timeframe="1m")


@pytest.fixture()
def free_config() -> BacktestConfig:
    """Zero-cost config so fill prices equal trigger/open prices exactly."""
    return BacktestConfig(
        warmup_bars=2,
        min_trades=1,
        spread_bps=0.0,
        slippage_bps=0.0,
        commission_bps=0.0,
    )


class ScriptStrategy:
    """Emits scripted intents at scripted bars; records every on_bar call."""

    name = "script"
    modules: tuple = ()

    def __init__(self, script: dict[int, list[OrderIntent]] | None = None) -> None:
        self.script = script or {}
        self.calls: list[int] = []
        self.results_seen: list[object] = []
        self.window_sizes: list[int] = []

    def on_bar(self, bar_index, series, results, position, equity) -> list[OrderIntent]:
        self.calls.append(bar_index)
        self.results_seen.append(results)
        self.window_sizes.append(len(series.candles))
        return [
            intent.model_copy(update={"created_index": bar_index})
            for intent in self.script.get(bar_index, [])
        ]


class ParamToyStrategy:
    """Grid-search toy: enters long once at ``enter_bar`` with ``tp_r`` target."""

    name = "param_toy"
    modules: tuple = ()

    def __init__(self, enter_bar: int = 5, tp_r: float = 2.0, risk: float = 2.0) -> None:
        self.enter_bar = enter_bar
        self.tp_r = tp_r
        self.risk = risk

    def on_bar(self, bar_index, series, results, position, equity) -> list[OrderIntent]:
        if bar_index == self.enter_bar and position is None:
            close = series.candles[-1].close
            return [
                OrderIntent(
                    kind="market",
                    direction="bullish",
                    stop_loss=close - self.risk,
                    take_profit=close + self.tp_r * self.risk,
                    created_index=bar_index,
                )
            ]
        return []


def make_candle(
    i: int, open_: float, high: float, low: float, close: float, minute: int | None = None
) -> Candle:
    return Candle(
        timestamp=f"2024-01-01T00:{(minute if minute is not None else i) % 60:02d}:00Z",
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
    )
