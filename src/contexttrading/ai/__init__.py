"""AI analyst layer (Phase 8, MP03): explain-only, evidence-bound.

The AI NEVER calculates — it consumes versioned engine JSON
(:class:`AnalysisContext` / :class:`JournalContext`) and produces
structured, citation-validated reports. See ``docs/modules/ai-layer.md``.
"""

from contexttrading.ai.analysts import InstitutionalAnalyst
from contexttrading.ai.context import (
    AnalysisContext,
    EvidenceEntry,
    JournalContext,
    build_analysis_context,
    build_journal_context,
    build_performance_context,
)
from contexttrading.ai.prompts.loader import PROMPTS, get_prompt
from contexttrading.ai.providers import (
    AnthropicProvider,
    LLMProvider,
    MockProvider,
    OpenAIProvider,
    provider_from_config,
)
from contexttrading.ai.validation import parse_and_validate

__all__ = [
    "PROMPTS",
    "AnalysisContext",
    "AnthropicProvider",
    "EvidenceEntry",
    "InstitutionalAnalyst",
    "JournalContext",
    "LLMProvider",
    "MockProvider",
    "OpenAIProvider",
    "build_analysis_context",
    "build_journal_context",
    "build_performance_context",
    "get_prompt",
    "parse_and_validate",
    "provider_from_config",
]
