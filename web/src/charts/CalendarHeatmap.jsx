// Usage calendar heatmap (SPEC 8B.5): GitHub-style grid of days colored by
// daily kWh, with a $ toggle (TOU-costed), a bolt badge on outage days, and
// tap-a-day opens that day's load profile. Newest week on the right;
// horizontally scrollable back through history.

import { useMemo, useRef, useEffect, useState } from "react";

const CELL = 30; // px, comfortably tappable alongside the 44pt row height
const GAP = 4;

function heatColor(v, max) {
  if (v == null || max <= 0) return "var(--surface-2)";
  const f = Math.min(1, v / max);
  // Accent ramp: 12% floor so any-data days read differently from no-data.
  const pct = 12 + Math.round(f * 78);
  return `color-mix(in srgb, var(--accent) ${pct}%, var(--surface-2))`;
}

export default function CalendarHeatmap({ items, onSelectDay }) {
  const [money, setMoney] = useState(false);
  const scrollRef = useRef(null);

  const byDate = useMemo(() => new Map(items.map((d) => [d.date, d])), [items]);

  // Build a contiguous run of weeks (columns), Mon-Sun rows, ending today.
  const weeks = useMemo(() => {
    if (!items.length) return [];
    const first = new Date(`${items[0].date}T12:00:00`);
    const last = new Date(`${items[items.length - 1].date}T12:00:00`);
    // Back up to the Monday on/before the first day.
    const start = new Date(first);
    start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
    const cols = [];
    const d = new Date(start);
    while (d <= last) {
      const col = [];
      for (let i = 0; i < 7; i++) {
        const p = (n) => String(n).padStart(2, "0");
        const key = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
        col.push({ key, inRange: d >= first && d <= last, month: d.getMonth(), day: d.getDate() });
        d.setDate(d.getDate() + 1);
      }
      cols.push(col);
    }
    return cols;
  }, [items]);

  const max = useMemo(() => {
    const vals = items.map((d) => (money ? d.cost_cents.total : d.total_kwh));
    return Math.max(0, ...vals);
  }, [items, money]);

  // Start scrolled to the newest week.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [weeks]);

  const monthLabel = (col, i) => {
    // Label a column when it contains the 1st, or it's the first column.
    const firstOfMonth = col.find((c) => c.day === 1);
    if (i === 0 || firstOfMonth) {
      const c = firstOfMonth ?? col[0];
      return new Date(`${c.key}T12:00:00`).toLocaleDateString([], { month: "short" });
    }
    return null;
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-muted text-xs">
          {money ? "daily supply cost" : "daily energy"}
        </span>
        <button
          onClick={() => setMoney((m) => !m)}
          className="px-3 rounded-lg text-sm border border-border tnum"
          style={{
            minHeight: "2.35rem",
            color: money ? "var(--text)" : "var(--muted)",
            background: money ? "var(--surface-2)" : "transparent",
          }}
        >
          $
        </button>
      </div>
      <div ref={scrollRef} className="overflow-x-auto pb-1" style={{ WebkitOverflowScrolling: "touch" }}>
        <div className="inline-block">
          <div className="flex" style={{ gap: GAP }}>
            {weeks.map((col, i) => (
              <div key={col[0].key} className="flex flex-col" style={{ gap: GAP }}>
                <div className="text-muted" style={{ fontSize: "0.6rem", height: 12 }}>
                  {monthLabel(col, i)}
                </div>
                {col.map((c) => {
                  const d = byDate.get(c.key);
                  const v = d ? (money ? d.cost_cents.total : d.total_kwh) : null;
                  return (
                    <button
                      key={c.key}
                      onClick={() => d && onSelectDay?.(c.key)}
                      disabled={!d}
                      aria-label={
                        d
                          ? `${c.key}: ${money ? `$${(v / 100).toFixed(2)}` : `${v} kWh`}${d.outage ? ", outage" : ""}`
                          : `${c.key}: no data`
                      }
                      className="relative rounded"
                      style={{
                        width: CELL,
                        height: CELL,
                        background: c.inRange ? heatColor(v, max) : "transparent",
                        opacity: c.inRange ? 1 : 0,
                      }}
                    >
                      {d?.outage && (
                        <span
                          className="absolute -top-1 -right-1 text-[0.6rem] leading-none"
                          style={{ color: "var(--warn)" }}
                          title="outage this day"
                        >
                          ⚡
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between mt-1">
        <span className="text-muted" style={{ fontSize: "0.65rem" }}>
          tap a day to open its load profile · ⚡ = outage
        </span>
        <span className="flex items-center gap-1 text-muted" style={{ fontSize: "0.65rem" }}>
          less
          {[0.15, 0.4, 0.7, 1].map((f) => (
            <span key={f} className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: heatColor(f * (max || 1), max || 1) }} />
          ))}
          more
        </span>
      </div>
    </div>
  );
}
