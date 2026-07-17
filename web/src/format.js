// Display formatting. Edge values are in SI-ish units already (W, V, %, kWh);
// these helpers only choose precision/labels per the five-second rule.

export function fmtW(w) {
  if (w == null) return "--";
  const a = Math.abs(w);
  if (a >= 1000) return `${(w / 1000).toFixed(1)} kW`;
  return `${Math.round(w)} W`;
}

// Whole watts, no decimals: used on glance pages (Home).
export function fmtWInt(w) {
  return w == null ? "--" : `${Math.round(w)} W`;
}

export function fmtPct(p) {
  return p == null ? "--" : `${Math.round(p)}%`;
}

export function fmtAge(s) {
  if (s == null) return "";
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m ago`;
}

export function fmtDuration(s) {
  if (s == null) return "--";
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

export function fmtHours(h, capped) {
  if (capped) return "> 24 hrs";
  if (h == null) return "--";
  return `${h.toFixed(1)} hrs`;
}

// Status derivation: the single source of truth for color+icon+word.
// Priority: fault > on battery > stale/no-data > normal.
export function deriveStatus(state, stale) {
  if (!state || state.no_data) {
    return { level: "danger", word: "NO DATA", icon: "warning" };
  }
  if (state.fault_active) {
    return { level: "danger", word: "FAULT", icon: "warning" };
  }
  if (state.on_battery) {
    return { level: "warn", word: "ON BATTERY", icon: "bolt" };
  }
  if (stale) {
    return { level: "warn", word: "STALE", icon: "warning" };
  }
  return { level: "ok", word: "All Normal", icon: "check" };
}

export const LEVEL_COLOR = {
  ok: "var(--ok)",
  warn: "var(--warn)",
  danger: "var(--danger)",
};
