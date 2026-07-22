"""PostgreSQL result store: the same envelope contract as the SQLite store.

Optional deployment backend. ``psycopg`` is NOT a hard dependency — it is
imported lazily, and a missing driver raises
:class:`~contexttrading.core.errors.ConfigurationError` with an install hint
(the same pattern as the httpx-based AI providers). Select it via
``CT_STORAGE__BACKEND=postgresql`` and ``CT_STORAGE__URL=postgresql://...``;
the compose ``db`` profile starts a matching postgres service.

Like the SQLite store, rows are keyed by
``(symbol, timeframe, module, series_hash)`` and re-runs upsert; payloads
are the envelope's canonical JSON, validated against the current schema
version on load. Storage never recomputes analysis.
"""

from __future__ import annotations

import json
import threading
from typing import Any

from contexttrading.core.errors import ConfigurationError, DataError, SchemaVersionError
from contexttrading.core.versioning import is_compatible
from contexttrading.data.store import PAYLOAD_MODELS
from contexttrading.models.outputs import AnalysisResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    module TEXT NOT NULL,
    series_hash TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (symbol, timeframe, module, series_hash)
)
"""

_UPSERT = """
INSERT INTO results (symbol, timeframe, module, series_hash, schema_version, payload_json)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, timeframe, module, series_hash)
DO UPDATE SET schema_version = EXCLUDED.schema_version,
              payload_json = EXCLUDED.payload_json
"""

_SELECT = """
SELECT schema_version, payload_json FROM results
WHERE symbol = %s AND timeframe = %s AND module = %s AND series_hash = %s
"""


def _load_psycopg():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise ConfigurationError(
            "psycopg is required for the PostgreSQL result store "
            "(pip install 'psycopg[binary]')",
            context={"package": "psycopg"},
        ) from exc
    return psycopg


class PostgresResultStore:
    """PostgreSQL-backed store for versioned analysis envelopes.

    Mirrors :class:`~contexttrading.data.store.ResultStore`
    (``save``/``load``/``ping``/``close``/context manager) so the API can
    swap backends through configuration alone.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._psycopg = _load_psycopg()
        self._lock = threading.Lock()
        try:
            self._conn = self._psycopg.connect(dsn)
            with self._lock:
                self._conn.execute(_SCHEMA)
                self._conn.commit()
        except self._psycopg.Error as exc:  # pragma: no cover - needs a server
            raise DataError(
                "Cannot open PostgreSQL result store",
                context={"error": str(exc)},
            ) from exc

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def ping(self) -> bool:
        """Liveness probe used by /readyz."""
        with self._lock:
            self._conn.execute("SELECT 1")
        return True

    def __enter__(self) -> PostgresResultStore:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def save(self, result: AnalysisResult, series_hash: str) -> None:  # type: ignore[type-arg]
        """Insert or update one analysis envelope.

        Args:
            result: Envelope to persist (must serialize to JSON).
            series_hash: :func:`~contexttrading.data.store.hash_series` of
                the input series.

        Raises:
            DataError: On any database failure.
        """
        try:
            with self._lock:
                self._conn.execute(
                    _UPSERT,
                    (
                        result.symbol,
                        str(result.timeframe),
                        result.module,
                        series_hash,
                        result.schema_version,
                        result.model_dump_json(),
                    ),
                )
                self._conn.commit()
        except self._psycopg.Error as exc:
            self._conn.rollback()
            raise DataError(
                "Failed to persist analysis result",
                context={"module": result.module, "error": str(exc)},
            ) from exc

    def load(
        self, symbol: str, timeframe: str, module: str, series_hash: str
    ) -> AnalysisResult | None:  # type: ignore[type-arg]
        """Load a stored envelope, validating schema compatibility.

        Returns the typed envelope, or None when no row matches. Raises
        :class:`DataError` for unknown modules/corrupt rows and
        :class:`SchemaVersionError` for incompatible stored schemas — same
        contract as the SQLite store.
        """
        model = PAYLOAD_MODELS.get(module)
        if model is None:
            raise DataError(f"Unknown module {module!r}", context={"module": module})
        try:
            with self._lock:
                row = self._conn.execute(
                    _SELECT, (symbol, timeframe, module, series_hash)
                ).fetchone()
        except self._psycopg.Error as exc:
            raise DataError(
                "Failed to read analysis result",
                context={"module": module, "error": str(exc)},
            ) from exc
        if row is None:
            return None
        stored_version, payload_json = row
        if not is_compatible(stored_version, AnalysisResult.SCHEMA_VERSION):
            raise SchemaVersionError(
                "Stored result has incompatible schema version",
                context={
                    "module": module,
                    "stored": stored_version,
                    "current": AnalysisResult.SCHEMA_VERSION,
                },
            )
        try:
            return AnalysisResult[model].model_validate(json.loads(payload_json))
        except (json.JSONDecodeError, ValueError) as exc:
            raise DataError(
                "Stored result failed validation",
                context={"module": module, "error": str(exc)},
            ) from exc
