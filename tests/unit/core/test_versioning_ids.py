"""Tests for core.versioning and core.ids (determinism-critical)."""

from __future__ import annotations

import pytest

from contexttrading.core.ids import (
    canonical_json,
    content_hash,
    deterministic_id,
    new_run_id,
)
from contexttrading.core.versioning import (
    CURRENT_SCHEMA_VERSIONS,
    is_compatible,
    major_of,
    parse_version,
)
from contexttrading.models.visualization import VisualStyle


class TestVersionParsing:
    def test_parse_valid(self) -> None:
        assert parse_version("1.0.0") == (1, 0, 0)
        assert parse_version("2.10.3") == (2, 10, 3)

    @pytest.mark.parametrize("raw", ["", "1", "1.0", "1.0.0.0", "a.b.c", "1.0.x"])
    def test_parse_invalid(self, raw: str) -> None:
        with pytest.raises(ValueError, match="Invalid schema version"):
            parse_version(raw)

    def test_major_of(self) -> None:
        assert major_of("3.2.1") == 3

    def test_compatibility(self) -> None:
        assert is_compatible("1.0.0", "1.0.0")
        assert is_compatible("1.2.0", "1.5.0")  # same major, producer minor <= consumer
        assert not is_compatible("1.5.0", "1.2.0")  # producer newer in minor
        assert not is_compatible("2.0.0", "1.9.9")  # major mismatch

    def test_registry_is_consistent(self) -> None:
        for name, version in CURRENT_SCHEMA_VERSIONS.items():
            assert parse_version(version)[0] >= 1, name


class TestDeterministicIds:
    def test_stable_for_identical_content(self) -> None:
        content = {"module": "fvg", "index": 3, "prices": [1.1, 2.2]}
        assert deterministic_id(content, prefix="fvg") == deterministic_id(content, prefix="fvg")

    def test_differs_for_different_content(self) -> None:
        a = deterministic_id({"x": 1}, prefix="obj")
        b = deterministic_id({"x": 2}, prefix="obj")
        assert a != b

    def test_prefix_applied(self) -> None:
        assert deterministic_id({"x": 1}, prefix="swing").startswith("swing_")

    def test_key_order_irrelevant(self) -> None:
        a = canonical_json({"b": 1, "a": 2})
        b = canonical_json({"a": 2, "b": 1})
        assert a == b

    def test_canonical_json_tight_separators(self) -> None:
        assert canonical_json({"a": [1, 2]}) == '{"a":[1,2]}'

    def test_pydantic_models_hash_by_content(self) -> None:
        style1 = VisualStyle(color="#FF0000", layer="zones")
        style2 = VisualStyle(color="#ff0000", layer="zones")  # normalized to same hex
        assert content_hash(style1) == content_hash(style2)

    def test_run_ids_unique_and_prefixed(self) -> None:
        ids = {new_run_id() for _ in range(100)}
        assert len(ids) == 100
        assert all(i.startswith("run_") for i in ids)
