"""Market structure package: swings, legs, BOS/CHoCH, trend."""

from contexttrading.analysis.structure.legs import alternating_swings, classify_legs
from contexttrading.analysis.structure.structure import (
    StructureScanner,
    analyze_structure,
    sequence_trend,
)
from contexttrading.analysis.structure.swings import detect_swing_sets, detect_swings
from contexttrading.analysis.structure.trend import TrendEngine, analyze_trend

__all__ = [
    "StructureScanner",
    "TrendEngine",
    "alternating_swings",
    "analyze_structure",
    "analyze_trend",
    "classify_legs",
    "detect_swing_sets",
    "detect_swings",
    "sequence_trend",
]
