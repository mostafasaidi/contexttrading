# visualization

Render engine: versioned chart payloads consumed by Lightweight Charts (or
any renderer) without recomputing analysis.

## Purpose

Turn `AnalysisResult` envelopes into a single, self-contained
`ChartPayload` — candles, volume, layered render primitives, theme, and
legend — that a frontend draws directly. The module **consumes** the
`VisualStyle` presets attached to detected objects; it never recolors,
re-weights, or re-detects anything. This is the boundary between
"analysis happened" and "pixels happen".

## Responsibilities

| Module | Responsibility |
|---|---|
| `primitives.py` | Chart-agnostic typed primitives (`PriceLine`, `Box`, `Marker`, `Label`, `Segment`, `AreaBand`) as a discriminated union. |
| `mappers.py` | Per-module translation: detected objects → primitives (pure passthrough of `VisualStyle`). |
| `serializer.py` | `build_chart_payload`: candles + volume + canonical layers + theme + legend into one envelope. |
| `frontend/` | No-build reference renderer (Lightweight Charts v4 + overlay canvas) with a committed demo payload. |
| `data/store.py` | SQLite `ResultStore` for versioned envelope persistence (round-trip cache, not a renderer concern, landed in the same phase). |

## Inputs

- A `CandleSeries` (the same window the results were computed from).
- `AnalysisResult` envelopes keyed by module name (`structure`,
  `liquidity`, `premium_discount`, `fvg`, `orderblocks`, `supplydemand`,
  `sessions`, `confluence`, `mtf`; `trend` has no geometry and is
  skipped).
- Optional `VisualizationConfig` (`Settings.visualization`): `theme`
  (`dark` | `light`), `hidden_layers`, `shown_layers`.

## Outputs

`AnalysisResult[ChartPayload]` with `module="chart"` (schemas
`ChartPayload-v1.json`, `LayerPayload-v1.json`, `ChartCandle-v1.json`,
`VolumeBar-v1.json`, `ChartTheme-v1.json`, plus one per primitive, all
version 1.0.0). The payload JSON is the *entire* render contract — a
frontend needs nothing else.

## Primitive inventory → Lightweight Charts mapping

| Primitive | Carries | LW Charts v4 surface |
|---|---|---|
| `PriceLine` | price, style, title | `ISeriesApi.createPriceLine(...)` |
| `Marker` | time, price, position, shape, text | `ISeriesApi.setMarkers(...)` |
| `Box` | time/price rectangle, opacity, fill | overlay canvas (no native rectangle in v4; v5 could use `attachPrimitive`) |
| `AreaBand` | full-height time span, opacity | overlay canvas |
| `Segment` | two time/price points, width | overlay canvas |
| `Label` | anchored text | overlay canvas |

Reference frontend decisions (`visualization/frontend/app.js`):

- Candles and volume use native series; volume sits on a separate price
  scale with `scaleMargins`.
- `Marker.shape="diamond"` falls back to `"square"` (v4 has no diamond).
- Boxes/bands/segments are drawn on an absolutely positioned overlay
  canvas, re-synced on visible-range changes and resizes; structured
  tooltips appear via hit-testing on hover.
- Layer visibility maps to checkboxes built from `payload.layers` +
  `payload.legend`.

## Layer inventory (canonical order = z-order)

23 layers, back-to-front: `sessions.boxes`, `sessions.killzones`,
`range.premium`, `range.discount`, `range.ote`, `range.equilibrium`,
`confluence.zones`, `fvg.zones`, `orderblocks.ob`, `orderblocks.brk`,
`orderblocks.mb`, `supplydemand.supply`, `supplydemand.demand`,
`liquidity.equal_levels`, `liquidity.pools`, `liquidity.sweeps`,
`sessions.levels`, `sessions.sweeps`, `mtf.levels`, `swings.external`,
`swings.internal` (hidden by default), `structure.breaks`,
`structure.protected`.

Layer rank (position in `LAYER_SPECS`) is the z-order base:
`primitive.z_order = rank * 100 + primitive.priority`. Primitives within a
layer are sorted by `(z_order, source_id)` so serialized bytes are stable.
All layers are emitted even when empty, so consumers can pin against a
fixed list.

## Deterministic rules

- **Time is UNIX seconds (UTC)** everywhere — Lightweight Charts'
  `UTCTimestamp`. Millisecond values never appear (test-guarded). Candle
  indices convert through `series.candles[i].timestamp`; open-ended zones
  extend to the last candle.
- **Style passthrough.** Every `color`, `opacity`, `line_style`, `fill`,
  `priority`, and `layer` value is copied from the source object's
  `VisualStyle`. The only colors born here are theme colors (candles,
  volume, chart chrome) and the bull/bear/neutral triplet for HTF level
  lines (which carry no style of their own).
- **Tooltips are structured** `dict[str, str]` derived from source-object
  fields — pre-formatted, no free text, no computation.
- **Byte determinism.** `build_chart_payload(series, results)` is a pure
  function: same inputs → identical `model_dump_json()` (regression
  goldens: `chart_five_day.json`, `chart_uptrend.json`).
- **Traceability.** Every `primitive.source_id` is the id of an object in
  the input result, or a documented synthetic aggregate id (`range:*`,
  `mtf:*`); property-tested.

## Themes

| Name | background | text | grid | up / down |
|---|---|---|---|---|
| `dark` (default) | `#131722` | `#d1d4dc` | `#1e222d` | `#22ab94` / `#f23645` |
| `light` | `#ffffff` | `#131722` | `#f0f3fa` | `#22ab94` / `#f23645` |

## Result store (`data.store`)

`ResultStore(path)` persists envelopes in SQLite keyed by
`(symbol, timeframe, module, series_hash)` with upsert semantics;
`hash_series(series)` is a sha256 over the canonical candle records. On
`load`, the stored `schema_version` is checked with `is_compatible`
(same major, stored minor ≤ current minor) — mismatches raise
`SchemaVersionError` (CT-2001), storage failures raise `DataError`
(CT-1000). `PAYLOAD_MODELS` registers every module's payload class
(including `chart`) so loads return fully typed envelopes.

## Frontend usage

```bash
python -m http.server 8000 --directory src/contexttrading/visualization/frontend
# open http://localhost:8000/
```

The page fetches the committed `demo-payload.json` (five-day 15m full
stack); the file picker loads any other `ChartPayload` envelope JSON. It
must be served over HTTP (fetch does not work from `file://`).

## Testing

- `tests/unit/visualization/test_primitives.py` — union validation, time rule.
- `tests/unit/visualization/test_mappers.py` — per-mapper counts, geometry,
  style passthrough, tooltip structure, seconds-only times.
- `tests/unit/visualization/test_serializer.py` — layer grouping/order,
  z-order rule, visibility overrides, themes, byte determinism.
- `tests/unit/visualization/test_visualization_property.py` — source-id
  traceability + series-bounded times across the full stack.
- `tests/unit/data/test_store.py` — round-trip, upsert, version
  compatibility, corrupt-row handling.
- `tests/regression/test_goldens.py::TestChartGoldens` — byte-exact
  full-stack and subset chart goldens.
- `tests/integration/test_phase7b.py` — 2000-candle pipeline → payload →
  store round-trip.

## Limitations

- The reference frontend is a static demo (CDN Lightweight Charts v4, no
  build step), not a packaged app; rectangles live on an overlay canvas
  rather than native chart primitives (a v5 `attachPrimitive` port is a
  drop-in upgrade).
- `Label` primitives are emitted by no current mapper (reserved for the
  AI layer's annotations).
- The store is SQLite only; PostgreSQL/Redis adapters are deferred (the
  `ResultStore` surface is small enough to mirror).
- A `Plotly` renderer is not included; the payload is renderer-agnostic
  by design and Plotly was dropped in favor of the Lightweight Charts
  contract.
