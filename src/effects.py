# src/effects.py
import datetime
import json
import math
import random
import threading
import time
import tkinter as tk
import urllib.request

from sprites import build_flake_sprites
from win32 import is_reduce_motion_enabled, uses_fahrenheit, user32

# Each entry: (5-step bulb glass gradient, 5-step filament core gradient, outer bloom color)
BULB_PALETTE = [
    (
        ("#451A03", "#92400E", "#D97706", "#F59E0B", "#FDE68A"),
        ("#78350F", "#B45309", "#FDE047", "#FEF9C3", "#FFFFFF"),
        "#F59E0B",
    ),
    (
        ("#450A0A", "#7F1D1D", "#B91C1C", "#EF4444", "#FCA5A5"),
        ("#7F1D1D", "#991B1B", "#F87171", "#FECACA", "#FFF1F2"),
        "#EF4444",
    ),
    (
        ("#022C22", "#064E3B", "#059669", "#10B981", "#6EE7B7"),
        ("#064E3B", "#047857", "#34D399", "#A7F3D0", "#ECFDF5"),
        "#10B981",
    ),
    (
        ("#082F49", "#0C4A6E", "#0284C7", "#38BDF8", "#BAE6FD"),
        ("#0C4A6E", "#0369A1", "#7DD3FC", "#E0F2FE", "#F0F9FF"),
        "#38BDF8",
    ),
]

_SIN_TABLE = [math.sin(i * math.tau / 256.0) for i in range(256)]
_PHASE_SCALE = 256.0 / math.tau
_TICK_SCALE = 0.03 * _PHASE_SCALE


class Flake:
    __slots__ = (
        "item",
        "x",
        "y",
        "size",
        "vy",
        "phase_idx",
        "sway",
        "layer",
        "sprite_idx",
        "stuck_to",
        "pile_key",
        "pile_size",
        "melt_rate",
    )

    def __init__(self, item, x, y, size, vy, phase_idx, sway, layer, sprite_idx, melt_rate):
        self.item = item
        self.x = x
        self.y = y
        self.size = size
        self.vy = vy
        self.phase_idx = phase_idx
        self.sway = sway
        self.layer = layer
        self.sprite_idx = sprite_idx
        self.stuck_to = None
        self.pile_key = None
        self.pile_size = 0.0
        self.melt_rate = melt_rate


class SnowSystem:
    def __init__(self, canvas, vw, vh):
        self.canvas = canvas
        self.vw, self.vh = vw, vh
        self.falling: list[Flake] = []
        self.stuck: list[Flake] = []
        self.sprites = build_flake_sprites()
        self.piles: dict[tuple, float] = {}
        self.wind = 0.0
        self.target_wind = 0.0
        self.enabled = True
        self.target_count = 140
        self._reduce_motion = is_reduce_motion_enabled()
        self._sway_mul = 0.4 if self._reduce_motion else 1.0
        self._speed_mul = 0.7 if self._reduce_motion else 1.0

    @property
    def total_count(self) -> int:
        return len(self.falling) + len(self.stuck)

    def set_enabled(self, enabled: bool):
        self.enabled = enabled
        self.sync_count(self.target_count if enabled else 0)

    def set_target(self, target: int):
        self.target_count = target
        self.sync_count(target if self.enabled else 0)

    def sync_count(self, target: int):
        while self.total_count < target:
            self.falling.append(self._spawn())
        while self.total_count > target:
            f = self.falling.pop() if self.falling else self.stuck.pop()
            self._decrement_pile(f)
            self.canvas.delete(f.item)
        if target == 0:
            self.piles.clear()

    def _decrement_pile(self, flake: Flake):
        key = flake.pile_key
        if key is not None and key in self.piles:
            new_h = self.piles[key] - flake.pile_size
            if new_h < 0.05:
                del self.piles[key]
            else:
                self.piles[key] = new_h

    def _random_flake_props(self):
        r = random.random()
        if r < 0.45:
            layer, s_idx, size, vy = 0, 0, 8.0, random.uniform(0.9, 1.6)
        elif r < 0.80:
            layer, s_idx, size, vy = 1, 3, 12.0, random.uniform(1.8, 2.9)
        else:
            layer, s_idx, size, vy = 2, 6, 16.0, random.uniform(3.0, 4.4)
        sway = random.uniform(0.3, 1.1) * (layer + 1) * 0.45
        return layer, s_idx, size, vy * self._speed_mul, sway * self._sway_mul

    def _spawn(self, random_y=True) -> Flake:
        layer, s_idx, size, vy, sway = self._random_flake_props()
        x = random.uniform(0, self.vw)
        y = random.uniform(0, self.vh) if random_y else -size
        item = self.canvas.create_image(x, y, image=self.sprites[s_idx], anchor="nw")
        return Flake(
            item=item,
            x=x,
            y=y,
            size=size,
            vy=vy,
            phase_idx=random.randint(0, 255),
            sway=sway,
            layer=layer,
            sprite_idx=s_idx,
            melt_rate=random.uniform(0.12, 0.30),
        )

    def _recycle(self, f: Flake):
        self._decrement_pile(f)
        f.stuck_to = None
        f.pile_key = None
        f.pile_size = 0.0
        layer, s_idx, size, vy, sway = self._random_flake_props()
        f.layer = layer
        f.size = size
        f.vy = vy
        f.sway = sway
        f.x = random.uniform(0, self.vw)
        f.y = -size
        if s_idx != f.sprite_idx:
            f.sprite_idx = s_idx
            self.canvas.itemconfigure(f.item, image=self.sprites[s_idx])
        self.canvas.coords(f.item, f.x, f.y)

    def _stick(self, f: Flake, edge_y: float, edge_key):
        bucket = int(f.x) >> 3
        key = (edge_key, bucket)
        pile_h = self.piles.get(key, 0.0)
        f.stuck_to = edge_key
        f.pile_key = key
        f.pile_size = max(0.4, f.size * 0.35)
        f.y = edge_y - (14.0 if pile_h > 14.0 else pile_h) - random.uniform(0, 1.2)
        new_h = pile_h + f.pile_size
        self.piles[key] = 14.0 if new_h > 14.0 else new_h
        f.vy = 0.0
        self.canvas.coords(f.item, f.x, f.y)

    def _update_stuck(self, env_rects):
        if not self.stuck:
            return
        tb = env_rects["taskbar"]
        fg = env_rects["fg"]
        fg_hwnd = env_rects["fg_hwnd"]
        still_stuck = []

        for f in self.stuck:
            x, y = f.x, f.y
            valid = False
            if f.stuck_to == "taskbar" and tb:
                tx1, ty1, tx2, _ = tb
                valid = tx1 - 20 <= x <= tx2 + 20 and ty1 - 20 <= y <= ty1 + 20
            elif f.stuck_to != "taskbar" and fg and f.stuck_to == fg_hwnd:
                wx1, wy1, wx2, _ = fg
                valid = wx1 - 20 <= x <= wx2 + 20 and wy1 - 20 <= y <= wy1 + 20

            if not valid:
                f.stuck_to = None
                self._decrement_pile(f)
                f.pile_key = None
                f.pile_size = 0.0
                f.vy = random.uniform(1.0, 2.0) * self._speed_mul
                self.falling.append(f)
                continue

            f.size -= f.melt_rate
            if f.size <= 1.5:
                self._recycle(f)
                self.falling.append(f)
                continue

            new_idx = (f.layer * 3) + (2 if f.size > 12 else 1 if f.size > 8 else 0)
            if new_idx != f.sprite_idx:
                f.sprite_idx = new_idx
                self.canvas.itemconfigure(f.item, image=self.sprites[new_idx])
            still_stuck.append(f)

        self.stuck = still_stuck

    def update(self, tick, cx, cy, env_rects):
        if not self.enabled:
            return
        if tick % 180 == 0:
            self.target_wind = random.uniform(-1.6, 1.6)
        self.wind += (self.target_wind - self.wind) * 0.02

        if tick % 6 == 0:
            self._update_stuck(env_rects)

        if not self.falling:
            return

        tb = env_rects["taskbar"]
        fg = env_rects["fg"]
        fg_hwnd = env_rects["fg_hwnd"]
        tick_offset = int(tick * _TICK_SCALE)
        wind = self.wind
        vw = float(self.vw)
        vh = float(self.vh)
        move = self.canvas.move
        sin_tbl = _SIN_TABLE
        still_falling = []

        for f in self.falling:
            old_x, old_y = f.x, f.y
            size = f.size

            x = old_x + sin_tbl[(tick_offset + f.phase_idx) & 255] * f.sway + wind * (
                0.4 + f.layer * 0.35
            )
            y = old_y + f.vy

            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            if 0 < d2 < 2500.0:
                dist = math.sqrt(d2)
                f_push = ((50.0 - dist) / 50.0) * 2.5
                x += (dx / dist) * f_push
                y += (dy / dist) * f_push

            if tb:
                tx1, ty1, tx2, _ = tb
                if tx1 - 2 <= x <= tx2 + 2 and -3.0 < (y - ty1) < 3.0:
                    f.x, f.y = x, y
                    self._stick(f, ty1, "taskbar")
                    self.stuck.append(f)
                    continue

            if fg and fg_hwnd:
                wx1, wy1, wx2, _ = fg
                if wx1 - 2 <= x <= wx2 + 2 and -3.0 < (y - wy1) < 3.0:
                    f.x, f.y = x, y
                    self._stick(f, wy1, fg_hwnd)
                    self.stuck.append(f)
                    continue

            if y > vh + size:
                self._recycle(f)
                still_falling.append(f)
                continue

            if x < -size:
                x = vw
            elif x > vw + size:
                x = -size

            move(f.item, x - old_x, y - old_y)
            f.x, f.y = x, y
            still_falling.append(f)

        self.falling = still_falling


class FairyLights:
    def __init__(self, canvas, monitors, vx, vy):
        self.canvas = canvas
        self.light_items = []
        self.bulbs = []
        self._speed_mul = 0.5 if is_reduce_motion_enabled() else 1.0
        self._build(monitors, vx, vy)

    def _build(self, monitors, vx, vy):
        for left, top, right, _ in monitors:
            rl, rr, rt = left - vx, right - vx, top - vy
            width = rr - rl
            span = 168
            steps = max(1, int(width // span))
            actual = width / steps

            main_wire = []
            twist_wire = []
            for s in range(steps):
                x0 = rl + s * actual
                for sub in range(16):
                    t = sub / 16.0
                    wx = x0 + t * actual
                    wy = rt + 5 + math.sin(t * math.pi) * 15
                    main_wire.extend((wx, wy))
                    twist_wire.extend((wx, wy + math.sin(wx * 0.22) * 1.1))
            main_wire.extend((rr, rt + 5))
            twist_wire.extend((rr, rt + 5))

            self.light_items.append(
                self.canvas.create_line(*main_wire, fill="#14261C", width=3, smooth=True)
            )
            self.light_items.append(
                self.canvas.create_line(*twist_wire, fill="#264032", width=1, smooth=True)
            )

            spacing = 42
            count = int(width // spacing)
            for i in range(1, count):
                bx = rl + i * spacing
                local_t = ((i * spacing) % actual) / actual
                by = rt + 5 + math.sin(local_t * math.pi) * 15

                slope = (math.pi * 15.0 / actual) * math.cos(local_t * math.pi)
                nx = -slope * 0.35
                ny = 1.0

                glass_ramp, core_ramp, bloom_color = BULB_PALETTE[i % len(BULB_PALETTE)]
                cx, cy = bx + nx * 10, by + ny * 10

                outer_halo = self.canvas.create_oval(
                    cx - 11, cy - 10, cx + 12, cy + 13,
                    fill="", outline=glass_ramp[2], width=1,
                )
                inner_halo = self.canvas.create_oval(
                    cx - 7.5, cy - 7, cx + 8.5, cy + 10,
                    fill="", outline=bloom_color, width=1,
                )
                socket = self.canvas.create_rectangle(
                    bx - 2.5, by - 1, bx + 3.5, by + 4, fill="#18181B", outline="#27272A", width=1
                )
                collar = self.canvas.create_rectangle(
                    bx + nx * 3 - 3, by + ny * 3, bx + nx * 3 + 4, by + ny * 3 + 3,
                    fill="#3F3F46", outline="",
                )
                bulb = self.canvas.create_oval(
                    cx - 4.5, cy - 5.5, cx + 5.5, cy + 7.5,
                    fill=glass_ramp[4], outline=glass_ramp[2], width=1,
                )
                core = self.canvas.create_oval(
                    cx - 1.8, cy - 2.5, cx + 2.5, cy + 3.5,
                    fill=core_ramp[4], outline="",
                )
                glint = self.canvas.create_oval(
                    cx - 2.6, cy - 3.6, cx - 1.0, cy - 1.0,
                    fill="#FFFFFF", outline="",
                )

                self.light_items.extend((outer_halo, inner_halo, socket, collar, bulb, core, glint))
                self.bulbs.append(
                    {
                        "bulb": bulb,
                        "core": core,
                        "outer_halo": outer_halo,
                        "inner_halo": inner_halo,
                        "glass": glass_ramp,
                        "cores": core_ramp,
                        "phase": i * 0.85,
                        "speed": (0.055 + (i % 3) * 0.012) * self._speed_mul,
                        "level": 4,
                    }
                )

    def toggle(self, visible: bool):
        state = "normal" if visible else "hidden"
        for item in self.light_items:
            self.canvas.itemconfigure(item, state=state)

    def update(self, tick: int):
        for b in self.bulbs:
            wave = 0.5 + 0.5 * math.sin(tick * b["speed"] + b["phase"])
            lvl = min(4, int(wave * 5.0))
            if lvl == b["level"]:
                continue
            b["level"] = lvl

            glass = b["glass"]
            self.canvas.itemconfigure(b["bulb"], fill=glass[lvl], outline=glass[max(0, lvl - 1)])
            self.canvas.itemconfigure(b["core"], fill=b["cores"][lvl])
            self.canvas.itemconfigure(b["inner_halo"], state="normal" if lvl >= 2 else "hidden")
            self.canvas.itemconfigure(b["outer_halo"], state="normal" if lvl >= 3 else "hidden")


class WeatherMonitor:
    """Periodically checks local temperature in a background thread."""

    THRESHOLD_C = 18.5
    REFRESH_SEC = 1800

    def __init__(self, on_update=None):
        self.temp_c: float | None = None
        self.fahrenheit = uses_fahrenheit()
        self._on_update = on_update
        self._running = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_cold(self) -> bool:
        return self.temp_c is not None and self.temp_c <= self.THRESHOLD_C

    def format_temp(self) -> str:
        if self.temp_c is None:
            return ""
        if self.fahrenheit:
            return f"{self.temp_c * 9.0 / 5.0 + 32.0:.0f}°F"
        return f"{self.temp_c:.0f}°C"

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop.set()

    def _worker(self) -> None:
        while self._running:
            self._fetch()
            if self._stop.wait(self.REFRESH_SEC):
                return

    def _fetch(self) -> None:
        try:
            req = urllib.request.Request(
                "https://ipwho.is/",
                headers={"User-Agent": "ChristmasOverlay/1.0"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                geo = json.loads(resp.read().decode("utf-8"))
            if not geo.get("success"):
                return
            lat, lon = geo["latitude"], geo["longitude"]
            w_url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}&current=temperature_2m"
            )
            w_req = urllib.request.Request(
                w_url, headers={"User-Agent": "ChristmasOverlay/1.0"}
            )
            with urllib.request.urlopen(w_req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            val = data.get("current", {}).get("temperature_2m")
            if val is not None:
                self.temp_c = float(val)
                if self._on_update:
                    self._on_update()
        except Exception:
            pass


class FrostBorder:
    IDLE_THRESHOLD_SEC = 300.0
    _BANDS = (
        ("gray12", "#E0F2FE", 42.0),
        ("gray25", "#BAE6FD", 22.0),
        ("gray50", "#7DD3FC", 10.0),
    )

    def __init__(self, canvas, vw: int, vh: int, initial_progress: float = 0.0):
        self.canvas = canvas
        self.vw = vw
        self.vh = vh
        self.progress = max(0.0, min(1.0, initial_progress))
        self._rendered_progress = -1.0
        self._visible = False
        self.layers = []

        for stipple, color, max_t in self._BANDS:
            rects = (
                canvas.create_rectangle(0, 0, vw, 0, fill=color, outline="", stipple=stipple, state="hidden"),
                canvas.create_rectangle(0, vh, vw, vh, fill=color, outline="", stipple=stipple, state="hidden"),
                canvas.create_rectangle(0, 0, 0, vh, fill=color, outline="", stipple=stipple, state="hidden"),
                canvas.create_rectangle(vw, 0, vw, vh, fill=color, outline="", stipple=stipple, state="hidden"),
            )
            self.layers.append((rects, max_t))

        if self.progress > 0.0:
            self._apply_geometry()

    def update(self, mode_idx: int, idle_sec: float, is_cold: bool) -> None:
        if mode_idx == 2:
            target = 0.0
        elif mode_idx == 1:
            target = 1.0
        else:
            target = 1.0 if (idle_sec >= self.IDLE_THRESHOLD_SEC or is_cold) else 0.0

        if target > self.progress:
            if self.progress < 0.04:
                self.progress = 0.04
            self.progress = min(target, self.progress + 0.00055)
        elif target < self.progress:
            self.progress = max(target, self.progress - 0.016)

        if abs(self.progress - self._rendered_progress) >= 0.003 or (
            self.progress == 0.0 and self._visible
        ):
            self._apply_geometry()

    def _apply_geometry(self) -> None:
        self._rendered_progress = self.progress
        p = self.progress
        if p <= 0.001:
            if self._visible:
                for rects, _ in self.layers:
                    for item in rects:
                        self.canvas.itemconfigure(item, state="hidden")
                self._visible = False
            return

        if not self._visible:
            for rects, _ in self.layers:
                for item in rects:
                    self.canvas.itemconfigure(item, state="normal")
            self._visible = True

        vw, vh = self.vw, self.vh
        coords = self.canvas.coords
        eased = 1.0 - (1.0 - p) * (1.0 - p)
        for (top_r, bot_r, left_r, right_r), max_t in self.layers:
            t = max_t * eased
            coords(top_r, 0, 0, vw, t)
            coords(bot_r, 0, vh - t, vw, vh)
            coords(left_r, 0, 0, t, vh)
            coords(right_r, vw - t, 0, vw, vh)


class CountdownHUD:
    def __init__(self, canvas, vx: int, vy: int, visible: bool = True, user_name: str = ""):
        from win32 import get_work_area_for_point

        self.canvas = canvas
        self.user_name = user_name or ""
        self.last_date = datetime.date.today()
        _, _, wr, wb = get_work_area_for_point(0, 0)
        self.item = canvas.create_text(
            wr - 40 - vx,
            wb - 14 - vy,
            text=self._format_text(self.last_date, self.user_name),
            fill="#CBD5E1",
            font=("Segoe UI", 10, "bold"),
            anchor="se",
            state="normal" if visible else "hidden",
        )

    @staticmethod
    def _format_text(today: datetime.date, name: str = "") -> str:
        xmas = datetime.date(today.year, 12, 25)
        if today > xmas:
            xmas = datetime.date(today.year + 1, 12, 25)
        days = (xmas - today).days
        who = f", {name}" if name else ""
        if days == 0:
            return f"Merry Christmas{who}!"
        return f"{days} day{'s' if days > 1 else ''} to Christmas{who}"

    def toggle(self, visible: bool):
        self.canvas.itemconfigure(self.item, state="normal" if visible else "hidden")

    def refresh_if_new_day(self):
        today = datetime.date.today()
        if today != self.last_date:
            self.last_date = today
            self.canvas.itemconfigure(self.item, text=self._format_text(today, self.user_name))


class SparkleSystem:
    _COLORS = ("#FBBF24", "#38BDF8", "#FFFFFF", "#10B981")

    def __init__(self, canvas):
        self.canvas = canvas
        self.particles = []
        self.snowballs = []

    def spawn(self, cx: float, cy: float):
        for _ in range(8):
            a, sp = random.uniform(0, math.tau), random.uniform(1.5, 3.5)
            item = self.canvas.create_oval(
                cx, cy, cx + 4, cy + 4, fill=random.choice(self._COLORS), outline=""
            )
            self.particles.append([item, cx, cy, math.cos(a) * sp, math.sin(a) * sp, 30])

    def spawn_snowball(self, cx: float, cy: float):
        item = self.canvas.create_oval(
            cx - 5, cy - 5, cx + 5, cy + 5, fill="#FFFFFF", outline="#DDE7F0"
        )
        vx = random.uniform(-2.0, 2.0)
        vy = random.uniform(-14.0, -10.0)
        self.snowballs.append([item, cx, cy, vx, vy, 90])

    def _update_snowballs(self, env_rects: dict):
        if not self.snowballs:
            return
        tb = env_rects.get("taskbar")
        alive = []
        for s in self.snowballs:
            item, x, y, vx, vy, life = s
            vy += 0.55
            x += vx
            y += vy
            s[1], s[2], s[3], s[4], s[5] = x, y, vx, vy, life - 1

            hit = False
            if tb and tb[0] <= x <= tb[2] and tb[1] - 4 <= y <= tb[1] + 6 and vy > 0:
                hit = True

            if hit or life - 1 <= 0:
                self._splat(x, y)
                self.canvas.delete(item)
            else:
                self.canvas.coords(item, x - 5, y - 5, x + 5, y + 5)
                alive.append(s)
        self.snowballs = alive

    def _splat(self, x: float, y: float):
        for _ in range(6):
            a = random.uniform(0, math.tau)
            sp = random.uniform(1.0, 3.0)
            item = self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#FFFFFF", outline="")
            self.particles.append([item, x, y, math.cos(a) * sp, math.sin(a) * sp, 15])

    def update(self, env_rects: dict | None = None):
        if env_rects is not None:
            self._update_snowballs(env_rects)
        if not self.particles:
            return
        alive = []
        for p in self.particles:
            p[1] += p[3]
            p[2] += p[4]
            p[4] += 0.15
            p[5] -= 1
            if p[5] <= 0:
                self.canvas.delete(p[0])
            else:
                s = 4.0 * (p[5] / 30.0)
                self.canvas.coords(p[0], p[1], p[2], p[1] + s, p[2] + s)
                alive.append(p)
        self.particles = alive