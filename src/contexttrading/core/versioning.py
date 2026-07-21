"""Schema version constants and helpers.

Every emitted model inherits :class:`~contexttrading.models.base.VersionedModel`
and carries a ``schema_version`` string. Breaking field changes require a
version bump here plus a migration note in ``docs/modules/<module>.md``.
"""

from __future__ import annotations

# Envelope and Phase-2 model schema versions.
SCHEMA_VERSION_ENVELOPE: str = "1.0.0"
SCHEMA_VERSION_CANDLE: str = "1.0.0"
SCHEMA_VERSION_GAP_WINDOW: str = "1.0.0"
SCHEMA_VERSION_VISUAL_STYLE: str = "1.0.0"
SCHEMA_VERSION_ANALYSIS_OBJECT: str = "1.0.0"

# Phase-3 model schema versions.
SCHEMA_VERSION_STRUCTURE: str = "1.0.0"
SCHEMA_VERSION_LIQUIDITY: str = "1.0.0"
SCHEMA_VERSION_RANGE: str = "1.0.0"

# Phase-4 model schema versions.
SCHEMA_VERSION_FVG: str = "1.0.0"

# Phase-5 model schema versions.
SCHEMA_VERSION_ORDERBLOCK: str = "1.0.0"
SCHEMA_VERSION_SUPPLYDEMAND: str = "1.0.0"

# Phase-6 model schema versions.
SCHEMA_VERSION_SESSION: str = "1.0.0"
SCHEMA_VERSION_MTF: str = "1.0.0"

#: Registry of all current schema versions, keyed by logical model name.
CURRENT_SCHEMA_VERSIONS: dict[str, str] = {
    "AnalysisResult": SCHEMA_VERSION_ENVELOPE,
    "DataWindow": SCHEMA_VERSION_ENVELOPE,
    "Candle": SCHEMA_VERSION_CANDLE,
    "GapWindow": SCHEMA_VERSION_GAP_WINDOW,
    "VisualStyle": SCHEMA_VERSION_VISUAL_STYLE,
    "AnalysisObject": SCHEMA_VERSION_ANALYSIS_OBJECT,
    "SwingPoint": SCHEMA_VERSION_STRUCTURE,
    "Leg": SCHEMA_VERSION_STRUCTURE,
    "StructureBreak": SCHEMA_VERSION_STRUCTURE,
    "TrendState": SCHEMA_VERSION_STRUCTURE,
    "MarketStructureResult": SCHEMA_VERSION_STRUCTURE,
    "TrendResult": SCHEMA_VERSION_STRUCTURE,
    "EqualLevel": SCHEMA_VERSION_LIQUIDITY,
    "LiquidityPool": SCHEMA_VERSION_LIQUIDITY,
    "LiquiditySweep": SCHEMA_VERSION_LIQUIDITY,
    "LiquidityResult": SCHEMA_VERSION_LIQUIDITY,
    "DealingRange": SCHEMA_VERSION_RANGE,
    "DealingRangeResult": SCHEMA_VERSION_RANGE,
    "FVG": SCHEMA_VERSION_FVG,
    "FVGResult": SCHEMA_VERSION_FVG,
    "OrderBlock": SCHEMA_VERSION_ORDERBLOCK,
    "BreakerBlock": SCHEMA_VERSION_ORDERBLOCK,
    "MitigationBlock": SCHEMA_VERSION_ORDERBLOCK,
    "OrderBlockResult": SCHEMA_VERSION_ORDERBLOCK,
    "SupplyDemandZone": SCHEMA_VERSION_SUPPLYDEMAND,
    "SupplyDemandResult": SCHEMA_VERSION_SUPPLYDEMAND,
    "SessionStats": SCHEMA_VERSION_SESSION,
    "SessionSweep": SCHEMA_VERSION_SESSION,
    "SessionResult": SCHEMA_VERSION_SESSION,
    "TimeframeContext": SCHEMA_VERSION_MTF,
    "MTFBias": SCHEMA_VERSION_MTF,
    "MTFResult": SCHEMA_VERSION_MTF,
}


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse a ``"major.minor.patch"`` version string.

    Args:
        version: Semantic version string.

    Returns:
        ``(major, minor, patch)`` tuple.

    Raises:
        ValueError: If the string is not a three-part numeric version.
    """
    parts = version.strip().split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"Invalid schema version: {version!r} (expected 'major.minor.patch')")
    return int(parts[0]), int(parts[1]), int(parts[2])


def major_of(version: str) -> int:
    """Return the major component of a schema version."""
    return parse_version(version)[0]


def is_compatible(produced: str, consumed: str) -> bool:
    """Compatibility rule: same major version and producer not newer in minor.

    Args:
        produced: Schema version of the artifact being read.
        consumed: Schema version the consumer was built against.

    Returns:
        True when the consumer may safely interpret the artifact.
    """
    p_major, p_minor, _ = parse_version(produced)
    c_major, c_minor, _ = parse_version(consumed)
    return p_major == c_major and p_minor <= c_minor
