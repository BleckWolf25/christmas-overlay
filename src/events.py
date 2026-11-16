# src/events.py
import io
import math
import random
import tkinter as tk

from PIL import Image, ImageDraw, ImageFilter

from win32 import is_reduce_motion_enabled

_SS = 4

def _bez(p0, p1, p2, n=14):
    pts = []
    for i in range(n + 1):
        t = i / n
        a, b, c = (1 - t) ** 2, 2 * (1 - t) * t, t * t
        pts.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return pts


def _to_photo(img: Image.Image) -> tk.PhotoImage:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return tk.PhotoImage(data=buf.getvalue(), format="png")


class _Painter:
    """Tiny helper that draws in logical units onto a supersampled RGBA layer."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * _SS, h * _SS), (0, 0, 0, 0))
        self.glow = Image.new("RGBA", (w * _SS, h * _SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.g = ImageDraw.Draw(self.glow)

    @staticmethod
    def _p(pts):
        return [(x * _SS, y * _SS) for x, y in pts]

    def poly(self, pts, fill, outline=None):
        self.d.polygon(self._p(pts), fill=fill, outline=outline)

    def ellipse(self, x1, y1, x2, y2, fill, outline=None, width=1):
        self.d.ellipse(
            [x1 * _SS, y1 * _SS, x2 * _SS, y2 * _SS],
            fill=fill, outline=outline, width=max(1, int(width * _SS)),
        )

    def circle(self, cx, cy, r, fill, outline=None, width=1):
        self.ellipse(cx - r, cy - r, cx + r, cy + r, fill, outline, width)

    def rect(self, x1, y1, x2, y2, fill, radius=0):
        box = [x1 * _SS, y1 * _SS, x2 * _SS, y2 * _SS]
        if radius:
            self.d.rounded_rectangle(box, radius=radius * _SS, fill=fill)
        else:
            self.d.rectangle(box, fill=fill)

    def line(self, pts, fill, width=1):
        self.d.line(self._p(pts), fill=fill, width=max(1, int(width * _SS)), joint="curve")

    def glow_circle(self, cx, cy, r, fill):
        self.g.ellipse(
            [(cx - r) * _SS, (cy - r) * _SS, (cx + r) * _SS, (cy + r) * _SS], fill=fill
        )

    def finish(self, blur: float = 3.0) -> Image.Image:
        glow = self.glow.filter(ImageFilter.GaussianBlur(blur * _SS))
        out = Image.alpha_composite(glow, self.img)
        return out.resize((self.w, self.h), Image.Resampling.LANCZOS)

SANTA_W, SANTA_H = 250, 92
_BROWN = "#8B5A33"
_BROWN_D = "#5C3A1E"
_BROWN_L = "#D9B38C"
_GOLD = "#FBBF24"
_GOLD_D = "#B45309"


def _draw_reindeer(p: _Painter, ox: float, oy: float, phase: float, rudolph: bool) -> None:
    # far legs (darker), then body, then near legs
    def legs(offsets, color):
        for hip_dx, off in offsets:
            swing = math.sin(phase + off) * 7.0
            lift = max(0.0, math.cos(phase + off)) * 4.0
            hip = (ox + hip_dx, oy + 3)
            knee = (ox + hip_dx + swing * 0.55, oy + 11 - lift * 0.4)
            hoof = (ox + hip_dx + swing, oy + 19 - lift)
            p.line([hip, knee, hoof], color, 3)
            p.circle(hoof[0], hoof[1], 1.8, "#1F1409")

    legs([(7, math.pi), (29, math.pi * 0.35)], _BROWN_D)

    # tail
    p.ellipse(ox - 4, oy - 9, ox + 3, oy - 2, _BROWN_L)
    # body
    p.ellipse(ox, oy - 10, ox + 37, oy + 8, _BROWN, _BROWN_D, 0.8)
    p.ellipse(ox + 5, oy - 1, ox + 32, oy + 7, _BROWN_L)
    # neck
    p.poly([(ox + 28, oy - 7), (ox + 36, oy - 24), (ox + 44, oy - 19), (ox + 37, oy - 1)], _BROWN)
    # head + snout
    p.ellipse(ox + 35, oy - 29, ox + 50, oy - 15, _BROWN, _BROWN_D, 0.6)
    p.ellipse(ox + 45, oy - 26, ox + 55, oy - 17, _BROWN_L, _BROWN_D, 0.6)
    # ear
    p.poly([(ox + 37, oy - 28), (ox + 34, oy - 33), (ox + 41, oy - 30)], _BROWN_D)
    # antlers
    p.line([(ox + 41, oy - 29), (ox + 39, oy - 36), (ox + 42, oy - 41)], "#E7D3B0", 1.6)
    p.line([(ox + 39, oy - 36), (ox + 35, oy - 38)], "#E7D3B0", 1.3)
    p.line([(ox + 44, oy - 29), (ox + 46, oy - 36), (ox + 50, oy - 39)], "#E7D3B0", 1.6)
    p.line([(ox + 46, oy - 36), (ox + 43, oy - 40)], "#E7D3B0", 1.3)
    # eye
    p.circle(ox + 44.5, oy - 22.5, 1.3, "#111111")
    # nose
    if rudolph:
        p.glow_circle(ox + 55, oy - 21, 9, (255, 60, 60, 210))
        p.circle(ox + 55, oy - 21, 3.2, "#EF4444", "#B91C1C", 0.5)
        p.circle(ox + 54, oy - 22, 1.0, "#FECACA")
    else:
        p.circle(ox + 55, oy - 21, 2.2, "#2B1B10")
    # harness collar
    p.line([(ox + 30, oy - 6), (ox + 36, oy - 2)], _GOLD, 2)
    p.circle(ox + 33, oy - 4, 1.4, _GOLD_D)

    legs([(10, 0.0), (32, math.pi * 1.35)], _BROWN)


def _render_santa_frame(phase: float) -> Image.Image:
    p = _Painter(SANTA_W, SANTA_H)

    # reins / harness
    p.line([(100, 46), (118, 44)], _GOLD_D, 1.4)
    p.line([(155, 44), (176, 44)], _GOLD_D, 1.4)

    _draw_reindeer(p, 118, 50, phase + 0.9, False)
    _draw_reindeer(p, 176, 48, phase, True)

    # gift sack + presents behind the sleigh rim
    p.ellipse(14, 14, 54, 46, "#9F1239", "#5A0E0E", 0.8)
    p.ellipse(20, 18, 34, 30, "#BE123C")
    p.poly([(28, 16), (34, 8), (40, 16)], "#9F1239", "#5A0E0E")
    p.line([(26, 17), (42, 17)], _GOLD, 2)
    p.rect(54, 22, 70, 38, "#16A34A", 1.5)
    p.rect(60, 22, 64, 38, _GOLD)
    p.rect(54, 28, 70, 31, _GOLD)
    p.rect(70, 26, 84, 40, "#2563EB", 1.5)
    p.rect(75, 26, 79, 40, "#FDE68A")

    # Santa
    p.ellipse(68, 28, 94, 54, "#DC2626", "#7F1D1D", 0.8)
    p.rect(68, 42, 94, 46, "#1F1F1F")
    p.rect(79, 41.5, 83, 46.5, _GOLD)
    p.circle(81, 22, 7.5, "#FDBA74", "#C2743A", 0.5)
    p.ellipse(73, 22, 90, 36, "#FFFFFF", "#D1D5DB", 0.5)  # beard
    p.circle(86, 21.5, 1.2, "#111111")  # eye
    p.circle(88, 24, 1.7, "#F87171")  # nose
    p.poly([(72, 19), (90, 18), (82, 5), (66, 11)], "#DC2626", "#7F1D1D")  # hat
    p.rect(71, 16.5, 91, 21, "#FFFFFF", 2)
    p.circle(66, 11, 3.6, "#FFFFFF")
    # arm + mitten holding reins
    p.line([(86, 36), (101, 42)], "#B91C1C", 5)
    p.circle(102, 43, 3.2, "#FFFFFF")
    p.line([(102, 43), (118, 44)], _GOLD_D, 1.2)

    # sleigh body (curved bowl), trim, runner
    bowl = (
        _bez((6, 34), (6, 60), (32, 60))
        + [(78, 60)]
        + _bez((78, 60), (104, 60), (104, 34))
    )
    p.poly(bowl, "#B91C1C", "#5A0E0E")
    p.line(_bez((10, 44), (14, 54), (34, 54)) + [(76, 54)] + _bez((76, 54), (96, 54), (100, 44)), _GOLD, 1.8)
    p.rect(4, 31, 106, 36, _GOLD, 2.5)
    p.rect(4, 31, 106, 33, "#FDE68A", 1)
    # struts
    p.line([(30, 59), (30, 74)], "#9CA3AF", 2)
    p.line([(78, 59), (78, 74)], "#9CA3AF", 2)
    # runner with curled front
    runner = (
        [(2, 62)]
        + _bez((2, 62), (-1, 76), (14, 76))
        + [(96, 76)]
        + _bez((96, 76), (112, 76), (112, 62))
        + _bez((112, 62), (112, 57), (108, 56), 6)
    )
    p.line(runner, "#CBD5E1", 2.6)

    # festive sparkle at sleigh tail
    p.glow_circle(6, 34, 6, (255, 220, 120, 120))

    return p.finish(blur=3.0)

def _render_star(angle: float, length: int = 90):
    """Returns (PhotoImage, head_offset_x, head_offset_y) for a tapered glowing comet."""
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    pad = 14
    w = int(abs(cos_a) * length) + pad * 2
    h = int(abs(sin_a) * length) + pad * 2
    hx = w - pad if cos_a >= 0 else pad
    hy = h - pad if sin_a >= 0 else pad
    p = _Painter(w, h)

    n = 44
    tail_x, tail_y = hx - cos_a * length, hy - sin_a * length
    prev = (tail_x, tail_y)
    for i in range(1, n + 1):
        t = i / n
        pt = (tail_x + (hx - tail_x) * t, tail_y + (hy - tail_y) * t)
        alpha = int(255 * (t ** 1.7))
        width = 0.4 + 2.6 * t
        col = (255, int(235 + 20 * t), int(170 + 70 * t), alpha)
        p.line([prev, pt], col, width)
        prev = pt

    p.glow_circle(hx, hy, 8, (255, 240, 170, 190))
    p.circle(hx, hy, 2.6, (255, 255, 255, 255))
    # 4-point glint
    r1, r2 = 8.0, 2.0
    p.poly([(hx, hy - r1), (hx + r2 * 0.5, hy - r2 * 0.5), (hx + r1, hy), (hx + r2 * 0.5, hy + r2 * 0.5),
            (hx, hy + r1), (hx - r2 * 0.5, hy + r2 * 0.5), (hx - r1, hy), (hx - r2 * 0.5, hy - r2 * 0.5)],
           (255, 255, 255, 235))
    return _to_photo(p.finish(blur=2.5)), hx, hy


def _star_points(x: float, y: float, r: float) -> list:
    k = r * 0.3
    return [x, y - r, x + k, y - k, x + r, y, x + k, y + k, x, y + r, x - k, y + k, x - r, y, x - k, y - k]


def _rounded_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class RandomEventSystem:
    """Occasional ambient animations: Santa's sleigh, shooting stars, greetings, aurora."""

    SANTA_FIRST_DELAY_S = 15
    SANTA_INTERVAL_S = (120, 300)
    STAR_INTERVAL_S = (60, 180)
    HOHO_INTERVAL_S = (240, 600)
    HOHO_TEXT = ("Ho Ho Ho!", "Merry Christmas!", "Feliz Natal!")

    _TRAIL_COLORS = ("#FEF3C7", "#FDE68A", "#FBBF24", "#B45309")
    _TRAIL_LIFE = 20

    def __init__(self, canvas, vw: int, vh: int):
        self.canvas = canvas
        self.vw, self.vh = vw, vh
        self.reduce_motion = is_reduce_motion_enabled()
        self._tick = 0

        self._santa_frames: list[tk.PhotoImage] | None = None
        self._star_photo: tk.PhotoImage | None = None

        self._santa = None
        self._next_santa = self.SANTA_FIRST_DELAY_S * 30

        self._star = None
        self._next_star = random.randint(*self.STAR_INTERVAL_S) * 30

        self._hoho = None
        self._next_hoho = random.randint(*self.HOHO_INTERVAL_S) * 30

        self._aurora = self._build_aurora()

    def _build_aurora(self):
        """Aurora"""
        if self.reduce_motion:
            return []
        items = []
        for i, color in enumerate(("#10B981", "#34D399", "#818CF8")):
            pts = []
            for x in range(-40, self.vw + 40, 60):
                t = x / max(1, self.vw)
                y = 8 + i * 6 + math.sin(t * math.pi * 4 + i * 1.3) * 12
                pts.extend((x, y))
            items.append(
                self.canvas.create_line(
                    *pts, fill=color, width=2, smooth=True, stipple="gray12"
                )
            )
        return items

    def update(self, tick: int, env_rects: dict) -> None:
        self._tick = tick
        if self._santa is None and tick >= self._next_santa:
            self._start_santa()
        if self._santa is not None:
            self._update_santa()

        if self._star is None and tick >= self._next_star:
            self._start_star()
        if self._star is not None:
            self._update_star()

        if self._hoho is None and tick >= self._next_hoho:
            self._start_hoho()
        if self._hoho is not None:
            self._update_hoho()

    def _interval(self, pair) -> int:
        lo, hi = pair
        if self.reduce_motion:
            lo, hi = lo * 2, hi * 2
        return random.randint(lo, hi) * 30

    def _ensure_santa_frames(self) -> list:
        if self._santa_frames is None:
            count = 1 if self.reduce_motion else 4
            self._santa_frames = [
                _to_photo(_render_santa_frame(i * math.tau / 4.0)) for i in range(count)
            ]
        return self._santa_frames

    def _start_santa(self) -> None:
        """Santa's sleigh"""
        frames = self._ensure_santa_frames()
        start_y = random.uniform(self.vh * 0.10, self.vh * 0.28)
        x = -float(SANTA_W)
        item = self.canvas.create_image(x, start_y, image=frames[0], anchor="w")
        self._santa = {
            "x": x,
            "y": start_y,
            "base_y": start_y,
            "item": item,
            "frame": 0,
            "trail": [],
            "t": 0,
        }

    def _update_santa(self) -> None:
        s = self._santa
        c = self.canvas
        s["t"] += 1
        s["x"] += 3.2
        s["y"] = s["base_y"] + math.sin(s["t"] * 0.06) * 6
        c.coords(s["item"], s["x"], s["y"])

        frames = self._santa_frames
        if len(frames) > 1:
            f = (s["t"] // 4) % len(frames)
            if f != s["frame"]:
                s["frame"] = f
                c.itemconfigure(s["item"], image=frames[f])

        # sparkle trail from the runners
        if s["t"] % 3 == 0:
            tx = s["x"] + 6 + random.uniform(-3, 3)
            ty = s["y"] + 34 + random.uniform(-4, 4)
            it = c.create_polygon(
                *_star_points(tx, ty, 5.0), fill=self._TRAIL_COLORS[0], outline=""
            )
            s["trail"].append([it, self._TRAIL_LIFE, tx, ty])

        alive = []
        for entry in s["trail"]:
            it, life, tx, ty = entry
            life -= 1
            if life <= 0:
                c.delete(it)
                continue
            ty += 0.35
            frac = life / self._TRAIL_LIFE
            col = self._TRAIL_COLORS[min(3, int((1.0 - frac) * 4))]
            c.coords(it, *_star_points(tx, ty, 1.5 + 3.5 * frac))
            c.itemconfigure(it, fill=col)
            alive.append([it, life, tx, ty])
        s["trail"] = alive

        if s["x"] > self.vw + 20:
            c.delete(s["item"])
            for entry in s["trail"]:
                c.delete(entry[0])
            self._santa = None
            self._next_santa = self._tick + self._interval(self.SANTA_INTERVAL_S)

    def _start_star(self) -> None:
        """Shooting star"""
        x0 = random.uniform(self.vw * 0.15, self.vw * 0.85)
        y0 = random.uniform(30, max(40, self.vh * 0.25))
        angle = math.pi * random.uniform(0.15, 0.35)
        speed = 22
        photo, ox, oy = _render_star(angle)
        self._star_photo = photo  # keep a reference
        item = self.canvas.create_image(x0 - ox, y0 - oy, image=photo, anchor="nw")
        self._star = {
            "x": x0, "y": y0,
            "vx": math.cos(angle) * speed,
            "vy": math.sin(angle) * speed,
            "ox": ox, "oy": oy,
            "item": item, "life": 40,
        }

    def _update_star(self) -> None:
        s = self._star
        s["x"] += s["vx"]
        s["y"] += s["vy"]
        self.canvas.coords(s["item"], s["x"] - s["ox"], s["y"] - s["oy"])
        s["life"] -= 1
        if s["life"] <= 0 or s["y"] > self.vh or s["x"] > self.vw or s["x"] < 0:
            self.canvas.delete(s["item"])
            self._star = None
            self._star_photo = None
            self._next_star = self._tick + self._interval(self.STAR_INTERVAL_S)

    def _start_hoho(self) -> None:
        """Ho ho!"""
        c = self.canvas
        text = random.choice(self.HOHO_TEXT)
        x = self.vw - 160
        y = self.vh - 100

        txt = c.create_text(
            x, y, text=text, fill="#FDE68A", font=("Segoe UI", 18, "bold"), anchor="e"
        )
        bb = c.bbox(txt)
        items = [txt]
        if bb:
            padx, pady = 14, 8
            x1, y1, x2, y2 = bb[0] - padx, bb[1] - pady, bb[2] + padx, bb[3] + pady
            shadow = c.create_polygon(
                *_rounded_points(x1 + 2, y1 + 3, x2 + 2, y2 + 3, 14),
                smooth=True, fill="#020617", stipple="gray50", outline="",
            )
            bubble = c.create_polygon(
                *_rounded_points(x1, y1, x2, y2, 14),
                smooth=True, fill="#7F1D1D", outline="#FBBF24", width=2,
            )
            tail = c.create_polygon(
                x2 - 30, y2 - 1, x2 - 12, y2 - 1, x2 - 8, y2 + 12,
                fill="#7F1D1D", outline="#FBBF24", width=2,
            )
            cover = c.create_line(x2 - 28, y2 - 1, x2 - 14, y2 - 1, fill="#7F1D1D", width=3)
            items = [shadow, bubble, tail, cover, txt]
            c.tag_raise(txt)
        self._hoho = {"items": items, "life": 130}

    def _update_hoho(self) -> None:
        h = self._hoho
        h["life"] -= 1
        if not self.reduce_motion:
            for item in h["items"]:
                self.canvas.move(item, 0, -0.15)
        if h["life"] <= 0:
            for item in h["items"]:
                self.canvas.delete(item)
            self._hoho = None
            self._next_hoho = self._tick + self._interval(self.HOHO_INTERVAL_S)