"""Chart payload example: full stack -> renderer-ready JSON file.

Run:  PYTHONPATH=src python examples/chart_payload.py

Writes ``examples/output/chart_payload.json`` — the same contract the
reference frontend consumes (serve ``src/contexttrading/visualization/
frontend/`` via ``python -m http.server`` and point it at this file; see
docs/modules/visualization.md). Prints layer count and primitive total.
"""

from __future__ import annotations

from pathlib import Path

from _data import regime_series

from contexttrading.analysis.pipeline import run_full_stack
from contexttrading.visualization import build_chart_payload

OUT_DIR = Path(__file__).parent / "output"


def main(out_dir: Path = OUT_DIR) -> Path:
    series = regime_series("trend_up", count=300)
    results = run_full_stack(series)
    chart = build_chart_payload(series, results)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "chart_payload.json"
    path.write_text(chart.model_dump_json(indent=2), encoding="utf-8")
    payload = chart.payload
    primitives = sum(len(layer.primitives) for layer in payload.layers)
    print(f"chart: {len(payload.layers)} layers, {primitives} primitives")
    print(f"wrote {path}")
    return path


if __name__ == "__main__":
    main()
