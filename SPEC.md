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

## 8A. Charts (design + behavior, applies to every chart in the app)

Charts get the same design care as the pages. A default ECharts config is not
acceptable. All charts share one theme module so they look like one product.

Shared theme:
- Dark background matching the app; no chart border/box. Gridlines faint
  (low-opacity), horizontal only; no vertical gridlines.
- Axis labels in the muted secondary text color; tabular-nums; sensible unit
  suffixes (W, kW, %, V). Y-axis starts at 0 for power/load; auto for voltage.
- One accent color for the primary series; thresholds and bands use semantic
  colors (amber = caution, red = danger) consistent with the status system.
- Smooth line, subtle area gradient fill under it, no data-point dots except
  on marked peaks/events. Line thin but legible on a phone.
- Time axis: labels adapt to window (HH:mm for 1h/24h, ddd for 7d, MMM d for
  30d). Always show the user's local timezone.

Interaction (touch-first):
- Tap-and-hold / drag shows a tooltip with the value and timestamp at that
  point; tooltip never runs off-screen on a narrow phone.
- Pinch to zoom and one-finger pan on the time axis (ECharts dataZoom, inside
  type). A "reset zoom" affordance appears once zoomed.
- No hover-only behavior anywhere (phones have no hover).

Data integrity (non-negotiable):
- Gaps render as GAPS: break the line where samples are missing (connectNulls
  false). Never interpolate across a collector-down gap. A faint "no data"
  shading over gap spans is a plus.
- Short windows (1h, 24h) read raw `samples`; long windows (7d, 30d) read
  `rollup_1m`; pick the source by window, and when zoomed into a long window
  far enough, allow fetching finer data for the visible span.
- Downsample for render so a 30d view never ships hundreds of thousands of
  points to the phone (server-side bucketing or ECharts sampling); target
  smooth interaction, < 200ms response to zoom/pan.

Empty / loading / stale states (every chart must handle all three):
- Loading: skeleton or spinner, never a flash of empty axes.
- No data yet (fresh install): a friendly "collecting data, check back soon"
  message, not a broken chart.
- Stale: if the underlying data is stale, the chart dims slightly and shows
  the same freshness treatment as the rest of the app.

Per-chart specifics:
- **Load profile** (History #1): primary series = total load (W/kW). Two
  horizontal threshold lines via markLine: continuous rating 6500W, and the
  bypass limit (~40A/leg -> compute the W equivalent, label it). Sampled
  peaks marked with a labeled point + timestamp, clearly tagged "sampled".
  Optional secondary faint series: SoC on a right axis, toggleable.
- **Battery trends** (History #5): daily min/max SoC as a band (area between
  min and max) with the mean line; DoD shown as a small companion bar or as
  a summary stat, whichever reads cleaner on mobile.
- **TOU cost** (History #4): a simple stacked bar by rate band (off/mid/on-
  peak) per day or per week; keep it a bar, not a line; label totals.
- Home and Outage pages remain ECharts-free by design. Their visual elements
  (SoC ring, load gauges, flow diagram, burn-down) are custom SVG per
  sections 7 and 8B.

## 8B. Signature visualizations (build on 8A; function first, then flourish)

Principles: SVG/CSS-first (no canvas unless a piece cannot hit performance
targets otherwise); every animation throttled to the poll cadence; respect
prefers-reduced-motion with a defined static fallback; portrait thumb-zone
layout; each signature piece has a plain fallback (the pre-8B version) if it
cannot hit the < 200ms interaction bar on iPhone.

1. **Living energy flow** (Home + Outage, replaces the static flow diagram).
   Three nodes: grid, battery, home. SVG paths between them carry animated
   pulses (stroke-dashoffset animation) in the direction of power flow;
   pulse speed and path thickness scale with watts (3 buckets is enough).
   Direction comes from the power-balance logic, never the current sign.
   States: grid->home + grid->battery (normal/charging, green tones);
   battery->home with grid node dimmed (outage, amber); fault state freezes
   flow and shows the red status treatment. Reduced motion: static arrows
   with W labels. Update at poll cadence, no faster.
2. **Twin-leg headroom lanes** (Outage page; Home keeps the single total bar
   with small L1/L2 tick marks). Two horizontal lanes, L1 and L2, in amps,
   filling toward a hard labeled ceiling line at the bypass limit (~40A).
   Semantic fill colors (green -> amber -> red zones). Leg imbalance must be
   visible at a glance. Below the lanes: the plain-language available
   capacity readout from the Outage page spec.
3. **Outage burn-down** ("will we make it to morning", Outage page, below
   the runtime hero). Projected SoC line from now toward empty at the
   smoothed draw, rendered in the 8A chart style. Markers: the low-SoC
   alert threshold, projected-empty time label, and local sunrise/sunset
   computed offline from configured lat/long (a small suncalc-style
   function; no network calls, config stays local). If draw is near zero,
   show a flat line with "> 24 hrs" instead of a misleading slope.
4. **TOU day-ring** (History, cost section). A 24-hour clock dial: ring
   segments colored by the current season's rate bands (off/mid/on-peak,
   from the TOU engine so it is always correct), radial bars around the
   ring showing load by hour for the selected day (default: last 24h), and
   a "now" marker. Rate legend with cents/kWh. If the radial form proves
   unreadable on a small screen at checkpoint review, the fallback is a
   24h horizontal band strip with the same coloring.
5. **Usage calendar heatmap** (History). GitHub-style grid of days colored
   by daily kWh with a $ toggle (TOU-costed); outage days badged with a
   bolt icon; tap a day to open that day's load profile. Month view default,
   scrollable back.
6. **Fault flight-recorder card** (History, event detail; upgrades the
   plain expandable snapshot). Tapping a fault event opens a report card:
   a +/- 10 minute load mini-trace around the event with the trip moment
   marked, and a facts panel: fault codes with plain-language names,
   machine state, SoC, per-leg watts/amps at trip. Same card pattern for
   pack-protection events with the relevant battery numbers.
7. **High-water marks** (load profile chart). Sampled peaks rendered as
   small tick + date markers at their height, flood-marker style, always
   tagged "sampled". Show day/week/all-time marks; declutter below 24h
   windows.
8. **State-change theatre** (app-wide). On outage start/end and fault
   raise/clear, the app's accent temperature and banner transition together
   so the state change is felt (a shift, not a flash). Reduced motion:
   instant swap. Never color-only: the banner word and icon always change
   with it.

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
  thresholds, capacity/usable fraction, TOU rates, ntfy topic, retention,
  and location lat/long for the offline sunrise math (default: Bracebridge,
  ON: 45.04, -79.31). Location is used only in the local sunrise formula
  and never leaves the machine.
- Simple versioned schema migrations (a migrations table + numbered SQL).
- Frontend: Vite + React + Tailwind + ECharts; SSE for live data (EventSource
  reconnects natively); component structure per page; no state library
  needed beyond React.
- Runbook README: start/stop, laptop power settings (disable sleep on AC),
  Windows service option (Task Scheduler or NSSM), where the DB lives, how
  to back it up, known limits (gaps, sampled peaks, alerts-only-when-awake).
- License-clean dependencies only.
