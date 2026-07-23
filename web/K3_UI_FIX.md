# URGENT FIX — ContextTrading Web UI Rendering Policy
# The layout/design is approved. The chart rendering is UNUSABLE: it draws
# every detected object in history at once (484 structure objects, 721 order
# blocks, 231 FVGs...). Apply this rendering policy exactly.

## THE PROBLEM (from the owner's screenshot)

- The chart is a solid wall of red/cyan boxes and lines — nothing is readable.
- Session high/low labels spam the entire price axis (hundreds of "session high / swing high (broken)" labels).
- Every layer toggle is ON by default with every historical object rendered.
- AI panel shows raw floats ("0.440302899585490") and oversized citation hashes that overflow their cards.

## RENDERING POLICY (implement exactly)

### 1. Active-only default (the core rule)
Every engine object has a lifecycle status. By default render ONLY active objects:
- FVG: status UNMITIGATED (untouched) or PARTIALLY_FILLED. Hide FILLED + inverted history.
- Order blocks / breakers / mitigation blocks: UNMITIGATED or PARTIALLY_MITIGATED. Hide MITIGATED/VIOLATED.
- Supply/demand: FRESH or TESTED. Hide BROKEN/MITIGATED.
- Liquidity pools: untapped only. Swept pools show only the sweep MARKER from the last 2 sessions, not the pool line.
- Add one sidebar toggle per category: "Show history" (default OFF) that reveals inactive objects at 25% opacity.

### 2. Caps + relevance ranking
- Hard cap per layer: **max 25 objects**, selected by (a) lifecycle-active first, (b) highest strength/priority, (c) nearest to current price. Show "23 more hidden" hint in the layer row when capped.
- Structure: external swings + last 10 breaks (BOS/CHoCH) by default; internal swings render as 3px dots with NO labels.
- Session levels: only the MOST RECENT instance per session type + current-day prev-day high/low. Never label older instances.
- Default visible layers ON: Structure breaks, FVG (active), Order Blocks (active), current Session. Everything else starts OFF.

### 3. Visual noise rules
- No text label may render outside the chart's right edge +20px; anchor labels at the object's start candle.
- Overlapping same-type zones: keep the highest-strength one at full opacity, others at 40%.
- Zones that end before the visible range's left edge are not drawn.

### 4. Number & text formatting
- ALL confidence/probability/score floats: round to 2 decimals ("0.44", never "0.440302899585490").
- Citation chips: short form `#ob_a3f9` (first 6 hex chars) with full id in tooltip. Chips must never overflow their card (ellipsis + wrap).
- Prices: format with symbol-appropriate precision and thousands separators.

### 5. Mock-mode honesty
- When the backend reports `ai_provider: "mock"` (see /readyz), show a small amber banner above the AI panel: "Demo analysis — connect a real LLM key on the server for live reports." Never present mock output as real analysis.

## ACCEPTANCE (owner will verify with a screenshot)
- [ ] Default view shows ≤ ~60 rendered objects total and the chart is immediately readable: candles clearly visible, a handful of zones, a few labels.
- [ ] Side-by-side with web/mockup/index.html the *density* feels the same (the mockup shows ~7 overlays, not 700).
- [ ] Layer toggles still reveal everything on demand — filtering is a view policy, not data loss.
- [ ] No raw floats, no overflowing citation chips anywhere.

Apply, rebuild, redeploy to n8meme.eu, and reply with a screenshot of the DEFAULT view with demo data.
