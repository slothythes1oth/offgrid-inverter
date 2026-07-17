"""Generate app icons with no third-party dependency (pure stdlib PNG writer).

A dark rounded tile with an amber lightning bolt = backup power. Renders the
sizes iOS home-screen install and the web manifest need. Re-run to regenerate:
    .venv/Scripts/python scripts/gen_icons.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).parent.parent / "web" / "public" / "icons"

BG = (11, 15, 20)  # #0b0f14, matches theme-color
BOLT = (255, 176, 32)  # #ffb020 amber

# Lightning bolt polygon in a 0..1 unit square (x, y), y down.
BOLT_POLY = [
    (0.56, 0.10),
    (0.30, 0.56),
    (0.47, 0.56),
    (0.42, 0.90),
    (0.72, 0.42),
    (0.53, 0.42),
]


def _point_in_poly(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _render(size: int) -> bytes:
    corner = size * 0.22  # rounded-square mask radius
    rows = bytearray()
    for py in range(size):
        rows.append(0)  # PNG filter byte (none) per scanline
        for px in range(size):
            # Rounded-corner alpha: outside the radius at corners -> transparent
            fx, fy = px + 0.5, py + 0.5
            transparent = False
            for cx, cy in ((corner, corner), (size - corner, corner),
                           (corner, size - corner), (size - corner, size - corner)):
                in_corner_box = (
                    (cx == corner and fx < corner or cx != corner and fx > size - corner)
                    and (cy == corner and fy < corner or cy != corner and fy > size - corner)
                )
                if in_corner_box:
                    if (fx - cx) ** 2 + (fy - cy) ** 2 > corner**2:
                        transparent = True
                    break
            if transparent:
                rows.extend((0, 0, 0, 0))
                continue
            u, v = fx / size, fy / size
            r, g, b = BOLT if _point_in_poly(u, v, BOLT_POLY) else BG
            rows.extend((r, g, b, 255))
    raw = bytes(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def _svg() -> str:
    pts = " ".join(f"{x*512:.0f},{y*512:.0f}" for x, y in BOLT_POLY)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" '
        'viewBox="0 0 512 512">'
        '<rect width="512" height="512" rx="112" fill="#0b0f14"/>'
        f'<polygon points="{pts}" fill="#ffb020"/>'
        "</svg>\n"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in [
        ("icon-192.png", 192),
        ("icon-512.png", 512),
        ("apple-touch-icon.png", 180),
    ]:
        (OUT / name).write_bytes(_render(size))
        print(f"wrote {name} ({size}x{size})")
    (OUT / "icon.svg").write_text(_svg(), encoding="utf-8")
    print("wrote icon.svg")


if __name__ == "__main__":
    main()
