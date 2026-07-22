# Developer Guide

## Environment setup

```bash
git clone https://github.com/contexttrading/contexttrading.git
cd contexttrading
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install                 # optional but recommended
```

Requires Python 3.12+.

## Code style

- **Formatting:** `black` (line length 100).
- **Linting:** `ruff` (pycodestyle, pyflakes, isort, pyupgrade, bugbear, simplify).
- **Typing:** every public function and class is fully annotated;
  `from __future__ import annotations` is allowed. No bare `Any` in public
  signatures without a comment.
- **Docstrings:** Google style, covering Args/Returns/Raises for public API.
- **Design:** SOLID; composition over inheritance; dependency injection for
  config/loggers/clients; small single-responsibility modules — no monolithic
  files; no placeholder code or toy examples in `src/`.

Run everything:

```bash
ruff check .
black --check .
pytest -q
```

## Testing

- `tests/unit/` — fast, isolated, no I/O.
- `tests/integration/` — cross-layer flows; may use temp files.
- `tests/regression/` — golden-file determinism tests (from Phase 3).
- `tests/performance/` — plain-timing tripwires (`-m benchmark`, no
  pytest-benchmark). Ceilings are calibrated to the dev machine (~4-5x
  observed) as regression alarms, NOT SLAs; under CI (`CI` env var) they
  are multiplied by 2.5 (`CT_BENCH_MULTIPLIER` overrides) rather than
  weakened locally. Ratio checks (scaling, interval trade-off) are
  machine-independent.

Conventions:

- One test module per source module: `test_<module>.py`.
- Property-based tests with `hypothesis` for parsers and validators.
- No wall-clock, no randomness, no network in unit tests. Inject clocks,
  seeds, and clients.

## Configuration

Settings are layered: **defaults < config file (YAML/.env) < environment
variables**. Environment variables use the prefix `CT_` with `__` as the
section separator, e.g. `CT_SESSIONS__DEFAULT_TIMEZONE=America/New_York`.
See `contexttrading.core.config`.

## Commit conventions

[Conventional Commits](https://www.conventionalcommits.org/), one coherent
change set per commit:

```text
feat(analysis): add swing detection
fix(models): reject naive candle timestamps
docs: add architecture overview
test(core): cover timeframe parsing edge cases
chore: bump dependencies
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `chore`, `ci`.
Scope (optional) names the package: `core`, `models`, `analysis`, `data`, …

## Schema changes

1. Bump the model's `schema_version` (`core.versioning`).
2. Regenerate exports: `python -m contexttrading.schemas.export`.
3. Note the migration in `docs/modules/<module>.md`.
4. Update regression goldens if engine output changed.

## Determinism checklist for new engine code

- [ ] No `datetime.now()` / `time.time()` in emitted models.
- [ ] No unseeded randomness; seeds are config and recorded in output.
- [ ] All timestamps UTC-aware; session logic uses explicit IANA zones.
- [ ] Output is a `VersionedModel` inside `AnalysisResult[T]`.
- [ ] New golden regression fixture added.
