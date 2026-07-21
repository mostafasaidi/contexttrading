"""Property-based tests (hypothesis) for the confluence engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from contexttrading.analysis.confluence import analyze_confluence
from contexttrading.core.constants import TrendDirection
from contexttrading.models.candle import CandleSeries
from tests.fixtures import engine_config

_SETTINGS = settings(
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=None,
)


def _analyze(steps: list[tuple[float, bool, float]]):
    """Run confluence; reject inputs outside the structure engine's domain.

    Degenerate walks (strictly monotonic, zero-wick) can produce swing
    pairs sharing a price or an index, which the structure engine's
    documented ``Leg`` contracts (magnitude > 0, duration >= 1) reject.
    Those inputs test structure-engine edge handling, not confluence
    invariants, so they are excluded here.
    """
    try:
        return analyze_confluence(_to_series(steps), engine_config())
    except ValidationError:
        assume(False)


T0 = datetime(2024, 1, 1, tzinfo=UTC)

# Random-walk steps with a minimum magnitude so consecutive swings can
# never share a price (Leg.magnitude is strictly positive by contract).
_steps = st.lists(
    st.tuples(
        st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        st.booleans(),
        st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
    ),
    min_size=60,
    max_size=120,
)


def _to_series(steps: list[tuple[float, bool, float]]) -> CandleSeries:
    records = []
    price = 100.0
    for i, (step, up_move, wick) in enumerate(steps):
        o = price
        c = price + step if up_move else price - step
        # Per-bar epsilon: no two candle extremes can coincide exactly
        # (zero-magnitude legs violate the structure engine's contracts).
        epsilon = (i + 1) * 1e-9
        records.append(
            {
                "timestamp": (T0 + timedelta(minutes=i)).isoformat(),
                "open": o,
                "high": max(o, c) + wick + epsilon,
                "low": min(o, c) - wick - epsilon,
                "close": c,
                "volume": 100.0,
            }
        )
        price = c
    return CandleSeries.from_records(records, symbol="PROP", timeframe="1m")


@given(steps=_steps)
@_SETTINGS
def test_scores_are_bounded_and_consistent(steps: list[tuple[float, bool, float]]) -> None:
    """Scores lie in [0, 1]; bias always matches the winning side."""
    result = _analyze(steps)
    p = result.payload
    assert 0.0 <= p.bullish_score <= 1.0
    assert 0.0 <= p.bearish_score <= 1.0
    assert p.bullish_score + p.bearish_score <= 1.0 + 1e-9
    assert p.score == max(p.bullish_score, p.bearish_score)
    if p.bullish_score > p.bearish_score:
        assert p.bias is TrendDirection.BULLISH
    elif p.bearish_score > p.bullish_score:
        assert p.bias is TrendDirection.BEARISH
    else:
        assert p.bias is TrendDirection.RANGING


@given(steps=_steps)
@_SETTINGS
def test_factor_contributions_are_exact(steps: list[tuple[float, bool, float]]) -> None:
    """contribution == weight * raw, raw in [0, 1]; counts never exceed factors."""
    result = _analyze(steps)
    p = result.payload
    for f in p.factors:
        assert 0.0 <= f.raw <= 1.0
        assert f.weight >= 0
        assert abs(f.contribution - f.weight * f.raw) < 1e-9
    assert p.agreeing_factors + p.conflicting_factors <= len(p.factors)


@given(steps=_steps)
@_SETTINGS
def test_zones_are_well_formed(steps: list[tuple[float, bool, float]]) -> None:
    """Zones: score in [0,1], valid geometry, >= 2 members, sorted by score."""
    result = _analyze(steps)
    zones = result.payload.zones
    for zone in zones:
        assert 0.0 <= zone.score <= 1.0
        assert zone.zone_top > zone.zone_bottom
        assert len(zone.member_ids) >= 2
        assert len(zone.member_kinds) >= 2
        assert zone.direction in (TrendDirection.BULLISH, TrendDirection.BEARISH)
    scores = [z.score for z in zones]
    assert scores == sorted(scores, reverse=True)
