<!-- prompt-version: 1.0.0 -->
# Task: Performance Review (Weekly/Monthly)

Interpret the provided period statistics. The numbers are inputs; you
explain what they mean and what to do next — you never compute new ones.

## Instructions

- Summary must reference the headline provided statistics (cite `stat:*`
  ids).
- what_worked / what_failed: ground each item in provided stats or trades
  (cite ids). Do not infer strategies that are not represented in the input.
- risk_review: interpret drawdown/risk-related provided stats only; if none
  were provided, state that limitation.
- plan_next_period: concrete, measurable adjustments tied to the evidence.
- Confidence reflects sample size and completeness of the provided stats.

## Context (period statistics + optional trades + evidence index)

{{CONTEXT_JSON}}

## Output

Output ONLY a JSON object conforming to this schema:

{{SCHEMA_JSON}}
