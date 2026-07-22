"""Edge-case hardening matrix: every module x degenerate series.

Expected behavior contract (documented per module docs and enforced here):

- Too-short series (empty / single / three candles): every module raises
  the typed ``InsufficientDataError`` (CT-3001) — never a raw
  ``ValidationError``, ``IndexError``, or ``ZeroDivisionError``. ``mtf`` is
  the one exception for non-empty short series: it degrades to UNKNOWN
  contexts by design (resampled HTFs are legitimately short), but still
  rejects an empty base series.
- Degenerate but full-length series (flat price, 10x gap, zero volume,
  news spike, low liquidity): every module completes and its envelope
  serializes to strict JSON — no NaN/Infinity leaks into payloads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from contexttrading.analysis.pipeline import MODULE_ORDER, run_module
from contexttrading.core.config import EngineConfig
from contexttrading.core.errors import InsufficientDataError
from contexttrading.models.candle import CandleSeries
from tests.fixtures import (
    flat_series,
    long_news_spike_series,
    low_liquidity_series,
    make_candle,
)

T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _series(records, symbol: str = "EDGE") -> CandleSeries:
    return CandleSeries.from_records(records, symbol=symbol, timeframe="15m")


def _gap10x_series() -> CandleSeries:
    records = [
        make_candle(i, 100 + i * 0.1, 100.5 + i * 0.1, 99.5 + i * 0.1, 100.2 + i * 0.1)
        for i in range(30)
    ]
    records += [make_candle(30 + i, 1000 + i, 1001 + i, 999 + i, 1000.5 + i) for i in range(30)]
    return _series(records, symbol="GAP")


def _zero_volume_series() -> CandleSeries:
    return _series(
        [
            make_candle(i, 100 + i * 0.1, 100.5 + i * 0.1, 99.5 + i * 0.1, 100.2 + i * 0.1, 0.0)
            for i in range(60)
        ],
        symbol="ZVOL",
    )


SHORT_SERIES = {
    "empty": lambda: _series([]),
    "single": lambda: _series([make_candle(0, 100, 101, 99, 100.5)]),
    "three": lambda: _series(
        [make_candle(i, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(3)]
    ),
}

FULL_LENGTH_SERIES = {
    "flat": lambda: flat_series(count=60),
    "gap10x": _gap10x_series,
    "zero_volume": _zero_volume_series,
    "news_spike": long_news_spike_series,
    "low_liquidity": low_liquidity_series,
}


def _strict_json(envelope) -> None:
    """model_dump_json must contain no NaN/Infinity constants."""

    def reject(constant: str) -> None:
        raise AssertionError(f"non-strict JSON constant {constant} in payload")

    json.loads(envelope.model_dump_json(), parse_constant=reject)


SHORT_CASES = [
    (module, case)
    for module in MODULE_ORDER
    for case in sorted(SHORT_SERIES)
    # mtf degrades non-empty short series to UNKNOWN contexts by design
    if not (module == "mtf" and case != "empty")
]


@pytest.fixture()
def config() -> EngineConfig:
    return EngineConfig()


@pytest.mark.parametrize(("module", "case"), SHORT_CASES)
def test_short_series_raises_typed_error(module, case, config):
    with pytest.raises(InsufficientDataError):
        run_module(module, SHORT_SERIES[case](), config)


def test_mtf_short_series_degrades_to_unknown(config):
    for case in ("single", "three"):
        result = run_module("mtf", SHORT_SERIES[case](), config)
        assert all(ctx.trend is None for ctx in result.payload.contexts)


@pytest.mark.parametrize("module", MODULE_ORDER)
@pytest.mark.parametrize("case", sorted(FULL_LENGTH_SERIES))
def test_degenerate_series_completes_without_nan(module, case, config):
    result = run_module(module, FULL_LENGTH_SERIES[case](), config)
    _strict_json(result)
