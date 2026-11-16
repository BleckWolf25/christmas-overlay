# src/festive_assets.py
import math
import os
import random
import struct
from PIL import Image, ImageDraw, ImageFilter

_SS = 4


def save_cur(img: Image.Image, path: str, hot_x: int, hot_y: int) -> None:
    """Encodes a Pillow RGBA image as a valid 32-bit BGRA Windows .cur file."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    raw = rgba.tobytes("raw", "BGRA")
    row_bytes = w * 4

    # DIB scanlines are stored bottom-up
    xor_data = b"".join(
        raw[y * row_bytes : (y + 1) * row_bytes] for y in range(h - 1, -1, -1)
    )

    and_stride = ((w + 31) // 32) * 4
    and_rows = bytearray()
    px = rgba.load()
    for y in range(h - 1, -1, -1):
        row = bytearray(and_stride)
        for x in range(w):
            if px[x, y][3] < 128:
                row[x >> 3] |= 0x80 >> (x & 7)
        and_rows.extend(row)
    and_data = bytes(and_rows)

    bih = struct.pack(
        "<IiiHHIIiiII",
        40,
        w,
        h * 2,
        1,
        32,
        0,
        len(xor_data) + len(and_data),
        0,
        0,
        0,
        0,
    )
    payload = bih + xor_data + and_data
    header = struct.pack("<HHH", 0, 2, 1)
    entry = struct.pack(
        "<BBBBHHII",
        w if w < 256 else 0,
        h if h < 256 else 0,
        0,
        0,
        max(0, min(w - 1, int(hot_x))),
        max(0, min(h - 1, int(hot_y))),
        len(payload),
        22,
    )
    with open(path, "wb") as f:
        f.write(header + entry + payload)


def _scale_pt(pt: tuple[float, float], size: int) -> tuple[float, float]:
    s = (size * _SS) / 32.0
    return (pt[0] * s, pt[1] * s)


def _scale_pts(pts: list[tuple[float, float]], size: int) -> list[tuple[float, float]]:
    return [_scale_pt(p, size) for p in pts]


def render_candy_arrow_cursor(size: int = 36) -> tuple[Image.Image, int, int]:
    """Candy-cane striped pointer arrow with gold trim and holly accent."""
    canvas = Image.new("RGBA", (size * _SS, size * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    s = (size * _SS) / 32.0

    arrow = _scale_pts(
        [(2, 2), (2, 25), (7.5, 19.5), (12, 29), (15.5, 27.5), (11, 18), (18.5, 18)],
        size,
    )
    # Dark outer drop shadow + crisp gold outline
    d.polygon([(x + 1.2 * s, y + 1.5 * s) for x, y in arrow], fill=(15, 23, 42, 140))
    d.polygon(arrow, fill="#FFFFFF", outline="#7F1D1D")

    # Mask candy-cane diagonal stripes inside arrow
    mask = Image.new("L", (size * _SS, size * _SS), 0)
    ImageDraw.Draw(mask).polygon(arrow, fill=255)
    stripes = Image.new("RGBA", (size * _SS, size * _SS), (255, 255, 255, 255))
    sd = ImageDraw.Draw(stripes)
    step = int(5.5 * s)
    for offset in range(-size * _SS, size * _SS * 2, step * 2):
        sd.line(
            [(offset, 0), (offset - size * _SS, size * _SS)],
            fill="#DC2626",
            width=max(2, int(2.6 * s)),
        )
    canvas.paste(stripes, (0, 0), mask)
    d.line(arrow + [arrow[0]], fill="#FBBF24", width=max(2, int(1.35 * s)), joint="curve")

    # Tiny holly leaf & berry near the hilt
    hx, hy = 13.5 * s, 21.5 * s
    d.ellipse([hx - 3.2 * s, hy - 1.8 * s, hx + 0.5 * s, hy + 1.8 * s], fill="#15803D")
    d.ellipse([hx - 0.5 * s, hy - 1.8 * s, hx + 3.2 * s, hy + 1.8 * s], fill="#16A34A")
    d.ellipse([hx - 1.3 * s, hy - 1.3 * s, hx + 1.3 * s, hy + 1.3 * s], fill="#EF4444")

    out = canvas.resize((size, size), Image.Resampling.LANCZOS)
    hot = max(1, int(round(2 * size / 32.0)))
    return out, hot, hot


def render_santa_mitten_cursor(size: int = 36) -> tuple[Image.Image, int, int]:
    """Cozy red Santa mitten pointing finger for links and buttons."""
    canvas = Image.new("RGBA", (size * _SS, size * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    s = (size * _SS) / 32.0

    # Pointing index finger + mitten body + thumb
    d.rounded_rectangle(
        [10.5 * s, 2 * s, 16.5 * s, 16 * s],
        radius=3 * s,
        fill="#DC2626",
        outline="#7F1D1D",
        width=max(2, int(1.1 * s)),
    )
    d.rounded_rectangle(
        [8 * s, 10 * s, 24 * s, 24 * s],
        radius=6.5 * s,
        fill="#DC2626",
        outline="#7F1D1D",
        width=max(2, int(1.1 * s)),
    )
    d.rounded_rectangle(
        [4.5 * s, 13 * s, 11.5 * s, 20 * s],
        radius=3.2 * s,
        fill="#B91C1C",
        outline="#7F1D1D",
        width=max(2, int(1.0 * s)),
    )
    # White fluffy cuff + gold jingle bell
    d.rounded_rectangle(
        [7.5 * s, 22.5 * s, 24.5 * s, 28.5 * s],
        radius=2.8 * s,
        fill="#F8FAFC",
        outline="#94A3B8",
        width=max(2, int(1.0 * s)),
    )
    d.ellipse([14 * s, 24 * s, 18 * s, 28 * s], fill="#FBBF24", outline="#B45309")

    out = canvas.resize((size, size), Image.Resampling.LANCZOS)
    return out, int(round(13.5 * size / 32.0)), max(1, int(round(2.5 * size / 32.0)))


def render_wreath_cursor(size: int = 36) -> tuple[Image.Image, int, int]:
    """Christmas wreath with red bow for busy/background states."""
    canvas = Image.new("RGBA", (size * _SS, size * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    s = (size * _SS) / 32.0
    cx = cy = 16 * s

    d.ellipse(
        [4.5 * s, 4.5 * s, 27.5 * s, 27.5 * s],
        outline="#15803D",
        width=max(3, int(5.2 * s)),
    )
    d.ellipse(
        [5.5 * s, 5.5 * s, 26.5 * s, 26.5 * s],
        outline="#22C55E",
        width=max(2, int(2.0 * s)),
    )
    # Berries around the wreath
    for deg in range(0, 360, 45):
        rad = math.radians(deg)
        bx = cx + math.cos(rad) * 11.0 * s
        by = cy + math.sin(rad) * 11.0 * s
        d.ellipse([bx - 1.5 * s, by - 1.5 * s, bx + 1.5 * s, by + 1.5 * s], fill="#EF4444")

    # Top red ribbon bow
    d.polygon([(cx, 5 * s), (cx - 5.5 * s, 2 * s), (cx - 4 * s, 8 * s)], fill="#DC2626")
    d.polygon([(cx, 5 * s), (cx + 5.5 * s, 2 * s), (cx + 4 * s, 8 * s)], fill="#DC2626")
    d.ellipse([cx - 2 * s, 3.5 * s, cx + 2 * s, 7.5 * s], fill="#FBBF24")

    out = canvas.resize((size, size), Image.Resampling.LANCZOS)
    mid = size // 2
    return out, mid, mid


def render_ibeam_cursor(size: int = 36) -> tuple[Image.Image, int, int]:
    """High-contrast peppermint candy-cane I-beam cursor."""
    canvas = Image.new("RGBA", (size * _SS, size * _SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    s = (size * _SS) / 32.0
    cx = 16 * s

    # Top and bottom serifs + vertical shaft
    d.line([(10 * s, 4 * s), (22 * s, 4 * s)], fill="#7F1D1D", width=max(3, int(3.4 * s)))
    d.line([(10 * s, 28 * s), (22 * s, 28 * s)], fill="#7F1D1D", width=max(3, int(3.4 * s)))
    d.line([(cx, 4 * s), (cx, 28 * s)], fill="#7F1D1D", width=max(3, int(3.8 * s)))

    d.line([(10.5 * s, 4 * s), (21.5 * s, 4 * s)], fill="#FFFFFF", width=max(2, int(2.0 * s)))
    d.line([(10.5 * s, 28 * s), (21.5 * s, 28 * s)], fill="#FFFFFF", width=max(2, int(2.0 * s)))
    for idx, y in enumerate(range(4, 28, 3)):
        col = "#DC2626" if idx % 2 == 0 else "#FFFFFF"
        d.line([(cx, y * s), (cx, (y + 3) * s)], fill=col, width=max(2, int(2.2 * s)))

    out = canvas.resize((size, size), Image.Resampling.LANCZOS)
    mid = size // 2
    return out, mid, mid


def render_recycle_bin_icon(full: bool) -> Image.Image:
    """256x256 master sprite for Windows Recycle Bin (empty stocking vs full toy sack)."""
    size = 256
    canvas = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    if not full:
        # Empty knitted Christmas stocking hanging neatly
        d.rounded_rectangle([168, 72, 312, 310], radius=36, fill="#DC2626", outline="#7F1D1D", width=8)
        d.rounded_rectangle([120, 260, 312, 396], radius=64, fill="#DC2626", outline="#7F1D1D", width=8)
        # Heel & toe patches
        d.pieslice([224, 244, 326, 346], 270, 90, fill="#15803D")
        d.pieslice([112, 264, 224, 392], 90, 270, fill="#15803D")
        # Gold snowflake stitch
        d.ellipse([212, 168, 256, 212], outline="#FBBF24", width=6)
        # Fluffy white cuff & hanging loop
        d.rounded_rectangle([152, 52, 328, 114], radius=24, fill="#F8FAFC", outline="#CBD5E1", width=6)
        d.arc([286, 22, 342, 78], 180, 90, fill="#FBBF24", width=10)
    else:
        # Full Santa velvet toy sack overflowing with presents & candy canes
        # Candy cane & gifts sticking out the top
        d.line([(164, 150), (144, 72), (176, 52), (196, 80)], fill="#FFFFFF", width=22, joint="curve")
        d.line([(164, 150), (144, 72), (176, 52), (196, 80)], fill="#EF4444", width=9, joint="curve")
        d.rounded_rectangle([206, 58, 304, 154], radius=12, fill="#16A34A", outline="#14532D", width=6)
        d.rectangle([248, 58, 264, 154], fill="#FBBF24")
        d.rectangle([206, 98, 304, 114], fill="#FBBF24")
        d.rounded_rectangle([282, 82, 368, 168], radius=12, fill="#2563EB", outline="#1E3A8A", width=6)
        d.rectangle([318, 82, 332, 168], fill="#FDE68A")

        # Plump velvet sack body + ruffled top + gold rope tie
        d.polygon([(172, 146), (148, 96), (218, 114), (272, 92), (344, 146)], fill="#B91C1C", outline="#7F1D1D")
        d.ellipse([96, 144, 416, 456], fill="#DC2626", outline="#7F1D1D", width=10)
        d.ellipse([132, 180, 290, 370], fill="#EF4444")
        d.rounded_rectangle([162, 138, 350, 166], radius=12, fill="#FBBF24", outline="#B45309", width=5)
        d.ellipse([236, 134, 276, 174], fill="#FDE047", outline="#B45309", width=5)

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def render_festive_app_icon() -> Image.Image:
    """256x256 Santa-hat golden Christmas ornament icon for the app and tray."""
    size = 256
    canvas = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    # Golden bauble
    d.ellipse([96, 148, 416, 468], fill="#DC2626", outline="#7F1D1D", width=10)
    d.ellipse([130, 182, 330, 382], fill="#EF4444")
    # Decorative gold band
    d.rectangle([104, 286, 408, 332], fill="#FBBF24")
    d.ellipse([138, 192, 188, 242], fill="#FCA5A5")

    # Jaunty Santa hat perched on top of the ornament
    d.polygon(
        [(136, 168), (368, 152), (242, 36), (104, 96)],
        fill="#B91C1C",
        outline="#7F1D1D",
    )
    d.rounded_rectangle([124, 144, 384, 188], radius=20, fill="#F8FAFC", outline="#CBD5E1", width=6)
    d.ellipse([76, 72, 132, 128], fill="#F8FAFC", outline="#CBD5E1", width=6)

    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def render_winter_backdrop(width: int, height: int, path: str, lockscreen: bool = False) -> str:
    """Renders a crisp winter aurora & snowy pine forest image for wallpaper or lock screen."""
    w = max(800, int(width))
    h = max(600, int(height))
    img = Image.new("RGB", (w, h), "#071024")
    d = ImageDraw.Draw(img)

    # Deep arctic twilight vertical gradient
    top_rgb = (6, 14, 34)
    bot_rgb = (20, 44, 78)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top_rgb[0] + (bot_rgb[0] - top_rgb[0]) * t)
        g = int(top_rgb[1] + (bot_rgb[1] - top_rgb[1]) * t)
        b = int(top_rgb[2] + (bot_rgb[2] - top_rgb[2]) * t)
        d.line([(0, y), (w, y)], fill=(r, g, b))

    # Northern lights ribbon
    aurora = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ad = ImageDraw.Draw(aurora)
    for band, col in enumerate(((16, 185, 129, 95), (52, 211, 153, 75), (129, 140, 248, 65))):
        pts = []
        for x in range(-40, w + 40, 32):
            y = int(h * (0.20 + band * 0.05) + math.sin(x / max(1, w) * math.tau * 1.6 + band) * (h * 0.06))
            pts.append((x, y))
        if len(pts) > 1:
            ad.line(pts, fill=col, width=max(14, h // 18), joint="curve")
    aurora = aurora.filter(ImageFilter.GaussianBlur(max(12, h // 32)))
    img = Image.alpha_composite(img.convert("RGBA"), aurora).convert("RGB")
    d = ImageDraw.Draw(img)

    # Moon & stars
    rng = random.Random(20261225 if lockscreen else 1225)
    for _ in range(140):
        sx = rng.randint(0, w - 1)
        sy = rng.randint(0, int(h * 0.65))
        sr = rng.choice((1, 1, 2))
        d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill="#F8FAFC")

    mx, my, mr = int(w * 0.80), int(h * 0.18), max(24, h // 24)
    d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill="#FEF9C3")

    # Rolling snow hills
    hill1 = [(0, h)]
    for x in range(0, w + 40, 40):
        y = int(h * 0.78 + math.sin(x / max(1, w) * math.pi * 1.4) * (h * 0.04))
        hill1.append((x, y))
    hill1.append((w, h))
    d.polygon(hill1, fill="#CBD5E1")

    hill2 = [(0, h)]
    for x in range(0, w + 40, 40):
        y = int(h * 0.85 + math.cos(x / max(1, w) * math.pi * 1.8) * (h * 0.035))
        hill2.append((x, y))
    hill2.append((w, h))
    d.polygon(hill2, fill="#F1F5F9")

    # Layered evergreen pine silhouettes
    tree_count = max(14, w // 90)
    for i in range(tree_count):
        tx = int((i + 0.5) * (w / tree_count) + rng.uniform(-18, 18))
        base_y = int(h * rng.uniform(0.79, 0.90))
        th = int(h * rng.uniform(0.11, 0.22))
        tw = int(th * 0.48)
        col = "#0F292E" if i % 2 == 0 else "#13383B"
        for tier in range(3):
            top_y = base_y - th + int(tier * th * 0.24)
            bot_y = base_y - int((2 - tier) * th * 0.26)
            span = int(tw * (0.45 + tier * 0.28))
            d.polygon([(tx, top_y), (tx - span, bot_y), (tx + span, bot_y)], fill=col)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "PNG")
    return path