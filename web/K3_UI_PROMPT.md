# MASTER PROMPT — ContextTrading Web UI Build
# Paste this to the agent building the web UI (Kimi K3). It is also committed
# to the repo so the agent can read it with full repo context.

You are the Lead Frontend Engineer for **ContextTrading** — a deterministic Smart Money Concepts (SMC) trading framework. The Python engine, FastAPI backend, and chart-payload contract are COMPLETE and tested. Your ONLY job: build the web UI that renders what the backend returns.

## GOLDEN RULES (never violate)

1. **The UI NEVER calculates.** No indicators, no structure detection, no math on market data in JavaScript. The UI renders engine output only.
2. **The approved design already exists.** `web/mockup/index.html` in this repo is the pixel reference. Your output must look like it — same layout, same colors, same density, same components. Do not invent a different layout. Do not produce a sparse white page.
3. **Dark institutional terminal aesthetic.** No light mode, no casino neon.

## WHAT WENT WRONG BEFORE (do not repeat)

A previous attempt produced a mostly-empty white page with a bare chart and a "LAYERS" box. That is rejected. The deliverable is a full terminal: top bar + left sidebar + chart with SMC overlays + AI analyst panel + status bar, exactly like the mockup.

## TECH STACK

React 18+ · TypeScript · Vite · Tailwind CSS · shadcn/ui · TradingView Lightweight Charts v4 (`lightweight-charts` npm). Location: `web/app/`. The existing `web/mockup/` stays untouched as the design reference.

## DESIGN TOKENS (exact, from the mockup)

```
bg #0b0e13 · panel #10141b · panel-2 #151a23 · hover #1a2130
border #1e2633 · text #e7ebf2 · text-dim #8b95a8 · text-faint #5b6577
teal #2dd4bf (bullish) · rose #fb7185 (bearish) · amber #fbbf24 (liquidity/session)
purple #a78bfa (breakers/AI) · blue #60a5fa (structure/info)
fonts: Inter (UI), JetBrains Mono (numbers/code)
```

## LAYOUT (CSS grid, exactly like the mockup)

```
rows: 48px topbar / 1fr / 34px statusbar
cols: 232px sidebar / 1fr chart / 360px analyst panel
```

### 1. Top bar
Logo mark (gradient teal→blue, "CT") + "ContextTrading"; symbol selector (BTCUSDT ▾ + price + change%); timeframe pill group (1m 5m 15m 1H 4H 1D 1W, active = 15m); right side: **bias badge** (▲ BULLISH 0.78, teal), **session chip** (pulsing dot + "London KZ · 08:42 UTC", amber), API-key and settings icon buttons.

### 2. Left sidebar
- **Watchlist** — symbol rows (name, price, % change teal/rose), active row highlighted
- **MTF Bias Matrix** — 4 cells (1W/1D/4H/1H) each with arrow ▲/▼/◆ colored by direction + market phase label; alignment summary line ("3/4 bullish · htf_influence 0.22")
- **Engine Layers** — rows: colored dot, layer name, object count, on/off toggle (Structure, FVG, Order Blocks, Liquidity, Sessions/KZ, Premium/Discount, Confluence Zones, HTF Levels)

### 3. Center chart
- Toolbar: O/H/L/C values, volume, ATR, right-aligned chips "engine v1.0.0 · deterministic ✓" and "schema 1.0.0"
- Lightweight Charts: teal/rose candles, dark grid (#151b26), crosshair #33415c
- **SMC overlays from the chart payload** (`POST /v1/charts/payload`): boxes (FVG teal, OB rose, OTE blue dashed), price lines (EQH amber dashed, EQ gray dotted), markers (sweeps amber circles), session background bands (purple tint), BOS/CHoCH segments with labels. Every payload primitive type (PriceLine, Box, Marker, Label, Segment, AreaBand) must render — see `docs/modules/visualization.md` for the payload contract.
- Layer toggles in the sidebar filter primitives by their `layer` field.

### 4. Right panel — AI Analyst (the differentiator)
Header: "AI Analyst · evidence-bound" + confidence ring (0.78). Cards, matching `POST /v1/ai/market-analysis` response sections:
- **Executive Summary** — narrative with inline **citation chips** (`#ob_a3f9c2`, mono font, blue tint)
- **Confluence Breakdown** — per-factor horizontal bars with weights (from the report's confluences/factor contributions)
- **Trade Evaluation** — 2×2 grid (Entry/SL/TP/Probability) + R:R pill + invalidation note
- **Alternative Scenarios** — left-bordered items (teal=bullish, rose=bearish) with probability %
- **Weaknesses** — ⚠ items with citations
- **Action Items** — → items
- Footer: prompt version · model · citations verified · data quality
- **Citation interaction (must have):** clicking a citation chip highlights/flashes the corresponding object on the chart (match `evidence_ids` to primitive `source_id`).

### 5. Status bar
Tabs: 📊 Chart (active) · ⚡ Backtest · 📓 Journal · 📅 Weekly Review. Right side: "● API connected", "stream: NDJSON", "full-stack: 1.66s @2k bars", UTC clock.

## BACKEND CONTRACTS (FastAPI — see docs/api/README.md)

- `POST /v1/charts/payload` — body: candles array → full chart payload (candles + primitives + layers + theme)
- `POST /v1/analysis/full` — full 10-module engine results (powers MTF matrix, layer counts, bias badge)
- `POST /v1/ai/market-analysis` — AI report JSON (powers the entire right panel; every statement has `evidence_ids`)
- `POST /v1/stream/analysis` — NDJSON progressive stream (use it so layers appear live as modules finish)
- Auth: `X-API-Key` header (settings page stores it in localStorage)
- **Demo mode (must have):** when the API is unreachable, load `src/contexttrading/visualization/frontend/demo-payload.json` (bundled copy) so the UI always renders a full, populated screen.

## BUILD INCREMENTS (deliver in this order)

1. **Shell** — grid layout, dark tokens, top bar, status bar, empty panels (must already look like the mockup)
2. **Chart** — Lightweight Charts + all primitive renderers + layer toggles + demo payload
3. **Sidebar** — watchlist, MTF matrix (from `/v1/analysis/full`), layer counts
4. **AI panel** — all six cards from `/v1/ai/market-analysis` + citation-click highlight
5. **Polish** — streaming via NDJSON, loading skeletons, settings (API key, backend URL), responsive ≥1280px

## ACCEPTANCE CRITERIA (all must pass)

- [ ] Side-by-side with `web/mockup/index.html`, the app is visually indistinguishable in layout, color, and density
- [ ] Demo mode shows a fully populated screen without any backend
- [ ] With the backend running, chart overlays = exactly the payload primitives (no more, no less)
- [ ] Clicking any `#id` citation chip flashes the matching chart object
- [ ] No market-data math anywhere in the frontend (code-review rule)
- [ ] `npm run build` passes with TypeScript strict mode, zero any-types on API contracts (generate types from the OpenAPI schema)

Start with Increment 1 now. Show the result after each increment before continuing.
