"""Backtest endpoint contract tests."""

from __future__ import annotations

#: Overrides keeping the five-day fixture fast while exercising all levers.
OVERRIDES = {
    "warmup_bars": 30,
    "min_trades": 1,
    "recompute_interval": 8,
    "window_bars": 200,
}


class TestBacktestRoute:
    def test_happy_path(self, client, auth_headers, candles_body) -> None:
        response = client.post(
            "/v1/backtest",
            json={**candles_body, "backtest_overrides": OVERRIDES},
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["module"] == "backtest"
        assert body["strategy"] == "smc_pullback"
        assert body["generated_from"]["candle_count"] == 480
        stats = body["statistics"]
        assert stats["total_trades"] == len(body["trades"])
        assert stats["statistics_reliable"] is False or stats["total_trades"] >= 1
        for trade in body["trades"]:
            assert len(trade["evidence_ids"]) >= 1
        assert len(body["equity_curve"]) == 480

    def test_deterministic_rerun(self, client, auth_headers, candles_body) -> None:
        payload = {**candles_body, "backtest_overrides": OVERRIDES}
        first = client.post("/v1/backtest", json=payload, headers=auth_headers)
        second = client.post("/v1/backtest", json=payload, headers=auth_headers)
        assert first.content == second.content

    def test_unknown_strategy_422(self, client, auth_headers, candles_body) -> None:
        response = client.post(
            "/v1/backtest",
            json={**candles_body, "strategy": "astrology"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CT-2000"

    def test_bad_backtest_override_422(self, client, auth_headers, candles_body) -> None:
        response = client.post(
            "/v1/backtest",
            json={**candles_body, "backtest_overrides": {"not_a_field": 1}},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "CT-2000"

    def test_auth_required(self, client, candles_body) -> None:
        response = client.post("/v1/backtest", json=candles_body)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "CT-7001"

    def test_strategy_params_accepted(self, client, auth_headers, candles_body) -> None:
        response = client.post(
            "/v1/backtest",
            json={
                **candles_body,
                "backtest_overrides": OVERRIDES,
                "strategy_params": {"min_confluence_score": 0.9, "allow_short": False},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["strategy_params"]["min_confluence_score"] == 0.9
