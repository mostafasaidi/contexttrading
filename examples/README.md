# Examples

Runnable examples land in Phase 11, after the engine modules they
demonstrate exist (no toy examples against stubs). Planned:

- `01_load_candles.py` — CSV → `CandleSeries`, gap handling
- `02_market_structure.py` — swings, BOS/CHoCH on a sample dataset
- `03_zones.py` — FVG + order blocks with visualization styles
- `04_confluence.py` — multi-module confluence scoring
- `05_ai_narrative.py` — explain-only AI layer over engine JSON
- `06_backtest.py` — deterministic event replay

Each example ships with its own small fixture dataset and asserts its
expected (deterministic) output so it doubles as documentation.
