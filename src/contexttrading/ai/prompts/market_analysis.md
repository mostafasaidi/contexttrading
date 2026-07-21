<!-- prompt-version: 1.0.0 -->
# Task: Market Analysis

Produce a complete institutional market analysis from the provided engine
context.

## Instructions

- Read every section of the context: structure, trend, liquidity,
  zones_nearby, premium_discount, sessions, mtf, confluence, data_quality,
  truncation.
- Base your bias primarily on the confluence engine's scores and factor
  breakdown; explain WHICH factors drive it, citing `factor:NN:name` ids.
- The market narrative must cover all six sections. Where the engine
  provides no evidence for a section, say so instead of improvising.
- Risk levels must reflect provided evidence: liquidity risk from untapped
  pools/sweeps, volatility from ATR presence and expansion/correction
  evidence, session risk from session context, trend risk from trend
  health. Set `news_risk` to "high" ONLY if a provided flag says so;
  otherwise "low" or "medium" with rationale that no news data was provided.
- Weaknesses are mandatory: list the strongest evidence against your bias.
- Confidence must be evidence-based: lean on the confluence score,
  agreement counts, and data quality; justify with factor ids.
- Action items must be concrete and conditional (e.g. "stand aside until
  pool X is swept"), never promises.
- Declare `data_quality` honestly, mirroring or downgrading the context's
  own flags.

## Context (complete engine state + evidence index)

{{CONTEXT_JSON}}

## Output

Output ONLY a JSON object conforming to this schema:

{{SCHEMA_JSON}}
