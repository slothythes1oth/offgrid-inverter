// Shared chart theme (SPEC 8A). Every chart in the app builds on these
// helpers so they read as one product: dark background, faint HORIZONTAL
// gridlines only, muted tabular axis text, one accent series color, semantic
// threshold colors, touch-first interaction, no hover-only behavior.

// CSS variables read at build time so charts match the active color scheme.
export function tokens() {
  const s = getComputedStyle(document.documentElement);
  const v = (name) => s.getPropertyValue(name).trim();
  return {
    text: v("--text"),
    muted: v("--muted"),
    border: v("--border"),
    surface: v("--surface"),
    surface2: v("--surface-2"),
    accent: v("--accent"),
    ok: v("--ok"),
    warn: v("--warn"),
    danger: v("--danger"),
  };
}

const FONT =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export function fmtWatts(v) {
  if (v == null) return "--";
  if (Math.abs(v) >= 1000) {
    const kw = v / 1000;
    return `${kw >= 10 ? Math.round(kw) : kw.toFixed(1)} kW`;
  }
  return `${Math.round(v)} W`;
}

// Time-axis label matched to the visible span (SPEC 8A): HH:mm within a
// couple of days, weekday for a week, month+day beyond.
export function timeLabelFormatter(spanS) {
  if (spanS <= 48 * 3600) {
    return (ms) =>
      new Date(ms).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  if (spanS <= 10 * 86400) {
    return (ms) => new Date(ms).toLocaleDateString([], { weekday: "short" });
  }
  return (ms) =>
    new Date(ms).toLocaleDateString([], { month: "short", day: "numeric" });
}

export function fmtTooltipTime(ms, spanS) {
  const d = new Date(ms);
  if (spanS <= 48 * 3600) {
    return d.toLocaleString([], {
      weekday: "short",
      hour: "numeric",
      minute: "2-digit",
    });
  }
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// Base option shared by every time-series chart. Charts spread/extend this.
export function baseTimeOption({ spanS }) {
  const t = tokens();
  return {
    animation: false, // phones: no entrance theatrics, data is the point
    backgroundColor: "transparent",
    grid: { left: 44, right: 12, top: 18, bottom: 26 },
    xAxis: {
      type: "time",
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false }, // no vertical gridlines (8A)
      axisLabel: {
        color: t.muted,
        fontFamily: FONT,
        fontSize: 10,
        hideOverlap: true,
        formatter: timeLabelFormatter(spanS),
      },
    },
    yAxis: {
      type: "value",
      min: 0, // power/load y starts at 0 (8A)
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: true, lineStyle: { color: t.border, opacity: 0.5 } },
      axisLabel: {
        color: t.muted,
        fontFamily: FONT,
        fontSize: 10,
        formatter: fmtWatts,
      },
    },
    tooltip: {
      trigger: "axis",
      confine: true, // never runs off a narrow phone screen (8A)
      backgroundColor: t.surface,
      borderColor: t.border,
      textStyle: { color: t.text, fontFamily: FONT, fontSize: 12 },
      axisPointer: { lineStyle: { color: t.muted, opacity: 0.6 } },
    },
    // Pinch to zoom + one-finger pan on the time axis (8A touch-first).
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: 0,
        filterMode: "none",
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
      },
    ],
  };
}

// The primary series look: smooth thin accent line, subtle gradient fill,
// no data-point dots, gaps NEVER bridged (8A data integrity).
export function primaryLineSeries(data, { name = "Load" } = {}) {
  const t = tokens();
  return {
    name,
    type: "line",
    data,
    connectNulls: false,
    showSymbol: false,
    smooth: 0.25,
    lineStyle: { color: t.accent, width: 1.6 },
    itemStyle: { color: t.accent },
    emphasis: { disabled: true },
    areaStyle: {
      color: {
        type: "linear",
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: mix(t.accent, 0.22) },
          { offset: 1, color: mix(t.accent, 0) },
        ],
      },
    },
  };
}

// Threshold markLine in the semantic status colors (amber caution, red danger).
export function thresholdLines(lines) {
  const t = tokens();
  const color = { caution: t.warn, danger: t.danger };
  return {
    silent: true,
    symbol: "none",
    animation: false,
    lineStyle: { type: "dashed", width: 1 },
    label: {
      position: "insideEndTop",
      fontFamily: FONT,
      fontSize: 9,
      distance: [0, 2],
    },
    data: lines.map((l) => ({
      yAxis: l.value,
      lineStyle: { color: color[l.level] || t.muted },
      label: { formatter: l.label, color: color[l.level] || t.muted },
    })),
  };
}

// Faint "no data" shading over gap spans (8A: gaps render as gaps, plus).
export function gapAreas(gaps) {
  const t = tokens();
  return {
    silent: true,
    itemStyle: { color: mix(t.muted, 0.08) },
    data: gaps.map(([a, b]) => [{ xAxis: a * 1000 }, { xAxis: b * 1000 }]),
  };
}

// High-water marks (SPEC 8B.7): sampled peaks as small flood-marker ticks
// with date + value, always tagged "sampled".
export function peakMarkers(peaks) {
  const t = tokens();
  return {
    silent: true,
    animation: false,
    symbol: "path://M0,0 L12,0 L6,9 Z", // small downward tick
    symbolSize: [10, 7],
    symbolOffset: [0, -6],
    itemStyle: { color: t.text, opacity: 0.85 },
    label: {
      show: true,
      position: "top",
      fontFamily: FONT,
      fontSize: 9,
      color: t.muted,
      formatter: (p) => p.data.peakLabel,
    },
    data: peaks.map((pk) => ({
      coord: [pk.ts * 1000, pk.load_w],
      peakLabel:
        `${fmtWatts(pk.load_w)} · ` +
        new Date(pk.ts * 1000).toLocaleDateString([], { month: "short", day: "numeric" }) +
        ` · sampled ${pk.period === "all" ? "all-time" : pk.period} peak`,
    })),
  };
}

function mix(hex, alpha) {
  // color-mix equivalent for canvas: hex -> rgba with alpha.
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
