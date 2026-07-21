"""Unit tests for the SQLite result store."""

from __future__ import annotations

import pytest

from contexttrading.analysis.fvg import analyze_fvg
from contexttrading.analysis.structure import analyze_structure
from contexttrading.core.errors import DataError, SchemaVersionError
from contexttrading.data.store import PAYLOAD_MODELS, ResultStore, hash_series
from contexttrading.visualization import build_chart_payload
from tests.fixtures import engine_config, full_stack_results, uptrend_series


@pytest.fixture()
def store(tmp_path):
    with ResultStore(tmp_path / "results.db") as s:
        yield s


class TestHashSeries:
    def test_stable_for_same_series(self) -> None:
        assert hash_series(uptrend_series()) == hash_series(uptrend_series())

    def test_differs_for_different_series(self) -> None:
        from tests.fixtures import downtrend_series

        assert hash_series(uptrend_series()) != hash_series(downtrend_series())


class TestRoundTrip:
    def test_analysis_result(self, store: ResultStore) -> None:
        series = uptrend_series()
        result = analyze_structure(series, engine_config())
        digest = hash_series(series)
        store.save(result, digest)
        loaded = store.load(series.symbol, str(series.timeframe), "structure", digest)
        assert loaded == result

    def test_chart_payload(self, store: ResultStore) -> None:
        series = uptrend_series()
        chart = build_chart_payload(series, full_stack_results(series, engine_config()))
        digest = hash_series(series)
        store.save(chart, digest)
        loaded = store.load(series.symbol, str(series.timeframe), "chart", digest)
        assert loaded == chart

    def test_missing_row_returns_none(self, store: ResultStore) -> None:
        series = uptrend_series()
        assert store.load(series.symbol, "15m", "structure", hash_series(series)) is None

    def test_upsert_replaces(self, store: ResultStore, tmp_path) -> None:
        series = uptrend_series()
        result = analyze_fvg(series, engine_config())
        digest = hash_series(series)
        store.save(result, digest)
        store.save(result, digest)
        rows = store._conn.execute("SELECT COUNT(*) FROM results").fetchone()
        assert rows[0] == 1


class TestVersionChecks:
    def _insert_raw(self, store: ResultStore, series, schema_version: str) -> str:
        result = analyze_structure(series, engine_config())
        digest = hash_series(series)
        store._conn.execute(
            "INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?, ?)",
            (
                series.symbol,
                str(series.timeframe),
                "structure",
                digest,
                schema_version,
                result.model_dump_json(),
            ),
        )
        store._conn.commit()
        return digest

    def test_older_major_rejected(self, store: ResultStore) -> None:
        series = uptrend_series()
        digest = self._insert_raw(store, series, "0.9.0")
        with pytest.raises(SchemaVersionError):
            store.load(series.symbol, str(series.timeframe), "structure", digest)

    def test_newer_minor_rejected(self, store: ResultStore) -> None:
        series = uptrend_series()
        digest = self._insert_raw(store, series, "1.99.0")
        with pytest.raises(SchemaVersionError):
            store.load(series.symbol, str(series.timeframe), "structure", digest)

    def test_older_minor_accepted(self, store: ResultStore) -> None:
        series = uptrend_series()
        digest = self._insert_raw(store, series, "1.0.0")
        loaded = store.load(series.symbol, str(series.timeframe), "structure", digest)
        assert loaded is not None

    def test_corrupt_payload_raises_data_error(self, store: ResultStore) -> None:
        series = uptrend_series()
        digest = hash_series(series)
        store._conn.execute(
            "INSERT OR REPLACE INTO results VALUES (?, ?, ?, ?, ?, ?)",
            (series.symbol, "15m", "structure", digest, "1.0.0", "{not json"),
        )
        store._conn.commit()
        with pytest.raises(DataError):
            store.load(series.symbol, "15m", "structure", digest)

    def test_unknown_module_raises_data_error(self, store: ResultStore) -> None:
        with pytest.raises(DataError):
            store.load("X", "15m", "astrology", "abc")


class TestRegistry:
    def test_all_analysis_modules_registered(self) -> None:
        expected = {
            "structure",
            "trend",
            "liquidity",
            "premium_discount",
            "fvg",
            "orderblocks",
            "supplydemand",
            "sessions",
            "mtf",
            "confluence",
            "chart",
        }
        assert set(PAYLOAD_MODELS) == expected

    def test_storage_failure_raises_data_error(self, tmp_path) -> None:
        store = ResultStore(tmp_path / "results.db")
        store.close()
        series = uptrend_series()
        result = analyze_structure(series, engine_config())
        with pytest.raises(DataError):
            store.save(result, hash_series(series))
        with pytest.raises(DataError):
            store.load(series.symbol, "15m", "structure", hash_series(series))
