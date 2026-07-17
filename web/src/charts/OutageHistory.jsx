// Outage history (History #3): rollup stats + reverse-chron list.

import { useEffect, useState } from "react";

import { getJSON } from "../api";
import { fmtDuration } from "../format";

function Stat({ label, value }) {
  return (
    <div className="flex-1 text-center">
      <div className="tnum text-xl font-bold">{value}</div>
      <div className="text-muted" style={{ fontSize: "0.65rem" }}>{label}</div>
    </div>
  );
}

function fmtStart(ts) {
  return new Date(ts * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function OutageHistory() {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getJSON("/api/history/outages")
      .then(setData)
      .catch(() => setFailed(true));
  }, []);

  if (failed) return <div className="text-muted text-sm py-2">Can't reach the API</div>;
  if (!data) return <div className="chart-skeleton w-full" style={{ height: 90 }} />;

  const s = data.stats;
  return (
    <div>
      <div className="flex gap-2 py-1">
        <Stat label="outages" value={s.count} />
        <Stat label="avg duration" value={s.avg_duration_s != null ? fmtDuration(s.avg_duration_s) : "--"} />
        <Stat label="avg kWh each" value={s.avg_kwh != null ? s.avg_kwh.toFixed(1) : "--"} />
      </div>
      {data.items.length === 0 ? (
        <div className="text-muted text-sm py-2 text-center">
          No outages recorded yet — that's a good thing
        </div>
      ) : (
        <ul className="divide-y divide-border mt-1">
          {data.items.map((o) => (
            <li key={o.id} className="py-2.5 flex items-center gap-3">
              <span className="text-lg" style={{ color: "var(--warn)" }}>⚡</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium tnum">{fmtStart(o.started_ts)}</span>
                <span className="block text-muted text-xs tnum">
                  {o.ended_ts == null
                    ? "ongoing"
                    : `${fmtDuration(o.duration_s)} · SoC ${o.soc_start}% → ${o.soc_end}%`}
                </span>
              </span>
              <span className="tnum text-sm font-semibold shrink-0">
                {o.kwh_used != null ? `${o.kwh_used.toFixed(1)} kWh` : "--"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
