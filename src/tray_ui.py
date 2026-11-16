# src/tray_ui.py
from ctypes import byref, wintypes
import threading
import tkinter as tk
import webbrowser

from pystray import Icon, Menu, MenuItem

from sprites import load_tray_image
from state import FROST_MODES, SNOW_MODES, SPARKLE_MODES
from version import __version__, GITHUB_REPO
from win32 import (
    apply_rounded_corners,
    get_work_area_for_point,
    is_windows_light_theme,
    user32,
)

def _palette(light: bool) -> dict:
    if light:
        return {
            "bg": "#F9FAFB",
            "border": "#E5E7EB",
            "fg": "#111827",
            "muted": "#6B7280",
            "hover": "#E5E7EB",
            "pill": "#F3F4F6",
            "accent": "#DC2626",
            "accent_fg": "#FFFFFF",
            "on": "#16A34A",
            "off": "#9CA3AF",
            "sep": "#E5E7EB",
            "link": "#2563EB",
        }
    return {
        "bg": "#18181B",
        "border": "#27272A",
        "fg": "#F4F4F5",
        "muted": "#A1A1AA",
        "hover": "#27272A",
        "pill": "#202024",
        "accent": "#DC2626",
        "accent_fg": "#FFFFFF",
        "on": "#22C55E",
        "off": "#52525B",
        "sep": "#27272A",
        "link": "#60A5FA",
    }


class TrayPopup:
    WIDTH = 296

    def __init__(self, root: tk.Tk, state, enqueue, actions: dict):
        self.root = root
        self.state = state
        self.enqueue = enqueue
        self.actions = actions
        self.win: tk.Toplevel | None = None
        self.is_open = False
        self._widgets = {}
        self._focus_ready = False
        self._focus_gen = 0
        self._pal = _palette(False)

    def toggle_at(self, x: int, y: int) -> None:
        if self.is_open:
            self.hide()
        else:
            self.show_at(x, y)

    def show_at(self, x: int, y: int) -> None:
        self._pal = _palette(is_windows_light_theme())
        if self.win is None or not self.win.winfo_exists():
            self._build()
        else:
            self._retheme()
        self.refresh()

        self.win.update_idletasks()
        w = self.WIDTH
        h = self.win.winfo_reqheight()
        wl, wt, wr, wb = get_work_area_for_point(x, y)

        px = max(wl + 8, min(int(x) - w // 2, wr - w - 8))
        py = int(y) - h - 12
        if py < wt + 8:
            py = min(wb - h - 8, int(y) + 12)
        py = max(wt + 8, min(py, wb - h - 8))

        self.win.geometry(f"{w}x{h}+{px}+{py}")
        self._focus_gen += 1
        self._focus_ready = False
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        self.is_open = True
        self.win.after(120, lambda: self._arm_focus_close(self._focus_gen))

    def _arm_focus_close(self, gen: int) -> None:
        if gen == self._focus_gen:
            self._focus_ready = True

    def hide(self) -> None:
        if self.win is not None and self.win.winfo_exists():
            self.win.withdraw()
        self.is_open = False
        self._focus_ready = False
        self._focus_gen += 1

    def _on_focus_out(self, event) -> None:
        if not self.is_open or not self._focus_ready:
            return
        if self.win is not None and self.win.focus_get() is None:
            self.hide()

    def _fire(self, key: str, close_after: bool = False) -> None:
        self.enqueue(self.actions[key])
        if close_after:
            self.hide()

    def _build(self) -> None:
        p = self._pal
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=p["border"])
        win.bind("<Escape>", lambda e: self.hide())
        win.bind("<FocusOut>", self._on_focus_out)

        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        apply_rounded_corners(hwnd)

        outer = tk.Frame(win, bg=p["bg"], padx=12, pady=10)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        hdr = tk.Frame(outer, bg=p["bg"])
        hdr.pack(fill="x", pady=(0, 8))
        title = tk.Label(
            hdr,
            text="Christmas Overlay",
            bg=p["bg"],
            fg=p["fg"],
            font=("Segoe UI", 10, "bold"),
        )
        title.pack(side="left")

        vis_btn = tk.Label(
            hdr,
            text="Show",
            bg=p["accent"],
            fg=p["accent_fg"],
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=2,
            cursor="hand2",
        )
        vis_btn.pack(side="right")
        vis_btn.bind("<Button-1>", lambda e: self._fire("toggle_visibility"))

        self._widgets["outer"] = outer
        self._widgets["hdr"] = hdr
        self._widgets["title"] = title
        self._widgets["vis_btn"] = vis_btn
        self._widgets["rows"] = []
        self._widgets["seps"] = []
        self._widgets["media_btns"] = []

        self._add_sep(outer)
        self._add_toggle_row(outer, "snow", "Snowfall", "toggle_snow")
        self._add_cycle_row(outer, "mode", "Density", "cycle_mode")
        self._add_toggle_row(outer, "lights", "Fairy Lights", "toggle_lights")
        self._add_cycle_row(outer, "frost", "Frost Border", "cycle_frost")
        self._add_toggle_row(
            outer, "countdown", "Christmas Countdown", "toggle_countdown", "Shown", "Hidden"
        )
        self._add_cycle_row(outer, "sparkles", "Click Sparkles", "cycle_sparkles")
        self._add_toggle_row(outer, "advent", "Advent Calendar", "toggle_advent")

        self._add_sep(outer)
        self._add_toggle_row(outer, "chime", "Mode Chime", "toggle_chime_audio")
        self._add_toggle_row(outer, "bells", "Ambient Sleigh Bells", "toggle_ambient_bells")
        self._add_toggle_row(outer, "music", "Windows Music", "toggle_music")
        self._add_media_controls(outer)
        self._add_action_row(outer, "music_folder", "Open Music Folder", "open_music_folder")

        self._add_sep(outer)
        self._add_toggle_row(outer, "wallpaper", "Festive Wallpaper", "toggle_wallpaper")
        self._add_toggle_row(outer, "accent", "Festive Accent Color", "toggle_accent")
        self._add_toggle_row(outer, "autostart", "Start with Windows", "toggle_autostart")
        self._add_toggle_row(outer, "seasonal", "Seasonal Auto-Mode", "toggle_seasonal")

        self._add_sep(outer)
        self._add_action_row(outer, "update", "Check for Updates", "handle_update", close=False)

        # Footer: version + repo link
        footer = tk.Frame(outer, bg=p["bg"])
        footer.pack(fill="x", pady=(6, 0))
        version_lbl = tk.Label(
            footer,
            text=f"v{__version__}",
            bg=p["bg"],
            fg=p["muted"],
            font=("Segoe UI", 8),
        )
        version_lbl.pack(side="left")
        repo_lbl = tk.Label(
            footer,
            text="GitHub",
            bg=p["bg"],
            fg=p["link"],
            font=("Segoe UI", 8, "underline"),
            cursor="hand2",
        )
        repo_lbl.pack(side="right")
        repo_lbl.bind(
            "<Button-1>",
            lambda e: webbrowser.open(f"https://github.com/{GITHUB_REPO}"),
        )
        self._widgets["version_lbl"] = version_lbl
        self._widgets["repo_lbl"] = repo_lbl
        self._widgets["footer"] = footer

        self._add_action_row(outer, "quit", "Quit", "shutdown", close=True, danger=True)

        self.win = win
        self.state.subscribe(self.refresh)

    def _add_media_controls(self, parent) -> None:
        p = self._pal
        card = tk.Frame(parent, bg=p["pill"], padx=8, pady=5)
        card.pack(fill="x", pady=(2, 3))

        track_lbl = tk.Label(
            card,
            text="♪ Ready",
            bg=p["pill"],
            fg=p["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        )
        track_lbl.pack(fill="x", pady=(0, 4))

        bar = tk.Frame(card, bg=p["pill"])
        bar.pack(fill="x")

        def make_btn(text: str, action_key: str, padx: int = 7):
            btn = tk.Label(
                bar,
                text=text,
                bg=p["bg"],
                fg=p["fg"],
                font=("Segoe UI", 8, "bold"),
                padx=padx,
                pady=2,
                cursor="hand2",
            )
            btn.bind("<Enter>", lambda _: btn.configure(bg=self._pal["hover"]))
            btn.bind("<Leave>", lambda _: btn.configure(bg=self._pal["bg"]))
            btn.bind("<Button-1>", lambda _: self._fire(action_key))
            self._widgets["media_btns"].append(btn)
            return btn

        prev_btn = make_btn("⏮", "music_prev", padx=6)
        prev_btn.pack(side="left", padx=(0, 3))

        play_btn = make_btn("▶", "music_play_pause", padx=8)
        play_btn.pack(side="left", padx=(0, 3))

        next_btn = make_btn("⏭", "music_next", padx=6)
        next_btn.pack(side="left")

        vol_up = make_btn("+", "music_vol_up", padx=5)
        vol_up.pack(side="right")

        vol_lbl = tk.Label(
            bar,
            text="75%",
            bg=p["pill"],
            fg=p["muted"],
            font=("Segoe UI", 8),
            width=4,
        )
        vol_lbl.pack(side="right", padx=2)

        vol_down = make_btn("−", "music_vol_down", padx=5)
        vol_down.pack(side="right")

        self._widgets["media_card"] = card
        self._widgets["media_bar"] = bar
        self._widgets["media_track"] = track_lbl
        self._widgets["media_play_btn"] = play_btn
        self._widgets["media_vol_lbl"] = vol_lbl

    def _add_sep(self, parent) -> None:
        s = tk.Frame(parent, bg=self._pal["sep"], height=1)
        s.pack(fill="x", pady=4)
        self._widgets["seps"].append(s)

    def _make_row_frame(self, parent, action_key: str, close: bool = False):
        p = self._pal
        row = tk.Frame(parent, bg=p["bg"], padx=6, pady=3, cursor="hand2")
        row.pack(fill="x", pady=1)

        def on_enter(_):
            row.configure(bg=self._pal["hover"])
            for c in row.winfo_children():
                c.configure(bg=self._pal["hover"])

        def on_leave(_):
            row.configure(bg=self._pal["bg"])
            for c in row.winfo_children():
                c.configure(bg=self._pal["bg"])

        def on_click(_):
            self._fire(action_key, close_after=close)

        row.bind("<Enter>", on_enter)
        row.bind("<Leave>", on_leave)
        row.bind("<Button-1>", on_click)
        return row, on_click

    def _add_toggle_row(self, parent, key, label, action_key, on_text="On", off_text="Off"):
        p = self._pal
        row, on_click = self._make_row_frame(parent, action_key)
        dot = tk.Label(row, text="●", bg=p["bg"], fg=p["on"], font=("Segoe UI", 9))
        dot.pack(side="left", padx=(0, 7))
        lbl = tk.Label(row, text=label, bg=p["bg"], fg=p["fg"], font=("Segoe UI", 9))
        lbl.pack(side="left")
        val = tk.Label(row, text=on_text, bg=p["bg"], fg=p["muted"], font=("Segoe UI", 8))
        val.pack(side="right")
        for w in (dot, lbl, val):
            w.bind("<Button-1>", on_click)
        self._widgets[key] = ("toggle", dot, val, on_text, off_text)
        self._widgets["rows"].append((row, lbl, "fg"))

    def _add_cycle_row(self, parent, key, label, action_key):
        p = self._pal
        row, on_click = self._make_row_frame(parent, action_key)
        lbl = tk.Label(row, text=label, bg=p["bg"], fg=p["fg"], font=("Segoe UI", 9))
        lbl.pack(side="left")
        val = tk.Label(row, text="", bg=p["bg"], fg=p["muted"], font=("Segoe UI", 8))
        val.pack(side="right")
        for w in (lbl, val):
            w.bind("<Button-1>", on_click)
        self._widgets[key] = ("cycle", val)
        self._widgets["rows"].append((row, lbl, "fg"))

    def _add_action_row(self, parent, key, label, action_key, close=False, danger=False):
        p = self._pal
        fg_key = "accent" if danger else "fg"
        row, on_click = self._make_row_frame(parent, action_key, close=close)
        lbl = tk.Label(row, text=label, bg=p["bg"], fg=p[fg_key], font=("Segoe UI", 9))
        lbl.pack(side="left")
        lbl.bind("<Button-1>", on_click)
        self._widgets[key] = ("action", lbl)
        self._widgets["rows"].append((row, lbl, fg_key))

    def _retheme(self) -> None:
        p = self._pal
        self.win.configure(bg=p["border"])
        for k in ("outer", "hdr", "footer"):
            self._widgets[k].configure(bg=p["bg"])
        self._widgets["title"].configure(bg=p["bg"], fg=p["fg"])
        self._widgets["version_lbl"].configure(bg=p["bg"], fg=p["muted"])
        self._widgets["repo_lbl"].configure(bg=p["bg"], fg=p["link"])
        self._widgets["media_card"].configure(bg=p["pill"])
        self._widgets["media_bar"].configure(bg=p["pill"])
        self._widgets["media_track"].configure(bg=p["pill"], fg=p["muted"])
        self._widgets["media_vol_lbl"].configure(bg=p["pill"], fg=p["muted"])
        for btn in self._widgets["media_btns"]:
            btn.configure(bg=p["bg"], fg=p["fg"])
        for s in self._widgets["seps"]:
            s.configure(bg=p["sep"])
        for row, lbl, fg_key in self._widgets["rows"]:
            row.configure(bg=p["bg"])
            for c in row.winfo_children():
                c.configure(bg=p["bg"])
            lbl.configure(fg=p[fg_key])

    def refresh(self) -> None:
        if self.win is None or not self.win.winfo_exists():
            return
        p = self._pal
        st = self.state
        self._widgets["vis_btn"].configure(
            text="Hide Overlay (Ctrl+Alt+X)" if st.visible else "Show Overlay (Ctrl+Alt+X)",
            bg=p["hover"] if st.visible else p["accent"],
            fg=p["fg"] if st.visible else p["accent_fg"],
        )
        toggles = {
            "snow": st.snow_enabled,
            "lights": st.lights_visible,
            "countdown": st.countdown_visible,
            "chime": st.audio_enabled,
            "bells": st.ambient_bells_enabled,
            "music": st.music_enabled,
            "wallpaper": st.wallpaper_enabled,
            "accent": st.accent_enabled,
            "advent": st.advent_enabled,
            "autostart": st.start_with_windows,
            "seasonal": st.auto_seasonal,
        }
        for k, on in toggles.items():
            _, dot, val, on_txt, off_txt = self._widgets[k]
            dot.configure(fg=p["on"] if on else p["off"])
            val.configure(text=on_txt if on else off_txt)

        # Media player status
        media_info = self.actions["music_status"]() if "music_status" in self.actions else {}
        is_playing = bool(media_info.get("playing", False))
        track = media_info.get("track", "")
        if len(track) > 34:
            track = track[:33] + "…"
        prefix = "♪ " if is_playing else ("❚❚ " if media_info.get("paused") else "♪ ")
        self._widgets["media_track"].configure(
            text=f"{prefix}{track}" if track else "♪ Add audio files to Windows Music",
            fg=p["fg"] if is_playing else p["muted"],
        )
        self._widgets["media_play_btn"].configure(text="❚❚" if is_playing else "▶")
        self._widgets["media_vol_lbl"].configure(text=f"{st.music_volume}%")

        frost_txt = FROST_MODES[st.frost_mode_idx]
        if st.frost_mode_idx == 0 and "weather_temp" in self.actions:
            t_str = self.actions["weather_temp"]()
            if t_str:
                frost_txt = f"Auto ({t_str})"

        self._widgets["mode"][1].configure(text=SNOW_MODES[st.mode_idx][0])
        self._widgets["frost"][1].configure(text=frost_txt)
        self._widgets["sparkles"][1].configure(text=SPARKLE_MODES[st.sparkle_mode_idx])
        self._widgets["update"][1].configure(text=self.actions["update_label"]())


class TrayController:
    def __init__(self, root: tk.Tk, state, enqueue, actions: dict):
        self.root = root
        self.state = state
        self.enqueue = enqueue
        self.actions = actions
        self.popup = TrayPopup(root, state, enqueue, actions)
        self.icon = None

    def _on_left_click(self, icon, item) -> None:
        p = wintypes.POINT()
        user32.GetCursorPos(byref(p))
        self.root.after(0, lambda: self.popup.toggle_at(p.x, p.y))

    def start(self) -> None:
        menu = Menu(
            MenuItem("Open Controls", self._on_left_click, default=True),
            MenuItem(
                lambda _: "Hide Overlay" if self.state.visible else "Show Overlay",
                lambda *_: self.enqueue(self.actions["toggle_visibility"]),
            ),
            MenuItem("Quit", lambda *_: self.enqueue(self.actions["shutdown"])),
        )
        self.icon = Icon("ChristmasOverlay", load_tray_image(), "Christmas Overlay", menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def notify(self, msg: str, title: str = "Christmas Overlay") -> None:
        if self.icon:
            try:
                self.icon.notify(msg, title)
            except Exception:
                pass

    def stop(self) -> None:
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass