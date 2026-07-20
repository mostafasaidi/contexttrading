"""Tests for core.logging: JSON output, context binding, no global abuse."""

from __future__ import annotations

import io
import json
import logging

from contexttrading.core.logging import (
    BoundLogger,
    JsonFormatter,
    configure_logging,
    get_logger,
)


class TestBoundLogger:
    def test_bind_returns_new_logger(self) -> None:
        base = BoundLogger(logging.getLogger("ct.test.bind"))
        child = base.bind(symbol="ES")
        assert child is not base
        assert base.context == {}
        assert child.context == {"symbol": "ES"}

    def test_bind_merges_without_mutation(self) -> None:
        base = BoundLogger(logging.getLogger("ct.test.merge"), {"a": 1})
        child = base.bind(b=2)
        assert child.context == {"a": 1, "b": 2}
        assert base.context == {"a": 1}

    def test_context_property_is_copy(self) -> None:
        logger = BoundLogger(logging.getLogger("ct.test.copy"), {"a": 1})
        logger.context["a"] = 999
        assert logger.context == {"a": 1}


class TestConfiguration:
    def test_json_output(self) -> None:
        stream = io.StringIO()
        configure_logging(level="DEBUG", json_output=True, stream=stream)
        logger = get_logger("ct.test.json", symbol="ES")
        logger.info("engine started", module="fvg")
        record = json.loads(stream.getvalue().strip())
        assert record["message"] == "engine started"
        assert record["level"] == "INFO"
        assert record["context"] == {"symbol": "ES", "module": "fvg"}
        assert "ts" in record

    def test_plain_output(self) -> None:
        stream = io.StringIO()
        configure_logging(level="INFO", json_output=False, stream=stream)
        get_logger("ct.test.plain").warning("heads up")
        text = stream.getvalue()
        assert "WARNING" in text and "heads up" in text

    def test_level_filtering(self) -> None:
        stream = io.StringIO()
        configure_logging(level="WARNING", json_output=True, stream=stream)
        logger = get_logger("ct.test.level")
        logger.debug("invisible")
        logger.error("visible")
        lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        assert json.loads(lines[0])["message"] == "visible"

    def test_quiet_without_configuration(self) -> None:
        # Fresh logger name, no configure_logging: must not raise and must be silent.
        silent = get_logger("ct.test.silent.unique")
        silent.info("nobody hears this")  # NullHandler swallow, no exception

    def test_json_formatter_includes_exception(self) -> None:
        formatter = JsonFormatter()
        try:
            raise ValueError("kaboom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                "ct.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
            )
        payload = json.loads(formatter.format(record))
        assert "ValueError: kaboom" in payload["exception"]
