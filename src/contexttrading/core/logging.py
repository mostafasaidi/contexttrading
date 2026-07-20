"""Structured logging facade over :mod:`logging`.

- Optional single-line JSON output for machine ingestion.
- Context binding via :meth:`BoundLogger.bind` — returns a new logger, never
  mutates shared state.
- No implicit global configuration: call :func:`configure_logging` once at a
  composition root; libraries call :func:`get_logger` and stay quiet by
  default (``NullHandler``).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, TextIO

_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Serialize log records as single-line JSON.

    Bound context is carried on the record's ``context`` attribute by
    :class:`BoundLogger`. Wall-clock timestamps appear only in log records —
    never in emitted models — per the determinism contract.
    """

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if context:
            payload["context"] = context
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class BoundLogger:
    """Thin wrapper around a :class:`logging.Logger` with immutable context.

    Obtain via :func:`get_logger`. ``bind`` returns a *new* instance with
    merged context — safe to share across layers.
    """

    __slots__ = ("_context", "_logger")

    def __init__(self, logger: logging.Logger, context: dict[str, Any] | None = None) -> None:
        self._logger = logger
        self._context: dict[str, Any] = dict(context) if context else {}

    @property
    def name(self) -> str:
        """Underlying logger name."""
        return self._logger.name

    @property
    def context(self) -> dict[str, Any]:
        """Copy of the bound context."""
        return dict(self._context)

    def bind(self, **context: Any) -> BoundLogger:
        """Return a new logger with additional bound context."""
        merged = {**self._context, **context}
        return BoundLogger(self._logger, merged)

    def _log(self, level: int, message: str, **context: Any) -> None:
        if not self._logger.isEnabledFor(level):
            return
        merged = {**self._context, **context} if context else self._context
        record = self._logger.makeRecord(
            self._logger.name,
            level,
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None,
        )
        record.context = merged
        self._logger.handle(record)

    def debug(self, message: str, **context: Any) -> None:
        """Log at DEBUG with optional structured context."""
        self._log(logging.DEBUG, message, **context)

    def info(self, message: str, **context: Any) -> None:
        """Log at INFO with optional structured context."""
        self._log(logging.INFO, message, **context)

    def warning(self, message: str, **context: Any) -> None:
        """Log at WARNING with optional structured context."""
        self._log(logging.WARNING, message, **context)

    def error(self, message: str, **context: Any) -> None:
        """Log at ERROR with optional structured context."""
        self._log(logging.ERROR, message, **context)

    def exception(self, message: str, **context: Any) -> None:
        """Log at ERROR with the active exception attached."""
        self._logger.exception(message, extra={"context": {**self._context, **context}})


def configure_logging(
    *,
    level: str = "INFO",
    json_output: bool = False,
    stream: TextIO | None = None,
) -> None:
    """Configure the root ``contexttrading`` logger. Call once at entrypoints.

    Args:
        level: Minimum level name (e.g. ``"INFO"``).
        json_output: Emit JSON lines instead of plain text.
        stream: Target stream (defaults to stderr).
    """
    global _CONFIGURED
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter() if json_output else logging.Formatter(_DEFAULT_FORMAT))
    root = logging.getLogger("contexttrading")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str, **context: Any) -> BoundLogger:
    """Get a bound logger for a module.

    Args:
        name: Dotted module path, typically ``__name__``.
        context: Initial bound context (e.g. ``symbol="ES"``).

    Returns:
        A :class:`BoundLogger`; silent unless :func:`configure_logging` ran.
    """
    full_name = name if name.startswith("contexttrading") else f"contexttrading.{name}"
    logger = logging.getLogger(full_name)
    root = logging.getLogger("contexttrading")
    if not _CONFIGURED and not logger.handlers and not root.handlers:
        logger.addHandler(logging.NullHandler())
    return BoundLogger(logger, context)
