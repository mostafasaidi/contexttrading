"""JSON Schema export tooling.

Dumps every public pydantic model's JSON schema to
``docs/schemas/json/<ModelName>-v<major>.json`` so consumers (API clients,
AI prompt builders, other languages) can pin against versioned contracts.

Run with::

    python -m contexttrading.schemas.export [--out DIR]

Generated files are build artifacts — regenerate, never hand-edit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from contexttrading import __version__ as ENGINE_VERSION
from contexttrading.core.versioning import major_of
from contexttrading.models.base import VersionedModel
from contexttrading.models.candle import Candle, GapWindow
from contexttrading.models.fvg import FVG, FVGResult
from contexttrading.models.liquidity import (
    EqualLevel,
    LiquidityPool,
    LiquidityResult,
    LiquiditySweep,
)
from contexttrading.models.outputs import AnalysisResult, DataWindow
from contexttrading.models.range import DealingRange, DealingRangeResult
from contexttrading.models.structure import (
    Leg,
    MarketStructureResult,
    StructureBreak,
    SwingPoint,
    TrendResult,
    TrendState,
)
from contexttrading.models.visualization import VisualStyle

#: Every model whose schema is part of the public contract.
EXPORTED_MODELS: tuple[type[BaseModel], ...] = (
    Candle,
    GapWindow,
    DataWindow,
    AnalysisResult,
    VisualStyle,
    SwingPoint,
    Leg,
    StructureBreak,
    TrendState,
    MarketStructureResult,
    TrendResult,
    EqualLevel,
    LiquidityPool,
    LiquiditySweep,
    LiquidityResult,
    DealingRange,
    DealingRangeResult,
    FVG,
    FVGResult,
)


def default_output_dir() -> Path:
    """Repository ``docs/schemas/json`` directory (derived from this file)."""
    return Path(__file__).resolve().parents[3] / "docs" / "schemas" / "json"


def model_schema_document(model: type[BaseModel]) -> dict[str, Any]:
    """Build the export document for one model."""
    schema_version = getattr(model, "SCHEMA_VERSION", None)
    return {
        "name": model.__name__,
        "schema_version": schema_version,
        "engine_version": ENGINE_VERSION,
        "json_schema": model.model_json_schema(),
    }


def export_schemas(out_dir: str | Path | None = None) -> list[Path]:
    """Write one versioned ``.json`` file per exported model.

    Args:
        out_dir: Target directory (defaults to ``docs/schemas/json``).

    Returns:
        Paths of the written files, in export order.
    """
    target = Path(out_dir) if out_dir is not None else default_output_dir()
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in EXPORTED_MODELS:
        document = model_schema_document(model)
        if issubclass(model, VersionedModel):
            major = major_of(model.SCHEMA_VERSION)
            filename = f"{model.__name__}-v{major}.json"
        else:  # pragma: no cover - all exported models are versioned
            filename = f"{model.__name__}.json"
        path = target / filename
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for ``python -m contexttrading.schemas.export``."""
    parser = argparse.ArgumentParser(description="Export model JSON schemas.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: docs/schemas/json).",
    )
    args = parser.parse_args(argv)
    written = export_schemas(args.out)
    for path in written:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
