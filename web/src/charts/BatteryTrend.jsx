// Battery trends (History #5): daily SoC min/max band with the mean line,
// in the shared 8A style, plus a DoD summary — the band-with-mean form reads
// better on a phone than a second bar chart.

import { useEffect, useMemo, useState } from "react";

import { getJSON } from "../api";
import { baseTimeOption, tokens } from "./theme";
import EChart from "./EChart";

function Tile({ label, value }) {
  return (
    <div className="flex-1 rounded-xl px-2 py-2 text-center" style={{ background: "var(--surface-2)" }}>
      <div className="tnum text-lg font-bold">{value}</div>
      <div className="text-muted" style={{ fontSize: "0.62rem" }}>{label}</div>
    </div>
  );
}

export default function BatteryTrend() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getJSON("/api/history/battery/daily?days=90")
      .then(setData)
      .catch(() => setFailed(true));
  }, []);

  const option = useMemo(() => {
    if (!data || !data.items.length) return null;
    const t = tokens();
    const days = data.items;
    const cat = days.map((d) => d.date);
    const base = baseTimeOption({ spanS: days.length * 86400 });
    return {
      ...base,
      dataZoom: [],
      xAxis: {
        ...base.xAxis,
        type: "category",
        data: cat,
        axisLabel: {
          ...base.xAxis.axisLabel,
          formatter: (v) =>
            new Date(`${v}T12:00:00`).toLocaleDateString([], { month: "short", day: "numeric" }),
        },
      },
      yAxis: {
        ...base.yAxis,
        max: 100,
        axisLabel: { ...base.yAxis.axisLabel, formatter: (v) => `${v}%` },
      },
      tooltip: {
        ...base.tooltip,
        formatter: (params) => {
          const d = days[params[0].dataIndex];
          const date = new Date(`${d.date}T12:00:00`).toLocaleDateString([], {
            weekday: "short",
            month: "short",
            day: "numeric",
          });
          return `${date}<br/>SoC <b>${d.soc_min}–${d.soc_max}%</b> · avg ${d.soc_avg}%<br/>DoD: <b>${d.dod}%</b>`;
        },
      },
      series: [
        // Invisible floor + banded ceiling = the min/max envelope.
        {
          name: "min",
          type: "line",
          stack: "band",
          data: days.map((d) => d.soc_min),
          lineStyle: { opacity: 0 },
          itemStyle: { opacity: 0 },
          showSymbol: false,
          emphasis: { disabled: true },
          tooltip: { show: false },
        },
        {
          name: "range",
          type: "line",
          stack: "band",
          data: days.map((d) => d.soc_max - d.soc_min),
          lineStyle: { opacity: 0 },
          showSymbol: false,
          areaStyle: { color: t.accent, opacity: 0.22 },
          emphasis: { disabled: true },
          tooltip: { show: false },
        },
        {
          name: "avg SoC",
          type: "line",
          data: days.map((d) => d.soc_avg),
          showSymbol: false,
          smooth: 0.25,
          lineStyle: { color: t.accent, width: 1.6 },
          itemStyle: { color: t.accent },
          emphasis: { disabled: true },
        },
      ],
    };
  }, [data]);

  if (failed) return <div className="text-muted text-sm py-2">Can't reach the API</div>;

  const s = data?.summary;
  return (
    <div className="flex flex-col gap-3">
      <EChart
        option={option}
        loading={!data}
        empty={data && data.items.length === 0}
        height={190}
      />
      {s && (
        <div className="flex gap-2">
          <Tile label="avg depth of discharge" value={s.avg_dod != null ? `${s.avg_dod}%` : "--"} />
          <Tile label="max depth of discharge" value={s.max_dod != null ? `${s.max_dod}%` : "--"} />
          <Tile label="days tracked" value={s.days_with_data} />
        </div>
      )}
    </div>
  );
}
