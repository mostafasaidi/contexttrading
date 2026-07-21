"""LLM provider abstraction for the analyst pipeline.

``LLMProvider`` is the dependency-injected seam: the analyst pipeline only
knows ``complete(messages, response_schema) -> raw_text``.

- :class:`MockProvider` — deterministic, offline, for tests and demos. Its
  output is a *pure function of the input context* (no RNG needed): a
  schema-valid canned report whose citations are drawn from the context's
  own evidence index, so it always passes citation validation.
- :class:`OpenAIProvider` / :class:`AnthropicProvider` — httpx-based.
  httpx is imported lazily (it is an optional runtime dependency); the API
  key comes from the environment variable named by ``AIConfig.api_key_env``
  — never from config files or code. Tests never touch the network.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol, runtime_checkable

from contexttrading.core.config import AIConfig
from contexttrading.core.errors import AIProviderError, ConfigurationError


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal completion contract used by the analyst pipeline."""

    name: str
    model: str

    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        """Return the raw assistant text (expected: JSON per response_schema)."""
        ...


# --------------------------------------------------------------------------
# Mock provider
# --------------------------------------------------------------------------


def _extract_context(messages: list[dict[str, str]]) -> dict[str, Any]:
    """Recover the injected context JSON from a rendered prompt message."""
    decoder = json.JSONDecoder()
    for message in reversed(messages):
        content = message.get("content", "")
        for i, char in enumerate(content):
            if char != "{":
                continue
            try:
                parsed, _end = decoder.raw_decode(content[i:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "evidence_index" in parsed:
                return parsed
    raise AIProviderError(
        "MockProvider could not locate a context JSON in the messages",
        context={"hint": "analyst pipeline injects context via prompt rendering"},
    )


def _first_ids(context: dict[str, Any], kinds: tuple[str, ...], limit: int) -> list[str]:
    """Deterministically pick evidence ids of the given kinds (sorted)."""
    index = context["evidence_index"]
    picked = sorted(entry_id for entry_id, entry in index.items() if entry.get("kind") in kinds)
    return picked[:limit]


def _statement(text: str, ids: list[str]) -> dict[str, Any]:
    return {"text": text, "evidence_ids": ids}


def _canned_analysis(context: dict[str, Any]) -> dict[str, Any]:
    index = context["evidence_index"]
    confluence = context.get("confluence") or {}
    bias = confluence.get("bias", "ranging")
    score = confluence.get("score", 0.0)
    factor_ids = [f["id"] for f in confluence.get("factors", [])[:3]]
    pool_ids = _first_ids(context, ("pool", "session_pool"), 2)
    zone_ids = _first_ids(context, ("fvg", "orderblock", "supplydemand"), 2)
    swing_ids = _first_ids(context, ("swing",), 2)
    break_ids = _first_ids(context, ("break",), 2)
    quality = context.get("data_quality", {"level": "good", "flags": []})

    def dq() -> dict[str, Any]:
        return {"level": quality["level"], "limitations": list(quality.get("flags", []))}

    narrative_ids = (factor_ids + swing_ids)[:3]
    report: dict[str, Any] = {
        "executive_summary": _statement(
            f"Confluence engine reports a {bias} bias at score {score}; "
            f"interpretation follows the provided factor breakdown.",
            factor_ids,
        ),
        "market_narrative": {
            "control": _statement(
                f"Control read follows the {bias} confluence bias.", narrative_ids
            ),
            "liquidity_objectives": _statement(
                "Nearest resting liquidity per provided pools.", pool_ids
            ),
            "trend_health": _statement(
                "Trend health per the provided trend state.",
                ["trend:state"] if "trend:state" in index else swing_ids,
            ),
            "momentum": _statement("Momentum per provided legs and breaks.", break_ids),
            "accumulation_distribution": _statement(
                "Accumulation/distribution read from provided session stats.",
                _first_ids(context, ("session",), 1),
            ),
            "expansion_correction": _statement(
                "Expansion/correction per provided trend state.", swing_ids
            ),
        },
        "bias": bias if bias in ("bullish", "bearish") else "ranging",
        "bias_rationale": _statement(
            f"Bias mirrors the confluence engine ({bias}, score {score}).", factor_ids
        ),
        "confluences": (
            [
                {
                    "description": _statement(
                        "Highest-scoring provided confluence zone.", factor_ids[:1]
                    ),
                    "direction": bias if bias in ("bullish", "bearish") else "ranging",
                    "factor_ids": factor_ids[:2],
                    "zone_id": (
                        context.get("confluence", {}).get("zones", [{}])[0].get("id")
                        if confluence.get("zones")
                        else None
                    ),
                }
            ]
            if factor_ids
            else []
        ),
        "risk_assessment": {
            "market_risk": "medium",
            "liquidity_risk": "medium" if pool_ids else "low",
            "volatility_risk": "medium",
            "session_risk": "low",
            "news_risk": "low",
            "trend_risk": "medium",
            "position_size_suggestion": "reduced" if quality["level"] != "good" else "normal",
            "risk_rationale": _statement(
                "Risk levels derived from provided pools, trend state, and data quality.",
                pool_ids + swing_ids,
            ),
            "capital_preservation_notes": _statement(
                "No news data provided; size conservatively when flags are present.",
                factor_ids[:1],
            ),
        },
        "weaknesses": (
            [
                _statement(
                    "Conflicting provided factors argue against the bias.",
                    _first_ids(context, ("factor",), 1),
                )
            ]
            if _first_ids(context, ("factor",), 1)
            else []
        ),
        "alternative_scenarios": (
            [
                {
                    "scenario": _statement(
                        "Price sweeps the nearest provided pool before resolving.", pool_ids
                    ),
                    "probability": "medium",
                    "trigger": _statement("Sweep of the cited pool.", pool_ids),
                }
            ]
            if pool_ids
            else []
        ),
        "confidence_score": {
            "score": score,
            "justification": _statement(
                "Confidence echoes the engine confluence score and data quality.",
                factor_ids,
            ),
            "factor_ids": factor_ids,
        },
        "action_items": [
            _statement("Stand aside unless provided confluence strengthens.", factor_ids[:1])
        ],
        "data_quality": dq(),
    }
    setup = context.get("setup")
    if setup is not None:
        report["trade_evaluation"] = {
            "entry_quality": "fair",
            "stop_loss_quality": "fair",
            "take_profit_quality": "fair",
            "rr_assessment": _statement(
                "Reward/risk interpreted from the caller-provided setup values only.",
                ["setup:current"],
            ),
            "confluence_alignment": _statement(
                f"Setup direction vs provided confluence bias ({bias}).", factor_ids
            ),
            "timing": _statement(
                "Timing per provided session context.", _first_ids(context, ("session",), 1)
            ),
            "probability": "medium",
            "invalidation": _statement(
                "A provided counter-direction break invalidates the setup.", break_ids
            ),
            "alternative_entries": (
                [_statement("Nearest provided zone as alternative entry.", zone_ids)]
                if zone_ids
                else []
            ),
            "overall": _statement(
                "Setup judged strictly against provided levels.", ["setup:current"]
            ),
        }
    cited: set[str] = set()

    def _collect(obj: Any) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in ("evidence_ids", "factor_ids") and isinstance(value, list):
                    cited.update(v for v in value if isinstance(v, str))
                elif key == "zone_id" and isinstance(value, str):
                    cited.add(value)
                else:
                    _collect(value)
        elif isinstance(obj, list):
            for item in obj:
                _collect(item)

    _collect(report)
    report["evidence_citations"] = sorted(cited)
    return report


def _canned_journal(context: dict[str, Any]) -> dict[str, Any]:
    stats = context.get("statistics", {})
    stat_ids = sorted(f"stat:{key}" for key in stats)[:3]
    trade_ids = _first_ids(context, ("journal_trade",), 2)
    quality = context.get("data_quality", {"level": "good", "flags": []})
    win_rate = stats.get("win_rate")
    report: dict[str, Any] = {
        "recurring_mistakes": (
            [_statement("Losses cluster in the provided trades.", trade_ids)] if trade_ids else []
        ),
        "strengths": (
            [_statement(f"Provided win rate is {win_rate}.", ["stat:win_rate"])]
            if "stat:win_rate" in context["evidence_index"]
            else []
        ),
        "discipline_flags": [
            {
                "kind": kind,
                "detected": False,
                "rationale": _statement("No provided statistic supports this flag.", stat_ids[:1]),
            }
            for kind in ("revenge_trading", "overtrading", "impatience", "poor_risk_management")
        ],
        "improvement_plan": (
            [_statement("Review the cited losing trades before the next session.", trade_ids)]
            if trade_ids
            else []
        ),
        "confidence_score": {
            "score": 0.5 if quality["level"] == "good" else 0.3,
            "justification": _statement(
                "Confidence reflects the provided sample size flags.", stat_ids[:1]
            ),
            "factor_ids": [],
        },
        "data_quality": {"level": quality["level"], "limitations": list(quality.get("flags", []))},
    }
    cited = set(stat_ids) | set(trade_ids)
    report["evidence_citations"] = sorted(cited)
    return report


def _canned_performance(context: dict[str, Any]) -> dict[str, Any]:
    stats = context.get("statistics", {})
    stat_ids = sorted(f"stat:{key}" for key in stats)[:4]
    quality = context.get("data_quality", {"level": "good", "flags": []})
    return {
        "period": context.get("period", ""),
        "summary": _statement(
            f"Period {context.get('period', '')}: {len(stats)} provided statistics.",
            stat_ids[:2],
        ),
        "what_worked": (
            [_statement("Positive provided statistics held up.", stat_ids[:1])] if stat_ids else []
        ),
        "what_failed": (
            [_statement("Weak provided statistics need attention.", stat_ids[1:2])]
            if len(stat_ids) > 1
            else []
        ),
        "risk_review": _statement("Risk review limited to provided statistics.", stat_ids[:1]),
        "plan_next_period": (
            [_statement("Keep doing what the cited stats support.", stat_ids[:1])]
            if stat_ids
            else []
        ),
        "confidence_score": {
            "score": 0.5 if quality["level"] == "good" else 0.3,
            "justification": _statement("Confidence reflects provided sample size.", stat_ids[:1]),
            "factor_ids": [],
        },
        "data_quality": {"level": quality["level"], "limitations": list(quality.get("flags", []))},
        "evidence_citations": sorted(stat_ids),
    }


_CANNED = {
    "AIAnalysisReport": _canned_analysis,
    "JournalReviewReport": _canned_journal,
    "PerformanceReviewReport": _canned_performance,
}


class MockProvider:
    """Deterministic offline provider; output is a pure function of input.

    Canned responses are derived from the injected context: every citation
    id comes from the context's own evidence index, so mock reports always
    pass citation validation. Used by tests and demos only — it demonstrates
    the contract, not analysis quality.
    """

    name = "mock"

    def __init__(self, model: str = "mock-analyst-v1") -> None:
        self.model = model
        self.calls: int = 0  # observable for retry tests

    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        self.calls += 1
        context = _extract_context(messages)
        builder = _CANNED.get(response_schema.get("title", ""))
        if builder is None:
            raise AIProviderError(
                "MockProvider has no canned response for this schema",
                context={"title": response_schema.get("title")},
            )
        return json.dumps(builder(context), sort_keys=True)


# --------------------------------------------------------------------------
# HTTP providers (lazy httpx; no network in tests)
# --------------------------------------------------------------------------


def _load_httpx():
    try:
        import httpx
    except ModuleNotFoundError as exc:  # pragma: no cover - env dependent
        raise ConfigurationError(
            "httpx is required for HTTP AI providers (pip install httpx)",
            context={"package": "httpx"},
        ) from exc
    return httpx


def _api_key(config: AIConfig) -> str:
    key = os.environ.get(config.api_key_env, "")
    if not key:
        raise ConfigurationError(
            f"API key env var {config.api_key_env!r} is not set",
            context={"env_var": config.api_key_env},
        )
    return key


class _HTTPProviderBase:
    """Shared retry/timeout/error handling for HTTP chat providers."""

    name = "base"

    def __init__(self, config: AIConfig) -> None:
        self._config = config
        self.model = config.model

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        httpx = _load_httpx()
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = httpx.post(
                    url, headers=headers, json=body, timeout=self._config.timeout_seconds
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:  # httpx errors + json errors
                last_error = exc
                if attempt < self._config.max_retries:
                    time.sleep(min(2.0**attempt, 8.0))
        raise AIProviderError(
            f"{self.name} provider call failed after {self._config.max_retries + 1} attempts",
            context={"provider": self.name, "error": str(last_error)},
        ) from last_error

    @staticmethod
    def _text(messages: list[dict[str, str]]) -> tuple[str, str]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        user = "\n\n".join(m["content"] for m in messages if m["role"] != "system")
        return system, user


class OpenAIProvider(_HTTPProviderBase):
    """OpenAI chat-completions provider (JSON mode)."""

    name = "openai"
    _URL = "https://api.openai.com/v1/chat/completions"

    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        config = self._config
        schema_note = {
            "role": "system",
            "content": "Respond with ONLY JSON conforming to this schema:\n"
            + json.dumps(response_schema, sort_keys=True),
        }
        body = {
            "model": self.model,
            "messages": [schema_note, *messages],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = self._post(
            config.base_url or self._URL,
            {"Authorization": f"Bearer {_api_key(config)}"},
            body,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError(
                "OpenAI response missing choices[0].message.content",
                context={"provider": self.name},
            ) from exc


class AnthropicProvider(_HTTPProviderBase):
    """Anthropic messages provider (schema instructed, temperature 0 default)."""

    name = "anthropic"
    _URL = "https://api.anthropic.com/v1/messages"
    _VERSION = "2023-06-01"

    def complete(self, messages: list[dict[str, str]], response_schema: dict[str, Any]) -> str:
        config = self._config
        system, user = self._text(messages)
        system += "\n\nRespond with ONLY JSON conforming to this schema:\n" + json.dumps(
            response_schema, sort_keys=True
        )
        body = {
            "model": self.model,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
        data = self._post(
            config.base_url or self._URL,
            {
                "x-api-key": _api_key(config),
                "anthropic-version": self._VERSION,
                "content-type": "application/json",
            },
            body,
        )
        try:
            return "".join(
                block.get("text", "") for block in data["content"] if block.get("type") == "text"
            )
        except (KeyError, TypeError) as exc:
            raise AIProviderError(
                "Anthropic response missing content blocks",
                context={"provider": self.name},
            ) from exc


def provider_from_config(config: AIConfig) -> LLMProvider:
    """Factory: build the configured provider (mock/none need no secrets)."""
    if config.provider == "mock":
        return MockProvider(model=config.model or "mock-analyst-v1")
    if config.provider == "openai":
        return OpenAIProvider(config)
    if config.provider == "anthropic":
        return AnthropicProvider(config)
    raise ConfigurationError(
        f"AI provider {config.provider!r} is not configured for use",
        context={"provider": config.provider},
    )
