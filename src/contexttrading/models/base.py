"""Base model contracts.

- :class:`VersionedModel` — every emitted model carries a ``schema_version``
  validated against the class-level ``SCHEMA_VERSION``.
- :class:`AnalysisObject` — mixin for engine-detected objects (swings, zones,
  breaks): deterministic content-hash ID, label, layer, priority.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contexttrading.core.ids import deterministic_id
from contexttrading.core.versioning import SCHEMA_VERSION_ANALYSIS_OBJECT, parse_version


class VersionedModel(BaseModel):
    """Base for all versioned, serializable models.

    Subclasses set ``SCHEMA_VERSION``; the ``schema_version`` field defaults
    to it and rejects mismatched values, so payloads can never silently drift
    from the class that validates them.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = Field(
        default="1.0.0", description="Version of this model's schema ('major.minor.patch')."
    )

    @model_validator(mode="before")
    @classmethod
    def _inject_schema_version(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = {**data}
            data.setdefault("schema_version", cls.SCHEMA_VERSION)
        return data

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, value: str) -> str:
        parse_version(value)  # raises on malformed strings
        expected = cls.SCHEMA_VERSION
        if value != expected:
            raise ValueError(
                f"schema_version mismatch: got {value!r}, {cls.__name__} expects {expected!r}"
            )
        return value

    def canonical_dict(self) -> dict[str, Any]:
        """JSON-mode dump used for deterministic hashing and golden files."""
        return self.model_dump(mode="json")


class AnalysisObject(VersionedModel):
    """Mixin for detected analysis objects with deterministic identity.

    The ``id`` defaults to a content hash of every field *except*
    ``id``/``label`` — identical detections get identical IDs. ``label`` is
    display metadata and therefore excluded from identity.
    """

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION_ANALYSIS_OBJECT

    id: str = Field(default="", description="Deterministic content-hash ID.")
    label: str | None = Field(default=None, description="Optional human-facing label.")
    layer: str = Field(default="default", description="Render/grouping layer.")
    priority: int = Field(default=0, description="Render/selection priority (higher wins).")

    # Identity prefix, e.g. "swing", "fvg". Subclasses must override.
    ID_PREFIX: ClassVar[str] = "obj"

    @model_validator(mode="after")
    def _ensure_deterministic_id(self) -> AnalysisObject:
        if not self.id:
            content = self.model_dump(mode="json", exclude={"id", "label"})
            # Bypass assignment validation; identity is derived, not user input.
            object.__setattr__(self, "id", deterministic_id(content, prefix=self.ID_PREFIX))
        return self
