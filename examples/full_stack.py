"""Full-stack analysis: every engine module over one series.

Run:  PYTHONPATH=src python examples/full_stack.py

Expected output: one summary line per module in canonical MODULE_ORDER
(structure -> mtf), ending with the confluence bias/scores. Deterministic
for the seeded series.
"""

from __future__ import annotations

from _data import regime_series

from contexttrading.analysis.pipeline import MODULE_ORDER, run_full_stack


def main() -> None:
    series = regime_series("trend_up", count=300)
    results = run_full_stack(series)
    print(f"full stack over {len(series.candles)} bars ({series.symbol} {series.timeframe})")
    for module in MODULE_ORDER:
        result = results[module]
        print(f"  {module:<17} {result.summary()['payload_type']}")
    confluence = results["confluence"].payload
    print(
        f"bias: {confluence.bias.value} "
        f"(bull {confluence.bullish_score:.3f} / bear {confluence.bearish_score:.3f})"
    )


if __name__ == "__main__":
    main()
