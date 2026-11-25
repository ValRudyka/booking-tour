"""Placeholder photos for the demo seed, generated locally: no downloads, no Pillow.

A small PNG of a seaside scene (sky, sun, sea with waves, sand). The colours and positions depend
on `seed`, so every tour and review photo looks a little different, and the same seed always gives
the same bytes. Pure Python: rows are built as byte strings and compressed with zlib, so a picture
takes a few milliseconds.
"""
import struct
import zlib

WIDTH, HEIGHT = 800, 500
SUN = (253, 230, 138)

# (sky top, sky at the horizon, sea, deep sea, sand, wet sand)
PALETTES = [
    ((14, 116, 144), (165, 216, 230), (14, 116, 144), (21, 94, 117), (242, 232, 213), (214, 196, 160)),
    ((30, 64, 175), (191, 219, 254), (8, 145, 178), (22, 78, 99), (245, 222, 179), (210, 180, 140)),
    ((124, 58, 237), (251, 207, 232), (13, 148, 136), (17, 94, 89), (250, 235, 215), (205, 175, 140)),
    ((2, 132, 199), (224, 242, 254), (3, 105, 161), (12, 74, 110), (237, 224, 200), (199, 180, 150)),
    ((234, 88, 12), (254, 215, 170), (15, 118, 110), (19, 78, 74), (240, 225, 200), (200, 170, 130)),
]


def _mix(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    t = min(max(t, 0.0), 1.0)
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def scene_png(seed: int, width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """PNG bytes (8-bit RGB) of a seaside scene that depends on `seed`."""
    sky_top, sky_low, sea, sea_deep, sand, sand_wet = PALETTES[seed % len(PALETTES)]
    horizon = int(height * (0.42 + (seed % 3) * 0.05))
    shore = int(height * (0.70 + (seed % 2) * 0.07))
    sun_x = int(width * (0.18 + (seed * 37 % 64) / 100))
    sun_y = int(horizon * (0.35 + (seed % 4) * 0.1))
    radius = height // 11
    wave_step = 14 + seed % 7

    rows = []
    for y in range(height):
        if y < horizon:
            color = _mix(sky_top, sky_low, y / horizon)
        elif y < shore:
            depth = (y - horizon) / (shore - horizon)
            color = _mix(sea_deep, sea, depth)
            if (y - horizon) % wave_step == 0:           # a lighter line = a wave
                color = _mix(color, (255, 255, 255), 0.35)
        else:
            color = _mix(sand_wet, sand, (y - shore) / max(height - shore, 1) * 2)
        row = bytearray(bytes(color) * width)
        dy = y - sun_y
        if y < horizon and abs(dy) < radius:
            half = int((radius * radius - dy * dy) ** 0.5)
            x0, x1 = max(sun_x - half, 0), min(sun_x + half, width)
            row[x0 * 3:x1 * 3] = bytes(SUN) * (x1 - x0)
        rows.append(b"\x00" + bytes(row))               # filter type 0 for every row

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)   # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + _chunk(b"IEND", b""))
