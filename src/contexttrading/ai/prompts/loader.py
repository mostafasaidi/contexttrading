"""Versioned prompt registry: prompt assets are files, not string literals.

Every prompt ships as a ``.md`` file beside this module with a
``<!-- prompt-version: X.Y.Z -->`` marker on line 1. The registry records
name, version, and the sha256 of the exact bytes — reports carry this
provenance so any AI output can be traced to the precise prompt text that
produced it.

Rendering is deterministic: ``{{CONTEXT_JSON}}`` and ``{{SCHEMA_JSON}}``
placeholders are replaced with canonical JSON (sorted keys, fixed indent).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from contexttrading.core.errors import ConfigurationError

_PROMPTS_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^<!-- prompt-version: (\d+\.\d+\.\d+) -->")

SYSTEM_PROMPT = "system_analyst"
TASK_PROMPTS = ("market_analysis", "trade_evaluation", "journal_review", "weekly_review")


@dataclass(frozen=True)
class PromptTemplate:
    """One immutable prompt asset with provenance."""

    name: str
    version: str
    sha256: str
    content: str

    def render(self, *, context: dict[str, Any], schema: dict[str, Any]) -> str:
        """Deterministically inject context + schema JSON into the template."""
        context_json = json.dumps(context, indent=2, sort_keys=True, ensure_ascii=False)
        schema_json = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False)
        return self.content.replace("{{CONTEXT_JSON}}", context_json).replace(
            "{{SCHEMA_JSON}}", schema_json
        )


def _load(name: str) -> PromptTemplate:
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():  # pragma: no cover - packaging failure
        raise ConfigurationError(f"Prompt asset missing: {path}", context={"prompt": name})
    content = path.read_text(encoding="utf-8")
    first_line = content.split("\n", 1)[0]
    match = _VERSION_RE.match(first_line)
    if match is None:  # pragma: no cover - authoring error
        raise ConfigurationError(
            f"Prompt {name!r} lacks a '<!-- prompt-version: X.Y.Z -->' marker",
            context={"prompt": name},
        )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return PromptTemplate(name=name, version=match.group(1), sha256=digest, content=content)


#: All registered prompts, loaded once at import (files are read-only assets).
PROMPTS: dict[str, PromptTemplate] = {name: _load(name) for name in (SYSTEM_PROMPT, *TASK_PROMPTS)}


def get_prompt(name: str) -> PromptTemplate:
    """Return a registered prompt template.

    Raises:
        ConfigurationError: If the name is not registered.
    """
    try:
        return PROMPTS[name]
    except KeyError as exc:
        raise ConfigurationError(
            f"Unknown prompt {name!r}",
            context={"prompt": name, "registered": sorted(PROMPTS)},
        ) from exc
