// Settings: editable TOU rates (SPEC section 5). Defaults come from
// config.yaml via the API; edits live in this browser's localStorage and are
// sent as query params, so the backend stays read-only. Supply-only note +
// the optional all-in override, per spec.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getJSON } from "../api";
import { Card } from "../components/primitives";
import { clearRates, getRates, setRates } from "../rates";

function Field({ label, value, placeholder, onChange, hint }) {
  return (
    <label className="block">
      <span className="text-muted text-xs">{label}</span>
      <input
        type="number"
        inputMode="decimal"
        step="0.1"
        min="0"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg px-3 tnum text-base"
        style={{
          minHeight: "2.75rem",
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          color: "var(--text)",
        }}
      />
      {hint && <span className="text-muted block mt-0.5" style={{ fontSize: "0.62rem" }}>{hint}</span>}
    </label>
  );
}

export default function Settings() {
  const [defaults, setDefaults] = useState(null);
  const stored = getRates();
  const [off, setOff] = useState(stored.off ?? "");
  const [mid, setMid] = useState(stored.mid ?? "");
  const [on, setOn] = useState(stored.on ?? "");
  const [allIn, setAllIn] = useState(stored.all_in ?? "");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getJSON("/api/settings").then((s) => setDefaults(s.tou_rates)).catch(() => {});
  }, []);

  const save = () => {
    setRates({ off, mid, on, all_in: allIn });
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };
  const reset = () => {
    clearRates();
    setOff(""); setMid(""); setOn(""); setAllIn("");
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  return (
    <div className="flex flex-col gap-3 max-w-md mx-auto w-full pb-4">
      <Card title="Electricity rates (¢/kWh)">
        <div className="flex flex-col gap-3">
          <Field label="Off-peak" value={off} onChange={setOff} placeholder={defaults ? `${defaults.off_peak}` : ""} />
          <Field label="Mid-peak" value={mid} onChange={setMid} placeholder={defaults ? `${defaults.mid_peak}` : ""} />
          <Field label="On-peak" value={on} onChange={setOn} placeholder={defaults ? `${defaults.on_peak}` : ""} />
          <Field
            label="All-in override (optional)"
            value={allIn}
            onChange={setAllIn}
            placeholder="off"
            hint="One flat ¢/kWh covering delivery + rebate. When set, it replaces the per-band rates in every cost figure."
          />
          <div className="flex gap-2">
            <button
              onClick={save}
              className="flex-1 rounded-lg font-medium"
              style={{ minHeight: "2.75rem", background: "var(--accent)", color: "#fff" }}
            >
              {saved ? "saved ✓" : "save"}
            </button>
            <button
              onClick={reset}
              className="px-4 rounded-lg border border-border text-muted"
              style={{ minHeight: "2.75rem" }}
            >
              reset to defaults
            </button>
          </div>
          <div className="text-muted" style={{ fontSize: "0.65rem" }}>
            Blank fields use the defaults from config (Hydro One standard TOU,
            Nov 2025 – Oct 2026). Per-band costs are supply-only: delivery and
            the Ontario rebate change the all-in number. Rates are stored on
            this device only.
          </div>
        </div>
      </Card>
      <Link to="/history" className="text-sm underline text-center" style={{ color: "var(--accent)" }}>
        back to History
      </Link>
    </div>
  );
}
