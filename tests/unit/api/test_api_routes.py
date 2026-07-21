"""Contract tests for chart, results, AI, and streaming routes."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from contexttrading.analysis.pipeline import MODULE_ORDER
from contexttrading.api.app import create_app
from tests.unit.api.conftest import make_settings


class TestCharts:
    def test_payload(self, client, auth_headers, candles_body) -> None:
        response = client.post("/v1/charts/payload", json=candles_body, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["chart"]["module"] == "chart"
        assert body["chart"]["payload"]["theme"]["name"] == "dark"
        assert body["series_hash"] is None

    def test_theme_override(self, client, auth_headers, candles_body) -> None:
        body = {**candles_body, "theme": "light"}
        response = client.post("/v1/charts/payload", json=body, headers=auth_headers)
        assert response.json()["chart"]["payload"]["theme"]["name"] == "light"

    def test_persist_and_fetch_round_trip(self, client, auth_headers, candles_body) -> None:
        response = client.post(
            "/v1/charts/payload", json={**candles_body, "persist": True}, headers=auth_headers
        )
        assert response.status_code == 200
        digest = response.json()["series_hash"]
        assert digest
        fetched = client.get(
            f"/v1/results/SESS/15m/chart?series_hash={digest}", headers=auth_headers
        )
        assert fetched.status_code == 200
        body = fetched.json()
        assert body["module"] == "chart"
        assert body["series_hash"] == digest
        assert body["result"]["payload"]["symbol"] == "SESS"


class TestResults:
    def test_missing_row_404(self, client, auth_headers) -> None:
        response = client.get(
            "/v1/results/SESS/15m/chart?series_hash=deadbeef00", headers=auth_headers
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CT-7003"

    def test_missing_hash_param_422(self, client, auth_headers) -> None:
        response = client.get("/v1/results/SESS/15m/chart", headers=auth_headers)
        assert response.status_code == 422

    def test_unknown_module_400(self, client, auth_headers) -> None:
        response = client.get(
            "/v1/results/SESS/15m/astrology?series_hash=deadbeef00", headers=auth_headers
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "CT-1000"


class TestAiRoutes:
    def test_market_analysis(self, client, auth_headers, candles_body) -> None:
        response = client.post("/v1/ai/market-analysis", json=candles_body, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["module"] == "ai.market_analysis"
        provenance = body["payload"]["provenance"]
        assert provenance["provider"] == "mock"
        assert provenance["prompt_name"] == "market_analysis"
        assert len(provenance["prompt_sha256"]) == 64

    def test_trade_evaluation(self, client, auth_headers, candles_body) -> None:
        body = {
            **candles_body,
            "setup": {
                "direction": "long",
                "entry_price": 100.0,
                "stop_loss": 99.0,
                "take_profits": [101.0],
            },
        }
        response = client.post("/v1/ai/trade-evaluation", json=body, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["payload"]["trade_evaluation"] is not None

    def test_journal_review(self, client, auth_headers) -> None:
        body = {
            "trades": [{"id": f"t{i}", "pnl": float(i - 5)} for i in range(12)],
            "period": "2024-W01",
        }
        response = client.post("/v1/ai/journal-review", json=body, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["module"] == "ai.journal_review"

    def test_weekly_review(self, client, auth_headers) -> None:
        body = {"statistics": {"trade_count": 25, "win_rate": 0.52}, "period": "2024-W01"}
        response = client.post("/v1/ai/weekly-review", json=body, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["payload"]["period"] == "2024-W01"

    def test_provider_not_configured_500(self, tmp_path, auth_headers, candles_body) -> None:
        settings = make_settings(tmp_path)
        settings.ai = settings.ai.model_copy(update={"provider": "none"})
        with TestClient(create_app(settings)) as client:
            response = client.post(
                "/v1/ai/market-analysis", json=candles_body, headers=auth_headers
            )
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "CT-4000"


class TestStreaming:
    def test_chunk_order_and_completeness(self, client, auth_headers, candles_body) -> None:
        response = client.post("/v1/stream/analysis", json=candles_body, headers=auth_headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        lines = [json.loads(line) for line in response.text.strip().split("\n")]
        modules = [line["module"] for line in lines]
        assert modules == [*MODULE_ORDER, "done"]
        streamed = {line["module"]: line["result"] for line in lines[:-1]}
        full = client.post("/v1/analysis/full", json=candles_body, headers=auth_headers).json()
        assert set(streamed) == set(full["results"])
        for module, result in streamed.items():
            assert result == full["results"][module]

    def test_deterministic_bytes(self, client, auth_headers, candles_body) -> None:
        first = client.post("/v1/stream/analysis", json=candles_body, headers=auth_headers).text
        second = client.post("/v1/stream/analysis", json=candles_body, headers=auth_headers).text
        assert first == second

    def test_stream_requires_auth(self, client, candles_body) -> None:
        response = client.post("/v1/stream/analysis", json=candles_body)
        assert response.status_code == 401


class TestOpenApi:
    ROUTES = (
        "/v1/analysis/full",
        "/v1/analysis/{module}",
        "/v1/charts/payload",
        "/v1/ai/market-analysis",
        "/v1/ai/trade-evaluation",
        "/v1/ai/journal-review",
        "/v1/ai/weekly-review",
        "/v1/results/{symbol}/{timeframe}/{module}",
        "/v1/stream/analysis",
        "/healthz",
        "/readyz",
    )

    def test_all_routes_exposed(self, client) -> None:
        spec = client.get("/openapi.json").json()
        for route in self.ROUTES:
            assert route in spec["paths"], f"missing {route}"

    def test_models_in_components(self, client) -> None:
        spec = client.get("/openapi.json").json()
        schemas = spec["components"]["schemas"]
        for model in (
            "CandlesInput",
            "AnalysisRequest",
            "ChartRequest",
            "ChartResponse",
            "TradeEvaluationRequest",
            "JournalReviewRequest",
            "WeeklyReviewRequest",
            "StoredResultResponse",
            "ErrorEnvelope",
        ):
            assert model in schemas, f"missing {model}"

    def test_metadata(self, client) -> None:
        spec = client.get("/openapi.json").json()
        assert spec["info"]["title"] == "ContextTrading"
        assert spec["info"]["version"]
        tags = {tag["name"] for tag in spec.get("tags", [])}
        assert {"analysis", "charts", "ai", "results", "stream"} <= tags
