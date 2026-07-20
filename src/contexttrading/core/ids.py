"""Deterministic and run-scoped ID generation.

- **Content-hash IDs** (:func:`deterministic_id`) identify analysis objects:
  identical detections (same swing, same FVG, same inputs) get identical IDs
  across runs and machines. This is what makes regression goldens and
  idempotent result stores possible.
- **Run-scoped IDs** (:func:`new_run_id`) use UUID4 for bookkeeping entities
  (analysis runs, API requests). They are metadata and never participate in
  analytical payload equality.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

_HASH_HEX_LENGTH = 24


def _canonicalize(value: Any) -> Any:
    """Convert arbitrary content into JSON-stable primitives."""
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {
            str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def canonical_json(content: Any) -> str:
    """Serialize content to canonical JSON (sorted keys, tight separators).

    The output is stable across processes and machines for equal content,
    which is what the determinism contract relies on.
    """
    return json.dumps(
        _canonicalize(content),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_hash(content: Any) -> str:
    """SHA-256 hex digest (truncated) of the canonical JSON of ``content``."""
    digest = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
    return digest[:_HASH_HEX_LENGTH]


def deterministic_id(content: Any, *, prefix: str = "obj") -> str:
    """Build a deterministic, human-greppable ID: ``"<prefix>_<hash24>"``.

    Args:
        content: Mapping, sequence, or pydantic model describing the object.
        prefix: Short lowercase type tag (e.g. ``"swing"``, ``"fvg"``).

    Returns:
        Deterministic ID stable for identical content.
    """
    return f"{prefix}_{content_hash(content)}"


def new_run_id() -> str:
    """New run-scoped ID (UUID4-based) for bookkeeping entities."""
    return f"run_{uuid.uuid4().hex}"
