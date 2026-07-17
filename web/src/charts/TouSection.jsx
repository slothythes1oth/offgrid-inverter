// TOU cost + savings section (History #4): summary tiles, the 8A stacked
// bars by rate band, the day-ring (8B.4), and the calendar heatmap (8B.5).
// Rates are editable in Settings; costs recompute server-side via query
// params. Costs shown are SUPPLY-ONLY (delivery + rebate change the all-in
// number) unless the all-in override is set.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { getJSON } from "../api";
import { rateQS } from "../rates";
import { baseTimeOption, tokens } from "./theme";
import CalendarHeatmap from "./CalendarHeatmap";
import DayRing from "./DayRing";
import EChart from "./EChart";

const BANDS = ["off_peak", "mid_peak", "on_peak"];
const BAND_LABEL = { off_peak: "off-peak", mid_peak: "mid-peak", on_peak: "on-peak" };

function Tile({ label, value, sub }) {
  return (
    <div className="flex-1 rounded-xl px-2 py-2 text-center" style={{ background: "var(--surface-2)" }}>
      <div className="tnum text-lg font-bold">{value}</div>
      <div className="text-muted" style={{ fontSize: "0.62rem" }}>{label}</div>
      {sub && <div className="text-muted tnum" style={{ fontSize: "0.62rem" }}>{sub}</div>}
    </div>
  );
}

export default function TouSection({ onSelectDay }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getJSON(`/api/history/tou/daily?days=120${rateQS()}`)
      .then(setData)
      .catch(() => setFailed(true));
  }, []);

  const totals = useMemo(() => {
    if (!data) return null;
    const last30 = data.items.slice(-30);
    const sum = (f) => last30.reduce((a, d) => a + f(d), 0);
    return {
      kwh: sum((d) => d.total_kwh),
      cost: sum((d) => d.cost_cents.total),
      charge: sum((d) => d.grid_charge_cost_cents),
      savings: sum((d) => d.savings_cents),
    };
  }, [data]);

  const barOption = useMemo(() => {
    if (!data) return null;
    const t = tokens();
    const days = data.items.slice(-14);
    const color = { off_peak: t.ok, mid_peak: t.warn, on_peak: t.danger };
    const base = baseTimeOption({ spanS: 14 * 86400 });
    return {
      ...base,
      grid: { ...base.grid, top: 10 },
      dataZoom: [],
      xAxis: {
        ...base.xAxis,
        type: "category",
        data: days.map((d) => d.date),
        axisLabel: {
          ...base.xAxis.axisLabel,
          formatter: (v) =>
            new Date(`${v}T12:00:00`).toLocaleDateString([], { day: "numeric" }),
        },
      },
      yAxis: {
        ...base.yAxis,
        axisLabel: { ...base.yAxis.axisLabel, formatter: (v) => `${v} kWh` },
      },
      tooltip: {
        ...base.tooltip,
        formatter: (params) => {
          const date = new Date(`${params[0].axisValue}T12:00:00`).toLocaleDateString([], {
            weekday: "short",
            month: "short",
            day: "numeric",
          });
          const day = days.find((d) => d.date === params[0].axisValue);
          const rows = params
            .map((p) => `${p.seriesName}: <b>${(+p.value).toFixed(1)} kWh</b>`)
            .join("<br/>");
          return `${date}<br/>${rows}<br/>cost: <b>$${(day.cost_cents.total / 100).toFixed(2)}</b>`;
        },
      },
      series: BANDS.map((b) => ({
        name: BAND_LABEL[b],
        type: "bar",
        stack: "kwh",
        data: days.map((d) => d.kwh[b]),
        itemStyle: { color: color[b] },
        barMaxWidth: 18,
        emphasis: { disabled: true },
      })),
    };
  }, [data]);

  if (failed) return <div className="text-muted text-sm py-2">Can't reach the API</div>;

  const usingOverride = data?.rates?.all_in_override != null;
  return (
    <div className="flex flex-col gap-4">
      {totals && (
        <div className="flex gap-2">
          <Tile label="30d supply cost" value={`$${(totals.cost / 100).toFixed(2)}`} sub={`${totals.kwh.toFixed(0)} kWh`} />
          <Tile label="grid-charge cost" value={`$${(totals.charge / 100).toFixed(2)}`} />
          <Tile label="peak-avoid savings" value={`$${(totals.savings / 100).toFixed(2)}`} />
        </div>
      )}

      <div>
        <div className="text-muted text-xs mb-1">last 14 days by rate band</div>
        <EChart
          option={barOption}
          loading={!data}
          empty={data && data.items.length === 0}
          height={190}
        />
      </div>

      <DayRing />

      <div>
        <div className="text-muted text-xs mb-1">calendar</div>
        {!data ? (
          <div className="chart-skeleton w-full" style={{ height: 200 }} />
        ) : (
          <CalendarHeatmap items={data.items} onSelectDay={onSelectDay} />
        )}
      </div>

      <div className="text-muted" style={{ fontSize: "0.65rem" }}>
        {usingOverride
          ? `Using your all-in override of ${data.rates.all_in_override}¢/kWh.`
          : "Supply-only costs; delivery charges and the Ontario rebate change the all-in number."}{" "}
        <Link to="/settings" className="underline" style={{ color: "var(--accent)" }}>
          edit rates
        </Link>
      </div>
    </div>
  );
}
