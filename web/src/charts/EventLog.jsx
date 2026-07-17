// Fault/event log (History #2). Reverse-chron list; fault and pack-protection
// entries open the flight-recorder card (SPEC 8B.6): a +/- 10 minute load
// trace with the trip moment marked, and a plain-language facts panel.
// Fault 13 is always shown as "Fault 13 - bypass overload".

import { useEffect, useMemo, useState } from "react";

import { getJSON } from "../api";
import { baseTimeOption, fmtTooltipTime, fmtWatts, primaryLineSeries, tokens } from "./theme";
import EChart from "./EChart";

const TYPE_META = {
  fault_raised: { icon: "⚠", color: "var(--danger)", flight: true },
  fault_cleared: { icon: "✓", color: "var(--ok)" },
  pack_protection: { icon: "⚠", color: "var(--warn)", flight: true },
  grid_lost: { icon: "⚡", color: "var(--warn)" },
  grid_restored: { icon: "✓", color: "var(--ok)" },
  low_soc: { icon: "▼", color: "var(--warn)" },
  gap_detected: { icon: "…", color: "var(--muted)" },
  collector_start: { icon: "▶", color: "var(--muted)" },
  collector_stop: { icon: "■", color: "var(--muted)" },
};

function title(ev) {
  if (ev.type === "fault_raised" || ev.type === "fault_cleared") {
    const codes = ev.fault_codes?.length
      ? ev.fault_codes.map((c) => `Fault ${c.code} - ${c.name}`).join(", ")
      : "Fault";
    return ev.type === "fault_raised" ? codes : `${codes} cleared`;
  }
  return {
    pack_protection: "Battery pack protection",
    grid_lost: "Grid lost — on battery",
    grid_restored: "Grid restored",
    low_soc: "Low battery during outage",
    gap_detected: "Data gap (collector off)",
    collector_start: "Collector started",
    collector_stop: "Collector stopped",
  }[ev.type] ?? ev.type;
}

function subtitle(ev) {
  const bits = [];
  if (ev.soc != null) bits.push(`SoC ${ev.soc}%`);
  if (ev.load_w_total != null) bits.push(`load ${fmtWatts(ev.load_w_total)}`);
  if (ev.gap_s != null) {
    const m = Math.round(ev.gap_s / 60);
    bits.push(m >= 90 ? `${(m / 60).toFixed(1)} h missing` : `${m} min missing`);
  }
  return bits.join(" · ");
}

function fmtEventTime(ts) {
  return new Date(ts * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function Fact({ label, value }) {
  if (value == null) return null;
  return (
    <div>
      <div className="text-muted" style={{ fontSize: "0.65rem" }}>{label}</div>
      <div className="tnum text-sm font-semibold">{value}</div>
    </div>
  );
}

// The flight-recorder card body: trace + facts, loaded on open.
function FlightRecorder({ eventId, eventTs }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    getJSON(`/api/history/events/${eventId}/trace`)
      .then((d) => alive && setData(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [eventId]);

  const option = useMemo(() => {
    if (!data) return null;
    const t = tokens();
    const spanS = 1200;
    const points = data.trace.points.map((p) => [p[0] * 1000, p[1]]);
    const base = baseTimeOption({ spanS });
    return {
      ...base,
      grid: { ...base.grid, top: 22 },
      dataZoom: [], // fixed +/-10 min view; no zoom inside the card
      tooltip: {
        ...base.tooltip,
        formatter: (params) =>
          `${fmtTooltipTime(params[0].value[0], spanS)}<br/>Load: <b>${fmtWatts(params[0].value[1])}</b>`,
      },
      series: [
        {
          ...primaryLineSeries(points),
          markLine: {
            silent: true,
            symbol: "none",
            animation: false,
            lineStyle: { color: t.danger, width: 1.4 },
            label: {
              formatter: "trip",
              color: t.danger,
              fontSize: 9,
              position: "insideEndTop",
            },
            data: [{ xAxis: eventTs * 1000 }],
          },
        },
      ],
    };
  }, [data, eventTs]);

  if (failed) return <div className="text-muted text-sm py-2">trace unavailable</div>;
  const f = data?.facts;
  return (
    <div className="pt-2">
      <EChart
        option={option}
        loading={!data}
        empty={data && data.trace.points.length === 0}
        emptyText="No samples remain around this event"
        height={150}
      />
      {f && (
        <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
          <Fact label="machine state" value={f.machine_state_name} />
          <Fact label="SoC" value={f.soc != null ? `${f.soc}%` : null} />
          <Fact label="battery" value={f.batt_v != null ? `${f.batt_v} V` : null} />
          <Fact label="total load" value={f.load_w_total != null ? fmtWatts(f.load_w_total) : null} />
          <Fact
            label="L1 at trip"
            value={f.load_w_l1 != null ? `${fmtWatts(f.load_w_l1)} · ${f.load_a_l1} A` : null}
          />
          <Fact
            label="L2 at trip"
            value={f.load_w_l2 != null ? `${fmtWatts(f.load_w_l2)} · ${f.load_a_l2} A` : null}
          />
        </div>
      )}
      <div className="text-muted mt-2" style={{ fontSize: "0.65rem" }}>
        5-second samples around the event; the inverter's hardware latch is the
        authoritative surge record.
      </div>
    </div>
  );
}

export default function EventLog() {
  const [pages, setPages] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(null); // event id

  const fetchPage = (beforeId = null) => {
    setLoading(true);
    const qs = beforeId ? `&before_id=${beforeId}` : "";
    getJSON(`/api/history/events?limit=30${qs}`)
      .then((d) => {
        setPages((p) => [...p, d.items]);
        setHasMore(d.has_more);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => {
    fetchPage();
  }, []);

  const items = pages.flat();
  return (
    <div>
      {items.length === 0 && !loading && (
        <div className="text-muted text-sm py-3 text-center">No events yet</div>
      )}
      <ul className="divide-y divide-border">
        {items.map((ev) => {
          const meta = TYPE_META[ev.type] ?? { icon: "·", color: "var(--muted)" };
          const expandable = meta.flight;
          const isOpen = open === ev.id;
          return (
            <li key={ev.id}>
              <button
                className="w-full flex items-center gap-3 py-2.5 text-left"
                style={{ minHeight: "2.9rem" }}
                onClick={() => expandable && setOpen(isOpen ? null : ev.id)}
                aria-expanded={expandable ? isOpen : undefined}
              >
                <span
                  className="w-7 h-7 rounded-full grid place-items-center shrink-0 text-sm"
                  style={{
                    color: meta.color,
                    background: `color-mix(in srgb, ${meta.color} 15%, var(--surface))`,
                  }}
                >
                  {meta.icon}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium truncate">{title(ev)}</span>
                  {subtitle(ev) && (
                    <span className="block text-muted text-xs truncate tnum">{subtitle(ev)}</span>
                  )}
                </span>
                <span className="text-muted text-xs tnum shrink-0">{fmtEventTime(ev.ts)}</span>
                {expandable && (
                  <span className="text-muted text-xs shrink-0">{isOpen ? "▾" : "▸"}</span>
                )}
              </button>
              {isOpen && <FlightRecorder eventId={ev.id} eventTs={ev.ts} />}
            </li>
          );
        })}
      </ul>
      {hasMore && (
        <button
          className="w-full mt-2 py-2 rounded-lg border border-border text-sm text-muted"
          style={{ minHeight: "2.75rem" }}
          onClick={() => fetchPage(items[items.length - 1].id)}
          disabled={loading}
        >
          {loading ? "loading..." : "load older events"}
        </button>
      )}
    </div>
  );
}
