"""
Stage 2: smallest real read. Connect with the real IP + serial and read a
few blocks of registers, printing RAW values. Read-only; no writes.

Goal: see even one plausible number (a voltage, a percentage) that clearly
comes from the inverter. Decoding into labelled quantities is Stage 3.
"""
from pysolarmanv5 import PySolarmanV5

IP = "192.168.50.82"
SERIAL = 3565365971

def main():
    modbus = PySolarmanV5(IP, SERIAL, port=8899, mb_slave_id=1, socket_timeout=10)

    # Probe several small blocks in both register spaces. For each block we
    # print whatever comes back, or the error, then move on.
    probes = [
        ("holding", 0x0100, 8),
        ("holding", 0x0200, 8),
        ("holding", 0x0000, 8),
        ("input",   0x0100, 8),
        ("input",   0x0200, 8),
        ("input",   0x0000, 8),
    ]

    for space, addr, qty in probes:
        try:
            if space == "holding":
                vals = modbus.read_holding_registers(addr, qty)
            else:
                vals = modbus.read_input_registers(addr, qty)
            # Show address:value pairs in both decimal and hex.
            pairs = ", ".join(
                f"[{addr+i}]={v} (0x{v:04x})" for i, v in enumerate(vals)
            )
            print(f"OK  {space:8} @0x{addr:04x} x{qty}: {pairs}")
        except Exception as e:
            print(f"ERR {space:8} @0x{addr:04x} x{qty}: {type(e).__name__}: {e}")

    modbus.disconnect()

if __name__ == "__main__":
    main()
