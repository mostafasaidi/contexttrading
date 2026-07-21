"""Order block engine: detection, lifecycle, breaker & mitigation blocks."""

from contexttrading.analysis.orderblocks.breakers import build_breakers
from contexttrading.analysis.orderblocks.detection import (
    RawOrderBlock,
    attach_fvg_overlaps,
    detect_raw_order_blocks,
)
from contexttrading.analysis.orderblocks.lifecycle import (
    BlockState,
    resolve_age,
    update_block_state,
)
from contexttrading.analysis.orderblocks.mitigation_blocks import build_mitigation_blocks
from contexttrading.analysis.orderblocks.orderblocks import (
    OrderBlockEngine,
    analyze_orderblocks,
)

__all__ = [
    "BlockState",
    "OrderBlockEngine",
    "RawOrderBlock",
    "analyze_orderblocks",
    "attach_fvg_overlaps",
    "build_breakers",
    "build_mitigation_blocks",
    "detect_raw_order_blocks",
    "resolve_age",
    "update_block_state",
]
