<!-- prompt-version: 1.0.0 -->
# Task: Journal Review

Review the trader's journal. All statistics in the context were computed
deterministically from the provided trades — interpret them; never
recompute or invent numbers.

## Instructions

- Recurring mistakes and strengths must be grounded in the provided trades
  (cite `trade:*` ids) and/or provided statistics (cite `stat:*` ids).
- Discipline flags (revenge_trading, overtrading, impatience,
  poor_risk_management) may be marked `detected: true` ONLY when the
  provided statistics/trades show the pattern (e.g. clusters of rapid
  sequential losses for revenge trading). Cite the supporting ids. When in
  doubt, `detected: false` with rationale.
- The improvement plan must be concrete, behavioral, and tied to the
  identified patterns — no generic advice.
- Small samples are a data-quality issue: say so and lower confidence.

## Context (journal statistics + trades + evidence index)

{{CONTEXT_JSON}}

## Output

Output ONLY a JSON object conforming to this schema:

{{SCHEMA_JSON}}
