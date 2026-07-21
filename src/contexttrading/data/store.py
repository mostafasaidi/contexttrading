"""SQLite result store: persist and reload ``AnalysisResult`` envelopes.

Deterministic cache keyed by ``(symbol, timeframe, module, series_hash)``:
the same analysis over the same data window always maps to one row, so
re-runs upsert instead of duplicating. Payloads are stored as the
envelope's canonical JSON (``model_dump_json``) and validated against the
current schema version on load — a major-version or newer-minor mismatch
raises :class:`~contexttrading.core.errors.SchemaVersionError` instead of
silently misinterpreting stale rows.

Storage itself never recomputes analysis; it only (de)serializes.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from contexttrading.core.errors import DataError, SchemaVersionError
from contexttrading.core.versioning import is_compatible
from contexttrading.models.base import VersionedModel
from contexttrading.models.candle import CandleSeries
from contexttrading.models.confluence import ConfluenceResult
from contexttrading.models.fvg import FVGResult
from contexttrading.models.liquidity import LiquidityResult
from contexttrading.models.mtf import MTFResult
from contexttrading.models.orderblock import OrderBlockResult
from contexttrading.models.outputs import AnalysisResult
from contexttrading.models.range import DealingRangeResult
from contexttrading.models.session import SessionResult
from contexttrading.models.structure import MarketStructureResult, TrendResult
from contexttrading.models.supplydemand import SupplyDemandResult
from contexttrading.visualization.serializer import ChartPayload

#: Module name -> payload model class (used to type the envelope on load).
PAYLOAD_MODELS: dict[str, type[VersionedModel]] = {
    "structure": MarketStructureResult,
    "trend": TrendResult,
    "liquidity": LiquidityResult,
    "premium_discount": DealingRangeResult,
    "fvg": FVGResult,
    "orderblocks": OrderBlockResult,
    "supplydemand": SupplyDemandResult,
    "sessions": SessionResult,
    "mtf": MTFResult,
    "confluence": ConfluenceResult,
    "chart": ChartPayload,
}

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


def hash_series(series: CandleSeries) -> str:
    """Stable content hash of a series (sha256 over canonical records)."""
    blob = json.dumps(series.to_records(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class ResultStore:
    """SQLite-backed store for versioned analysis envelopes."""

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        # check_same_thread=False: the API serves requests from worker
        # threads; the lock below serializes all access instead.
        self._lock = threading.Lock()
        try:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
            self._conn.execute(_SCHEMA)
        except sqlite3.Error as exc:  # pragma: no cover - environment failure
            raise DataError(
                f"Cannot open result store at {self._path}",
                context={"path": self._path, "error": str(exc)},
            ) from exc

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    def ping(self) -> bool:
        """Liveness probe used by /readyz."""
        with self._lock:
            self._conn.execute("SELECT 1")
        return True

    def __enter__(self) -> ResultStore:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def save(self, result: AnalysisResult, series_hash: str) -> None:  # type: ignore[type-arg]
        """Insert or replace one analysis envelope.

        Args:
            result: Envelope to persist (must serialize to JSON).
            series_hash: :func:`hash_series` of the input series.

        Raises:
            DataError: On any SQLite failure.
        """
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO results "
                    "(symbol, timeframe, module, series_hash, schema_version, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
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
        except sqlite3.Error as exc:
            raise DataError(
                "Failed to persist analysis result",
                context={"module": result.module, "error": str(exc)},
            ) from exc

    def load(
        self, symbol: str, timeframe: str, module: str, series_hash: str
    ) -> AnalysisResult | None:  # type: ignore[type-arg]
        """Load a stored envelope, validating schema compatibility.

        Args:
            symbol: Instrument symbol.
            timeframe: Timeframe string (e.g. ``"15m"``).
            module: Module name; must exist in :data:`PAYLOAD_MODELS`.
            series_hash: :func:`hash_series` of the input series.

        Returns:
            The typed envelope, or None when no row matches.

        Raises:
            DataError: Unknown module, corrupt row, or SQLite failure.
            SchemaVersionError: Stored schema is incompatible with the
                current code (different major, or newer minor).
        """
        model = PAYLOAD_MODELS.get(module)
        if model is None:
            raise DataError(f"Unknown module {module!r}", context={"module": module})
        try:
            with self._lock:
                row = self._conn.execute(
                    "SELECT schema_version, payload_json FROM results "
                    "WHERE symbol = ? AND timeframe = ? AND module = ? AND series_hash = ?",
                    (symbol, timeframe, module, series_hash),
                ).fetchone()
        except sqlite3.Error as exc:
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
