"""Validation-on-receive: the anti-fabrication enforcement layer.

Every provider response goes through :func:`parse_and_validate` before it
becomes a report:

1. **JSON parse** — markdown fences stripped; invalid JSON raises
   :class:`AIResponseError` (CT-5001).
2. **Schema validation** — pydantic model validation; failures raise
   :class:`AIResponseError` (CT-5001).
3. **Citation enforcement** — every id the AI cited (statement
   ``evidence_ids``, ``factor_ids``, ``zone_id``, and the flat
   ``evidence_citations`` list) must exist in the context's
   ``evidence_index``. Any unknown id is a hallucination and raises
   :class:`CitationError` (CT-5002) — a HARD error, never a warning.
4. **Uncited conclusions** — :class:`EvidenceStatement` fields with no
   citations produce WARNINGS (returned, recorded in provenance), because
   some legitimate statements (e.g. data-quality declarations) rest on the
   whole context rather than specific objects.

The analyst pipeline retries ONCE with the failure details fed back to the
provider; a second failure propagates the error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from contexttrading.ai.context import EvidenceEntry
from contexttrading.core.errors import AIResponseError, CitationError
from contexttrading.models.ai import (
    ConfidenceScore,
    ConfluenceNote,
    EvidenceStatement,
)
from contexttrading.models.base import VersionedModel

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

#: Model fields (besides EvidenceStatement.evidence_ids) that carry citable ids.
_ID_LIST_FIELDS = ("factor_ids",)
_ID_SCALAR_FIELDS = ("zone_id",)


def _strip_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text).strip()
    return text


def _collect_citations(obj: Any, cited: set[str], uncited: list[str]) -> None:
    """Walk a validated report, collecting cited ids and uncited statements."""
    if isinstance(obj, EvidenceStatement):
        if obj.evidence_ids:
            cited.update(obj.evidence_ids)
        else:
            snippet = obj.text[:60] + ("..." if len(obj.text) > 60 else "")
            uncited.append(f"uncited statement: {snippet!r}")
        return
    if isinstance(obj, (ConfluenceNote, ConfidenceScore)):
        cited.update(obj.factor_ids)
        if isinstance(obj, ConfluenceNote) and obj.zone_id is not None:
            cited.add(obj.zone_id)
    if isinstance(obj, VersionedModel):
        for value in obj.__dict__.values():
            _collect_citations(value, cited, uncited)
    elif isinstance(obj, list):
        for item in obj:
            _collect_citations(item, cited, uncited)
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect_citations(value, cited, uncited)


def parse_and_validate[ReportT: VersionedModel](
    raw: str,
    model: type[ReportT],
    evidence_index: Mapping[str, EvidenceEntry],
) -> tuple[ReportT, list[str]]:
    """Parse + schema-validate + citation-check one provider response.

    Args:
        raw: Raw provider text (expected JSON per the report schema).
        model: Report model class to validate against.
        evidence_index: The producing context's evidence index.

    Returns:
        ``(report, warnings)`` — warnings list uncited conclusions.

    Raises:
        AIResponseError: Invalid JSON or schema mismatch (CT-5001).
        CitationError: One or more cited ids are not in the evidence
            index (CT-5002) — hallucinated evidence.
    """
    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise AIResponseError(
            "Provider output is not valid JSON",
            context={"error": str(exc), "snippet": raw[:200]},
        ) from exc
    try:
        report = model.model_validate(data)
    except ValidationError as exc:
        raise AIResponseError(
            "Provider output does not match the report schema",
            context={"error": str(exc)[:500]},
        ) from exc

    cited: set[str] = set()
    uncited: list[str] = []
    _collect_citations(report, cited, uncited)
    flat = getattr(report, "evidence_citations", None)
    if isinstance(flat, list):
        cited.update(flat)

    unknown = sorted(cid for cid in cited if cid not in evidence_index)
    if unknown:
        raise CitationError(
            "Report cites evidence ids that do not exist in the context",
            context={"hallucinated_ids": unknown, "index_size": len(evidence_index)},
        )
    return report, uncited
