# Proven local-read facts (hand-off for the dashboard build)

Everything below is verified against the live inverter on 2026-07-17. Read-only.
This is the input spec for the dashboard; the dashboard itself is not built yet.

## Connection

- Stick IP: `192.168.50.82`
- Logger serial (numeric, for pysolarmanv5): `3565365971`
  - NOT the sticker string `SR-2507240240288-301704` (that's a product code).
  - The numeric serial was read out of the stick's own reply header.
- Local port: TCP `8899` (open on this firmware).
- Library: `pysolarmanv5` 3.0.6, in `.venv`. Modbus slave id `1`.
- Inverter uses **holding registers (function 3)**. Input registers (fn 4) are
  NOT supported (return AcknowledgeError).

## Hard-won connection constraints (these drove a mid-build outage)

- The stick tolerates ~**one local TCP connection at a time** and dislikes rapid
  reconnects. Hammering it with several short-lived connections made it refuse
  port 8899 for ~3.5 minutes before it recovered on its own.
- Design rules for the dashboard:
  1. Open **one** connection and **reuse** it for all polling. Never reconnect
     per read.
  2. Poll gently — every ~5 seconds is plenty (cloud app only updates ~5 min).
  3. The first read right after connect is often dropped: do a throwaway
     warm-up read, and retry individual reads 2-3x.
  4. On repeated failure, back off (wait seconds), then reconnect once. Show
     "disconnected/stale" in the UI rather than crashing or hammering.
  5. A single clean reconnect is fine; a reconnect *storm* is what breaks it.
- The cloud app and battery closed loop do NOT use port 8899 and are unaffected.

## Register map (SRNE hybrid, holding registers, fn 3)

Source: https://github.com/RAR/esphome-srne-inverter (REGISTER_MAP.md), verified
against the inverter's physical display.

| Register | Meaning            | Scale | Unit | Notes |
|----------|--------------------|-------|------|-------|
| 0x0100   | Battery SOC        | 1     | %    | |
| 0x0101   | Battery voltage    | 0.1   | V    | |
| 0x0102   | Battery current    | 0.1   | A    | see sign note |
| 0x0107   | PV1 voltage        | 0.1   | V    | |
| 0x0108   | PV1 current        | 0.1   | A    | |
| 0x0109   | PV1 power          | 1     | W    | |
| 0x0111   | PV2 power          | 1     | W    | |
| 0x0210   | Machine state      | enum  | -    | see enum below |
| 0x0213   | Grid voltage L1    | 0.1   | V    | 0 = no grid |
| 0x022A   | Grid voltage L2    | 0.1   | V    | |
| 0x021B   | Load power L1      | 1     | W    | |
| 0x0232   | Load power L2      | 1     | W    | |
| 0x021F   | Load percent L1    | 1     | %    | |
| 0x0236   | Load percent L2    | 1     | %    | |
| 0x0200-0x0203 | Fault bits    | -     | -    | all 0 = no faults |
| 0x0204-0x0207 | Fault codes   | -     | -    | up to 4 active |

Derived: Battery power = V x A. Total load = L1 + L2. Total PV = PV1 + PV2.

**Read in separate small blocks per group** (e.g. 0x0100 x18, then 0x0210 x16,
then 0x022A x13). A single read that spans the unmapped gaps fails wholesale
with IllegalDataAddress. `read_live.py` shows the working pattern + fallback.

Machine state enum (0x0210): 0 Power-up delay, 1 Waiting, 2 Initialization,
3 Soft start, 4 Mains powered, 5 Inverter powered, 6 Inverter to Mains,
7 Mains to Inverter, 8 Battery activate, 9 Shutdown by user, 10 Fault.

## Open item to confirm later

- **Battery current sign convention.** Confirmed on 2026-07-17: off-grid, no PV,
  feeding load -> register reads **positive while discharging**. So positive =
  discharge on this unit. This is provisional from one sample; confirm the
  charging case (midday sun, or grid charging) shows the expected sign before
  trusting the direction label. A robust dashboard can instead infer direction
  from the power balance (PV + grid vs load) rather than the current sign.

## Confirmed live snapshot (2026-07-17, off-grid)

SOC 96%, battery 52.8 V / ~11 A discharging (~600 W), PV 0 W, grid 0 V,
load L1 312 W + L2 154 W = ~466 W total, machine state 3.

## Files

- `read_live.py`  - the working one-shot reader/decoder (Stage 2+3). KEEP.
- `discover_serial.py`, `discover_serial2.py`, `read_raw.py`, `scan_holding.py`
  - scratch/diagnostic scripts used to find the serial and the register block.
    Safe to delete; kept for reference.
