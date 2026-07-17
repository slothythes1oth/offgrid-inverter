// Demo / simulated-data mode: `?demo=<mode>` fabricates live state entirely
// in the browser so the outage UI, burn-down, and state-change theatre can be
// reviewed WITHOUT touching the collector or the database (checkpoint rule).
//
// Modes:
//   normal    on grid, charging, quiet
//   outage    active outage, imbalanced legs, real sunrise from /api/settings
//   fault     fault 13 active while on grid (frozen red flow)
//   restore   starts in an outage, grid returns after ~25s (theatre + confirm)
//   blackout  starts normal, grid drops after ~20s (outage theatre + switch)
//
// Values tick every 5s with small jitter so the living flow and gauges move.

const NOMINAL_KWH = 15.36;
const USABLE = 0.8;

function outageState(now, startedTs, soc, l1W, l2W, sunEvents) {
  const total = l1W + l2W;
  const runtimeH = (NOMINAL_KWH * USABLE * (soc / 100) * 1000) / total;
  return {
    ts: now,
    age_s: 0,
    stale: false,
    no_data: false,
    soc,
    batt_v: 51.2,
    batt_a: total / 51.2,
    batt_w: total,
    pv1_w: 0,
    pv2_w: 0,
    pv_w_total: 0,
    grid_v_l1: 0,
    grid_v_l2: 0,
    load_w_l1: l1W,
    load_w_l2: l2W,
    load_w_total: total,
    load_a_l1: +(l1W / 120).toFixed(1),
    load_a_l2: +(l2W / 120).toFixed(1),
    machine_state: 3,
    machine_state_name: "Inverter powered",
    fault_active: false,
    on_battery: true,
    flow: "battery_to_house",
    headroom: {
      continuous_load_w: 6500,
      available_w: Math.max(0, 6500 - total),
      bypass_a_per_leg: 40,
      bypass_w_per_leg: 4800,
    },
    outage: {
      active: true,
      started_ts: startedTs,
      elapsed_s: Math.round(now - startedTs),
      soc_start: 89,
      low_soc_pct: 40,
      sun_events: sunEvents,
      drain_pct_per_hr: 9.1,
      smoothed_draw_w: total,
      runtime_remaining_h: Math.round(runtimeH * 10) / 10,
      runtime_capped: false,
    },
  };
}

function gridState(now, { fault = false, l1W = 312, l2W = 154, chargeW = 795 } = {}) {
  const total = l1W + l2W;
  return {
    ts: now,
    age_s: 0,
    stale: false,
    no_data: false,
    soc: 96,
    batt_v: 54.2,
    batt_a: -chargeW / 54.2,
    batt_w: -chargeW,
    pv1_w: 0,
    pv2_w: 0,
    pv_w_total: 0,
    grid_v_l1: 121.5,
    grid_v_l2: 122.1,
    load_w_l1: l1W,
    load_w_l2: l2W,
    load_w_total: total,
    load_a_l1: +(l1W / 120).toFixed(1),
    load_a_l2: +(l2W / 120).toFixed(1),
    machine_state: fault ? 10 : 2,
    machine_state_name: fault ? "Fault" : "Mains powered",
    fault_active: fault,
    on_battery: false,
    flow: chargeW >= 100 ? "grid_to_battery" : "grid_to_house",
    headroom: {
      continuous_load_w: 6500,
      available_w: Math.max(0, 6500 - total),
      bypass_a_per_leg: 40,
      bypass_w_per_leg: 4800,
    },
    outage: null,
  };
}

const jitter = (w) => Math.max(0, Math.round(w + (Math.random() - 0.5) * 60));

// Fallback sun events if /api/settings is unreachable (pure vite dev).
function fallbackSuns(now) {
  return [
    { type: "sunrise", ts: Math.round(now + 9.5 * 3600) },
    { type: "sunset", ts: Math.round(now + 23 * 3600) },
  ];
}

export function startDemo(mode, push) {
  let suns = null;
  let tick = 0;
  const startedTs = Date.now() / 1000 - 47 * 60; // outage began 47 min ago

  const emit = () => {
    const now = Date.now() / 1000;
    const sunEvents = suns ?? fallbackSuns(now);
    tick += 1;
    switch (mode) {
      case "fault":
        push(gridState(now, { fault: true, l1W: jitter(4800), l2W: jitter(1150), chargeW: 0 }));
        break;
      case "outage":
        push(outageState(now, startedTs, 48, jitter(1700), jitter(470), sunEvents));
        break;
      case "restore":
        if (tick <= 5) push(outageState(now, startedTs, 48, jitter(1700), jitter(470), sunEvents));
        else push(gridState(now, { l1W: jitter(312), l2W: jitter(154) }));
        break;
      case "blackout":
        if (tick <= 4) push(gridState(now, { l1W: jitter(312), l2W: jitter(154) }));
        else push(outageState(now, now - (tick - 4) * 5, 89, jitter(1700), jitter(470), sunEvents));
        break;
      default:
        push(gridState(now, { l1W: jitter(312), l2W: jitter(154) }));
    }
  };

  // Real sunrise/sunset from the backend (offline math) when reachable, so
  // the burn-down can be sanity-checked against tonight's actual sunrise.
  fetch("/api/settings")
    .then((r) => (r.ok ? r.json() : null))
    .then((s) => {
      if (s?.sun_events?.length) suns = s.sun_events;
    })
    .catch(() => {})
    .finally(emit);

  const id = setInterval(emit, 5000);
  return () => clearInterval(id);
}
