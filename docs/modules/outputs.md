# models.outputs

The universal module return contract.

- **`AnalysisResult[T]`** — generic envelope: `schema_version` (envelope),
  `engine_version`, `module`, `symbol`, `timeframe`, `generated_from`
  (`DataWindow`: `start`, `end`, `candle_count`), `payload: T`.
  `T` must be a `VersionedModel`.
- Rules:
  - Every engine module returns exactly this envelope — never free text,
    never raw dicts.
  - `generated_from` timestamps come from candle data only (determinism
    contract §1).
  - Consumers must check `schema_version` and `engine_version` before
    interpreting `payload`.

Migration history: v1.0.0 (Phase 2) — initial.
