# Solar Dashboard SPEC (master requirements)

Read this together with PROVEN.md, which is the verified ground truth for the
connection, register map, and stick behavior. If this spec and PROVEN.md ever
disagree about the hardware, PROVEN.md wins.

## 1. What we are building

A self-hosted, mobile-first monitoring dashboard for a SunGoldPower SPH6548P
inverter + 3x Eco-Worthy Cubix100 48V battery bank (grid-backup system, no
solar yet). Two components:

1. **Collector**: headless Python daemon. Owns the single persistent
   connection to the Solarman stick, polls every 5 seconds, detects events,
   writes to SQLite. The only process that ever touches the stick.
2. **Web app**: FastAPI backend + React frontend. Reads SQLite, serves the
   dashboard and a Server-Sent Events live stream. Never connects to the stick.

Strictly read-only against the inverter: Modbus function code 3 only. No write
path may exist anywhere in the codebase.

Deployment now: owner's Windows laptop (sleeps sometimes; gaps are expected
and must be handled honestly). Deployment later: dashboard possibly hosted
remotely with the collector remaining on the LAN pushing data up. Do not build
cloud sync in v1, but keep collector and web app decoupled so that split is a
config change, not a rewrite.

## 2. Hard connection rules (from PROVEN.md, non-negotiable)

- One persistent connection, reused for all polling. Never reconnect per read.
- Poll every ~5 seconds. Warm-up read after connect. Retry individual reads
  2-3x. On repeated failure: back off seconds, then ONE clean reconnect.
  Never a reconnect storm (it locks the stick out for minutes).
- Read holding registers (fn 3) in the small block groups PROVEN.md documents;
  spanning unmapped gaps fails wholesale.
- Stick IP, logger serial, slave id, port: from config, seeded from PROVEN.md.
- On sustained failure, mark data stale and keep the UI honest; never crash.

## 3. Data model (SQLite, WAL mode)

- `samples`: one wide row per poll (~5s). ts, soc, batt_v, batt_a, batt_w,
  pv1_w, pv2_w, grid_v_l1, grid_v_l2, load_w_l1, load_w_l2, load_w_total,
  load_pct_l1, load_pct_l2, machine_state, fault_active (bool).
- `rollup_1m`: per minute: avg/min/max of load_w_total, batt_w, soc; sample
  count. Built continuously by the collector.
- `events`: ts, type (fault_raised, fault_cleared, grid_lost, grid_restored,
  pack_protection, low_soc, collector_start, collector_stop, gap_detected),
  detail JSON (fault codes, snapshot of the poll that triggered it).
- `outages`: started_ts, ended_ts, duration_s, soc_start, soc_end, kwh_used.
- `config`/`meta`: schema version, settings snapshot.

Retention: raw `samples` pruned after 30 days. `rollup_1m`, `events`,
`outages` kept forever. Prune job runs daily inside the collector.

Single-writer discipline: only the collector writes. The web app opens
read-only connections.

## 4. Derived metrics and algorithms

- Total load = L1 + L2. Total PV = PV1 + PV2. Battery power = V x A.
- **Flow direction**: infer from power balance (PV + grid presence vs load),
  NOT from the battery current sign (PROVEN.md flags the sign as provisional).
- **On battery / on grid**: grid considered down when grid_v_l1 reads ~0 AND
  machine_state = 5 (Inverter powered). Debounce: state must persist for 3
  consecutive polls (~15s) before an outage is declared or ended. Log an
  `outages` row and events on both edges.
- **Runtime remaining** (outage page): usable_kWh_remaining / smoothed_draw.
  Smoothed draw = exponential moving average of discharge power over ~10 min.
  Usable capacity: 15.36 kWh nominal x usable fraction (config, default 0.8)
  x SoC. Display as "~X.X hrs at current load"; if draw is near zero show
  "> 24 hrs". Never show a jumpy raw-instant estimate.
- **Fault capture**: every poll reads fault bits/codes (0x0200-0x0207) and
  machine_state. Any nonzero fault -> event with codes + the same-poll load
  snapshot. Fault 13 gets its plain-language name in the UI ("bypass
  overload"). The inverter latches faults in hardware; this is the
  authoritative surge record. Do not pretend 5s sampling captures surges.
- **Sampled peaks**: track max load seen per day/week/all-time with timestamp,
  always labeled "sampled peak" in the UI.
- **Gap handling**: on collector start, if the last sample is old, write a
  `gap_detected` event. Charts must render gaps as gaps (no interpolation).

## 5. TOU cost engine (Ontario, Hydro One, standard TOU)

- Rates configurable, defaults (Nov 2025 - Oct 2026): off-peak 9.8, mid-peak
  15.7, on-peak 20.3 cents/kWh.
- Off-peak: weekdays 7 PM - 7 AM, all weekend, Ontario statutory holidays
  (include the holiday list; make it a data file).
- Seasonal window swap on May 1 / Nov 1: summer on-peak 11 AM - 5 PM, winter
  on-peak 7 - 11 AM and 5 - 7 PM; mid-peak fills the remaining weekday
  daytime. Implement as a pure, unit-tested function ts -> rate band.
- Compute: daily/weekly/monthly kWh consumed by band and cost; grid-charging
  kWh and cost separately (energy flowing into the battery from grid); and
  "peak avoidance savings" = kWh served from battery during on-peak x
  (on-peak - off-peak rate). Show costs as supply-only with a note that
  delivery/rebate change the all-in number; allow an optional all-in
  cents/kWh override in settings.

## 6. Alerts (ntfy)

Collector POSTs to a configurable ntfy topic. Alert on:
- Grid lost (on battery) and grid restored, after the 15s debounce.
- Any inverter fault raised (name Fault 13 explicitly) and cleared.
- Battery pack protection flag or pack count dropping below 3.
- SoC below threshold during an outage (default 40%, config).
Rules: dedupe (no repeat alert for the same ongoing condition), include the
key numbers in the message (SoC, load, duration), critical priority for
outage/fault. Known limit, documented in README: if the collector host is
asleep, no alerts; this is accepted for v1.

## 7. Design system

- Dark theme default (respect prefers-color-scheme), system font stack
  (renders SF Pro on iPhone), tabular-nums for all live values.
- Card-based layout, consistent spacing scale, one accent color.
- Status is ALWAYS color + icon + word (never color alone): green/check/
  "All Normal", amber/lightning/"ON BATTERY", red/warning/"FAULT".
- Global freshness: subtle "updated Xs ago" everywhere; a full-width banner
  when data is stale/disconnected (per PROVEN.md rule 4).
- Five-second rule on Home and Outage: most important element on top, no
  decimals on glance pages, progressive disclosure for detail.

## 8. Pages

### Home ("are we okay?")
1. Status banner (hero): full width, state word + icon + color.
2. SoC ring: large SVG circular gauge, percentage centered.
3. Two cards side by side: current load with horizontal bar vs safe zone
   (thresholds: continuous 6500W; bypass limit ~40A/leg shown when on grid);
   power-flow mini diagram (grid->house, grid->battery, battery->house) with
   one-word label.
4. Health strip: collapsed gray line "3 packs OK · 24C" when fine; expands
   and colors only on pack drop/imbalance/overtemp.
No charts, no decimals. Boring when normal.

### Outage (auto-switches in when grid drops, per owner choice)
1. Hero: runtime remaining, biggest number in the app, "at current load".
2. SoC + drain rate: "48% · dropping ~9%/hr".
3. Load vs headroom gauge, prominent, danger zone explicit.
4. "Available capacity" readout in plain terms (~kW free) so a non-technical
   family member can judge turning something on.
5. Elapsed outage timer.
Higher contrast, larger type than Home. Returns to Home on grid restore
(with a "back on grid" confirmation state).

### History ("what's my pattern, why did it trip?") - priority order
1. Load profile chart: ECharts time series, windows 1h/24h/7d/30d, threshold
   overlays, sampled peaks marked, touch zoom/pan. Uses rollups for long
   windows, raw for short.
2. Fault/event log: reverse-chron list, tappable to the captured snapshot.
3. Outage history: list + rollup stats (count, avg duration, kWh per outage).
4. TOU cost and savings: consumption by band, grid-charge cost, peak-
   avoidance savings; editable rates in settings.
5. Battery health trends: daily min/max SoC, DoD distribution over time.

### Technical ("show me everything")
Per-pack cards (SoC, V, A, temp, protection flags), cell voltages with
min/max/spread highlighted, inverter internals (L1/L2, PV registers,
machine_state in words, raw fault bits), connection diagnostics (last poll,
success rate, collector uptime), collapsible raw register table.
Note: per-pack and cell-level data are NOT in the current inverter register
map. Phase 1 ships bank-level only; the Technical page shows bank data plus
a clearly labeled "per-pack data: not yet connected" section. (Future source:
battery RS232/Bluetooth; out of scope for this build.)

## 9. iPhone / PWA requirements

- PWA manifest + apple-touch-icon; installable to home screen, standalone
  display, theme-color matching the dark background.
- Safe-area insets (notch), 100dvh layouts, no hover-dependent UI,
  touch targets >= 44pt, -webkit-tap-highlight handled.
- Charts must be smooth on a phone: use rollups + ECharts sampling for long
  ranges; target < 200ms interaction response.
- Test target: iPhone Safari, portrait. Desktop is secondary but must not
  be broken.

## 10. Engineering standards

- Python 3.11+, typed, pydantic models for config and records, ruff + black.
- pytest units for: TOU band function (including holiday + seasonal swap
  edges), runtime estimator, outage debounce, downsampler/pruner, alert
  dedupe. Collector logic testable against a fake register source.
- Structured logging (one line per poll cycle summary; events at INFO).
- Single config file (config.yaml or .env): stick IP/serial/port/slave id,
  thresholds, capacity/usable fraction, TOU rates, ntfy topic, retention.
- Simple versioned schema migrations (a migrations table + numbered SQL).
- Frontend: Vite + React + Tailwind + ECharts; SSE for live data (EventSource
  reconnects natively); component structure per page; no state library
  needed beyond React.
- Runbook README: start/stop, laptop power settings (disable sleep on AC),
  Windows service option (Task Scheduler or NSSM), where the DB lives, how
  to back it up, known limits (gaps, sampled peaks, alerts-only-when-awake).
- License-clean dependencies only.
