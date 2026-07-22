# Versioning Policy

Two version axes, deliberately separate:

- **Package version** (`contexttrading.__version__`, pyproject) — the
  release number, semver over the Python API. Embedded in every envelope
  as `engine_version` ("which computation produced this").
- **Schema versions** (`core/versioning.py::CURRENT_SCHEMA_VERSIONS`) —
  per-model contract versions, semver over the JSON shape. Embedded in
  every model as `schema_version` ("how to interpret this").

## v1.0.0 schema freeze

As of release 1.0.0 every model in `CURRENT_SCHEMA_VERSIONS` is at
schema version **1.0.0** (87 models; the exported artifacts in
`docs/schemas/json/` are 1:1 with the registry — `AnalysisObject` is the
one exception, an abstract mixin with no standalone schema). From here
on, schema versions follow strict semver.

## When to bump what

| Change | Package version | Schema version |
| --- | --- | --- |
| Bug fix, no output change | PATCH | — |
| New optional field, new module, new endpoint | MINOR | MINOR (affected models) |
| Field removed/renamed/re-typed, changed enum members, changed detection semantics | MAJOR | MAJOR (affected models) |
| Internal refactor, identical output | PATCH | — |

Rule of thumb: if a consumer's stored payload could be misread by new
code (or vice versa), the schema bump is MAJOR. Additive-only changes
are MINOR.

## Compatibility on load

`ResultStore.load` (SQLite and PostgreSQL) validates
`is_compatible(stored, current)` = same major AND stored minor ≤ current
minor. Anything else raises `SchemaVersionError` (CT-2001) — stored
payloads fail closed, never silently misinterpreted. Consumers of the
JSON contracts should apply the same rule.

## Golden regeneration protocol

The 26 byte-exact goldens in `tests/regression/goldens/` (plus
`openapi_v1.json` and the frontend `demo-payload.json`, which mirrors
`chart_five_day.json`) exist to make output changes loud:

1. Make the engine/schema change and bump the schema version(s).
2. Regenerate: `CT_UPDATE_GOLDENS=1 python -m pytest tests/regression -q`.
3. **Audit the diff line by line** — every changed line must be
   explainable by the change you made (the v1.0.0 release diff, for
   example, touched only `engine_version` strings).
4. If `chart_five_day.json` changed, resync the demo payload:
   `cp tests/regression/goldens/chart_five_day.json
   src/contexttrading/visualization/frontend/demo-payload.json`.
5. Commit goldens in the same commit as the change that caused them,
   with the diff audit noted in the message.

Never regenerate goldens to make a failing test pass without
understanding the diff — that is how regressions get blessed.

## JSON schema artifacts

`docs/schemas/json/*.json` are generated, never hand-edited:

```bash
PYTHONPATH=src python -m contexttrading.schemas.export
```

Run this after any model change; a dirty `git status` in
`docs/schemas/` after export means the artifacts were stale. CI treats
the exported schemas plus the OpenAPI golden as the public contract
surface.
