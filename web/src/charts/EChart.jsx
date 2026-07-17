// React wrapper for ECharts with the three mandatory 8A states:
//   loading  -> skeleton shimmer, never a flash of empty axes
//   empty    -> "collecting data" message, not a broken chart
//   stale    -> chart dims + the same freshness treatment as the app
// Handles init/dispose, container resize, and event wiring.

import { useEffect, useRef } from "react";

import echarts from "./echarts";

export default function EChart({
  option,
  loading = false,
  empty = false,
  emptyText = "Collecting data — check back soon",
  stale = false,
  height = 260,
  onEvents = null,
}) {
  const ref = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(ref.current);
    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !option) return;
    chartRef.current.setOption(option, { notMerge: true });
  }, [option]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onEvents) return;
    const entries = Object.entries(onEvents);
    for (const [ev, fn] of entries) chart.on(ev, fn);
    return () => {
      if (chart.isDisposed()) return;
      for (const [ev, fn] of entries) chart.off(ev, fn);
    };
  }, [onEvents]);

  const showChart = !loading && !empty;
  return (
    <div className="relative" style={{ height }}>
      <div
        ref={ref}
        className="w-full h-full"
        style={{
          opacity: showChart ? (stale ? 0.55 : 1) : 0,
          transition: "opacity 0.4s ease",
        }}
      />
      {loading && (
        <div className="absolute inset-0 rounded-xl overflow-hidden" aria-label="loading chart">
          <div className="chart-skeleton w-full h-full" />
        </div>
      )}
      {!loading && empty && (
        <div className="absolute inset-0 grid place-items-center text-center px-6">
          <span className="text-muted text-sm">{emptyText}</span>
        </div>
      )}
      {showChart && stale && (
        <div
          className="absolute top-1 right-1 text-xs px-2 py-0.5 rounded-md"
          style={{ background: "color-mix(in srgb, var(--warn) 18%, var(--surface))", color: "var(--warn)" }}
        >
          stale
        </div>
      )}
    </div>
  );
}
