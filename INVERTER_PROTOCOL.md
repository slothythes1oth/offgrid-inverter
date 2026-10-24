# Inverter protocol & command map (reverse-engineered from the firmware tools)

What this document is: a build-oriented map of how the inverter talks, derived
by reverse-engineering the two files shipped with the firmware update:

- `ASP4860U135H_TMS320F377SPTPT_00_V8.20.9_20250717.bin` — a firmware image for
  one of the inverter's internal MCUs (a TI TMS320F28377 "C2000" control DSP).
- `sriap-1.33Upgrade software.exe` — the vendor's firmware-flashing tool.

It complements [PROVEN.md](PROVEN.md), which holds facts verified against the
live unit. **PROVEN.md wins on any hardware conflict.** This file adds things
that could only be learned from the vendor software, and flags which of them
are confirmed vs. still need a live check.

---

## 1. TL;DR — the load-bearing findings

1. **The inverter is an SRNE OEM unit.** The upgrade tool has the literal string
   `Copyrigt©SRNE Solar Co.,Ltd` / `版权©深圳硕日新能源科技有限公司` baked in.
   Your SunGoldPower SPH6548P is a rebadged **SRNE** hybrid inverter. This is
   direct evidence, not inference — and it validates using the SRNE register map
   the collector already relies on.
2. **The link is Modbus RTU** with the standard Modbus **CRC-16** (poly `0xA001`).
   The tool's own "communication test" is a plain Modbus **function 0x03**
   (read holding registers) frame — exactly the read path the project uses.
3. **A wired USB path into the same Modbus interface exists**, independent of the
   Solarman WiFi stick. The inverter has a USB type-B port that enumerates as a
   serial COM port and speaks the same protocol at a selectable baud
   (9600 / 19200 / 38400 / 57600 / 115200). This is a candidate fallback for the
   flaky stick (see PROVEN.md's outage notes).
4. **A write path exists** (Modbus **function 0x10**, write-multiple-registers).
   The project deliberately never writes; this documents exactly what the write
   capability is so it stays a conscious choice, and flags the one register that
   must never be touched (the bootloader trigger, §6).
5. **The device is multi-MCU.** Firmware comes in four flavors — Normal,
   Communication, Control MCU1, Control MCU2. The `.bin` you have is a *control
   DSP* image. The **Communication MCU** is what serves the Modbus register
   interface you read.

---

## 2. Physical communication interfaces

From the inverter's rear panel (vendor doc photo):

| Port            | Use                                                            |
|-----------------|---------------------------------------------------------------|
| **USB type-B**  | Direct serial/Modbus + firmware upgrade. Enumerates as a COM port. |
| **RS485-1**     | Modbus RTU (the Solarman stick sits here or on its own port).  |
| **CAN / RS485-2** | Battery BMS closed-loop (CAN) / second RS485.               |
| **Dry contact** | Relay signaling (generator start, alarm).                     |
| **Parallel**    | Inter-unit link for stacking multiple inverters.              |

For a dashboard you care about the **Modbus** ports (USB, RS485-1). CAN is BMS
traffic and out of scope for read-only monitoring.

---

## 3. Transport & framing (confirmed from the tool)

- **Protocol:** Modbus RTU (binary, CRC-terminated frames).
- **CRC:** standard Modbus CRC-16, polynomial `0xA001`, low byte first. The tool
  ships the exact `auchCRCHi/auchCRCLo` lookup tables (`iap/crc.py`).
- **Slave address:** default **30** on this unit (vendor upgrade doc says "change
  address 30 → 1 before upgrading"). PROVEN.md reads it at slave id **1** via the
  stick, so the stick presents/normalizes to 1. If you talk to the USB/RS485 port
  directly, expect **30** unless you've changed it in the inverter menu (Setup
  param ID 30).
- **Baud:** selectable; the tool's list is 9600 / 19200 / 38400 / 57600 / 115200.
- **Read function:** `0x03` (read holding registers). Matches PROVEN.md: fn 3 is
  supported, **fn 4 (input registers) is not** — returns AcknowledgeError.
- **Frame layout:** `[addr] [func] [payload…] [CRC_lo] [CRC_hi]`.

---

## 4. Command map — what you can actually send

### Reads (what a dashboard uses)

All reads are Modbus fn `0x03`: `[addr] 03 [reg_hi] [reg_lo] [count_hi] [count_lo] [CRC]`.

| Purpose                     | Register    | Count | Source                          |
|-----------------------------|-------------|-------|---------------------------------|
| Presence / comm test        | `0x0001`    | 1     | tool's `connect()` ping         |
| Part ID / version block     | `0x0061`    | 2     | tool's `readpartid()`           |
| **Live telemetry**          | `0x0100`+   | —     | see [PROVEN.md](PROVEN.md) map  |

The live telemetry registers (SOC, battery V/A, PV, grid, load, machine state,
faults) are **not** in the upgrade tool — it only pings. Those come from the
SRNE register map in PROVEN.md, verified against the physical display. Read them
in **small per-group blocks** (0x0100×18, 0x0210×16, 0x022A×13); one read
spanning the unmapped gaps fails wholesale with IllegalDataAddress.

Key registers (full table and enums in PROVEN.md):

| Register | Meaning          | Scale | Unit |
|----------|------------------|-------|------|
| `0x0100` | Battery SOC      | 1     | %    |
| `0x0101` | Battery voltage  | 0.1   | V    |
| `0x0102` | Battery current  | 0.1   | A    | (negative = charging on this unit) |
| `0x0107`–`0x0111` | PV1/PV2 V/A/W | var | V/A/W |
| `0x0210` | Machine state    | enum  | —    | (enum is shifted −2 on this unit) |
| `0x0213` / `0x022A` | Grid V L1/L2 | 0.1 | V    |
| `0x021B` / `0x0232` | Load W L1/L2 | 1   | W    |
| `0x0200`–`0x0207`   | Fault bits / codes | — | — |

### Writes (exist, but the project does not use them)

Write-multiple-registers is fn `0x10`:
`[addr] 10 [reg_hi] [reg_lo] [cnt_hi] [cnt_lo] [bytecount] [data…] [CRC]`.

The only fn-`0x10` write the tool issues is the **bootloader trigger** (§6) —
do not send it from a dashboard. Setpoint/config registers (charge current,
work mode, TOU windows, on/off) are writable on SRNE units via fn `0x10` /
fn `0x06`, but their addresses are **not** in these files and are **unverified
here** — treat any control feature as a separate, carefully-tested project.

---

## 5. How this maps onto the existing build

- **Register-map source is validated.** The collector uses the SRNE map
  (`esphome-srne-inverter`). The firmware string confirms the unit is genuinely
  SRNE, so that map is the right one.
- **You now have a stick-independent path.** If the Solarman stick misbehaves
  again, the USB type-B port is a wired Modbus-RTU route to the same registers
  (pyserial + a Modbus-RTU lib, or `minimalmodbus`). Address is likely 30 on the
  wire; baud selectable. This does **not** go through TCP 8899, so it sidesteps
  the stick's one-connection fragility entirely.
- **The "no write path" stance is now precise.** The only write the vendor tool
  performs is the bootloader jump at register `0x0438`. Keep the collector
  fn-3-only; if control is ever added, it's fn `0x06`/`0x10` to *config*
  registers, never `0x0438`.

---

## 6. Firmware upgrade sequence (documented so nobody triggers it by accident)

The tool (`iap/iapup.py → SerialUpApp`) flashes over serial in these steps:

1. **Enter bootloader** — Modbus fn `0x10` write to register **`0x0438`**, two
   registers: `[firmware_type]` and `[upgrade_baud ÷ 100]`. Frame:
   `[addr] 10 04 38 00 02 04 [fw_hi] [fw_lo] [baud/100_hi] [baud/100_lo] [CRC]`.
   `firmware_type`: 0 Normal, 1 Communication, 2 Control MCU1, 3 Control MCU2.
2. Switch to the upgrade baud, wait for the device to ACK the command.
3. Wait for the bootloader's **`C` (0x43)** start-of-transfer character.
4. **Stream the `.bin`** in an XMODEM/YMODEM-style flow: 1024-byte packets, each
   ACK'd (`0x06`) / retried on NAK (`0x15`), cancel on `0x18`, end on EOT `0x04`.
   Control bytes: SOH=`0x01`, STX=`0x02`, ETX=`0x03`, EOT=`0x04`, ACK=`0x06`,
   NAK=`0x15`, CAN=`0x18`, CTRL-Z=`0x1A`, START=`C`/`0x43`.

**Safety:** register `0x0438` is the "drop to bootloader" trigger. A monitoring
app must never write it. Reading is always safe; this whole sequence is
write-initiated, so a fn-3-only collector cannot start it.

---

## 7. Recommended downstream toolchain

Because the unit is confirmed SRNE, the open-source ecosystem applies directly:

- **`esphome-srne-inverter`** — the register map already in use (canonical).
- **`pysolarmanv5`** — current path via the Solarman stick over TCP 8899.
- **`minimalmodbus` / `pymodbus`** — for the direct USB/RS485 path (fn 3 reads,
  standard CRC-16 as documented above).
- Solar Assistant / Home Assistant SRNE integrations — useful as cross-checks on
  register meanings, but PROVEN.md is the authority for *this* unit (the machine-
  state enum and battery-current sign both differ from the generic SRNE docs).

---

## 8. Provenance & confidence

| Fact | Confidence | Basis |
|------|-----------|-------|
| Manufacturer = SRNE | **Confirmed** | literal copyright string in the .exe |
| Modbus RTU + CRC-16 `0xA001` | **Confirmed** | CRC tables + frames in the tool |
| Read = fn 0x03; comm-test reg 0x0001 | **Confirmed** | tool `connect()` |
| Write = fn 0x10 exists; bootloader reg 0x0438 | **Confirmed** | tool `sendupcmd_serial()` |
| USB port speaks the same Modbus | **Confirmed** (tool uses it) | tool + panel photo |
| On-wire slave address = 30 by default | **Likely** | vendor doc; verify on USB/RS485 |
| Multi-MCU (Normal/Comm/Ctrl1/Ctrl2) | **Confirmed** | tool's firmware-type list |
| Live telemetry register meanings | **Verified separately** | PROVEN.md (not these files) |
| Config/control register addresses | **Unknown** | not present in these files |

The `.bin` itself is compiled C2000 DSP machine code with no readable strings, so
it does not yield a register map directly; everything above comes from the
upgrade tool (a PyInstaller-packed Python/PyQt5 app, decompiled) plus the vendor
operation document.
