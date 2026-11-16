# src/window_snow.py
import math
import random


def _subtract_intervals(
    base: tuple[float, float], blockers: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Returns visible horizontal segments of `base` after subtracting occluded `blockers`."""
    spans = [base]
    for bx1, bx2 in blockers:
        next_spans = []
        for sx1, sx2 in spans:
            if bx2 <= sx1 or bx1 >= sx2:
                next_spans.append((sx1, sx2))
            else:
                if bx1 > sx1:
                    next_spans.append((sx1, bx1))
                if bx2 < sx2:
                    next_spans.append((bx2, sx2))
        spans = next_spans
        if not spans:
            break
    return [s for s in spans if (s[1] - s[0]) >= 44.0]


class WindowSnowLedges:
    """Renders sculpted snow drifts & icicles perched on visible top edges of open windows."""

    def __init__(self, canvas):
        self.canvas = canvas
        self.enabled = True
        # hwnd_key -> {"rect": (x1, y1, x2, y2), "depth": float, "seed": int, "items": list[int]}
        self._drifts: dict[int, dict] = {}
        # Falling snow clumps when a snow-capped window moves or closes
        self._clumps: list[list] = []

    def clear(self) -> None:
        for entry in self._drifts.values():
            for it in entry["items"]:
                self.canvas.delete(it)
        self._drifts.clear()
        for c in self._clumps:
            self.canvas.delete(c[0])
        self._clumps.clear()

    def set_enabled(self, on: bool) -> None:
        self.enabled = on
        if not on:
            self.clear()

    @staticmethod
    def _extract_entries(
        env_rects,
    ) -> list[tuple[int, tuple[float, float, float, float]]]:
        """Normalizes (hwnd, (x1, y1, x2, y2)) entries from WindowTracker.get_env_rects()."""
        entries: list[tuple[int, tuple[float, float, float, float]]] = []
        if isinstance(env_rects, dict):
            raw_entries = env_rects.get("window_entries")
            if raw_entries:
                for hwnd, r in raw_entries:
                    x1, y1, x2, y2 = float(r[0]), float(r[1]), float(r[2]), float(r[3])
                    if (x2 - x1) >= 160.0 and (y2 - y1) >= 80.0 and y1 >= 4.0:
                        entries.append((int(hwnd), (x1, y1, x2, y2)))
                return entries

            raw = None
            for key in ("windows", "rects", "window_rects", "ledges"):
                if env_rects.get(key):
                    raw = env_rects[key]
                    break
            if raw is None and env_rects.get("fg"):
                fg = env_rects["fg"]
                fg_id = int(env_rects.get("fg_hwnd") or 1)
                x1, y1, x2, y2 = float(fg[0]), float(fg[1]), float(fg[2]), float(fg[3])
                if (x2 - x1) >= 160.0 and (y2 - y1) >= 80.0 and y1 >= 4.0:
                    return [(fg_id, (x1, y1, x2, y2))]
                return []
        elif isinstance(env_rects, (list, tuple)):
            raw = env_rects
        else:
            return []

        for idx, r in enumerate(raw or []):
            if isinstance(r, (list, tuple)) and len(r) >= 4:
                x1, y1, x2, y2 = float(r[0]), float(r[1]), float(r[2]), float(r[3])
            elif hasattr(r, "left") and hasattr(r, "top"):
                x1, y1, x2, y2 = float(r.left), float(r.top), float(r.right), float(r.bottom)
            else:
                continue
            if (x2 - x1) >= 160.0 and (y2 - y1) >= 80.0 and y1 >= 4.0:
                entries.append((idx + 1, (x1, y1, x2, y2)))
        return entries

    def _shatter_drift(
        self, rect: tuple[float, float, float, float], depth: float
    ) -> None:
        """Turns a displaced snow cap into tumbling snow clumps."""
        x1, y1, x2, _ = rect
        span = max(40.0, x2 - x1)
        count = min(22, max(5, int((span / 45.0) * depth)))
        for _ in range(count):
            px = random.uniform(x1 + 8, x2 - 8)
            py = y1 + random.uniform(-4, 2)
            r = random.uniform(2.2, 4.4) * (0.5 + 0.5 * depth)
            it = self.canvas.create_oval(
                px - r, py - r, px + r, py + r, fill="#F8FAFC", outline="#BAE6FD"
            )
            self._clumps.append(
                [it, px, py, random.uniform(-1.1, 1.1), random.uniform(-1.4, 0.4), r, 28]
            )

    def _update_clumps(self) -> None:
        alive = []
        for entry in self._clumps:
            it, x, y, vx, vy, r, life = entry
            life -= 1
            if life <= 0:
                self.canvas.delete(it)
                continue
            x += vx
            y += vy
            vy += 0.24
            nr = max(0.8, r * (life / 28.0))
            self.canvas.coords(it, x - nr, y - nr, x + nr, y + nr)
            alive.append([it, x, y, vx, vy, r, life])
        self._clumps = alive

    def _render_ledge(
        self, x1: float, x2: float, y: float, depth: float, seed: int
    ) -> list[int]:
        items: list[int] = []
        rng = random.Random(seed)
        h_max = 3.5 + 7.5 * depth
        step = 18.0
        n = max(3, int((x2 - x1) / step))

        top_pts: list[float] = [x1, y]
        bot_pts: list[float] = []
        for i in range(n + 1):
            t = i / n
            px = x1 + (x2 - x1) * t
            taper = math.sin(t * math.pi) ** 0.45
            bump = 0.65 + 0.35 * math.sin(t * math.pi * (3 + (seed % 4)) + seed)
            ridge_y = y - h_max * taper * bump
            lip_y = y + (1.5 + 2.2 * depth) * taper * (0.6 + 0.4 * rng.random())
            top_pts.extend((px, ridge_y))
            bot_pts.append((px, lip_y))

        poly_pts = list(top_pts)
        for px, py in reversed(bot_pts):
            poly_pts.extend((px, py))

        shadow = self.canvas.create_polygon(
            *poly_pts, smooth=True, fill="#BAE6FD", outline=""
        )
        items.append(shadow)

        crest_pts: list[float] = [x1 + 2, y]
        for i in range(n + 1):
            t = i / n
            px = x1 + (x2 - x1) * t
            taper = math.sin(t * math.pi) ** 0.45
            bump = 0.65 + 0.35 * math.sin(t * math.pi * (3 + (seed % 4)) + seed)
            crest_pts.extend((px, y - h_max * taper * bump))
        crest_pts.extend((x2 - 2, y))
        crest = self.canvas.create_polygon(
            *crest_pts, smooth=True, fill="#FFFFFF", outline=""
        )
        items.append(crest)

        if depth >= 0.50 and (x2 - x1) >= 120:
            icicle_count = min(5, max(2, int((x2 - x1) / 140)))
            for idx in range(icicle_count):
                frac = (idx + 0.35 + 0.3 * rng.random()) / icicle_count
                ix = x1 + 14 + (x2 - x1 - 28) * frac
                iw = 2.0 + 1.4 * depth
                ih = (7.0 + rng.uniform(3.0, 9.0)) * depth
                ic = self.canvas.create_polygon(
                    ix - iw,
                    y + 1.0,
                    ix + iw,
                    y + 1.0,
                    ix,
                    y + ih,
                    fill="#E0F2FE",
                    outline="#7DD3FC",
                )
                items.append(ic)

        return items

    def update(self, tick: int, env_rects, snow_active: bool = True) -> None:
        if not self.enabled:
            if self._drifts or self._clumps:
                self.clear()
            return

        self._update_clumps()

        if tick % 3 != 0:
            return

        entries = self._extract_entries(env_rects)[:8]
        new_drifts: dict[int, dict] = {}
        matched_keys: set[int] = set()

        for idx, (key, rect) in enumerate(entries):
            x1, y1, x2, y2 = rect
            blockers = []
            for _, higher in entries[:idx]:
                hx1, hy1, hx2, hy2 = higher
                if hy1 <= y1 + 10.0 and hy2 >= y1 - 4.0:
                    blockers.append((hx1, hx2))

            visible_spans = _subtract_intervals((x1 + 6.0, x2 - 6.0), blockers)
            if not visible_spans:
                continue

            prev = self._drifts.get(key)
            if prev is not None:
                px1, py1, px2, _ = prev["rect"]
                moved = (
                    abs(x1 - px1) > 8.0
                    or abs(y1 - py1) > 8.0
                    or abs(x2 - px2) > 12.0
                )
                for it in prev["items"]:
                    self.canvas.delete(it)
                if moved:
                    if prev["depth"] > 0.2:
                        self._shatter_drift(prev["rect"], prev["depth"])
                    depth = 0.14 if snow_active else 0.0
                    seed = random.randint(1, 9999)
                else:
                    rate = 0.018 if snow_active else -0.008
                    depth = max(0.0, min(1.0, prev["depth"] + rate))
                    seed = prev["seed"]
                matched_keys.add(key)
            else:
                depth = 0.16 if snow_active else 0.0
                seed = random.randint(1, 9999)

            if depth <= 0.02:
                continue

            items: list[int] = []
            for sx1, sx2 in visible_spans:
                items.extend(self._render_ledge(sx1, sx2, y1, depth, seed))

            new_drifts[key] = {
                "rect": rect,
                "depth": depth,
                "seed": seed,
                "items": items,
            }

        for old_key, old_entry in self._drifts.items():
            if old_key not in matched_keys:
                for it in old_entry["items"]:
                    self.canvas.delete(it)
                if old_entry["depth"] > 0.2:
                    self._shatter_drift(old_entry["rect"], old_entry["depth"])

        self._drifts = new_drifts