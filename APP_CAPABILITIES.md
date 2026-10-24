# App capability map — what a user-controlled app can do

Reconstructed from the protocol map ([INVERTER_PROTOCOL.md](INVERTER_PROTOCOL.md))
and verified hardware behavior ([PROVEN.md](PROVEN.md)). This is a *what's
possible* catalog for planning — it separates:

- ✅ **Have it** — data/registers already verified on this unit.
- 🟡 **Reachable** — real on SRNE units, but the register address is **not**
  proven from your files; confirm against `esphome-srne-inverter` + a bench read
  before trusting.
- 🔴 **Write** — requires the control path the project currently forbids.

Everything in §1–§2 is **fn-3 read-only** and safe. §3 is control, deliberately
walled off.

---

## 1. Monitoring — raw signals available

### ✅ Verified live signals (already decoded by the collector)

| Signal | Register | Unit | Notes |
|--------|----------|------|-------|
| Battery SOC | `0x0100` | % | primary "fuel gauge" |
| Battery voltage | `0x0101` | V | |
| Battery current | `0x0102` | A | **− = charging, + = discharging** (this unit) |
| PV1 voltage / current / power | `0x0107`–`0x0109` | V/A/W | |
| PV2 power | `0x0111` | W | |
| Machine state | `0x0210` | enum | enum shifted −2 here; {2,4}=mains, {3,5}=inverting |
| Grid voltage L1 / L2 | `0x0213` / `0x022A` | V | 0 = no grid (per-leg ~120 V) |
| Load power L1 / L2 | `0x021B` / `0x0232` | W | |
| Load percent L1 / L2 | `0x021F` / `0x0236` | % | |
| Fault bits / codes | `0x0200`–`0x0207` | — | up to 4 active |

### 🟡 Extended signals SRNE units expose (verify addresses before use)

These are standard on the SRNE register map but were **not** in your firmware
files — treat as a to-confirm list, not gospel:

- **Temperatures** — inverter/heatsink temp, DC-DC temp, battery temp. High value
  for health + fan/derating context.
- **Built-in energy accumulators** — daily & total kWh for PV, battery
  charge/discharge, load, grid. **If present, prefer these over integrating power
  yourself** — they survive collector downtime.
- **Grid/output frequency**, apparent power (VA), power factor.
- **Battery config read-back** — charge-current setting, cutoff voltages,
  work-mode/output-priority as *read* values (useful to display even if you never
  write them).

---

## 2. Monitoring — KPIs & dashboards you can build

### Instantaneous (direct from a single poll)

- **Power-flow diagram** — PV → battery/load, grid ↔ load, battery ↔ load, with
  live watts on each arrow. Direction from the **power balance** (PV + grid vs
  load), not the current sign — matches the PROVEN.md design rule.
- **Fuel gauge** — SOC %, battery V/A, instantaneous charge/discharge W.
- **Source badge** — "On grid" / "On battery" / "Fault" from machine state +
  grid voltage.
- **Home load now** — total load W (L1+L2), per-leg balance, load %.
- **Health strip** — active faults, machine state, (🟡 temps when confirmed).

### Derived over time (you have SQLite history + a collector)

- **Backup runtime remaining** — SOC × usable kWh ÷ current load W → "≈ N h at
  this load." The headline KPI for a backup system.
- **Energy dashboard** — kWh/day for load, battery in/out, grid import, PV
  harvest (integrate power, or 🟡 read accumulators). Daily/weekly/monthly rollups.
- **Cost / TOU** — $ today & this month using `costs.py` + TOU rates in
  `config.yaml`; "battery saved you $X by covering peak."
- **Self-sufficiency %** — share of load served by battery+PV vs grid.
- **Outage log** — start/end/duration + kWh delivered on battery, from grid-V→0
  and machine-state transitions (flight-recorder pattern already in the build).
- **Battery behavior** — SOC cycling depth, charge/discharge cycles/day,
  round-trip efficiency (kWh out ÷ kWh in), voltage sag under load.
- **Load profile** — average load by hour-of-day/day-of-week; peak load & when.

### Alerting (push/ntfy)

- Grid lost / restored (outage start/end).
- SOC below threshold → "≈ N h of backup left."
- Any fault code active; machine state = Fault.
- Data stale / stick disconnected (collector heartbeat).
- 🟡 Over-temp or approaching derate (once temp regs confirmed).

---

## 3. Remote command / control (the "nice to have")

**Reality check first.** None of the control register *addresses* are in the
files you gave me — the vendor tool only reads a ping register and writes the
one **forbidden** bootloader register (`0x0438`). So control is genuinely
possible (SRNE units accept Modbus **fn 0x06 / 0x10** writes) but every address
below is 🟡 **unverified** and must be pulled from the verified SRNE map and
bench-tested one at a time.

### What SRNE hybrids typically let you write

- **Output on/off** (inverter enable).
- **Output/charge source priority** — e.g. Solar → Battery → Grid ordering,
  Solar-only vs Solar+Grid charging.
- **Max charge current** and **grid-charge current**.
- **Battery cutoffs** — low-voltage/low-SOC disconnect, back-to-grid / back-to-
  battery SOC thresholds.
- **TOU charge/discharge windows.**

The high-value, low-risk remote actions for *your* use case are probably:
force-charge before a storm, cap grid-charge current, flip output priority for a
TOU window — all setpoint writes, not real-time control.

### Control architecture (if you build it)

The monitoring stance ("collector is the only thing that touches the link, fn-3
only") is exactly right and control must not break it:

1. **Single writer.** Only the collector issues writes, on the *same* reused
   connection it polls with. The web app never touches the link — it enqueues a
   command; the collector drains the queue between polls.
2. **Register allowlist.** A hard-coded set of writable registers with
   min/max/step per register. **`0x0438` is permanently blacklisted.** Anything
   not on the allowlist is rejected before it reaches the wire.
3. **Read-back verify.** After every write, read the register back and confirm
   the value took; surface success/failure in the UI. Never fire-and-forget.
4. **Auth + audit.** Control endpoints behind real auth (the read dashboard can
   stay open on the LAN; writes cannot). Log every command: who, when, old→new,
   confirmed value.
5. **Confirm-to-commit UX.** Show the exact change ("Grid-charge current 20 A →
   40 A") and require an explicit confirm for anything that affects power flow.
6. **Path caveat.** Writes may not work through the Solarman stick at all (many
   are read-only gateways). The **direct USB/RS485 path** (from
   INVERTER_PROTOCOL.md §2) is the more reliable control route — plan for it, and
   test writes there first.

### What to *not* do remotely

- Anything touching firmware/bootloader (`0x0438`) — bricking risk.
- Battery cutoff voltages without understanding the Eco-Worthy BMS limits — the
  BMS and inverter must agree or you get nuisance trips.
- Real-time/fast control loops over Modbus — the link is for setpoints, not PWM.

---

## 4. Suggested build order

1. **Confirm the 🟡 extended reads** (temps, energy accumulators, frequency) —
   pure upside, no risk, fills out the dashboards in §2.
2. **Ship the derived KPIs** — backup-runtime, energy/cost, outage log,
   self-sufficiency — mostly SQLite queries over data you already collect.
3. **Only then** consider control: start with a single read-back-verified write
   (e.g. grid-charge current) over the USB/RS485 path, behind auth, before any
   broader control surface.
