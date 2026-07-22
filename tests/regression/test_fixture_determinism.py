"""Cross-platform determinism guards for fixture generators.

The five-day fixture once produced a different golden byte on Linux CI:
``math.sin`` differs by 1 ulp between glibc and MSVC, and the raw float
flowed into the chart payload's volume series. Fixture data that feeds
byte-exact goldens must be built from IEEE-exact operations only
(+, -, *, /, abs, min, max) or the platform-independent seeded ``random``
module. These tests guard the rule two ways:

1. Source scan — no libm transcendental calls in fixture generators.
2. Purity — calling a generator twice yields identical records.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.fixtures import five_day_15m_records, judas_15m_records, zigzag_records

REPO_ROOT = Path(__file__).resolve().parents[2]

#: libm functions whose results may differ by 1 ulp across platforms.
_TRANSCENDENTAL = re.compile(
    r"\bmath\.(sin|cos|tan|asin|acos|atan|exp|expm1|log|log2|log10|sqrt|pow)\b"
)

#: Generators whose output feeds byte-exact goldens or example smoke tests.
FIXTURE_SOURCES = [
    REPO_ROOT / "tests" / "fixtures.py",
    REPO_ROOT / "tests" / "fvg_fixtures.py",
    REPO_ROOT / "tests" / "ob_fixtures.py",
    REPO_ROOT / "examples" / "_data.py",
]


def test_fixture_sources_use_no_transcendental_math():
    for path in FIXTURE_SOURCES:
        text = path.read_text(encoding="utf-8")
        hits = _TRANSCENDENTAL.findall(text)
        assert not hits, (
            f"{path.relative_to(REPO_ROOT)} uses libm {sorted(set(hits))} — "
            f"results may differ by 1 ulp across platforms; use rational "
            f"arithmetic or seeded random instead"
        )


def test_five_day_records_are_pure():
    assert five_day_15m_records() == five_day_15m_records()


def test_judas_records_are_pure():
    assert judas_15m_records() == judas_15m_records()


def test_zigzag_records_are_pure():
    pivots = [10, 14, 12, 16, 14]
    assert zigzag_records(pivots) == zigzag_records(pivots)


def test_example_regime_records_are_pure():
    import sys

    sys.path.insert(0, str(REPO_ROOT / "examples"))
    try:
        from _data import regime_records

        assert regime_records("volatile", 100) == regime_records("volatile", 100)
    finally:
        sys.path.remove(str(REPO_ROOT / "examples"))
