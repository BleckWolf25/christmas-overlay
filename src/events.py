# src/events.py
import io
import math
import random
import tkinter as tk

from PIL import Image, ImageDraw, ImageFilter

from win32 import get_work_area_for_point, is_reduce_motion_enabled

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
    """Draws in logical units onto a supersampled RGBA layer with soft glow compositing."""

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
            fill=fill,
            outline=outline,
            width=max(1, int(width * _SS)),
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

    def glow_line(self, pts, fill, width=2):
        self.g.line(self._p(pts), fill=fill, width=max(1, int(width * _SS)), joint="curve")

    def finish(self, blur: float = 3.0) -> Image.Image:
        glow = self.glow.filter(ImageFilter.GaussianBlur(blur * _SS))
        out = Image.alpha_composite(glow, self.img)
        return out.resize((self.w, self.h), Image.Resampling.LANCZOS)


SANTA_W, SANTA_H = 340, 108
_BROWN = "#8B5A33"
_BROWN_D = "#5C3A1E"
_BROWN_L = "#E2BE98"
_GOLD = "#FBBF24"
_GOLD_D = "#B45309"


def _draw_reindeer(
    p: _Painter,
    ox: float,
    oy: float,
    phase: float,
    rudolph: bool,
    body_col: str = _BROWN,
    dark_col: str = _BROWN_D,
) -> None:
    bob = math.sin(phase * 2.0) * 1.4
    oy = oy + bob
    head_nod = math.cos(phase * 2.0) * 1.2

    def legs(offsets, color):
        for hip_dx, off in offsets:
            swing = math.sin(phase + off) * 8.5
            lift = max(0.0, math.cos(phase + off)) * 5.0
            hip = (ox + hip_dx, oy + 3)
            knee = (ox + hip_dx + swing * 0.55, oy + 12 - lift * 0.45)
            hoof = (ox + hip_dx + swing, oy + 20 - lift)
            p.line([hip, knee, hoof], color, 3.0)
            p.circle(hoof[0], hoof[1], 1.9, "#1F1409")

    # Far legs
    legs([(7, math.pi), (30, math.pi * 0.35)], dark_col)

    # Tail
    p.ellipse(ox - 5, oy - 9, ox + 3, oy - 1, _BROWN_L)
    # Torso & chest
    p.ellipse(ox, oy - 10, ox + 39, oy + 8, body_col, dark_col, 0.8)
    p.ellipse(ox + 6, oy - 1, ox + 34, oy + 7, _BROWN_L)

    # Articulated neck & head
    hy = oy + head_nod
    p.poly(
        [(ox + 28, oy - 7), (ox + 37, hy - 25), (ox + 45, hy - 19), (ox + 37, oy - 1)],
        body_col,
    )
    p.ellipse(ox + 35, hy - 30, ox + 51, hy - 15, body_col, dark_col, 0.6)
    p.ellipse(ox + 46, hy - 26, ox + 57, hy - 17, _BROWN_L, dark_col, 0.6)

    # Ear
    p.poly([(ox + 37, hy - 29), (ox + 33, hy - 35), (ox + 41, hy - 31)], dark_col)

    # Multi-tine antlers
    p.line([(ox + 41, hy - 30), (ox + 39, hy - 38), (ox + 42, hy - 44)], "#EDE0C8", 1.7)
    p.line([(ox + 39, hy - 37), (ox + 35, hy - 40)], "#EDE0C8", 1.3)
    p.line([(ox + 40, hy - 41), (ox + 44, hy - 43)], "#EDE0C8", 1.2)
    p.line([(ox + 44, hy - 30), (ox + 47, hy - 38), (ox + 51, hy - 42)], "#EDE0C8", 1.7)
    p.line([(ox + 47, hy - 37), (ox + 43, hy - 41)], "#EDE0C8", 1.3)
    p.line([(ox + 49, hy - 40), (ox + 53, hy - 39)], "#EDE0C8", 1.2)

    # Eye
    p.circle(ox + 45.5, hy - 23, 1.4, "#111111")
    p.circle(ox + 45.9, hy - 23.4, 0.45, "#FFFFFF")

    # Nose (Rudolph's nose pulses warmly with phase)
    if rudolph:
        pulse = 0.85 + 0.25 * math.sin(phase * 2.0)
        p.glow_circle(ox + 57, hy - 21.5, 11 * pulse, (255, 55, 55, 225))
        p.circle(ox + 57, hy - 21.5, 3.4, "#EF4444", "#991B1B", 0.6)
        p.circle(ox + 55.8, hy - 22.6, 1.1, "#FECACA")
    else:
        p.circle(ox + 57, hy - 21.5, 2.3, "#2B1B10")

    # Harness collar & jingle bell
    p.line([(ox + 30, oy - 6), (ox + 37, oy - 1)], "#DC2626", 2.4)
    p.line([(ox + 30, oy - 6), (ox + 37, oy - 1)], _GOLD, 1.1)
    p.circle(ox + 34, oy - 3, 1.8, _GOLD, _GOLD_D, 0.4)

    # Near legs
    legs([(10, 0.0), (33, math.pi * 1.35)], body_col)


def _render_santa_frame(phase: float) -> Image.Image:
    p = _Painter(SANTA_W, SANTA_H)
    sleigh_bob = math.sin(phase) * 1.2

    # Background pair of reindeer (slightly darker/offset for depth)
    _draw_reindeer(p, 126, 52, phase + 1.4, False, "#734827", "#4A2E18")
    _draw_reindeer(p, 198, 50, phase + 0.5, False, "#734827", "#4A2E18")

    # Golden reins spanning from Santa's hand to both teams
    sy = 46 + sleigh_bob
    p.line(_bez((104, sy), (135, sy + 5), (165, 51)), _GOLD_D, 1.3)
    p.line(_bez((165, 51), (200, 54), (242, 49)), _GOLD_D, 1.3)
    p.line(_bez((104, sy), (125, sy + 4), (154, 55)), _GOLD, 1.1)
    p.line(_bez((154, 55), (190, 57), (232, 53)), _GOLD, 1.1)

    # Foreground pair of reindeer (with Rudolph leading!)
    _draw_reindeer(p, 136, 57, phase + 0.9, False)
    _draw_reindeer(p, 212, 55, phase, True)

    # Sleigh cargo: overflowing velvet toy sack, candy cane & wrapped gifts
    p.ellipse(14, 18 + sleigh_bob, 56, 52 + sleigh_bob, "#9F1239", "#5A0E0E", 0.9)
    p.ellipse(20, 22 + sleigh_bob, 36, 36 + sleigh_bob, "#BE123C")
    p.poly(
        [(28, 20 + sleigh_bob), (35, 11 + sleigh_bob), (42, 20 + sleigh_bob)],
        "#9F1239",
        "#5A0E0E",
    )
    p.line([(26, 21 + sleigh_bob), (44, 21 + sleigh_bob)], _GOLD, 2.2)

    # Candy cane peeking out of sack
    p.line(
        _bez((44, 22 + sleigh_bob), (48, 10 + sleigh_bob), (53, 14 + sleigh_bob), 8),
        "#FFFFFF",
        2.6,
    )
    p.line(
        _bez((44, 22 + sleigh_bob), (48, 10 + sleigh_bob), (53, 14 + sleigh_bob), 8),
        "#EF4444",
        1.1,
    )

    # Wrapped presents
    p.rect(54, 26 + sleigh_bob, 72, 44 + sleigh_bob, "#16A34A", 1.5)
    p.rect(61, 26 + sleigh_bob, 65, 44 + sleigh_bob, _GOLD)
    p.rect(54, 33 + sleigh_bob, 72, 36 + sleigh_bob, _GOLD)
    p.rect(71, 30 + sleigh_bob, 86, 46 + sleigh_bob, "#2563EB", 1.5)
    p.rect(77, 30 + sleigh_bob, 80, 46 + sleigh_bob, "#FDE68A")

    # Santa Claus (waving right arm + swaying hat pom-pom)
    wave_dy = math.sin(phase) * 4.5
    pom_dy = math.cos(phase) * 2.2

    # Waving back arm
    p.line([(76, 39 + sleigh_bob), (64, 26 + sleigh_bob + wave_dy)], "#B91C1C", 4.8)
    p.circle(63, 25 + sleigh_bob + wave_dy, 3.2, "#FFFFFF")

    # Torso & belt
    p.ellipse(69, 32 + sleigh_bob, 96, 59 + sleigh_bob, "#DC2626", "#7F1D1D", 0.8)
    p.rect(69, 47 + sleigh_bob, 96, 51 + sleigh_bob, "#1F1F1F")
    p.rect(81, 46.5 + sleigh_bob, 86, 51.5 + sleigh_bob, _GOLD)

    # Head, beard, rosy cheek, hat
    p.circle(83, 26 + sleigh_bob, 7.8, "#FDBA74", "#C2743A", 0.5)
    p.circle(86, 28 + sleigh_bob, 1.8, "#FCA5A5")  # rosy cheek
    p.ellipse(74, 26 + sleigh_bob, 92, 41 + sleigh_bob, "#FFFFFF", "#D1D5DB", 0.5)  # beard
    p.circle(88, 25.5 + sleigh_bob, 1.2, "#111111")  # eye
    p.circle(90, 28 + sleigh_bob, 1.8, "#F87171")  # nose
    p.poly(
        [
            (73, 23 + sleigh_bob),
            (92, 22 + sleigh_bob),
            (83, 8 + sleigh_bob),
            (66, 15 + sleigh_bob + pom_dy),
        ],
        "#DC2626",
        "#7F1D1D",
    )
    p.rect(72, 20.5 + sleigh_bob, 93, 25 + sleigh_bob, "#FFFFFF", 2)
    p.circle(66, 15 + sleigh_bob + pom_dy, 3.8, "#FFFFFF")

    # Front arm holding reins
    p.line([(87, 40 + sleigh_bob), (103, sy)], "#DC2626", 5.0)
    p.circle(104, sy, 3.3, "#FFFFFF")

    # Curved Sleigh Bowl & Gold Filigree
    bowl = (
        _bez((6, 38 + sleigh_bob), (6, 66 + sleigh_bob), (34, 66 + sleigh_bob))
        + [(80, 66 + sleigh_bob)]
        + _bez((80, 66 + sleigh_bob), (107, 66 + sleigh_bob), (107, 38 + sleigh_bob))
    )
    p.poly(bowl, "#B91C1C", "#5A0E0E")
    p.line(
        _bez((11, 49 + sleigh_bob), (15, 60 + sleigh_bob), (36, 60 + sleigh_bob))
        + [(78, 60 + sleigh_bob)]
        + _bez((78, 60 + sleigh_bob), (99, 60 + sleigh_bob), (103, 49 + sleigh_bob)),
        _GOLD,
        1.9,
    )
    p.rect(4, 35 + sleigh_bob, 109, 40 + sleigh_bob, _GOLD, 2.5)
    p.rect(4, 35 + sleigh_bob, 109, 37 + sleigh_bob, "#FDE68A", 1)

    # Sleigh bow lantern with warm glow
    lx, ly = 111, 43 + sleigh_bob
    p.glow_circle(lx, ly, 9, (253, 224, 71, 185))
    p.line([(106, 38 + sleigh_bob), (lx, ly - 3)], _GOLD_D, 1.4)
    p.rect(lx - 2.5, ly - 3, lx + 2.5, ly + 4, "#FEF08A", 1)

    # Struts & Curled Runner
    p.line([(30, 65 + sleigh_bob), (30, 81 + sleigh_bob)], "#9CA3AF", 2.2)
    p.line([(80, 65 + sleigh_bob), (80, 81 + sleigh_bob)], "#9CA3AF", 2.2)
    runner = (
        [(2, 68 + sleigh_bob)]
        + _bez((2, 68 + sleigh_bob), (-1, 83 + sleigh_bob), (15, 83 + sleigh_bob))
        + [(98, 83 + sleigh_bob)]
        + _bez((98, 83 + sleigh_bob), (115, 83 + sleigh_bob), (115, 68 + sleigh_bob))
        + _bez((115, 68 + sleigh_bob), (115, 62 + sleigh_bob), (110, 61 + sleigh_bob), 6)
    )
    p.line(runner, "#E2E8F0", 2.8)

    # Magic dust glow at runner tail
    p.glow_circle(6, 40 + sleigh_bob, 8, (255, 225, 130, 150))

    return p.finish(blur=3.0)


def _render_star(angle: float, length: int = 135):
    """Returns (PhotoImage, head_offset_x, head_offset_y) for a multi-layered glowing comet."""
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    perp_x, perp_y = -sin_a, cos_a
    pad = 22
    w = int(abs(cos_a) * length) + pad * 2
    h = int(abs(sin_a) * length) + pad * 2
    hx = w - pad if cos_a >= 0 else pad
    hy = h - pad if sin_a >= 0 else pad
    p = _Painter(w, h)

    n = 56
    tail_x, tail_y = hx - cos_a * length, hy - sin_a * length

    # Outer ionized blue-gold aura ribbon
    prev = (tail_x, tail_y)
    for i in range(1, n + 1):
        t = i / n
        pt = (tail_x + (hx - tail_x) * t, tail_y + (hy - tail_y) * t)
        alpha = int(150 * (t ** 2.0))
        width = 0.8 + 5.2 * (t ** 1.4)
        col = (
            int(160 + 95 * t),
            int(215 + 40 * t),
            255,
            alpha,
        )
        p.glow_line([prev, pt], col, width)
        prev = pt

    # Inner bright warm-white core trail
    prev = (tail_x + (hx - tail_x) * 0.15, tail_y + (hy - tail_y) * 0.15)
    for i in range(8, n + 1):
        t = i / n
        wobble = math.sin(t * 14.0) * (1.0 - t) * 1.1
        pt = (
            tail_x + (hx - tail_x) * t + perp_x * wobble,
            tail_y + (hy - tail_y) * t + perp_y * wobble,
        )
        alpha = int(255 * (t ** 1.6))
        width = 0.4 + 2.8 * t
        col = (255, int(238 + 17 * t), int(175 + 80 * t), alpha)
        p.line([prev, pt], col, width)
        prev = pt

    # Dual-layer coma bloom
    p.glow_circle(hx, hy, 14, (147, 197, 253, 120))
    p.glow_circle(hx, hy, 8.5, (255, 245, 190, 220))
    p.circle(hx, hy, 3.2, (255, 255, 255, 255))

    # 8-point diffraction glint (4 long primary spikes + 4 diagonal secondary spikes)
    r1, r2 = 13.0, 2.2
    p.poly(
        [
            (hx, hy - r1),
            (hx + r2 * 0.45, hy - r2 * 0.45),
            (hx + r1, hy),
            (hx + r2 * 0.45, hy + r2 * 0.45),
            (hx, hy + r1),
            (hx - r2 * 0.45, hy + r2 * 0.45),
            (hx - r1, hy),
            (hx - r2 * 0.45, hy - r2 * 0.45),
        ],
        (255, 255, 255, 245),
    )
    d1, d2 = 7.5, 1.4
    diag = 0.7071
    p.poly(
        [
            (hx + d1 * diag, hy - d1 * diag),
            (hx + d2, hy),
            (hx + d1 * diag, hy + d1 * diag),
            (hx, hy + d2),
            (hx - d1 * diag, hy + d1 * diag),
            (hx - d2, hy),
            (hx - d1 * diag, hy - d1 * diag),
            (hx, hy - d2),
        ],
        (254, 249, 195, 200),
    )
    return _to_photo(p.finish(blur=3.0)), hx, hy


def _star_points(x: float, y: float, r: float) -> list:
    k = r * 0.3
    return [x, y - r, x + k, y - k, x + r, y, x + k, y + k, x, y + r, x - k, y + k, x - r, y, x - k, y - k]


def _rounded_points(x1, y1, x2, y2, r):
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
        x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


class RandomEventSystem:
    """Desktop-only ambient animations: Santa's sleigh, shooting stars, greetings, aurora."""

    SANTA_FIRST_DELAY_S = 12
    SANTA_INTERVAL_S = (120, 300)
    STAR_INTERVAL_S = (50, 160)
    HOHO_INTERVAL_S = (240, 600)
    HOHO_TEXT = ("Ho Ho Ho!", "Merry Christmas!", "Feliz Natal!")

    _TRAIL_COLORS = ("#FFFFFF", "#FEF3C7", "#FDE68A", "#FBBF24", "#D97706")
    _STAR_SPARK_COLORS = ("#FFFFFF", "#FEF08A", "#BAE6FD", "#7DD3FC")
    _TRAIL_LIFE = 26

    def __init__(self, canvas, vw: int, vh: int, vx: int = 0, vy: int = 0):
        self.canvas = canvas
        self.vw, self.vh = vw, vh
        self.vx, self.vy = vx, vy
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
        """Desktop aurora ribbons."""
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
            count = 1 if self.reduce_motion else 8
            self._santa_frames = [
                _to_photo(_render_santa_frame(i * math.tau / 8.0)) for i in range(count)
            ]
        return self._santa_frames

    def _start_santa(self) -> None:
        """Santa's 4-reindeer sleigh gliding across the desktop sky."""
        frames = self._ensure_santa_frames()
        _, wt, _, wb = get_work_area_for_point(0, 0)
        work_h = max(300, wb - wt)
        start_y = (wt - self.vy) + random.uniform(work_h * 0.10, work_h * 0.28)
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
        s["x"] += 3.4
        s["y"] = s["base_y"] + math.sin(s["t"] * 0.055) * 9.0
        c.coords(s["item"], s["x"], s["y"])

        frames = self._santa_frames
        if len(frames) > 1:
            f = (s["t"] // 2) % len(frames)
            if f != s["frame"]:
                s["frame"] = f
                c.itemconfigure(s["item"], image=frames[f])

        # Rich stardust trail from sleigh runners & Rudolph's glow
        if s["t"] % 2 == 0:
            tx = s["x"] + 8 + random.uniform(-4, 4)
            ty = s["y"] + 34 + random.uniform(-6, 6)
            r0 = random.uniform(3.5, 6.2)
            it = c.create_polygon(
                *_star_points(tx, ty, r0), fill=self._TRAIL_COLORS[0], outline=""
            )
            s["trail"].append(
                [it, self._TRAIL_LIFE, tx, ty, random.uniform(-0.35, 0.1), random.uniform(0.15, 0.5), r0]
            )

        alive = []
        for entry in s["trail"]:
            it, life, tx, ty, vx, vy, r0 = entry
            life -= 1
            if life <= 0:
                c.delete(it)
                continue
            tx += vx
            ty += vy
            frac = life / self._TRAIL_LIFE
            col_idx = min(len(self._TRAIL_COLORS) - 1, int((1.0 - frac) * len(self._TRAIL_COLORS)))
            c.coords(it, *_star_points(tx, ty, 1.0 + r0 * frac))
            c.itemconfigure(it, fill=self._TRAIL_COLORS[col_idx])
            alive.append([it, life, tx, ty, vx, vy, r0])
        s["trail"] = alive

        if s["x"] > self.vw + 40:
            c.delete(s["item"])
            for entry in s["trail"]:
                c.delete(entry[0])
            self._santa = None
            self._next_santa = self._tick + self._interval(self.SANTA_INTERVAL_S)

    def _start_star(self) -> None:
        """Shooting star with parabolic arc and shedding stardust sparkles."""
        wl, wt, wr, wb = get_work_area_for_point(0, 0)
        work_w = max(600, wr - wl)
        work_h = max(400, wb - wt)
        x0 = (wl - self.vx) + random.uniform(work_w * 0.12, work_w * 0.72)
        y0 = (wt - self.vy) + random.uniform(28, work_h * 0.22)
        angle = math.pi * random.uniform(0.14, 0.28)
        speed = random.uniform(21.0, 26.0)
        photo, ox, oy = _render_star(angle)
        self._star_photo = photo
        item = self.canvas.create_image(x0 - ox, y0 - oy, image=photo, anchor="nw")
        self._star = {
            "x": x0,
            "y": y0,
            "vx": math.cos(angle) * speed,
            "vy": math.sin(angle) * speed,
            "ox": ox,
            "oy": oy,
            "item": item,
            "life": 46,
            "sparks": [],
        }

    def _update_star(self) -> None:
        s = self._star
        c = self.canvas
        s["x"] += s["vx"]
        s["y"] += s["vy"]
        s["vy"] += 0.14  # gentle celestial arc
        s["vx"] *= 0.992
        c.coords(s["item"], s["x"] - s["ox"], s["y"] - s["oy"])
        s["life"] -= 1

        # Shedding stardust sparkles along the wake
        if s["life"] > 4 and s["life"] % 2 == 0:
            for _ in range(2):
                sx = s["x"] + random.uniform(-6, 6)
                sy = s["y"] + random.uniform(-6, 6)
                r0 = random.uniform(2.5, 4.8)
                sp = c.create_polygon(
                    *_star_points(sx, sy, r0),
                    fill=random.choice(self._STAR_SPARK_COLORS),
                    outline="",
                )
                s["sparks"].append(
                    [sp, 18, sx, sy, random.uniform(-0.6, 0.6), random.uniform(-0.3, 0.6), r0]
                )

        alive_sparks = []
        for entry in s["sparks"]:
            sp, slife, sx, sy, svx, svy, r0 = entry
            slife -= 1
            if slife <= 0:
                c.delete(sp)
                continue
            sx += svx
            sy += svy
            frac = slife / 18.0
            c.coords(sp, *_star_points(sx, sy, 0.8 + r0 * frac))
            alive_sparks.append([sp, slife, sx, sy, svx, svy, r0])
        s["sparks"] = alive_sparks

        done = s["life"] <= 0 or s["y"] > self.vh or s["x"] > self.vw or s["x"] < 0
        if done and not s["sparks"]:
            c.delete(s["item"])
            self._star = None
            self._star_photo = None
            self._next_star = self._tick + self._interval(self.STAR_INTERVAL_S)
        elif done:
            c.itemconfigure(s["item"], state="hidden")

    def _start_hoho(self) -> None:
        """Festive speech bubble on the desktop."""
        c = self.canvas
        text = random.choice(self.HOHO_TEXT)
        _, _, wr, wb = get_work_area_for_point(0, 0)
        x = (wr - self.vx) - 160
        y = (wb - self.vy) - 100

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
                smooth=True,
                fill="#020617",
                stipple="gray50",
                outline="",
            )
            bubble = c.create_polygon(
                *_rounded_points(x1, y1, x2, y2, 14),
                smooth=True,
                fill="#7F1D1D",
                outline="#FBBF24",
                width=2,
            )
            tail = c.create_polygon(
                x2 - 30, y2 - 1, x2 - 12, y2 - 1, x2 - 8, y2 + 12,
                fill="#7F1D1D",
                outline="#FBBF24",
                width=2,
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