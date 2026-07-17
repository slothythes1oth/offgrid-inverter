"""
Read-only discovery of the Solarman stick's numeric logger serial.
Two harmless methods:
  1) UDP 48899 query  - ask the stick to report IP / MAC / SN.
  2) Passive TCP 8899 - listen briefly for a V5 data frame and parse the
     logger serial out of its header (bytes 7..11, little-endian).
Sends nothing to the inverter and writes nothing. Just listens/asks.
"""
import socket
import struct
import sys

IP = "192.168.50.82"

def try_udp_discovery():
    print("=== Method 1: UDP 48899 discovery query ===")
    for query in (b"WIFIKIT-214028-READ", b"HF-A11ASSISTHREAD"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(3)
            s.sendto(query, (IP, 48899))
            data, addr = s.recvfrom(1024)
            print(f"  query {query!r} -> reply from {addr}:")
            print(f"    text: {data.decode('ascii', 'replace').strip()}")
            print(f"    hex:  {data.hex()}")
        except Exception as e:
            print(f"  query {query!r} -> no usable reply ({e})")
        finally:
            try:
                s.close()
            except Exception:
                pass

def try_tcp_listen():
    print("=== Method 2: passive listen on TCP 8899 for a V5 frame ===")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(12)
        s.connect((IP, 8899))
        print("  connected; listening up to 12s for any pushed bytes...")
        buf = b""
        try:
            while len(buf) < 2048:
                chunk = s.recv(1024)
                if not chunk:
                    break
                buf += chunk
                # A V5 frame starts with 0xA5; serial is 4 bytes at offset 7.
                start = buf.find(b"\xa5")
                if start != -1 and len(buf) >= start + 11:
                    serial = struct.unpack("<I", buf[start + 7:start + 11])[0]
                    print(f"  got {len(buf)} bytes; raw hex: {buf.hex()}")
                    print(f"  >>> parsed logger serial from V5 frame: {serial}")
                    return serial
        except socket.timeout:
            pass
        if buf:
            print(f"  received {len(buf)} bytes but no clean V5 frame: {buf.hex()}")
        else:
            print("  stick sent nothing on connect (it may only speak when asked).")
    except Exception as e:
        print(f"  could not listen: {e}")
    finally:
        try:
            s.close()
        except Exception:
            pass
    return None

if __name__ == "__main__":
    try_udp_discovery()
    print()
    try_tcp_listen()
