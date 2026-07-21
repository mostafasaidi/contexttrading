"""Exception taxonomy for ContextTrading.

Every error carries a stable machine-readable ``code`` and a structured
``context`` dict so API error envelopes and logs can be built mechanically.

Code ranges:
    - ``CT-0xxx`` base / unknown
    - ``CT-1xxx`` data layer
    - ``CT-2xxx`` validation
    - ``CT-3xxx`` analysis engine
    - ``CT-4xxx`` configuration
    - ``CT-5xxx`` AI providers
    - ``CT-6xxx`` backtesting
    - ``CT-7xxx`` API surface
"""

from __future__ import annotations

from typing import Any, ClassVar


class ContextTradingError(Exception):
    """Base class for all ContextTrading errors.

    Args:
        message: Human-readable description.
        code: Machine-readable error code; defaults to the class code.
        context: Structured details (symbol, timeframe, field, …) safe to log
            and serialize.
    """

    default_code: ClassVar[str] = "CT-0000"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.context: dict[str, Any] = dict(context) if context else {}

    def with_context(self, **extra: Any) -> ContextTradingError:
        """Return ``self`` after merging extra context (fluent helper)."""
        self.context.update(extra)
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the API/log error envelope shape."""
        return {
            "error": {
                "type": type(self).__name__,
                "code": self.code,
                "message": self.message,
                "context": self.context,
            }
        }

    def __str__(self) -> str:
        if self.context:
            return f"[{self.code}] {self.message} | context={self.context}"
        return f"[{self.code}] {self.message}"


class DataError(ContextTradingError):
    """Ingestion, provider, or storage failures."""

    default_code = "CT-1000"


class DataGapError(DataError):
    """Unexpected gaps or missing candles in a series."""

    default_code = "CT-1001"


class ValidationError(ContextTradingError):
    """Domain validation failures beyond pydantic field errors."""

    default_code = "CT-2000"


class SchemaVersionError(ValidationError):
    """Unsupported or mismatched schema/engine version."""

    default_code = "CT-2001"


class AnalysisError(ContextTradingError):
    """Engine computation failures (structure, zones, confluence)."""

    default_code = "CT-3000"


class InsufficientDataError(AnalysisError):
    """Not enough candles to run a module."""

    default_code = "CT-3001"


class ConfigurationError(ContextTradingError):
    """Invalid, missing, or conflicting configuration."""

    default_code = "CT-4000"


class AIProviderError(ContextTradingError):
    """AI provider call or structured-output parsing failures."""

    default_code = "CT-5000"


class AIResponseError(AIProviderError):
    """Provider output is not valid JSON / does not match the schema."""

    default_code = "CT-5001"


class CitationError(AIProviderError):
    """AI cited evidence ids that do not exist in the context (fabrication)."""

    default_code = "CT-5002"


class BacktestError(ContextTradingError):
    """Backtest replay, fill, or accounting failures."""

    default_code = "CT-6000"


class APIError(ContextTradingError):
    """API-layer failures (auth, rate limits, serialization)."""

    default_code = "CT-7000"
