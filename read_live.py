"""
Stage 2 + 3: one gentle connection, read the live-data blocks, print raw and
decoded values. Read-only. Register map from the SRNE hybrid Modbus protocol
(v1.7), as used by the ESPHome SRNE component:
  https://github.com/RAR/esphome-srne-inverter/blob/HEAD/REGISTER_MAP.md

We read two contiguous blocks to minimise requests:
  A) 0x0100..0x0111  (battery + PV)
  B) 0x0210..0x021B  (machine state, grid, load)
"""
import time
from pysolarmanv5 import PySolarmanV5, NoSocketAvailableError

IP = "192.168.50.82"
SERIAL = 3565365971

# (register, name, scale, unit, signed)
FIELDS = [
    (0x0100, "Battery SOC",        1,   "%",  False),
    (0x0101, "Battery voltage",    0.1, "V",  False),
    (0x0102, "Battery current",    0.1, "A",  True),   # +charge / -discharge
    (0x0107, "PV1 voltage",        0.1, "V",  False),
    (0x0108, "PV1 current",        0.1, "A",  False),
    (0x0109, "PV1 power",          1,   "W",  False),
    (0x0111, "PV2 power",          1,   "W",  False),
    (0x0210, "Machine state",      1,   "(enum)", False),
    (0x0213, "Grid voltage L1",    0.1, "V",  False),
    (0x022A, "Grid voltage L2",    0.1, "V",  False),
    (0x021B, "Load power L1",      1,   "W",  False),
    (0x0232, "Load power L2",      1,   "W",  False),
    (0x021F, "Load percent L1",    1,   "%",  False),
    (0x0236, "Load percent L2",    1,   "%",  False),
]

def connect(retries=8, wait=5):
    for attempt in range(1, retries + 1):
        try:
            return PySolarmanV5(IP, SERIAL, port=8899, mb_slave_id=1, socket_timeout=8)
        except NoSocketAvailableError:
            print(f"  connect busy ({attempt}/{retries}); waiting {wait}s...")
            time.sleep(wait)
    raise SystemExit("Could not connect. The stick may need a power-cycle.")

def s16(v):
    return v - 0x10000 if v >= 0x8000 else v

def read_block(modbus, addr, qty, retries=3):
    for _ in range(retries):
        try:
            return modbus.read_holding_registers(addr, qty)
        except Exception:  # noqa
            time.sleep(0.4)
    return None

def main():
    modbus = connect()
    read_block(modbus, 0x0100, 1)  # warm-up; first packet often dropped

    # Read in small contiguous groups that avoid the unmapped gaps. If a group
    # fails as a whole (one illegal address kills the request), fall back to
    # reading just the FIELDS registers inside that group, one at a time.
    field_addrs = [reg for reg, *_ in FIELDS]
    regs = {}
    for base, qty in [(0x0100, 18), (0x0210, 16), (0x022A, 13)]:
        vals = read_block(modbus, base, qty)
        if vals:
            for i, v in enumerate(vals):
                regs[base + i] = v
        else:
            for reg in field_addrs:
                if base <= reg < base + qty:
                    one = read_block(modbus, reg, 1)
                    if one:
                        regs[reg] = one[0]
    modbus.disconnect()

    if not regs:
        print("No data returned.")
        return

    states = {0: "Power-up delay", 1: "Waiting", 2: "Initialization",
              3: "Soft start", 4: "Mains powered", 5: "Inverter powered",
              6: "Inverter to Mains", 7: "Mains to Inverter",
              8: "Battery activate", 9: "Shutdown by user", 10: "Fault"}

    print(f"{'Register':<10}{'Name':<20}{'Raw':>8}   {'Decoded':>12}")
    print("-" * 56)
    for reg, name, scale, unit, signed in FIELDS:
        if reg not in regs:
            print(f"0x{reg:04x}    {name:<20}{'(n/a)':>8}")
            continue
        raw = regs[reg]
        val = s16(raw) if signed else raw
        dec = round(val * scale, 2)
        extra = f"  [{states.get(raw, '?')}]" if reg == 0x0210 else ""
        print(f"0x{reg:04x}    {name:<20}{raw:>8}   {dec:>7} {unit}{extra}")

    # Derived, screen-comparable totals
    print("-" * 56)
    bv = regs.get(0x0101, 0) * 0.1
    ba = s16(regs.get(0x0102, 0)) * 0.1
    load_total = regs.get(0x021B, 0) + regs.get(0x0232, 0)
    pv_total = regs.get(0x0109, 0) + regs.get(0x0111, 0)
    # Confirmed off-grid on 2026-07-17: positive current = DISCHARGING.
    # Provisional until observed during an actual charge cycle (sun/grid).
    direction = "discharging" if ba >= 0 else "charging"
    print(f"Battery power (V x A):   {round(bv * abs(ba))} W  ({direction})")
    print(f"Total load (L1 + L2):    {load_total} W")
    print(f"Total PV (PV1 + PV2):    {pv_total} W")

if __name__ == "__main__":
    main()
