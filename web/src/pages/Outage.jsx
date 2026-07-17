import { useEffect, useState } from "react";

import { Card, LoadGauge, SocRing, StaleBanner } from "../components/primitives";
import { fmtDuration, fmtHours } from "../format";

// Outage: the runtime number is the biggest thing in the app. Higher contrast
// and larger type than Home so a non-technical family member can read it fast.
export default function Outage({ state, stale, ageText }) {
  const o = state?.outage;
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  void tick;

  // Elapsed advances locally between pushes off the server-anchored start.
  const elapsed = o ? o.elapsed_s + (state.age_s || 0) : 0;
  const load = state?.load_w_total;
  const cont = state?.headroom?.continuous_load_w ?? 6500;
  const availW = state?.headroom?.available_w ?? 0;

  return (
    <div className="flex flex-col gap-4 max-w-md mx-auto w-full">
      <div
        className="rounded-2xl px-5 py-3 text-center font-bold text-lg"
        style={{ background: "color-mix(in srgb, var(--warn) 20%, var(--surface))", color: "var(--warn)" }}
        role="status"
      >
        ⚡ ON BATTERY
      </div>

      {stale && <StaleBanner ageText={ageText} />}

      {/* Runtime hero: biggest number in the app */}
      <Card className="text-center py-6">
        <div className="text-muted text-sm uppercase tracking-wide mb-1">
          Runtime remaining
        </div>
        <div className="tnum font-extrabold leading-none" style={{ fontSize: "4rem" }}>
          {fmtHours(o?.runtime_remaining_h, o?.runtime_capped)}
        </div>
        <div className="text-muted mt-2">at current load</div>
      </Card>

      <div className="grid grid-cols-2 gap-3 items-center">
        <Card className="grid place-items-center">
          <SocRing soc={state?.soc} size={150} stroke={14} />
        </Card>
        <Card title="Drain rate">
          <div className="tnum text-3xl font-bold">
            {o?.drain_pct_per_hr != null ? `${o.drain_pct_per_hr}%/hr` : "--"}
          </div>
          <div className="text-muted text-sm mt-1">
            dropping{" "}
            {o?.drain_pct_per_hr != null ? `~${Math.abs(o.drain_pct_per_hr)}%/hr` : "steady"}
          </div>
        </Card>
      </div>

      <Card title="Load vs capacity">
        <LoadGauge value={load} max={cont} threshold={cont} label={null} big />
        <div className="mt-3 text-lg">
          <span className="text-muted">Available: </span>
          <span className="tnum font-semibold">
            ~{(availW / 1000).toFixed(1)} kW free
          </span>
        </div>
        <div className="text-muted text-xs mt-1">
          room to turn things on before the {(cont / 1000).toFixed(1)} kW limit
        </div>
      </Card>

      <Card title="Outage elapsed" className="text-center">
        <div className="tnum text-4xl font-bold">{fmtDuration(elapsed)}</div>
      </Card>
    </div>
  );
}
