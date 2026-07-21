"""Shared API test fixtures: app factory + request bodies."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contexttrading.api.app import create_app
from contexttrading.core.config import Settings
from tests.fixtures import engine_config, five_day_15m_series

TEST_KEY = "test-key"


def make_settings(tmp_path, **api_overrides) -> Settings:
    api = {"auth_enabled": True, "api_keys": [TEST_KEY], "max_candles_per_request": 20000}
    api.update(api_overrides)
    return Settings(
        engine=engine_config(),
        storage={"backend": "sqlite", "url": f"sqlite:///{tmp_path}/results.db"},
        api=api,
        ai={"provider": "mock"},
        _env_file=None,
    )


@pytest.fixture()
def client(tmp_path):
    with TestClient(create_app(make_settings(tmp_path))) as test_client:
        yield test_client


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": TEST_KEY}


@pytest.fixture(scope="module")
def candles_body() -> dict:
    series = five_day_15m_series()
    return {
        "series": {
            "symbol": series.symbol,
            "timeframe": str(series.timeframe),
            "candles": [c.model_dump(mode="json") for c in series.candles],
        }
    }
