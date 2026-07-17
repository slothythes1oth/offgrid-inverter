// TOU day-ring (SPEC 8B.4): a 24-hour clock dial. Outer ring segments are
// colored by the day's actual rate bands (straight from the TOU engine via
// the API, so seasonal windows and holidays are always right); radial bars
// show load by hour; a "now" marker points at the current time when viewing
// today. Bands use the app's semantic colors: off-peak green, mid amber,
// on-peak red — matching the status system. Fallback if this proves
// unreadable at checkpoint review: the 24h band strip (same data, linear).

import { useEffect, useMemo, useState } from "react";

import { getJSON } from "../api";
import { rateQS } from "../rates";

const BAND_COLOR = {
  off_peak: "var(--ok)",
  mid_peak: "var(--warn)",
  on_peak: "var(--danger)",
};
const BAND_LABEL = { off_peak: "off-peak", mid_peak: "mid-peak", on_peak: "on-peak" };

const CX = 160;
const CY = 160;
const RING_R = 138; // band ring centerline
const RING_W = 13;
const BAR_R0 = 56; // bars grow from here...
const BAR_R1 = 124; // ...to here at max kWh

const rad = (deg) => ((deg - 90) * Math.PI) / 180; // hour 0 at top, clockwise
const pt = (deg, r) => [CX + r * Math.cos(rad(deg)), CY + r * Math.sin(rad(deg))];

function arcPath(a0, a1, r, w) {
  const [x0, y0] = pt(a0, r);
  const [x1, y1] = pt(a1, r);
  const large = a1 - a0 > 180 ? 1 : 0;
  return { d: `M ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1}`, w };
}

function localDateStr(d = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

function shiftDate(dateStr, days) {
  const d = new Date(`${dateStr}T12:00:00`);
  d.setDate(d.getDate() + days);
  return localDateStr(d);
}

export default function DayRing() {
  const today = localDateStr();
  const [dateStr, setDateStr] = useState(today);
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    setData(null);
    setFailed(false);
    getJSON(`/api/history/tou/day?date=${dateStr}${rateQS()}`)
      .then((d) => alive && setData(d))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [dateStr]);

  const maxKwh = useMemo(
    () => Math.max(0.05, ...(data?.hours ?? []).map((h) => h.kwh ?? 0)),
    [data]
  );

  const isToday = dateStr === today;
  const nowDeg = isToday
    ? ((new Date().getHours() + new Date().getMinutes() / 60) / 24) * 360
    : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <button
          className="px-3 rounded-lg border border-border text-muted"
          style={{ minHeight: "2.35rem" }}
          onClick={() => setDateStr(shiftDate(dateStr, -1))}
          aria-label="previous day"
        >
          ‹
        </button>
        <span className="text-sm font-medium tnum">
          {new Date(`${dateStr}T12:00:00`).toLocaleDateString([], {
            weekday: "short",
            month: "short",
            day: "numeric",
          })}
          {isToday && " (today)"}
        </span>
        <button
          className="px-3 rounded-lg border border-border text-muted"
          style={{ minHeight: "2.35rem", opacity: isToday ? 0.3 : 1 }}
          onClick={() => !isToday && setDateStr(shiftDate(dateStr, 1))}
          disabled={isToday}
          aria-label="next day"
        >
          ›
        </button>
      </div>

      {failed && <div className="text-muted text-sm py-3 text-center">Can't reach the API</div>}
      {!failed && !data && <div className="chart-skeleton w-full" style={{ height: 300 }} />}
      {data && (
        <svg viewBox="0 0 320 320" width="100%" role="img" aria-label={`Time-of-use dial for ${dateStr}`}>
          {/* Band ring: one arc per hour in the hour's rate-band color. */}
          {data.hours.map((h, i) => {
            const a0 = (i / 24) * 360 + 0.8;
            const a1 = ((i + 1) / 24) * 360 - 0.8;
            const { d } = arcPath(a0, a1, RING_R, RING_W);
            return (
              <path
                key={h.ts}
                d={d}
                fill="none"
                stroke={BAND_COLOR[h.band]}
                strokeWidth={RING_W}
                opacity="0.45"
              />
            );
          })}

          {/* Radial load bars, colored by their hour's band. */}
          {data.hours.map((h, i) => {
            if (h.kwh == null) return null;
            const mid = ((i + 0.5) / 24) * 360;
            const r1 = BAR_R0 + (BAR_R1 - BAR_R0) * (h.kwh / maxKwh);
            const [x0, y0] = pt(mid, BAR_R0);
            const [x1, y1] = pt(mid, r1);
            return (
              <line
                key={h.ts}
                x1={x0}
                y1={y0}
                x2={x1}
                y2={y1}
                stroke={BAND_COLOR[h.band]}
                strokeWidth="7"
                strokeLinecap="round"
              />
            );
          })}

          {/* Clock anchors. */}
          {[["12a", 0], ["6a", 90], ["12p", 180], ["6p", 270]].map(([lbl, deg]) => {
            const [x, y] = pt(deg, RING_R + RING_W + 8);
            return (
              <text key={lbl} x={x} y={y + 3} textAnchor="middle" fontSize="9" fill="var(--muted)" className="tnum">
                {lbl}
              </text>
            );
          })}

          {/* Now marker: a needle across the ring. */}
          {nowDeg != null && (
            <g>
              <line
                x1={pt(nowDeg, BAR_R0 - 12)[0]}
                y1={pt(nowDeg, BAR_R0 - 12)[1]}
                x2={pt(nowDeg, RING_R + RING_W / 2 + 3)[0]}
                y2={pt(nowDeg, RING_R + RING_W / 2 + 3)[1]}
                stroke="var(--text)"
                strokeWidth="1.6"
              />
              <circle cx={pt(nowDeg, RING_R + RING_W / 2 + 5)[0]} cy={pt(nowDeg, RING_R + RING_W / 2 + 5)[1]} r="2.6" fill="var(--text)" />
            </g>
          )}

          {/* Center: the day's totals. */}
          <text x={CX} y={CY - 8} textAnchor="middle" fontSize="22" fontWeight="700" fill="var(--text)" className="tnum">
            {data.total_kwh.toFixed(1)}
          </text>
          <text x={CX} y={CY + 8} textAnchor="middle" fontSize="10" fill="var(--muted)">
            kWh
          </text>
          <text x={CX} y={CY + 26} textAnchor="middle" fontSize="12" fontWeight="600" fill="var(--text)" className="tnum">
            ${(data.total_cost_cents / 100).toFixed(2)}
          </text>
        </svg>
      )}

      {/* Rate legend with cents/kWh (8B.4). */}
      {data && (
        <div className="flex justify-center gap-4 mt-1 flex-wrap">
          {["off_peak", "mid_peak", "on_peak"].map((b) => (
            <span key={b} className="flex items-center gap-1.5 text-xs text-muted tnum">
              <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: BAND_COLOR[b] }} />
              {BAND_LABEL[b]}{" "}
              {data.rates.all_in_override != null
                ? `${data.rates.all_in_override}¢`
                : `${data.rates[b]}¢`}
              /kWh
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
