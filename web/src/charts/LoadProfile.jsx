// Load profile chart (History #1) through the shared 8A theme. Windows
// 1h/24h/7d/30d; thresholds as labeled markLines; sampled peaks as 8B.7
// high-water marks (decluttered below 24h); gaps as broken line + faint
// shading; pinch-zoom with a reset affordance; zooming deep into a long
// window re-fetches finer data for the visible span (SPEC 8A).

import { useEffect, useMemo, useRef, useState } from "react";

import { getJSON } from "../api";
import {
  baseTimeOption,
  fmtTooltipTime,
  fmtWatts,
  gapAreas,
  peakMarkers,
  primaryLineSeries,
  thresholdLines,
  tokens,
} from "./theme";
import EChart from "./EChart";

export const WINDOWS = ["1h", "24h", "7d", "30d"];
const WINDOW_S = { "1h": 3600, "24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400 };

// Drill when the zoomed span could come from a finer source than the
// current payload step delivers.
function finerAvailable(spanS, stepS) {
  if (stepS > 600 && spanS <= 10 * 86400) return true;
  if (stepS > 60 && spanS <= 48 * 3600) return true;
  if (stepS > 5 && spanS <= 3 * 3600) return true;
  return false;
}

function visiblePeaks(peaks, windowKey, t0, t1) {
  // Declutter (8B.7): none on 1h; day + all-time up to 7d; week + all on 30d.
  if (windowKey === "1h") return [];
  const wanted = windowKey === "30d" ? ["week", "all"] : ["day", "all"];
  const inRange = peaks.filter(
    (p) => wanted.includes(p.period) && p.ts >= t0 && p.ts <= t1
  );
  // The same sample often holds day/week/all records at once: one marker,
  // labeled with the longest period, wins.
  const rank = { all: 3, week: 2, day: 1 };
  const byTs = new Map();
  for (const p of inRange) {
    const cur = byTs.get(p.ts);
    if (!cur || rank[p.period] > rank[cur.period]) byTs.set(p.ts, p);
  }
  return [...byTs.values()];
}

export default function LoadProfile({ stale = false }) {
  const [windowKey, setWindowKey] = useState("24h");
  const [payload, setPayload] = useState(null);
  const [drill, setDrill] = useState(null); // finer payload for a zoomed span
  const [loading, setLoading] = useState(true);
  const [zoomed, setZoomed] = useState(false);
  const [showSoc, setShowSoc] = useState(false);
  const drillTimer = useRef(null);
  // Latest state via refs so the (stable) datazoom handler never goes stale.
  const payloadRef = useRef(null);
  const drillRef = useRef(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setDrill(null);
    setZoomed(false);
    getJSON(`/api/history/load?window=${windowKey}`)
      .then((d) => alive && setPayload(d))
      .catch(() => alive && setPayload(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [windowKey]);

  const active = drill ?? payload;
  payloadRef.current = payload;
  drillRef.current = drill;

  // Stable events object: EChart binds it once; refs keep it current.
  const chartEvents = useMemo(
    () => ({
      datazoom: (e) => {
        setZoomed(true);
        const base = payloadRef.current;
        if (!base) return;
        clearTimeout(drillTimer.current);
        drillTimer.current = setTimeout(() => {
          // Visible span from the zoom batch (percent of the full axis).
          const b = (e.batch && e.batch[0]) || e;
          if (b.start == null) return;
          const full = base.to - base.from;
          const t0 = Math.round(base.from + (b.start / 100) * full);
          const t1 = Math.round(base.from + (b.end / 100) * full);
          const stepNow = (drillRef.current ?? base).step_s;
          if (!finerAvailable(t1 - t0, stepNow)) return;
          getJSON(`/api/history/load?from=${t0}&to=${t1}`)
            .then((d) => setDrill(d))
            .catch(() => {});
        }, 350);
      },
    }),
    []
  );

  const resetZoom = () => {
    setDrill(null);
    setZoomed(false);
    // Re-set the same payload object to rebuild the option (clears dataZoom).
    setPayload((p) => ({ ...p }));
  };

  const option = useMemo(() => {
    if (!active) return null;
    const t = tokens();
    const spanS = active.to - active.from;
    const points = active.points.map((p) => [p[0] * 1000, p[1]]);
    const socPoints = active.points.map((p) => [p[0] * 1000, p[4]]);
    const dataMax = Math.max(0, ...active.points.map((p) => p[1] ?? 0));
    const th = active.thresholds;
    // Continuous limit always in view for spatial context; bypass appears
    // when the data pushes toward it. Low baselines reading low is honest.
    const yMax = Math.max(Math.round(dataMax * 1.25), Math.round(th.continuous_load_w * 1.1));

    const base = baseTimeOption({ spanS });
    const series = [
      {
        ...primaryLineSeries(points),
        markLine: thresholdLines([
          {
            value: th.continuous_load_w,
            level: "caution",
            label: `continuous ${fmtWatts(th.continuous_load_w)}`,
          },
          {
            value: th.bypass_w_total_balanced,
            level: "danger",
            label: `bypass ${fmtWatts(th.bypass_w_total_balanced)} (${th.bypass_a_per_leg} A/leg)`,
          },
        ]),
        markArea: gapAreas(active.gaps ?? []),
        markPoint: peakMarkers(
          visiblePeaks(active.sampled_peaks ?? [], drill ? "24h" : windowKey, active.from, active.to)
        ),
      },
    ];
    if (showSoc) {
      series.push({
        name: "SoC",
        type: "line",
        yAxisIndex: 1,
        data: socPoints,
        connectNulls: false,
        showSymbol: false,
        smooth: 0.25,
        lineStyle: { color: t.muted, width: 1, opacity: 0.7 },
        itemStyle: { color: t.muted },
        emphasis: { disabled: true },
      });
    }
    return {
      ...base,
      yAxis: [
        { ...base.yAxis, max: yMax },
        {
          type: "value",
          min: 0,
          max: 100,
          show: showSoc,
          axisLabel: {
            color: t.muted,
            fontSize: 10,
            formatter: (v) => `${v}%`,
          },
          splitLine: { show: false },
        },
      ],
      tooltip: {
        ...base.tooltip,
        formatter: (params) => {
          const time = fmtTooltipTime(params[0].value[0], spanS);
          const lines = params
            .map((p) => {
              const v = p.value[1];
              if (v == null) return `${p.seriesName}: no data`;
              return `${p.seriesName}: <b>${p.seriesName === "SoC" ? Math.round(v) + "%" : fmtWatts(v)}</b>`;
            })
            .join("<br/>");
          return `${time}<br/>${lines}`;
        },
      },
      series,
    };
  }, [active, windowKey, showSoc, drill]);

  const empty = !loading && (!active || active.points.every((p) => p[1] == null));

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="flex rounded-lg overflow-hidden border border-border" role="tablist">
          {WINDOWS.map((w) => (
            <button
              key={w}
              role="tab"
              aria-selected={w === windowKey}
              onClick={() => setWindowKey(w)}
              className="px-3 text-sm font-medium tnum"
              style={{
                minHeight: "2.35rem",
                background: w === windowKey ? "var(--surface-2)" : "transparent",
                color: w === windowKey ? "var(--text)" : "var(--muted)",
              }}
            >
              {w}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowSoc((s) => !s)}
            className="px-3 rounded-lg text-sm border border-border"
            style={{
              minHeight: "2.35rem",
              color: showSoc ? "var(--text)" : "var(--muted)",
              background: showSoc ? "var(--surface-2)" : "transparent",
            }}
          >
            SoC
          </button>
          {(zoomed || drill) && (
            <button
              onClick={resetZoom}
              className="px-3 rounded-lg text-sm border border-border"
              style={{ minHeight: "2.35rem", color: "var(--accent)" }}
            >
              reset zoom
            </button>
          )}
        </div>
      </div>

      <EChart
        option={option}
        loading={loading}
        empty={empty}
        emptyText={
          payload
            ? "No data in this window yet — collecting"
            : "Can't reach the API"
        }
        stale={stale}
        height={280}
        onEvents={chartEvents}
      />
      {drill && (
        <div className="text-muted text-xs mt-1 tnum">
          zoomed: finer data loaded ({drill.source}, {drill.step_s}s steps)
        </div>
      )}
    </div>
  );
}
