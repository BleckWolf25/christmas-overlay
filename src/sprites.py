# src/sprites.py
import math
import struct
import tkinter as tk
import zlib
from PIL import Image, ImageDraw
from paths import resource_path


def load_tray_image() -> Image.Image:
    try:
        return Image.open(resource_path("icon.png")).convert("RGBA")
    except Exception:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((6, 6, 58, 58), fill="#DC2626", outline="#FBBF24", width=4)
        d.ellipse((24, 24, 40, 40), fill="#FFFFFF")
        return img


def _encode_rgba_png(width: int, height: int, raw_rows: bytes) -> bytes:
    """Encodes raw filter-prefixed RGBA scanlines into a valid PNG byte stream."""
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rows, level=1))
        + chunk(b"IEND", b"")
    )


def make_snowflake_photo(size: int, color: str = "#FFFFFF") -> tk.PhotoImage:
    """Renders an anti-aliased 6-pointed snowflake directly into a native tk.PhotoImage."""
    r_col = int(color[1:3], 16)
    g_col = int(color[3:5], 16)
    b_col = int(color[5:7], 16)

    cx = cy = (size - 1) / 2.0
    radius = size * 0.45
    half_thick = max(0.55, size * 0.05)

    spokes = []
    for i in range(6):
        a = math.tau * i / 6.0
        ux, uy = math.cos(a), math.sin(a)
        b1x, b1y = math.cos(a - math.pi / 4.0), math.sin(a - math.pi / 4.0)
        b2x, b2y = math.cos(a + math.pi / 4.0), math.sin(a + math.pi / 4.0)
        spokes.append((ux, uy, b1x, b1y, b2x, b2y))

    def dist_to_seg(px: float, py: float, ax: float, ay: float, ux: float, uy: float, length: float) -> float:
        vx, vy = px - ax, py - ay
        proj = vx * ux + vy * uy
        if proj < 0.0:
            proj = 0.0
        elif proj > length:
            proj = length
        return math.hypot(vx - proj * ux, vy - proj * uy)

    raw = bytearray()
    branch_len = radius * 0.24
    for y in range(size):
        raw.append(0)  # PNG filter type 0 (None)
        for x in range(size):
            min_d = 999.0
            for ux, uy, b1x, b1y, b2x, b2y in spokes:
                d = dist_to_seg(x, y, cx, cy, ux, uy, radius)
                if d < min_d:
                    min_d = d
                for t in (0.55, 0.80):
                    bx = cx + ux * radius * t
                    by = cy + uy * radius * t
                    d1 = dist_to_seg(x, y, bx, by, b1x, b1y, branch_len)
                    if d1 < min_d:
                        min_d = d1
                    d2 = dist_to_seg(x, y, bx, by, b2x, b2y, branch_len)
                    if d2 < min_d:
                        min_d = d2

            # Smooth 1px anti-aliased edge
            coverage = max(0.0, min(1.0, (half_thick + 0.6 - min_d) / 1.2))
            alpha = int(coverage * 255)
            if alpha > 0:
                raw.extend((r_col, g_col, b_col, alpha))
            else:
                raw.extend((0, 0, 0, 0))

    png_bytes = _encode_rgba_png(size, size, bytes(raw))
    return tk.PhotoImage(data=png_bytes, format="png")


def build_flake_sprites() -> list[tk.PhotoImage]:
    layer_sizes = [[8, 10, 12], [10, 14, 18], [14, 18, 22]]
    layer_colors = [
        ["#FFFFFF", "#F2F6FA", "#DEE7EE"],
        ["#D8DEE4", "#C5D0DB", "#B4C2D0"],
        ["#BFC5CB", "#AAB6C2", "#98A5B4"],
    ]
    sprites = []
    for sizes, colors in zip(layer_sizes, layer_colors):
        for s, c in zip(sizes, colors):
            sprites.append(make_snowflake_photo(s, c))
    return sprites