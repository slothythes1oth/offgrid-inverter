// Technical: "show me everything." Bank-level battery card, inverter
// internals with machine_state in words, connection diagnostics, the
// collapsible register table, and the clearly-labeled per-pack placeholder
// (per-pack/cell data is NOT in the inverter register map; future source is
// the battery RS232/BT, out of scope for this build).

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { getJSON } from "../api";
import { Card, StaleBanner } from "../components/primitives";
import { fmtDuration } from "../format";

function Row({ label, value, mono = true }) {
  return (
    <div className="flex justify-between items-baseline py-1">
      <span className="text-muted text-sm">{label}</span>
      <span className={`text-sm font-medium ${mono ? "tnum" : ""}`}>{value ?? "--"}</span>
    </div>
  );
}

// The proven register map (PROVEN.md) with live decoded values. Values are
// stored decoded; the raw integer is value/scale for the curious.
const REGISTERS = (s) => [
  ["0x0100", "Battery SoC", s?.soc, "%"],
  ["0x0101", "Battery voltage", s?.batt_v, "V"],
  ["0x0102", "Battery current (signed; + = discharge)", s?.batt_a?.toFixed?.(1), "A"],
  ["0x0109", "PV1 power", s?.pv1_w, "W"],
  ["0x0111", "PV2 power", s?.pv2_w, "W"],
  ["0x0210", "Machine state (enum)", s?.machine_state, ""],
  ["0x0213", "Grid voltage L1", s?.grid_v_l1, "V"],
  ["0x022A", "Grid voltage L2", s?.grid_v_l2, "V"],
  ["0x021B", "Load power L1", s?.load_w_l1, "W"],
  ["0x0232", "Load power L2", s?.load_w_l2, "W"],
  ["0x021F", "Load percent L1", s?.load_pct_l1, "%"],
  ["0x0236", "Load percent L2", s?.load_pct_l2, "%"],
  ["0x0200-03", "Fault bits (captured on events)", s?.fault_active ? "ACTIVE" : "0", ""],
];

export default function Technical({ state, stale, ageText }) {
  const [diag, setDiag] = useState(null);
  const [showRegs, setShowRegs] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getJSON("/api/diagnostics").then((d) => alive && setDiag(d)).catch(() => {});
    load();
    const id = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const battWord =
    state == null
      ? "--"
      : state.batt_w > 100
        ? "discharging"
        : state.batt_w < -100
          ? "charging"
          : "idle";

  return (
    <div className="flex flex-col gap-3 max-w-md mx-auto w-full pb-4">
      {stale && <StaleBanner ageText={ageText} />}

      <Card title="Battery bank">
        <Row label="State of charge" value={state?.soc != null ? `${state.soc}%` : null} />
        <Row label="Voltage" value={state?.batt_v != null ? `${state.batt_v} V` : null} />
        <Row
          label="Current"
          value={state?.batt_a != null ? `${state.batt_a.toFixed(1)} A · ${battWord}` : null}
        />
        <Row
          label="Power"
          value={state?.batt_w != null ? `${Math.round(Math.abs(state.batt_w))} W ${battWord}` : null}
        />
      </Card>

      <Card title="Per-pack data">
        <div
          className="rounded-xl px-3 py-3 text-sm"
          style={{ background: "var(--surface-2)", color: "var(--muted)" }}
        >
          <span className="font-semibold">Not yet connected.</span> The inverter's
          register map only exposes bank-level battery data. Per-pack SoC,
          temperatures, protection flags, and cell voltages need the battery's
          own RS232/Bluetooth link — a future project. The 3 Cubix100 packs
          report only through the bank figures above.
        </div>
      </Card>

      <Card title="Inverter internals">
        <Row
          label="Machine state"
          value={
            state?.machine_state_name != null
              ? `${state.machine_state_name} (${state.machine_state})`
              : null
          }
          mono={false}
        />
        <Row label="Grid L1 / L2" value={state ? `${state.grid_v_l1} V / ${state.grid_v_l2} V` : null} />
        <Row
          label="Load L1"
          value={state ? `${state.load_w_l1} W · ${state.load_a_l1} A · ${state.load_pct_l1}%` : null}
        />
        <Row
          label="Load L2"
          value={state ? `${state.load_w_l2} W · ${state.load_a_l2} A · ${state.load_pct_l2}%` : null}
        />
        <Row label="PV1 / PV2" value={state ? `${state.pv1_w} W / ${state.pv2_w} W` : null} />
        <div className="flex justify-between items-baseline py-1">
          <span className="text-muted text-sm">Fault</span>
          {state?.fault_active ? (
            <Link to="/history" className="text-sm font-semibold underline" style={{ color: "var(--danger)" }}>
              ACTIVE — see event log
            </Link>
          ) : (
            <span className="text-sm font-medium" style={{ color: "var(--ok)" }}>none</span>
          )}
        </div>
      </Card>

      <Card title="Connection">
        <Row label="Last poll" value={ageText || null} />
        <Row
          label="Success rate"
          value={
            diag
              ? `${diag.success_rate_pct}% (${diag.samples_got}/${diag.samples_expected} in ${fmtDuration(diag.samples_window_s)})`
              : null
          }
        />
        <Row
          label="Collector started"
          value={
            diag?.collector_start_ts != null
              ? new Date(diag.collector_start_ts * 1000).toLocaleString([], {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })
              : null
          }
        />
        <Row label="Gaps (24h)" value={diag?.gap_events_24h} />
        <Row label="Poll interval" value={diag ? `${diag.poll_interval_s}s` : null} />
      </Card>

      <Card>
        <button
          className="w-full flex justify-between items-center text-sm font-medium"
          style={{ minHeight: "2.35rem" }}
          onClick={() => setShowRegs((v) => !v)}
          aria-expanded={showRegs}
        >
          <span className="text-muted">Register table (decoded, live)</span>
          <span className="text-muted">{showRegs ? "▾" : "▸"}</span>
        </button>
        {showRegs && (
          <table className="w-full mt-2 text-xs tnum">
            <thead>
              <tr className="text-muted text-left">
                <th className="py-1 font-medium">reg</th>
                <th className="py-1 font-medium">meaning</th>
                <th className="py-1 font-medium text-right">value</th>
              </tr>
            </thead>
            <tbody>
              {REGISTERS(state).map(([addr, name, val, unit]) => (
                <tr key={addr} className="border-t border-border">
                  <td className="py-1.5 pr-2 text-muted">{addr}</td>
                  <td className="py-1.5 pr-2">{name}</td>
                  <td className="py-1.5 text-right font-medium">
                    {val ?? "--"}
                    {unit && val != null ? ` ${unit}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
