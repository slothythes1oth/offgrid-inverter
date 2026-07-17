# solarmon — solar/backup monitoring collector

Read-only monitoring for a SunGoldPower SPH6548P inverter + 3x Eco-Worthy
Cubix100 48V bank, via the Solarman logger stick on the LAN.

Requirements live in [SPEC.md](SPEC.md); verified hardware behavior in
[PROVEN.md](PROVEN.md) (PROVEN.md wins any conflict). This phase builds the
collector daemon only — no web server yet.

**Status: under construction (checkpoint a — scaffold, config, schema).**
The full runbook (start/stop, power settings, backups, known limits) lands at
the end of this phase.

## Quick start (current state)

```powershell
.venv\Scripts\python -m pip install -e ".[dev]"   # once
.venv\Scripts\python -m pytest -q                  # tests
.venv\Scripts\python -m solarmon.main              # smoke: config + DB init
```

Configuration: `config.yaml` (validated at startup). Database: `data/solarmon.db`
(SQLite, WAL). Logs: `data/collector.log` + console.
