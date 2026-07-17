"""
Read-only serial discovery via the stick's own reply.

We send ONE well-formed Modbus read request wrapped in a V5 frame, using a
placeholder logger serial. The stick stamps its REAL serial into bytes 7..11
of any reply it sends. We read those bytes and print the real serial.

Nothing is written to the inverter or battery. If the firmware drops
wrong-serial requests, we simply get no reply and stop.
"""
import struct
from umodbus.client.serial import rtu
from pysolarmanv5 import PySolarmanV5

IP = "192.168.50.82"
PLACEHOLDER_SERIAL = 0  # dummy; only used to provoke a reply

def main():
    modbus = PySolarmanV5(
        IP,
        PLACEHOLDER_SERIAL,
        port=8899,
        mb_slave_id=1,
        socket_timeout=10,
        verbose=False,
    )
    # Try a few common read requests; any reply reveals the serial.
    attempts = [
        ("holding 0x0100 x1", lambda: rtu.read_holding_registers(1, 0x0100, 1)),
        ("input 0x0100 x1", lambda: rtu.read_input_registers(1, 0x0100, 1)),
        ("holding 0x0000 x1", lambda: rtu.read_holding_registers(1, 0x0000, 1)),
    ]
    found = None
    for label, build in attempts:
        try:
            mb = build()
            v5_req = modbus._v5_frame_encoder(mb)
            v5_resp = modbus._send_receive_v5_frame(v5_req)
            print(f"[{label}] raw reply ({len(v5_resp)} bytes): {v5_resp.hex(' ')}")
            if len(v5_resp) >= 11 and v5_resp[0] == 0xA5:
                serial = struct.unpack("<I", v5_resp[7:11])[0]
                print(f"    >>> stick's real logger serial: {serial}")
                found = serial
                break
        except Exception as e:
            print(f"[{label}] no usable reply: {type(e).__name__}: {e}")
    modbus.disconnect()
    if found:
        print(f"\nSUCCESS. Numeric logger serial = {found}")
    else:
        print("\nNo reply. This firmware likely requires the correct serial up front.")

if __name__ == "__main__":
    main()
