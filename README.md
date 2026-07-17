# solarmon — home backup power monitor

Self-hosted, mobile-first monitoring for a SunGoldPower SPH6548P inverter +
3x Eco-Worthy Cubix100 48V battery bank (grid-backup system, no solar panels
yet), read via the Solarman logger stick on the LAN.

Two independent processes:

- **Collector** (`solarmon`): polls the inverter every 5 s over one gentle,
  persistent connection (Modbus fn 3 only — **no write path exists anywhere
  in this codebase**), decodes registers, writes SQLite. The only process
  that ever touches the stick.
- **Web app** (`solarapi`): read-only FastAPI backend + React frontend with
  a live SSE stream. Reads the database, never the stick.

Requirements live in [SPEC.md](SPEC.md); verified hardware behavior in
[PROVEN.md](PROVEN.md) (PROVEN.md wins any conflict about the hardware).

## Quick start (from a fresh clone)

```powershell
# 1. Python env (3.11+)
python -m venv .venv
.venv\Scripts\pip install -e ".[web,dev]"

# 2. Frontend build (Node 18+; outputs web/dist, which the API serves)
cd web ; npm install ; npm run build ; cd ..

# 3. Check config.yaml: stick IP + serial (from PROVEN.md), thresholds,
#    TOU rates, lat/long (offline sunrise math), ntfy topic (optional).

# 4. Run (two terminals, or install the scheduled tasks below)
.venv\Scripts\python -m solarmon.main    # collector (Ctrl+C stops cleanly)
.venv\Scripts\python -m solarapi         # web app on 0.0.0.0:8080
```

Open `http://<laptop-LAN-ip>:8080/` on your phone (`ipconfig` shows the IP).

**iPhone install:** open the URL in Safari > Share > **Add to Home Screen**.
Launches standalone, dark, notch-safe. Values update every ~5 s.

## The four pages

- **Home** — "are we okay?" Status banner, SoC ring, load bar with L1/L2
  ticks, living energy flow (animated power pulses), health strip. Boring
  when everything is normal, by design.
- **Outage** — auto-switches in when the grid drops (15 s debounce), back to
  Home on restore. Runtime-remaining hero, burn-down projection with offline
  sunrise/sunset markers ("will we make it to morning"), SoC + drain rate,
  twin-leg headroom lanes toward the 40 A bypass ceiling, plain-language
  "~kW free" readout, elapsed timer.
- **History** — load profile (1h/24h/7d/30d, pinch-zoom, threshold lines,
  sampled-peak markers, gaps drawn as gaps), fault/event log with
  flight-recorder cards (±10 min trace + facts at trip), outage history,
  TOU cost + savings (day-ring, calendar heatmap with $ toggle, stacked
  bars; edit rates in `/settings`), battery SoC band + depth-of-discharge.
- **Technical** — bank-level battery data, inverter internals with machine
  state in words, connection diagnostics (success rate, gaps), collapsible
  live register table, and a clearly-labeled "per-pack data: not yet
  connected" section.

Add `?snapshot` to any page URL for a single non-live frame (debugging).
Add `?demo=outage|fault|restore|blackout` to preview those states with
fabricated data — the collector, stick, and DB are never involved.

## Alerts (ntfy)

Alerts fire for: grid lost / restored (after debounce), any inverter fault
(Fault 13 named "bypass overload"), pack protection, and low SoC during an
outage. Deduped: an ongoing outage alerts exactly once, even across collector
restarts.

Setup (~3 minutes):

1. Install the **ntfy** app (App Store) on the iPhone.
2. In the app: **+ > Subscribe to topic** and enter your topic name. Pick
   something unguessable, e.g. `solarmon-bc95eeb2` — ntfy.sh topics are
   public to anyone who knows the name.
3. Put the same topic in `config.yaml` under `alerts.ntfy_topic`, restart
   the collector.
4. Drill: `.venv\Scripts\python scripts\test_alerts.py` sends one test
   message of each type plus a dedupe check (exactly 8 messages). Without a
   topic configured it dry-runs to the log instead.

In the iPhone ntfy app settings, allow notifications and (recommended) set
the topic's priority handling so p5 (outage/fault) breaks through Focus.

## Deployment on this laptop (survives reboots)

```powershell
# elevated PowerShell, one time:
powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1
```

Registers two Scheduled Tasks — **Solarmon Collector** and **Solarmon Web** —
that start at boot (no login needed), restart on failure (10x, 1 min apart),
and have no execution time limit. Remove with the same script + `-Remove`.
Never start a second collector manually while the task is running: the stick
tolerates exactly one connection.

**Power settings (required):** Settings > System > Power & battery > Screen
and sleep > "When plugged in, put my device to sleep after" = **Never**
(screen off is fine, sleep is not), or from a terminal:
`powercfg /change standby-timeout-ac 0`. A sleeping laptop means no data and
no alerts; every wake writes an honest `gap_detected` event.

## Database + backup

- `data/solarmon.db` (WAL mode). Raw 5 s samples pruned after 30 days;
  1-minute rollups, events, and outages are kept forever. ~23 MB per 30 days
  at steady state.
- Backup while running: `.venv\Scripts\python scripts\backup_db.py` — takes
  a consistent snapshot into `data/backups/` (keeps 14). Restore: stop the
  collector, copy a backup over `data/solarmon.db`, start.
- Single-writer discipline: only the collector writes; everything else opens
  read-only (`file:...?mode=ro`).

## Configuration (config.yaml, validated at startup)

- `stick.*` — IP, numeric logger serial, port, slave id (from PROVEN.md).
- `thresholds.*` — continuous 6500 W, bypass 40 A/leg, low-SoC alert 40%.
- `location.*` — lat/long for the offline sunrise/sunset math on the outage
  burn-down. Used only in that formula; never leaves the machine.
- `tou.*` — Hydro One TOU rates (defaults Nov 2025–Oct 2026); optional
  all-in override. Rates edited in the app's Settings screen live in the
  browser only and recompute server-side per request. Ontario stat holidays:
  `src/solarmon/data/ontario_holidays.json` (2025–2030); extend with
  `scripts/gen_holidays.py 2025 2035`.
- `alerts.ntfy_topic` — empty = alerts off (dry-run logged).
- `database.retention_days_raw`, `polling.*`, `logging.*`.

## Logs

`data/collector.log` (rotating, 3x5 MB — rotation is built in, the process
never needs a restart for it) and console. One line per poll:

```
2026-07-17T15:58:05 INFO collector poll ok soc=98 load_w=488 batt_v=54.1 batt_w=-795.3 grid_v=119.3 state=2 fault=0 ms=527
```

`batt_w` sign: negative = charging, positive = discharging (confirmed live,
both directions — PROVEN.md).

## When the stick misbehaves

The collector follows PROVEN.md automatically: per-read retries, then backoff
and ONE clean reconnect; if the port refuses it waits out the ~4-minute
lockout once and retries gently forever after. It never hammers. If
`STICK LOCKED OUT` persists across many cycles, power-cycle the stick. The
cloud app and the battery's closed loop are unaffected either way.

## Testing

```powershell
.venv\Scripts\python -m pytest -q            # 93 tests, no hardware needed
.venv\Scripts\python -m ruff check src tests # lint (black for format)
.venv\Scripts\python scripts\simulate.py     # full outage+fault scenario on a
                                             # fake source + throwaway DB
.venv\Scripts\python scripts\test_alerts.py  # alert drill (see Alerts above)
```

## Known limits (v1, by design)

- **Sleeping laptop = no data, no alerts.** Gaps are recorded and rendered
  as gaps — never interpolated.
- **Sampled peaks:** 5 s polling cannot see sub-5-second surges. Peaks are
  always labeled "sampled"; the inverter's own latched fault (captured with
  its trigger snapshot in the event log) is the authoritative surge record.
- **Alerts only while awake and on the LAN** — see the deployment section.
- **LAN-only:** the dashboard is reachable only on the home network (see
  Future below for the remote path).
- **Bank-level battery data only:** per-pack SoC/temps/cells are not in the
  inverter's register map. The alert engine already handles pack events;
  they gain a data source when the battery RS232/BT feed is added.
- **Machine-state enum shift:** this unit reports states shifted from the
  SRNE docs (PROVEN.md). Outage detection is voltage-driven and tolerant of
  both encodings.
- `npm audit` flags the Vite/esbuild **dev server** chain (moderate). The
  production artifact is static files served by FastAPI — unaffected. Don't
  run `npm run dev` on an untrusted network; the fix is a two-major Vite
  bump, deferred.

## Future

- **Hosted split:** the collector and web app are already decoupled through
  the database, so the later move is: dashboard hosted remotely + a small
  local bridge that pushes collector data up. A config change and a sync
  layer, not a rewrite. Do not build cloud sync into v1.
- **Remote access sooner:** [Tailscale](https://tailscale.com) on the laptop
  + phone gives the existing LAN dashboard (and even the SSE stream) a
  private remote path with zero code changes. This is the intended interim
  answer before any hosted split.
- **Per-pack battery data** via the Cubix100 RS232/Bluetooth link — feeds
  the Technical page's placeholder section and the pack alerts.
