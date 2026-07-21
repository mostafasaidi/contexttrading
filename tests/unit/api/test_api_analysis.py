"""Contract tests for analysis routes and the auth matrix."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from contexttrading.analysis.pipeline import MODULE_ORDER
from contexttrading.api.app import create_app
from tests.unit.api.conftest import make_settings


class TestSingleModule:
    def test_structure(self, client, auth_headers, candles_body) -> None:
        response = client.post("/v1/analysis/structure", json=candles_body, headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["module"] == "structure"
        assert body["schema_version"] == "1.0.0"
        assert len(body["payload"]["swings"]) > 0

    def test_premium_discount_slug(self, client, auth_headers, candles_body) -> None:
        response = client.post(
            "/v1/analysis/premium-discount", json=candles_body, headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["module"] == "premium_discount"

    def test_mtf_with_timeframes(self, client, auth_headers, candles_body) -> None:
        body = {**candles_body, "mtf_timeframes": ["1h", "4h"]}
        response = client.post("/v1/analysis/mtf", json=body, headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["module"] == "mtf"

    def test_unknown_module_404(self, client, auth_headers, candles_body) -> None:
        response = client.post("/v1/analysis/astrology", json=candles_body, headers=auth_headers)
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "CT-7003"
        assert error["request_id"]


class TestFullStack:
    def test_all_modules_fixed_order(self, client, auth_headers, candles_body) -> None:
        response = client.post("/v1/analysis/full", json=candles_body, headers=auth_headers)
        assert response.status_code == 200
        assert list(response.json()["results"].keys()) == list(MODULE_ORDER)

    def test_config_overrides_applied(self, client, auth_headers, candles_body) -> None:
        body = {**candles_body, "config_overrides": {"internal_swing_lookback": 1}}
        response = client.post("/v1/analysis/structure", json=body, headers=auth_headers)
        assert response.status_code == 200

    def test_unknown_override_key_422(self, client, auth_headers, candles_body) -> None:
        body = {**candles_body, "config_overrides": {"not_a_field": 1}}
        response = client.post("/v1/analysis/full", json=body, headers=auth_headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CT-2000"


class TestAuthMatrix:
    def test_no_key_401(self, client, candles_body) -> None:
        response = client.post("/v1/analysis/full", json=candles_body)
        assert response.status_code == 401
        error = response.json()["error"]
        assert error["code"] == "CT-7001"
        assert set(response.json()) == {"error", "schema_version"}

    def test_wrong_key_401(self, client, candles_body) -> None:
        response = client.post(
            "/v1/analysis/full", json=candles_body, headers={"X-API-Key": "wrong"}
        )
        assert response.status_code == 401

    def test_auth_disabled_open(self, tmp_path, candles_body) -> None:
        settings = make_settings(tmp_path, auth_enabled=False)
        with TestClient(create_app(settings)) as client:
            response = client.post("/v1/analysis/structure", json=candles_body)
        assert response.status_code == 200

    def test_allow_anonymous_open(self, tmp_path, candles_body) -> None:
        settings = make_settings(tmp_path, allow_anonymous=True, api_keys=[])
        with TestClient(create_app(settings)) as client:
            response = client.post("/v1/analysis/structure", json=candles_body)
        assert response.status_code == 200

    def test_health_endpoints_open(self, client) -> None:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200


class TestValidationAndLimits:
    def test_bad_candle_record_400(self, client, auth_headers, candles_body) -> None:
        import json as _json

        body = _json.loads(_json.dumps(candles_body))
        body["series"]["candles"][3]["high"] = 0.0001  # high < open/close
        response = client.post("/v1/analysis/structure", json=body, headers=auth_headers)
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "CT-1000"

    def test_missing_field_422(self, client, auth_headers) -> None:
        response = client.post("/v1/analysis/full", json={"series": {}}, headers=auth_headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CT-2000"

    def test_insufficient_candles_422(self, client, auth_headers, candles_body) -> None:
        import json as _json

        body = _json.loads(_json.dumps(candles_body))
        body["series"]["candles"] = body["series"]["candles"][:3]  # below min_candles=5
        response = client.post("/v1/analysis/structure", json=body, headers=auth_headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CT-3001"

    def test_oversized_413(self, tmp_path, auth_headers, candles_body) -> None:
        settings = make_settings(tmp_path, max_candles_per_request=10)
        with TestClient(create_app(settings)) as client:
            response = client.post("/v1/analysis/full", json=candles_body, headers=auth_headers)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "CT-7002"

    def test_request_id_echoed(self, client, auth_headers, candles_body) -> None:
        response = client.post(
            "/v1/analysis/structure",
            json=candles_body,
            headers={**auth_headers, "X-Request-ID": "req-123"},
        )
        assert response.headers["X-Request-ID"] == "req-123"


@pytest.mark.parametrize(
    "module",
    ["liquidity", "fvg", "orderblocks", "supplydemand", "sessions", "confluence", "trend"],
)
def test_each_module_smoke(client, auth_headers, candles_body, module: str) -> None:
    response = client.post(f"/v1/analysis/{module}", json=candles_body, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["module"] == module
