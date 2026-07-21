"""Fair value gap engine: detection, inversion, mitigation, scoring."""

from contexttrading.analysis.fvg.detection import (
    RawFVG,
    assign_stack_groups,
    detect_raw_fvgs,
    find_parent,
    link_displacement,
)
from contexttrading.analysis.fvg.fvg import FVGEngine, analyze_fvg
from contexttrading.analysis.fvg.inversion import (
    closes_through_far_side,
    trades_through_far_side,
)
from contexttrading.analysis.fvg.mitigation import (
    LifecycleState,
    strength_score,
    update_state,
)

__all__ = [
    "FVGEngine",
    "LifecycleState",
    "RawFVG",
    "analyze_fvg",
    "assign_stack_groups",
    "closes_through_far_side",
    "detect_raw_fvgs",
    "find_parent",
    "link_displacement",
    "strength_score",
    "trades_through_far_side",
    "update_state",
]
