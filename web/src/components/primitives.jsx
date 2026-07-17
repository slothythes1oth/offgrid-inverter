// Reusable design-system primitives (SPEC section 7). Rendered together in
// the /gallery route for review before pages are assembled.

import { LEVEL_COLOR } from "../format";
import { BoltIcon, CheckIcon, PlugIcon, WarningIcon } from "./icons";

const ICONS = { check: CheckIcon, bolt: BoltIcon, warning: WarningIcon, plug: PlugIcon };

export function Card({ title, children, className = "" }) {
  return (
    <div
      className={`rounded-2xl bg-surface border border-border p-4 ${className}`}
    >
      {title && (
        <div className="text-muted text-sm font-medium mb-2">{title}</div>
      )}
      {children}
    </div>
  );
}

// Full-width hero banner: color + icon + word, always all three.
export function StatusBanner({ level, word, icon, sub }) {
  const Icon = ICONS[icon] || CheckIcon;
  const color = LEVEL_COLOR[level] || LEVEL_COLOR.ok;
  return (
    <div
      className="rounded-2xl px-5 py-4 flex items-center gap-3"
      style={{ background: `color-mix(in srgb, ${color} 16%, var(--surface))`, borderLeft: `5px solid ${color}` }}
      role="status"
    >
      <span style={{ color }} className="shrink-0">
        <Icon width={32} height={32} />
      </span>
      <div className="min-w-0">
        <div className="text-2xl font-bold tracking-tight" style={{ color }}>
          {word}
        </div>
        {sub && <div className="text-muted text-sm truncate">{sub}</div>}
      </div>
    </div>
  );
}

// Circular SoC gauge (pure SVG). size/stroke configurable for Home vs Outage.
export function SocRing({ soc, size = 200, stroke = 16, label = "State of charge" }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, soc ?? 0));
  const dash = (pct / 100) * c;
  const color =
    pct <= 20 ? "var(--danger)" : pct <= 40 ? "var(--warn)" : "var(--ok)";
  return (
    <div className="relative inline-grid place-items-center" role="img" aria-label={`${label}: ${Math.round(pct)} percent`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--surface-2)" strokeWidth={stroke} fill="none" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={color}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          style={{ transition: "stroke-dasharray 0.6s ease, stroke 0.4s ease" }}
        />
      </svg>
      <div className="absolute text-center">
        <div className="tnum font-bold leading-none" style={{ fontSize: size * 0.28 }}>
          {soc == null ? "--" : Math.round(pct)}
          <span style={{ fontSize: size * 0.12 }}>%</span>
        </div>
      </div>
    </div>
  );
}

// Horizontal load gauge with a safe-zone threshold marker.
export function LoadGauge({ value, max, threshold, label, big = false }) {
  const pct = Math.max(0, Math.min(100, ((value ?? 0) / max) * 100));
  const tPct = threshold ? Math.min(100, (threshold / max) * 100) : null;
  const over = threshold != null && value > threshold;
  const color = over ? "var(--danger)" : pct > 75 ? "var(--warn)" : "var(--accent)";
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        {label && <span className="text-muted text-sm">{label}</span>}
        <span className={`tnum font-semibold ${big ? "text-3xl" : "text-lg"}`}>
          {value == null ? "--" : Math.round(value)} W
        </span>
      </div>
      <div className="relative h-3 rounded-full bg-surface-2 overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: color, transition: "width 0.5s ease, background 0.3s" }}
        />
        {tPct != null && (
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-text/70"
            style={{ left: `${tPct}%` }}
            title="safe zone limit"
          />
        )}
      </div>
    </div>
  );
}

// Subtle "updated Xs ago" freshness indicator.
export function Freshness({ ageText, connected }) {
  return (
    <div className="text-muted text-xs flex items-center gap-1.5 tnum">
      <span
        className="inline-block w-1.5 h-1.5 rounded-full"
        style={{ background: connected ? "var(--ok)" : "var(--muted)" }}
      />
      {ageText || "connecting..."}
    </div>
  );
}

// Full-width banner shown when data is stale / disconnected.
export function StaleBanner({ ageText }) {
  return (
    <div
      className="rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm"
      style={{ background: "color-mix(in srgb, var(--warn) 18%, var(--surface))", color: "var(--warn)" }}
      role="alert"
    >
      <WarningIcon width={18} height={18} />
      <span className="font-medium">Data not updating</span>
      <span className="opacity-80">· last {ageText}</span>
    </div>
  );
}

// Compact power-flow mini diagram: source word, arrow, target word stacked so
// it always fits a narrow two-column card (no horizontal clipping at 390px).
const FLOW_PARTS = {
  grid_to_house: ["Grid", "House"],
  grid_to_battery: ["Grid", "Battery"],
  battery_to_house: ["Battery", "House"],
  idle: null,
};
export function FlowDiagram({ flow }) {
  const parts = FLOW_PARTS[flow];
  if (!parts) {
    return (
      <div className="flex items-center justify-center h-full min-h-[3.5rem]">
        <span className="text-base font-semibold text-muted">{flow ? "Idle" : "--"}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center justify-center gap-2 h-full min-h-[3.5rem]">
      <span className="text-base font-semibold text-text">{parts[0]}</span>
      <span className="text-accent text-xl leading-none">→</span>
      <span className="text-base font-semibold text-text">{parts[1]}</span>
    </div>
  );
}

// Collapsed gray health strip; colors/expands only on a problem.
export function HealthStrip({ ok, text, detail }) {
  return (
    <div
      className="rounded-xl px-4 py-2 text-sm flex items-center gap-2"
      style={{
        background: "var(--surface)",
        color: ok ? "var(--muted)" : "var(--warn)",
        border: `1px solid ${ok ? "var(--border)" : "var(--warn)"}`,
      }}
    >
      <span
        className="inline-block w-2 h-2 rounded-full"
        style={{ background: ok ? "var(--muted)" : "var(--warn)" }}
      />
      <span>{text}</span>
      {!ok && detail && <span className="opacity-80">· {detail}</span>}
    </div>
  );
}
