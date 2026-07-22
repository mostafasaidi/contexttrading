"""Unit tests for the PostgreSQL result store.

Two tiers:

- Driver-absence behavior runs everywhere (psycopg is an optional
  dependency; a missing driver must raise ConfigurationError, not
  ModuleNotFoundError).
- Live round-trip tests require psycopg AND a reachable server; point
  ``CT_TEST_POSTGRES_DSN`` at one (e.g. the compose ``db`` profile:
  ``postgresql://contexttrading:contexttrading@localhost:5432/contexttrading``).
  They skip cleanly otherwise.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

from contexttrading.analysis.structure import analyze_structure
from contexttrading.core.errors import ConfigurationError, DataError
from contexttrading.data.postgres import PostgresResultStore, _load_psycopg
from contexttrading.data.store import hash_series
from tests.fixtures import engine_config, uptrend_series

_HAS_PSYCOPG = importlib.util.find_spec("psycopg") is not None
_DSN = os.environ.get("CT_TEST_POSTGRES_DSN", "")

requires_postgres = pytest.mark.skipif(
    not (_HAS_PSYCOPG and _DSN),
    reason="needs psycopg and CT_TEST_POSTGRES_DSN pointing at a live server",
)


class TestDriverLoading:
    def test_missing_driver_raises_configuration_error(self, monkeypatch) -> None:
        # sys.modules entry of None makes `import psycopg` fail with
        # ModuleNotFoundError regardless of whether it is installed.
        monkeypatch.setitem(sys.modules, "psycopg", None)
        with pytest.raises(ConfigurationError, match="psycopg"):
            _load_psycopg()

    def test_init_propagates_configuration_error(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "psycopg", None)
        with pytest.raises(ConfigurationError):
            PostgresResultStore("postgresql://localhost/whatever")


@requires_postgres
class TestLiveRoundTrip:
    @pytest.fixture()
    def store(self):
        with PostgresResultStore(_DSN) as s:
            s._conn.execute("DELETE FROM results")
            s._conn.commit()
            yield s

    def test_ping(self, store: PostgresResultStore) -> None:
        assert store.ping() is True

    def test_save_load_roundtrip(self, store: PostgresResultStore) -> None:
        series = uptrend_series()
        result = analyze_structure(series, engine_config())
        digest = hash_series(series)
        store.save(result, digest)
        loaded = store.load(series.symbol, str(series.timeframe), "structure", digest)
        assert loaded == result

    def test_upsert_replaces(self, store: PostgresResultStore) -> None:
        series = uptrend_series()
        result = analyze_structure(series, engine_config())
        digest = hash_series(series)
        store.save(result, digest)
        store.save(result, digest)
        row = store._conn.execute("SELECT COUNT(*) FROM results").fetchone()
        assert row[0] == 1

    def test_missing_row_returns_none(self, store: PostgresResultStore) -> None:
        series = uptrend_series()
        assert store.load(series.symbol, "15m", "structure", hash_series(series)) is None

    def test_unknown_module_raises(self, store: PostgresResultStore) -> None:
        with pytest.raises(DataError, match="Unknown module"):
            store.load("X", "15m", "not_a_module", "0" * 64)
