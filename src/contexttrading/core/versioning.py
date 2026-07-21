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

# Phase-7 model schema versions.
SCHEMA_VERSION_CONFLUENCE: str = "1.0.0"

# Phase-7b/8 model schema versions (visualization).
SCHEMA_VERSION_VISUALIZATION: str = "1.0.0"

#: AI layer (Phase 8): analysis context + structured AI reports.
SCHEMA_VERSION_AI: str = "1.0.0"

#: REST API layer: versioned request/response models.
SCHEMA_VERSION_API: str = "1.0.0"

#: Backtesting layer: replay/execution/statistics/optimization outputs.
SCHEMA_VERSION_BACKTEST: str = "1.0.0"

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
    "FactorContribution": SCHEMA_VERSION_CONFLUENCE,
    "ConfluenceZone": SCHEMA_VERSION_CONFLUENCE,
    "ConfluenceResult": SCHEMA_VERSION_CONFLUENCE,
    "PriceLine": SCHEMA_VERSION_VISUALIZATION,
    "Box": SCHEMA_VERSION_VISUALIZATION,
    "Marker": SCHEMA_VERSION_VISUALIZATION,
    "Label": SCHEMA_VERSION_VISUALIZATION,
    "Segment": SCHEMA_VERSION_VISUALIZATION,
    "AreaBand": SCHEMA_VERSION_VISUALIZATION,
    "ChartCandle": SCHEMA_VERSION_VISUALIZATION,
    "VolumeBar": SCHEMA_VERSION_VISUALIZATION,
    "LayerPayload": SCHEMA_VERSION_VISUALIZATION,
    "ChartTheme": SCHEMA_VERSION_VISUALIZATION,
    "ChartPayload": SCHEMA_VERSION_VISUALIZATION,
    "EvidenceEntry": SCHEMA_VERSION_AI,
    "TruncationEntry": SCHEMA_VERSION_AI,
    "DataQualityFlags": SCHEMA_VERSION_AI,
    "AnalysisContext": SCHEMA_VERSION_AI,
    "JournalContext": SCHEMA_VERSION_AI,
    "EvidenceStatement": SCHEMA_VERSION_AI,
    "ReportProvenance": SCHEMA_VERSION_AI,
    "DataQualityDeclaration": SCHEMA_VERSION_AI,
    "MarketNarrative": SCHEMA_VERSION_AI,
    "ConfluenceNote": SCHEMA_VERSION_AI,
    "RiskAssessment": SCHEMA_VERSION_AI,
    "TradeSetup": SCHEMA_VERSION_AI,
    "TradeEvaluation": SCHEMA_VERSION_AI,
    "AlternativeScenario": SCHEMA_VERSION_AI,
    "ConfidenceScore": SCHEMA_VERSION_AI,
    "DisciplineFlag": SCHEMA_VERSION_AI,
    "AIAnalysisReport": SCHEMA_VERSION_AI,
    "JournalReviewReport": SCHEMA_VERSION_AI,
    "PerformanceReviewReport": SCHEMA_VERSION_AI,
    "AIReportResult": SCHEMA_VERSION_AI,
    "CandlesInput": SCHEMA_VERSION_API,
    "AnalysisRequest": SCHEMA_VERSION_API,
    "FullAnalysisResponse": SCHEMA_VERSION_API,
    "ChartRequest": SCHEMA_VERSION_API,
    "ChartResponse": SCHEMA_VERSION_API,
    "BacktestRequest": SCHEMA_VERSION_API,
    "TradeEvaluationRequest": SCHEMA_VERSION_API,
    "JournalReviewRequest": SCHEMA_VERSION_API,
    "WeeklyReviewRequest": SCHEMA_VERSION_API,
    "StoredResultResponse": SCHEMA_VERSION_API,
    "ErrorEnvelope": SCHEMA_VERSION_API,
    "OrderIntent": SCHEMA_VERSION_BACKTEST,
    "TradeRecord": SCHEMA_VERSION_BACKTEST,
    "EquityPoint": SCHEMA_VERSION_BACKTEST,
    "DrawdownInfo": SCHEMA_VERSION_BACKTEST,
    "BacktestStatistics": SCHEMA_VERSION_BACKTEST,
    "BacktestResult": SCHEMA_VERSION_BACKTEST,
    "OptimizationEntry": SCHEMA_VERSION_BACKTEST,
    "OptimizationResult": SCHEMA_VERSION_BACKTEST,
    "WalkForwardFold": SCHEMA_VERSION_BACKTEST,
    "WalkForwardResult": SCHEMA_VERSION_BACKTEST,
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
