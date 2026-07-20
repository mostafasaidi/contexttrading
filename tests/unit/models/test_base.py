"""Tests for models.base: VersionedModel and AnalysisObject contracts."""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import ValidationError as PydanticValidationError

from contexttrading.models.base import AnalysisObject, VersionedModel


class DummyPayload(VersionedModel):
    SCHEMA_VERSION: ClassVar[str] = "2.1.0"

    value: int


class SwingLike(AnalysisObject):
    ID_PREFIX: ClassVar[str] = "swing"

    price: float
    index: int


class TestVersionedModel:
    def test_default_version_injected(self) -> None:
        payload = DummyPayload(value=1)
        assert payload.schema_version == "2.1.0"

    def test_explicit_matching_version_accepted(self) -> None:
        payload = DummyPayload(value=1, schema_version="2.1.0")
        assert payload.schema_version == "2.1.0"

    def test_mismatched_version_rejected(self) -> None:
        with pytest.raises(PydanticValidationError, match="schema_version mismatch"):
            DummyPayload(value=1, schema_version="1.0.0")

    def test_malformed_version_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            DummyPayload(value=1, schema_version="two.point.zero")

    def test_extra_fields_forbidden(self) -> None:
        with pytest.raises(PydanticValidationError):
            DummyPayload(value=1, surprise=True)

    def test_canonical_dict_json_mode(self) -> None:
        assert DummyPayload(value=5).canonical_dict() == {"schema_version": "2.1.0", "value": 5}


class TestAnalysisObject:
    def test_id_generated_deterministically(self) -> None:
        a = SwingLike(price=101.5, index=3)
        b = SwingLike(price=101.5, index=3)
        assert a.id and a.id == b.id
        assert a.id.startswith("swing_")

    def test_id_changes_with_content(self) -> None:
        a = SwingLike(price=101.5, index=3)
        b = SwingLike(price=102.0, index=3)
        assert a.id != b.id

    def test_label_excluded_from_identity(self) -> None:
        a = SwingLike(price=101.5, index=3, label="swing high A")
        b = SwingLike(price=101.5, index=3, label="different label")
        assert a.id == b.id

    def test_explicit_id_preserved(self) -> None:
        obj = SwingLike(price=1.0, index=0, id="custom_id")
        assert obj.id == "custom_id"

    def test_defaults(self) -> None:
        obj = SwingLike(price=1.0, index=0)
        assert obj.layer == "default"
        assert obj.priority == 0
        assert obj.label is None
