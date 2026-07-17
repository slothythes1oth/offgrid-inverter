"""
Stage 2 (cont.): find where live data sits. Scan holding registers in small
blocks, retry timeouts once, and print any block that has a non-zero value.
Read-only.
"""
import time
from pysolarmanv5 import PySolarmanV5, NoSocketAvailableError

IP = "192.168.50.82"
SERIAL = 3565365971

def connect(retries=6, wait=3):
    """The stick accepts only one TCP connection at a time and can take a few
    seconds to free up. Retry politely instead of failing."""
    for attempt in range(1, retries + 1):
        try:
            return PySolarmanV5(IP, SERIAL, port=8899, mb_slave_id=1, socket_timeout=8)
        except NoSocketAvailableError:
            print(f"  connect busy (attempt {attempt}/{retries}); waiting {wait}s...")
            time.sleep(wait)
    raise SystemExit("Could not get a connection to the stick after retries.")

def read_block(modbus, addr, qty, retries=2):
    last = None
    for _ in range(retries):
        try:
            return modbus.read_holding_registers(addr, qty), None
        except Exception as e:  # noqa
            last = e
            time.sleep(0.3)
    return None, last

def main():
    modbus = connect()

    # Warm-up read (first packet after connect is often dropped).
    read_block(modbus, 0x0200, 1)

    qty = 8
    for base in range(0x0000, 0x0400, qty):
        vals, err = read_block(modbus, base, qty)
        if vals is None:
            name = type(err).__name__ if err else "None"
            # Only report errors that are not the very common ones, to cut noise
            if name not in ("Empty", "IllegalDataAddressError"):
                print(f"ERR @0x{base:04x}: {name}: {err}")
            continue
        if any(v != 0 for v in vals):
            pairs = ", ".join(f"[{base+i}]={v}" for i, v in enumerate(vals))
            print(f"DATA @0x{base:04x}: {pairs}")

    modbus.disconnect()

if __name__ == "__main__":
    main()
