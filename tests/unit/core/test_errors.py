"""Tests for core.errors: hierarchy, codes, context, envelopes."""

from __future__ import annotations

import pytest

from contexttrading.core.errors import (
    AIProviderError,
    AnalysisError,
    APIError,
    BacktestError,
    ConfigurationError,
    ContextTradingError,
    DataError,
    DataGapError,
    InsufficientDataError,
    SchemaVersionError,
    ValidationError,
)


class TestHierarchy:
    @pytest.mark.parametrize(
        "exc_cls",
        [
            DataError,
            DataGapError,
            ValidationError,
            SchemaVersionError,
            AnalysisError,
            InsufficientDataError,
            ConfigurationError,
            AIProviderError,
            BacktestError,
            APIError,
        ],
    )
    def test_all_subclass_base(self, exc_cls: type[ContextTradingError]) -> None:
        assert issubclass(exc_cls, ContextTradingError)

    def test_leaf_codes(self) -> None:
        assert DataGapError.default_code == "CT-1001"
        assert SchemaVersionError.default_code == "CT-2001"
        assert InsufficientDataError.default_code == "CT-3001"


class TestBehavior:
    def test_default_code_used(self) -> None:
        err = DataError("feed down")
        assert err.code == "CT-1000"
        assert err.context == {}

    def test_explicit_code_and_context(self) -> None:
        err = AnalysisError("boom", code="CT-3999", context={"module": "fvg"})
        assert err.code == "CT-3999"
        assert err.context == {"module": "fvg"}

    def test_context_is_copied(self) -> None:
        ctx = {"a": 1}
        err = DataError("x", context=ctx)
        ctx["a"] = 2
        assert err.context == {"a": 1}

    def test_with_context_merges(self) -> None:
        err = APIError("denied", context={"route": "/v1/analyze"})
        returned = err.with_context(status=401)
        assert returned is err
        assert err.context == {"route": "/v1/analyze", "status": 401}

    def test_to_dict_envelope(self) -> None:
        err = ConfigurationError("bad tz", context={"tz": "Mars/Olympus"})
        payload = err.to_dict()
        assert payload == {
            "error": {
                "type": "ConfigurationError",
                "code": "CT-4000",
                "message": "bad tz",
                "context": {"tz": "Mars/Olympus"},
            }
        }

    def test_str_includes_code_and_context(self) -> None:
        err = DataError("gap", context={"symbol": "ES"})
        text = str(err)
        assert "CT-1000" in text and "ES" in text and "gap" in text

    def test_str_without_context(self) -> None:
        assert str(ContextTradingError("plain")) == "[CT-0000] plain"

    def test_exception_message_preserved(self) -> None:
        err = ValidationError("invalid field")
        assert err.args == ("invalid field",)
