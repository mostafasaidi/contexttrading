# ai (analyst layer)

Institutional Trading Analyst (MP03): explain-only AI that consumes
versioned engine JSON and produces structured, evidence-bound reports.

## Invariants (enforced, not aspirational)

1. **AI NEVER calculates.** No indicators, ratios, RR, or detection. The
   provider only ever sees engine-produced JSON; all numbers in a report
   trace to it.
2. **AI NEVER detects.** Structure/liquidity/zones/sessions are final
   engine outputs.
3. **AI NEVER invents.** Every conclusion cites object ids; ids outside
   the context's `evidence_index` are hard validation errors
   (`CitationError`, CT-5002).
4. **Contradictory evidence is mandatory** (`weaknesses[]`), capital
   preservation comes first, and degraded `data_quality` must lower
   declared confidence.

## Responsibilities

| Module | Responsibility |
|---|---|
| `ai/context.py` | Deterministic context builders (`AnalysisContext`, `JournalContext`) with a complete evidence index and documented truncation. |
| `ai/prompts/` | Versioned prompt assets (`.md` files) + hash-verified registry and deterministic renderer. |
| `ai/providers.py` | `LLMProvider` protocol; deterministic `MockProvider`; httpx-based `OpenAIProvider`/`AnthropicProvider`. |
| `ai/validation.py` | Validation-on-receive: JSON parse, schema check, citation enforcement, uncited-conclusion warnings. |
| `ai/analysts.py` | `InstitutionalAnalyst`: context → prompt → provider → validate → provenance → `AIReportResult` envelope. |
| `models/ai.py` | Versioned report models (`AIAnalysisReport`, `JournalReviewReport`, `PerformanceReviewReport`, ...). |

## Context contract (`build_analysis_context`)

Deterministic Python (no AI). Assembles the complete engine state:

- `structure` (counts + most recent swings/breaks/legs + protected levels),
  `trend` (full `TrendState`), `liquidity` (pools untapped-first, recent
  sweeps, nearest equal levels), `zones_nearby` (FVG/OB/SD within
  `proximity_atr` ATRs of the last close, sorted by distance then
  strength), `premium_discount` (range + OTE + price location), `sessions`
  (recent sessions, pools, Judas events), `mtf` (bias, contexts, conflicts),
  `confluence` (COMPLETE factor breakdown — never truncated).
- `evidence_index`: id → `{kind, digest}` for **every** detected object,
  plus synthetic keys `trend:state`, `mtf:bias`, `range:dealing`,
  `factor:NN:name` (assembly order), and `setup:current` (trade
  evaluation). Never truncated — otherwise citations could not be checked.
- `data_quality`: deterministic flags (`data_gaps:N`,
  `module_not_provided:*`, `atr_unavailable`, `trend_weak_or_undecided`,
  `mtf_unknown_contexts:N`, `insufficient_confirmed_breaks`,
  `stale_untapped_pools:N` — untapped pools formed in the series' first
  half). Level: `poor` if gaps or ≥3 flags, `fair` if any flags, else
  `good`.
- `truncation`: per-category record (shown/total/keep rule). Rules:
  recency for swings/breaks/legs/sweeps/sessions; untapped-first then
  nearest for pools; nearest/strongest for zones. Cap:
  `AIConfig.max_objects_per_category` (zones get 3×).

`build_journal_context(trades)` computes journal statistics in Python
(caller data — the AI still never calculates) and cites them as `stat:*`;
`build_performance_context(stats)` wraps caller-provided statistics as-is.

## Citation enforcement (anti-fabrication)

`parse_and_validate(raw, Model, evidence_index)` runs on EVERY provider
response:

1. strip markdown fences, `json.loads` → `AIResponseError` CT-5001;
2. pydantic schema validation → `AIResponseError` CT-5001 (also catches
   invalid Literal verdicts like `risk="extreme"`);
3. recursively collect every cited id (`evidence_ids`, `factor_ids`,
   `zone_id`, flat `evidence_citations`) → any id missing from the
   evidence index is a hallucination: `CitationError` CT-5002 (HARD);
4. `EvidenceStatement`s with empty `evidence_ids` → WARNINGS (returned and
   recorded in `provenance.validation_warnings`).

The analyst retries exactly ONCE with the failure fed back to the provider
(full error text + regeneration rules); a second failure propagates.

## Providers

`AIConfig`: `provider` (`none|mock|openai|anthropic|local`), `model`,
`api_key_env` (env var NAME holding the key — never the key), `base_url`,
`temperature` (0), `max_tokens`, `max_retries`, `timeout_seconds`,
`proximity_atr`, `max_objects_per_category`. Env layering via `Settings`
(`CT_AI__PROVIDER=...`).

- `MockProvider`: offline, deterministic — output is a pure function of
  the injected context (citations drawn from the context's own evidence
  index, so it always validates). For tests/demos only; it demonstrates
  the contract, not analysis quality.
- `OpenAIProvider`/`AnthropicProvider`: httpx lazily imported (optional
  dependency), JSON-mode/schema-instructed, temperature 0 default,
  retries with exponential backoff, `timeout_seconds`. No network in
  tests.

## Prompt versioning

Prompts are files (`ai/prompts/*.md`) with a
`<!-- prompt-version: X.Y.Z -->` marker. The registry records
`name/version/sha256(content)`; `ReportProvenance` embeds all three plus
provider/model/warnings in every report — any report can be traced to the
exact prompt bytes that produced it. Rendering injects context + schema as
canonical JSON (sorted keys).

## Outputs

`AIReportResult[T]` envelope (schema v1.0.0): `module`
(`ai.market_analysis` / `ai.trade_evaluation` / `ai.journal_review` /
`ai.weekly_review`), `subject`, optional `generated_from` window,
`payload`. All payloads carry the MP03 sections: executive summary,
six-part market narrative, bias + rationale, confluences (factor-id
bound), categorized risk assessment + sizing suggestion, weaknesses,
optional trade evaluation, alternative scenarios, confidence with
justification + factor ids, action items, data-quality declaration, flat
`evidence_citations`, provenance.

## Testing

- `tests/unit/ai/test_context.py` — evidence-index completeness, never-
  truncated index/factors, truncation caps + determinism, proximity rule,
  data-quality flags, journal/performance contexts.
- `test_prompts.py` — hash stability vs file bytes, semver versions,
  deterministic rendering, invariant presence.
- `test_providers.py` — mock determinism, canned outputs pass schema +
  citations, factory, missing-key error before any network.
- `test_validation.py` — parse/schema errors, hallucinated ids (statement,
  flat, factor, zone) → CT-5002, uncited → warnings, fences.
- `test_analysts.py` — all four methods, provenance, retry-once on
  garbage and on hallucination, persistent failure propagates.
- `test_models_ai.py` — round-trips, Literal/bounds constraints.
- `test_ai_property.py` — every id in any validated report resolves in
  the evidence index, across three fixtures; byte-identical reruns.
- Goldens: `ai_context_five_day.json`, `ai_report_five_day.json`.
- `tests/integration/test_phase8_ai.py` — 2000-candle pipeline → context →
  mock analyst → validated report; independent revalidation of raw output.

## Limitations

- Report QUALITY depends entirely on the real provider; the mock only
  proves the plumbing. No prompt tuning has been done against live models.
- httpx is an optional dependency: HTTP providers raise
  `ConfigurationError` if it is missing (install `httpx` to use them).
- `news_risk` can only reflect provided flags — no news feed exists yet.
- Journal statistics are computed only over caller-provided `pnl` fields;
  richer journal schemas (tags, screenshots) are future work.
- The AI envelope is not yet registered in `data.store.PAYLOAD_MODELS`.
