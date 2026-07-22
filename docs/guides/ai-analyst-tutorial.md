# AI analyst tutorial: evidence-bound reports

The AI layer has one law: **Python calculates, AI explains.** The model
never sees raw candles, never computes a number, and may only cite
evidence IDs that actually exist in the engine context. This tutorial
runs a report with the zero-cost mock provider, then shows how to point
at a real provider.

## 1. A report with no API key (mock provider)

```bash
cd examples
PYTHONPATH="../src;.." python ai_analysis_mock.py
```

Expected output:

```
ai report: EXAMPLE/15m
bias: bullish (confidence 0.36)
summary: Confluence engine reports a bullish bias at score 0.35...
confluences cited: 1
weaknesses (mandatory): 1
action items: 1
```

The mock provider's output is a pure function of the engine context —
perfect for development, tests, and understanding the contract.

## 2. What actually happened

```python
from contexttrading.ai.analysts import InstitutionalAnalyst
from contexttrading.ai.providers import MockProvider
from contexttrading.analysis.pipeline import run_full_stack

results = run_full_stack(series)
analyst = InstitutionalAnalyst(MockProvider(), AIConfig(provider="mock"))
envelope = analyst.analyze_market(series, results)   # AIReportResult[AIAnalysisReport]
report = envelope.payload
```

The pipeline is:

1. **Context builder** compresses the engine envelopes into a bounded
   `AnalysisContext` — swings, breaks, zones, confluence factors, MTF
   bias — each with a citable evidence ID (engine object IDs plus
   synthetic keys like `trend:state`, `mtf:bias`, `factor:03:fvg`).
   Display sections may be truncated; the `evidence_index` never is.
2. **Prompt** (versioned markdown in `ai/prompts/`, hash-recorded in the
   report's `ReportProvenance`) instructs the model to produce the
   structured report schema.
3. **Validation** enforces the contract: any hallucinated ID anywhere
   (evidence_ids, factor_ids, zone_id, flat citations) is a hard
   `CitationError` (CT-5002); parse/schema failure is `AIResponseError`
   (CT-5001). Exactly one retry with error feedback, then the error
   propagates. Empty evidence on a statement downgrades to a warning in
   `provenance.validation_warnings`.

## 3. Reading the report

```python
envelope.subject            # "EXAMPLE/15m" (or "journal:2024-W03") — on the envelope
report.executive_summary    # EvidenceStatement — text + evidence_ids
report.bias                 # TrendDirection, with bias_rationale alongside
report.confluences          # each with evidence_ids you can verify
report.weaknesses           # MANDATORY section — the model must argue against itself
report.confidence_score     # ConfidenceScore (0..1 float + rationale)
report.action_items         # concrete next steps
report.provenance           # prompt name/version/hash, model, validation warnings
```

Verify a citation by checking the ID exists in the context's evidence
index — the validator already did, but the IDs are stable and meaningful
(they match engine object IDs you can find in the analysis envelopes).

## 4. Real providers

```bash
pip install "contexttrading[ai]"        # adds httpx (lazy-imported)

export OPENAI_API_KEY=sk-...            # the env var AIConfig.api_key_env names
export CT_AI__PROVIDER=openai           # or anthropic / mock / none
```

```python
from contexttrading.ai.providers import provider_from_config
from contexttrading.core.config import AIConfig

config = AIConfig(provider="openai")    # model, timeout, max_tokens configurable
analyst = InstitutionalAnalyst(provider_from_config(config), config)
```

Provider keys are read from the environment only, never logged, never
embedded in reports. A missing httpx raises `ConfigurationError` with an
install hint; a provider failure raises `AIProviderError` (→ 502/504 at
the API layer).

## 5. The other report types

```python
analyst.evaluate_trade(setup, series, results)      # evaluate a proposed setup
analyst.review_journal(trades, period="2024-W03")   # review posted journal trades
analyst.weekly_review(statistics, period="2024-W03", trades=...)  # performance stats
```

Same contract everywhere: structured input → structured, cited,
weakness-inclusive output. The journal/weekly subjects have no candle
window, which is why reports use the `AIReportResult` envelope (subject
string) rather than the engine's `AnalysisResult`.

## 6. Over HTTP

`POST /v1/ai/market-analysis` (and the three siblings) expose the same
pipeline — see the [API tutorial](api-tutorial.md) and
[docs/modules/ai-layer.md](../modules/ai-layer.md) for the full module
contract.
