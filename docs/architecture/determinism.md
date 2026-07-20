# Determinism Contract

Every ContextTrading module obeys this contract. It is the property that
makes the engine testable, backtestable, and safe to explain with AI.

## 1. Identical input ⇒ identical output

For a fixed `(input data, module config, schema_version, engine_version)`,
the serialized `AnalysisResult` is **byte-identical** across runs, processes,
and machines.

Consequences:

- **No wall-clock in outputs.** Timestamps in results derive from candle
  data (`generated_from` window, event timestamps). `datetime.now()` /
  `time.time()` are forbidden in engine and model code. Run bookkeeping
  (e.g. log lines) may use wall-clock, but never inside emitted models.
- **No unseeded randomness.** Any stochastic element (none in the engine
  today; possible in backtesting scenarios) requires an explicit injected
  seed recorded in the output.
- **No dict-order or set-order leakage.** Models serialize with stable field
  order (Pydantic declaration order) and collections are sorted where
  ordering is semantically irrelevant.
- **No environment dependence.** Locale, timezone of the host, and float
  printing must not affect output. All timestamps are UTC-aware.

## 2. Deterministic identity

Analysis objects carry **content-hash IDs** (`contexttrading.core.ids`):
the ID is derived from the object's canonical content, so identical
detections — same swing, same FVG, across re-runs — get identical IDs.
Run-scoped entities (analysis runs, API requests) use UUIDs instead; those
IDs are metadata, never part of the analytical payload equality.

## 3. Floating-point policy

- Prices and sizes are `float` in models but compared with tolerance in
  engine logic: `abs(a - b) <= max(rel_tol * max(|a|, |b|), abs_tol)` with
  `rel_tol = 1e-9`, `abs_tol = 1e-12` (constants in `core.constants`).
- Canonical serialization rounds nothing; equality for regression tests is
  exact on serialized JSON. Any tolerance-based decision happens *inside*
  the engine before a value is emitted.
- Decimal migration is deferred; if introduced it will be a schema-version
  bump.

## 4. Schema versioning

- Every emitted model inherits `VersionedModel` and carries
  `schema_version` (see `core.versioning`).
- Any breaking change to a model's fields **must** bump that model's
  schema version and add a migration note in `docs/modules/<module>.md`.
- `AnalysisResult` records both `schema_version` (envelope) and
  `engine_version` (`contexttrading.__version__`); consumers must check both.
- Exported JSON schemas live in `docs/schemas/json/<name>-v<major>.json`,
  regenerated with `python -m contexttrading.schemas.export`.

## 5. Timezone policy

- All `Candle.timestamp` values are timezone-aware UTC at model boundary.
  Naive datetimes are rejected at validation.
- Session logic converts UTC → configured session timezone explicitly
  (IANA names, e.g. `America/New_York`) — never via host-local time.

## 6. Regression enforcement

`tests/regression/` stores golden outputs per fixture dataset. A PR that
intentionally changes engine output must regenerate goldens *and* bump the
relevant schema or engine version; CI fails otherwise.
