"""Basic single-module analysis over a generated series.

Run:  PYTHONPATH=src python examples/basic_analysis.py

Expected output (deterministic, seed 11): swing/break counts for the
structure module, pool counts for liquidity, FVG count, and a JSON
excerpt of the first detected swing. Counts depend only on the seeded
data — identical on every run.
"""

from __future__ import annotations

import json

from _data import regime_series

from contexttrading.analysis.pipeline import run_module


def main() -> None:
    series = regime_series("trend_up", count=300)
    print(f"series: {series.symbol} {series.timeframe} x {len(series.candles)} bars")

    structure = run_module("structure", series).payload
    print(f"structure: {len(structure.swings)} swings, {len(structure.breaks)} breaks")

    liquidity = run_module("liquidity", series).payload
    print(f"liquidity: {len(liquidity.pools)} pools, {len(liquidity.sweeps)} sweeps")

    fvg = run_module("fvg", series).payload
    print(f"fvg: {fvg.total_count} gaps")

    if structure.swings:
        first = structure.swings[0]
        excerpt = {
            "id": first.id,
            "type": first.swing_type.value,
            "class": first.swing_class.value,
            "price": first.price,
        }
        print("first swing:", json.dumps(excerpt, indent=2))


if __name__ == "__main__":
    main()
