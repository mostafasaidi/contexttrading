<!-- prompt-version: 1.0.0 -->
# Task: Trade Evaluation

Evaluate the proposed trade setup (provided in the context under `setup`)
against the complete engine context. You judge quality; you do not design
trades.

## Instructions

- Grade entry, stop-loss, and take-profit quality against PROVIDED levels:
  zones_nearby, liquidity pools, premium/discount location, OTE, protected
  highs/lows, structure breaks. Cite the specific object ids.
- Assess confluence alignment from the confluence section ONLY (scores,
  agreeing/conflicting factors, zones). Do not recompute reward/risk — the
  caller's numbers stand; interpret them in `rr_assessment`.
- Timing: consider session context, recent sweeps/judas events, and MTF
  alignment as provided.
- Invalidation must reference concrete provided objects (e.g. "a confirmed
  CHoCH against the setup direction", citing the relevant swing/break ids
  that would matter).
- Alternative entries may only reference PROVIDED zones/levels (cite ids);
  if none are compelling, return an empty list.
- If confluence does not support the direction, say so plainly and reflect
  it in probability and the overall statement.

## Context (complete engine state + proposed setup + evidence index)

{{CONTEXT_JSON}}

## Output

Output ONLY a JSON object conforming to this schema:

{{SCHEMA_JSON}}
