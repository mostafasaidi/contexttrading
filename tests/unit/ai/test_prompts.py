"""Unit tests for the versioned prompt registry."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from contexttrading.ai.prompts.loader import (
    PROMPTS,
    SYSTEM_PROMPT,
    TASK_PROMPTS,
    get_prompt,
)
from contexttrading.core.errors import ConfigurationError

_PROMPTS_DIR = Path(__file__).parents[3] / "src" / "contexttrading" / "ai" / "prompts"


class TestRegistry:
    def test_all_prompts_registered(self) -> None:
        assert set(PROMPTS) == {SYSTEM_PROMPT, *TASK_PROMPTS}

    def test_hash_matches_file_bytes(self) -> None:
        for name, template in PROMPTS.items():
            content = (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
            assert template.sha256 == hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert template.content == content

    def test_versions_are_semver(self) -> None:
        for template in PROMPTS.values():
            parts = template.version.split(".")
            assert len(parts) == 3
            assert all(p.isdigit() for p in parts)

    def test_unknown_prompt_raises(self) -> None:
        with pytest.raises(ConfigurationError):
            get_prompt("nonexistent")


class TestRendering:
    def test_placeholders_replaced_deterministically(self) -> None:
        template = get_prompt("market_analysis")
        context = {"b": 2, "a": 1}
        schema = {"type": "object"}
        first = template.render(context=context, schema=schema)
        second = template.render(context=context, schema=schema)
        assert first == second
        assert "{{CONTEXT_JSON}}" not in first
        assert "{{SCHEMA_JSON}}" not in first
        assert '"a": 1' in first  # sorted keys
        assert '"type": "object"' in first

    def test_task_prompts_demand_json_and_citations(self) -> None:
        for name in TASK_PROMPTS:
            content = PROMPTS[name].content.lower()
            assert "only" in content and "json" in content
            assert "evidence" in content or "cite" in content

    def test_system_prompt_carries_invariants(self) -> None:
        content = PROMPTS[SYSTEM_PROMPT].content
        assert "NEVER calculate" in content
        assert "NEVER detect" in content
        assert "NEVER invent" in content
