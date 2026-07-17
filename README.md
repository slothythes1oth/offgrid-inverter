# solarmon — solar/backup monitoring collector (phase 1)

Read-only monitoring for a SunGoldPower SPH6548P inverter + 3x Eco-Worthy
Cubix100 48V bank, via the Solarman logger stick on the LAN.

Requirements: [SPEC.md](SPEC.md). Verified hardware behavior: [PROVEN.md](PROVEN.md)
(PROVEN.md wins any conflict). This phase is the collector daemon only; the
web dashboard is a later phase and runs as a separate process.

## What the collector does

Polls the inverter every 5 seconds over one gentle, persistent connection
(Modbus function 3 only — no write path exists anywhere in this codebase),
decodes the registers, and writes to SQLite (`data/solarmon.db`, WAL mode).
On top of that it maintains: 1-minute rollups, outage detection (15s
debounce) with an outage ledger, fault capture with the same-poll load
snapshot, sampled peak tracking, gap detection across restarts, 30-day raw
retention, and optional ntfy alerts.

## Start / stop

```powershell
cd "C:\Users\Nikhil Work\Claude\Personal projects\homeback up inverter"
.venv\Scripts\python -m solarmon.main            # start (Ctrl+C to stop cleanly)
.venv\Scripts\python -m solarmon.main --once     # single poll, print, exit
```

- Ctrl+C writes a `collector_stop` event. A hard kill is fine too: the next
  start writes a `gap_detected` event instead, which is the honest record.
- Never run two collectors at once: the stick tolerates one connection.
  (`--once` also counts; don't run it while the daemon is up.)

## Keep the laptop awake (required for continuous data)

Alerts and data collection stop when this laptop sleeps. On AC power:

Settings > System > Power & battery > Screen and sleep >
"When plugged in, put my device to sleep after" = **Never**.
(Screen off is fine; sleep is not.)

Optional, to run as a service that survives logouts/reboots: Task Scheduler >
Create Task > trigger "At startup", action
`C:\...\homeback up inverter\.venv\Scripts\python.exe -m solarmon.main`,
start in the project folder, "Run whether user is logged on or not". NSSM
works too if you prefer a real Windows service.

## Configuration

Everything lives in [config.yaml](config.yaml), validated at startup.
Notables:

- `alerts.ntfy_topic`: empty = alerts off (every would-be alert logs as
  `[dry-run]`). Set a topic (e.g. `solarmon-<random>`), subscribe in the ntfy
  app, restart the collector.
- `thresholds.low_soc_alert_pct` (default 40): low-battery alert during an
  outage.
- `database.retention_days_raw` (default 30): raw 5s samples pruned after
  this; 1-minute rollups, events, and outages are kept forever.
- TOU rates under `tou:` — update when Hydro One changes rates. Ontario stat
  holidays live in `src/solarmon/data/ontario_holidays.json` (2025–2030);
  extend with `.venv\Scripts\python scripts\gen_holidays.py 2025 2035`.

## Database

- Location: `data/solarmon.db` (plus `-wal`/`-shm` sidecars while running).
- Back up by copying the file while the collector is stopped, or use
  `sqlite3 data/solarmon.db ".backup backup.db"` while it runs.
- Only the collector writes. Anything else must open read-only
  (`file:...?mode=ro`).

## Logs

`data/collector.log` (rotating, 3x5 MB) and console. One line per poll:

```
2026-07-17T15:58:05 INFO collector poll ok soc=98 load_w=488 batt_v=54.1 batt_w=-795.3 grid_v=119.3 state=2 fault=0 ms=527
```

`batt_w` sign: negative = charging, positive = discharging (confirmed live
both directions, see PROVEN.md).

## When the stick misbehaves

The collector follows PROVEN.md automatically: per-read retries, then backoff
and ONE clean reconnect; if connecting fails outright it waits out the
~4-minute lockout once and tries once more. If the stick still refuses, it
logs `STICK LOCKED OUT` and retries gently every 4 minutes — it never
hammers. If that error persists across several cycles, power-cycle the stick.

## Testing and simulation

```powershell
.venv\Scripts\python -m pytest -q          # 65 unit tests, no hardware needed
.venv\Scripts\python -m ruff check .       # lint
.venv\Scripts\python scripts\simulate.py   # full outage+fault scenario on a fake
                                           # source + throwaway DB, dry-run alerts
```

## Dashboard (phase 2: API + web app)

A separate, read-only web app: a FastAPI backend that reads the collector's
SQLite database (never the stick) and a React (Vite + Tailwind) frontend with
a live SSE stream. The collector and the web app are independent processes.

### Run it

```powershell
# 1. Build the frontend once (outputs web/dist, which the API serves)
cd web ; npm install ; npm run build ; cd ..

# 2. Start the API (serves the API + the built frontend on one port)
.venv\Scripts\python -m solarmon-web            # or: python -m solarapi
#   defaults: host 0.0.0.0 (LAN), port 8080
```

Then open `http://<laptop-LAN-ip>:8080/` on your phone (find the IP with
`ipconfig`). The collector must also be running for live data.

For frontend development with hot reload: `cd web ; npm run dev` (Vite proxies
`/api` to the backend on 8080).

### Install to your iPhone home screen

Open the URL in Safari > Share > Add to Home Screen. It launches standalone
(no browser chrome), dark, with the status bar over the app background, and
respects the notch safe areas.

### Endpoints

`GET /api/current` (decoded state + derived), `/api/samples/recent`,
`/api/settings`, `/api/health`, `/api/stream` (SSE). All read-only.
Add `?snapshot` to any page URL to load a single frame instead of the live
stream (handy for debugging / headless capture).

### Notes

- Freshness is driven by data age, not connection state: if the collector
  dies, the UI shows the stale banner within seconds and grays the last
  values, even though the SSE socket is still open. It recovers on its own
  when the collector returns (no reload).
- `npm audit` reports two advisories in the Vite/esbuild dev-server chain.
  They affect the dev server only (a malicious site you visit while
  `npm run dev` is running could reach it); the production artifact FastAPI
  serves is static files with no esbuild. Not fixed here because the only fix
  is a two-major Vite bump. Don't run `npm run dev` on an untrusted network.
- Per-pack battery health (SoC/temp/cell voltages) is not in the inverter's
  register map, so the Home health strip shows bank-level data (fault state +
  battery voltage) rather than the "3 packs OK - 24C" mock in the spec. That
  gains real data when the battery RS232/BT feed is added.

## Known limits (v1, by design)

- **Sleeping laptop = no data, no alerts.** Gaps are recorded and shown as
  gaps, never interpolated.
- **Sampled peaks:** 5s polling cannot see sub-5s surges. The inverter's own
  latched fault (captured with its trigger snapshot) is the authoritative
  surge record.
- **Bank-level data only:** per-pack SoC/temps/cell voltages are not in the
  inverter's register map. Pack-level alerts (protection, pack-count) exist
  in the alert engine but have no data source until the battery RS232/BT
  feed is added.
- **Machine-state enum:** this unit reports states shifted from the SRNE
  documentation (see PROVEN.md). Outage detection is voltage-driven and
  tolerant of both encodings.
