/* ContextTrading reference renderer (Lightweight Charts v4).
 *
 * Consumes a ChartPayload envelope (see visualization/serializer.py) and
 * renders it without any analysis logic:
 *   candles/volume  -> native series
 *   price_line      -> ISeriesApi.createPriceLine
 *   marker          -> ISeriesApi.setMarkers ("diamond" falls back to "square";
 *                      v4 has no diamond shape)
 *   box/area_band/segment/label -> overlay canvas (v4 has no native rectangle
 *                      primitive; v5 could use attachPrimitive instead)
 *
 * Serve the folder over HTTP, e.g.:
 *   python -m http.server 8000 --directory src/contexttrading/visualization/frontend
 */
"use strict";

const LINE_STYLE_MAP = {
  solid: LightweightCharts.LineStyle.Solid,
  dashed: LightweightCharts.LineStyle.Dashed,
  dotted: LightweightCharts.LineStyle.Dotted,
};

const state = {
  chart: null,
  candleSeries: null,
  volumeSeries: null,
  payload: null,
  envelope: null,
  priceLineApis: [],
  overlayShapes: [], // {kind, layer, x1, y1, x2, y2, prim}
  visibleLayers: new Set(),
};

function tooltipText(prim) {
  const lines = Object.entries(prim.tooltip || {}).map(([k, v]) => `${k}: ${v}`);
  return lines.join("\n");
}

function hexToRgba(hex, alpha) {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.slice(0, 6);
  const n = parseInt(full, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

function layerList() {
  return (state.envelope && state.envelope.payload.layers) || [];
}

function visiblePrimitives(kind) {
  const out = [];
  for (const layer of layerList()) {
    if (!state.visibleLayers.has(layer.name)) continue;
    for (const prim of layer.primitives) {
      if (prim.primitive === kind) out.push(prim);
    }
  }
  return out;
}

function applyTheme(theme) {
  document.body.classList.toggle("light", theme.name === "light");
  state.chart.applyOptions({
    layout: {
      background: { type: "solid", color: theme.background },
      textColor: theme.text_color,
    },
    grid: {
      vertLines: { color: theme.grid_color },
      horzLines: { color: theme.grid_color },
    },
    timeScale: { borderColor: theme.grid_color },
    rightPriceScale: { borderColor: theme.grid_color },
  });
  state.candleSeries.applyOptions({
    upColor: theme.up_color,
    downColor: theme.down_color,
    wickUpColor: theme.up_color,
    wickDownColor: theme.down_color,
    borderVisible: false,
  });
}

function renderPriceLines() {
  for (const api of state.priceLineApis) state.candleSeries.removePriceLine(api);
  state.priceLineApis = [];
  for (const prim of visiblePrimitives("price_line")) {
    const api = state.candleSeries.createPriceLine({
      price: prim.price,
      color: prim.color,
      lineWidth: Math.max(1, Math.round(prim.line_width || 1)),
      lineStyle: LINE_STYLE_MAP[prim.line_style] ?? LightweightCharts.LineStyle.Solid,
      axisLabelVisible: true,
      title: prim.title || "",
    });
    state.priceLineApis.push(api);
  }
}

function renderMarkers() {
  const markers = visiblePrimitives("marker")
    .map((prim) => ({
      time: prim.time,
      position: prim.position,
      shape: prim.shape === "diamond" ? "square" : prim.shape, // v4 has no diamond
      color: prim.color,
      text: prim.text || "",
      size: 1,
    }))
    .sort((a, b) => a.time - b.time);
  state.candleSeries.setMarkers(markers);
}

function resizeOverlay() {
  const wrap = document.getElementById("chart-wrap");
  const canvas = document.getElementById("overlay");
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(wrap.clientWidth * dpr);
  canvas.height = Math.round(wrap.clientHeight * dpr);
  canvas.style.width = `${wrap.clientWidth}px`;
  canvas.style.height = `${wrap.clientHeight}px`;
}

function collectOverlayShapes() {
  const shapes = [];
  const kinds = ["area_band", "box", "segment", "label"];
  for (const kind of kinds) {
    for (const prim of visiblePrimitives(kind)) shapes.push({ kind, prim });
  }
  shapes.sort((a, b) => a.prim.z_order - b.prim.z_order);
  state.overlayShapes = shapes;
}

function drawOverlay() {
  const canvas = document.getElementById("overlay");
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.scale(dpr, dpr);
  const ts = state.chart.timeScale();
  const x = (t) => ts.timeToCoordinate(t);
  const y = (p) => state.candleSeries.priceToCoordinate(p);
  const h = canvas.height / dpr;
  const hit = [];
  for (const { kind, prim } of state.overlayShapes) {
    ctx.strokeStyle = prim.color;
    ctx.fillStyle = hexToRgba(prim.color, prim.opacity ?? 0.2);
    ctx.lineWidth = prim.line_width || 1;
    ctx.setLineDash(
      prim.line_style === "dashed" ? [6, 4] : prim.line_style === "dotted" ? [2, 3] : []
    );
    if (kind === "area_band") {
      const x1 = x(prim.start_time);
      const x2 = x(prim.end_time);
      if (x1 === null || x2 === null) continue;
      ctx.fillRect(x1, 0, x2 - x1, h);
      hit.push({ x1, y1: 0, x2, y2: h, prim });
    } else if (kind === "box") {
      const x1 = x(prim.start_time);
      const x2 = x(prim.end_time);
      const y1 = y(prim.top);
      const y2 = y(prim.bottom);
      if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
      if (prim.fill !== false) ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
      ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
      hit.push({ x1, y1, x2, y2, prim });
    } else if (kind === "segment") {
      const x1 = x(prim.start_time);
      const x2 = x(prim.end_time);
      const y1 = y(prim.start_price);
      const y2 = y(prim.end_price);
      if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2, y2);
      ctx.stroke();
      hit.push({ x1: Math.min(x1, x2) - 4, y1: Math.min(y1, y2) - 4,
                 x2: Math.max(x1, x2) + 4, y2: Math.max(y1, y2) + 4, prim });
    } else if (kind === "label") {
      const x1 = x(prim.time);
      const y1 = y(prim.price);
      if (x1 === null || y1 === null) continue;
      ctx.setLineDash([]);
      ctx.fillStyle = prim.color;
      ctx.font = "11px sans-serif";
      ctx.fillText(prim.text, x1 + 4, y1 - 4);
    }
  }
  ctx.restore();
  state.hitRegions = hit.reverse(); // top-most (highest z_order) first
}

function scheduleOverlay() {
  collectOverlayShapes();
  requestAnimationFrame(drawOverlay);
}

function renderAll() {
  renderPriceLines();
  renderMarkers();
  scheduleOverlay();
}

function buildSidebar() {
  const sidebar = document.getElementById("sidebar");
  sidebar.innerHTML = "";
  const legend = state.envelope.payload.legend || {};
  for (const layer of layerList()) {
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.visibleLayers.has(layer.name);
    box.addEventListener("change", () => {
      if (box.checked) state.visibleLayers.add(layer.name);
      else state.visibleLayers.delete(layer.name);
      renderAll();
    });
    const name = document.createElement("span");
    name.textContent = legend[layer.name] || layer.name;
    const count = document.createElement("span");
    count.className = "count";
    count.textContent = String(layer.primitives.length);
    label.append(box, name, count);
    sidebar.appendChild(label);
  }
}

function loadEnvelope(envelope) {
  state.envelope = envelope;
  const p = envelope.payload;
  state.payload = p;
  state.visibleLayers = new Set(p.layers.filter((l) => l.visible).map((l) => l.name));
  document.getElementById("title").textContent = `${p.symbol} · ${p.timeframe}`;
  document.getElementById("meta").textContent =
    `${p.candles.length} candles · schema ${envelope.schema_version} · engine ${envelope.engine_version}`;

  applyTheme(p.theme);
  state.candleSeries.setData(p.candles);
  state.volumeSeries.setData(
    p.volume.map((v) => ({ time: v.time, value: v.value, color: hexToRgba(v.color, 0.5) }))
  );
  buildSidebar();
  renderAll();
  state.chart.timeScale().fitContent();
}

function initChart() {
  state.chart = LightweightCharts.createChart(document.getElementById("chart"), {
    autoSize: true,
    rightPriceScale: { borderVisible: true },
    timeScale: { timeVisible: true, secondsVisible: false },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  });
  state.candleSeries = state.chart.addCandlestickSeries();
  state.volumeSeries = state.chart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
  });
  state.chart.priceScale("volume").applyOptions({
    scaleMargins: { top: 0.8, bottom: 0 },
  });
  resizeOverlay();
  window.addEventListener("resize", () => {
    resizeOverlay();
    scheduleOverlay();
  });
  state.chart.timeScale().subscribeVisibleLogicalRangeChange(scheduleOverlay);

  const wrap = document.getElementById("chart-wrap");
  const tip = document.getElementById("tip");
  wrap.addEventListener("mousemove", (ev) => {
    const rect = wrap.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;
    const found = (state.hitRegions || []).find(
      (r) => px >= r.x1 && px <= r.x2 && py >= r.y1 && py <= r.y2
    );
    if (found) {
      tip.style.display = "block";
      tip.style.left = `${Math.min(px + 12, rect.width - 270)}px`;
      tip.style.top = `${py + 12}px`;
      tip.textContent = tooltipText(found.prim);
    } else {
      tip.style.display = "none";
    }
  });
  wrap.addEventListener("mouseleave", () => {
    tip.style.display = "none";
  });
}

async function boot() {
  initChart();
  document.getElementById("file").addEventListener("change", (ev) => {
    const file = ev.target.files[0];
    if (!file) return;
    file.text().then((text) => loadEnvelope(JSON.parse(text)));
  });
  try {
    const res = await fetch("demo-payload.json");
    loadEnvelope(await res.json());
  } catch (err) {
    document.getElementById("meta").textContent =
      "no demo-payload.json (serve over HTTP, not file://) — use the file picker";
  }
}

boot();
