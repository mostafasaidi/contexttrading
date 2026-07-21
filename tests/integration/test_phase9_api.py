"""Phase 9 integration: REST API == direct engine calls on 2000 candles.

Posts the shared 2000-candle dataset through the HTTP stack (validation,
auth, DI, orchestration, serialization) and asserts byte-level equality
with a direct in-process ``run_full_stack`` call. Also covers the NDJSON
stream and the chart persist/retrieve round-trip on the same dataset.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from contexttrading.analysis.pipeline import MODULE_ORDER, run_full_stack
from contexttrading.api.app import create_app
from contexttrading.core.config import Settings
from tests.fixtures import engine_config
from tests.integration.test_pipeline import _dataset

AUTH = {"X-API-Key": "test-key"}


@pytest.fixture(scope="module")
def dataset():
    return _dataset()


@pytest.fixture(scope="module")
def body(dataset):
    return {
        "series": {
            "symbol": dataset.symbol,
            "timeframe": str(dataset.timeframe),
            "candles": [c.model_dump(mode="json") for c in dataset.candles],
        }
    }


@pytest.fixture()
def client(tmp_path):
    settings = Settings(
        engine=engine_config(),
        storage={"url": f"sqlite:///{tmp_path / 'results.db'}"},
        api={"auth_enabled": True, "api_keys": ["test-key"]},
        ai={"provider": "mock"},
        _env_file=None,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


class TestFullStackParity:
    def test_http_equals_direct(self, client, dataset, body) -> None:
        response = client.post("/v1/analysis/full", json=body, headers=AUTH)
        assert response.status_code == 200
        payload = response.json()
        assert list(payload["results"]) == list(MODULE_ORDER)

        direct = run_full_stack(dataset, engine_config())
        for module in MODULE_ORDER:
            assert payload["results"][module] == direct[module].model_dump(mode="json"), module

    def test_http_deterministic(self, client, body) -> None:
        first = client.post("/v1/analysis/full", json=body, headers=AUTH)
        second = client.post("/v1/analysis/full", json=body, headers=AUTH)
        assert first.status_code == second.status_code == 200
        assert first.content == second.content


class TestStreamParity:
    def test_stream_equals_direct(self, client, dataset, body) -> None:
        response = client.post("/v1/stream/analysis", json=body, headers=AUTH)
        assert response.status_code == 200
        lines = [json.loads(line) for line in response.text.strip().splitlines()]
        assert [line["module"] for line in lines] == [*MODULE_ORDER, "done"]
        assert lines[-1]["candle_count"] == len(dataset.candles)

        direct = run_full_stack(dataset, engine_config())
        for line in lines[:-1]:
            assert line["result"] == direct[line["module"]].model_dump(mode="json")


class TestChartRoundTrip:
    def test_chart_persist_and_fetch(self, client, dataset, body) -> None:
        response = client.post("/v1/charts/payload", json={**body, "persist": True}, headers=AUTH)
        assert response.status_code == 200
        payload = response.json()
        assert payload["series_hash"]

        fetched = client.get(
            f"/v1/results/{dataset.symbol}/{dataset.timeframe!s}/chart",
            params={"series_hash": payload["series_hash"]},
            headers=AUTH,
        )
        assert fetched.status_code == 200
        stored = fetched.json()
        assert stored["module"] == "chart"
        assert stored["series_hash"] == payload["series_hash"]
        assert stored["result"] == payload["chart"]
