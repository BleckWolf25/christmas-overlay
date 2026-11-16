# src/main.pyw
import atexit
import ctypes
from ctypes import wintypes
import datetime
import os
import queue
import random
import sys
import threading
import time
import tkinter as tk
import traceback

from advent import AdventCalendar
from audio import AudioManager
from effects import (
    CountdownHUD,
    FairyLights,
    FrostBorder,
    SnowSystem,
    SparkleSystem,
    WeatherMonitor,
)
from events import RandomEventSystem
from paths import exe_path, is_frozen
from single_instance import SingleInstance
from state import AppState, FROST_MODES, MUSIC_DIR, SNOW_MODES, SPARKLE_MODES
from system_theme import SystemThemeManager
from tray_ui import TrayController
import updater
from win32 import (
    GWL_EXSTYLE,
    HWND_TOPMOST,
    MOD_ALT,
    MOD_CONTROL,
    SM_CXVIRTUALSCREEN,
    SM_CYVIRTUALSCREEN,
    SM_XVIRTUALSCREEN,
    SM_YVIRTUALSCREEN,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    VK_CONTROL,
    VK_LBUTTON,
    VK_RBUTTON,
    VK_SHIFT,
    VK_X,
    WS_EX_LAYERED,
    WS_EX_NOACTIVATE,
    WS_EX_TOOLWINDOW,
    WS_EX_TRANSPARENT,
    GlobalHotkey,
    _GetWindowLong,
    _SetWindowLong,
    enable_per_monitor_dpi,
    get_idle_seconds,
    get_monitors,
    is_autostart_enabled,
    is_workstation_locked,
    kernel32,
    set_autostart,
    trim_working_set,
    user32,
)
from window_tracker import WindowTracker

if is_frozen():
    _exe_dir = os.path.dirname(exe_path())
    _log_path = os.path.join(_exe_dir, "christmas_overlay.log")
    _mode = "w" if (os.path.exists(_log_path) and os.path.getsize(_log_path) > 1_000_000) else "a"
    sys.stdout = sys.stderr = open(_log_path, _mode, buffering=1, encoding="utf-8")
    # Recover from a previous update if it left the exe missing
    try:
        updater.recover_previous_install()
    except Exception:
        pass
    for _stale in ("ChristmasOverlay.exe.new",):
        try:
            _p = os.path.join(_exe_dir, _stale)
            if os.path.exists(_p):
                os.remove(_p)
        except Exception:
            pass

CHROMA_KEY = "#010203"
_CTRL_HANDLER_TYPE = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)


def _is_in_season() -> bool:
    """Overlay season runs Nov 2 → Jan 6."""
    today = datetime.date.today()
    if today.month == 1:
        return today.day <= 6
    if today.month == 11:
        return today.day >= 2
    return today.month == 12


class ChristmasOverlay:
    LOOP_MS = 33
    ENV_INTERVAL = 6
    FULLSCREEN_INTERVAL = 30

    def __init__(self):
        enable_per_monitor_dpi()
        self.state = AppState.load()
        # Registry is source of truth for auto-start
        self.state.start_with_windows = is_autostart_enabled()
        # Seasonal auto-hide
        if self.state.auto_seasonal and not _is_in_season():
            self.state.visible = False

        self.theme_mgr = SystemThemeManager()
        self.audio = AudioManager()
        self.queue = queue.Queue()

        self.vx, self.vy, self.vw, self.vh = self._query_virtual_screen()
        self.monitors = get_monitors() or [(0, 0, self.vw, self.vh)]

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.vw}x{self.vh}+{self.vx}+{self.vy}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", CHROMA_KEY)
        self.root.configure(bg=CHROMA_KEY)

        self.canvas = tk.Canvas(
            self.root, width=self.vw, height=self.vh, bg=CHROMA_KEY, highlightthickness=0
        )
        self.canvas.pack()

        self.root.update_idletasks()
        self.hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        self._apply_win32_styles()

        self.tracker = WindowTracker(self.hwnd, self.vx, self.vy)
        self.weather = WeatherMonitor(
            on_update=lambda: self.root.after(0, self.tray.popup.refresh)
        )

        self.tick = 0
        self.env_counter = 0
        self._auto_hidden = False
        self._locked = False
        self._shutting_down = False
        self._restored = False
        self._update_available = None
        self._update_checking = False
        self._idle_sec = 0.0
        self.mouse_down = False
        self.rbutton_down = False
        self.mouse_hold_start = 0.0
        self._condensed_this_hold = False

        self._build_scene()
        self._apply_initial_system_state()
        self._register_cleanup_hooks()

        self.tray = TrayController(
            self.root, self.state, self.queue.put, self._build_tray_actions()
        )
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.hotkey = GlobalHotkey(self._hotkey_toggle)
        if self.state.hotkey_enabled:
            self.hotkey.register(MOD_CONTROL | MOD_ALT, VK_X)

        trim_working_set()

    def _hotkey_toggle(self) -> None:
        self.queue.put(lambda: self._toggle_attr("visible", lambda _: self._sync_window_visibility()))

    def _register_cleanup_hooks(self) -> None:
        atexit.register(self._restore_system_preferences)

        def _ctrl_handler(_ctrl_type: int) -> bool:
            self._restore_system_preferences()
            return False

        self._ctrl_cb = _CTRL_HANDLER_TYPE(_ctrl_handler)
        try:
            kernel32.SetConsoleCtrlHandler(self._ctrl_cb, True)
        except Exception:
            pass

    def _restore_system_preferences(self) -> None:
        if self._restored:
            return
        self._restored = True
        try:
            self.state.save()
        except Exception:
            pass
        try:
            self.audio.cleanup()
        except Exception:
            pass
        try:
            self.theme_mgr.restore_all()
        except Exception:
            pass

    @staticmethod
    def _query_virtual_screen() -> tuple[int, int, int, int]:
        return (
            user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
        )

    def _build_scene(self) -> None:
        prev_frost = getattr(self, "border", None)
        initial_progress = (
            prev_frost.progress
            if prev_frost
            else (1.0 if self.state.frost_mode_idx == 1 else 0.0)
        )
        self.canvas.delete("all")
        self.border = FrostBorder(self.canvas, self.vw, self.vh, initial_progress)
        self.lights = FairyLights(self.canvas, self.monitors, self.vx, self.vy)
        self.lights.toggle(self.state.lights_visible)
        self.snow = SnowSystem(self.canvas, self.vw, self.vh)
        self.snow.enabled = self.state.snow_enabled
        self.snow.set_target(SNOW_MODES[self.state.mode_idx][1])
        self.countdown = CountdownHUD(
            self.canvas, self.vx, self.vy, self.state.countdown_visible, self.state.user_name
        )
        self.sparkles = SparkleSystem(self.canvas)
        self.events = RandomEventSystem(self.canvas, self.vw, self.vh)
        self.advent = AdventCalendar(self.canvas, self.vx, self.vy)

    def _apply_initial_system_state(self) -> None:
        if self.state.wallpaper_enabled:
            ok, _ = self.theme_mgr.apply_wallpaper(self.vw, self.vh)
            if not ok:
                self.state.wallpaper_enabled = False
                self.state.save()
        if self.state.accent_enabled:
            self.theme_mgr.apply_accent()
        if self.state.music_enabled:
            if not self.audio.set_music_enabled(True):
                self.state.music_enabled = False
        elif self.state.ambient_bells_enabled:
            self.audio.set_ambient_chimes(True)

    def _toggle_attr(self, attr: str, side_effect=None) -> None:
        val = not getattr(self.state, attr)
        setattr(self.state, attr, val)
        if side_effect:
            side_effect(val)
        self.state.notify()

    def _build_tray_actions(self) -> dict:
        return {
            "toggle_visibility": lambda: self._toggle_attr(
                "visible", lambda _: self._sync_window_visibility()
            ),
            "toggle_snow": lambda: self._toggle_attr("snow_enabled", self.snow.set_enabled),
            "cycle_mode": self.cycle_mode,
            "toggle_lights": lambda: self._toggle_attr("lights_visible", self.lights.toggle),
            "cycle_frost": self.cycle_frost,
            "weather_temp": self.weather.format_temp,
            "toggle_countdown": lambda: self._toggle_attr(
                "countdown_visible", self.countdown.toggle
            ),
            "cycle_sparkles": self.cycle_sparkles,
            "toggle_advent": lambda: self._toggle_attr("advent_enabled", self._on_advent_toggle),
            "toggle_chime_audio": lambda: self._toggle_attr(
                "audio_enabled", lambda on: self.audio.play_chime() if on else None
            ),
            "toggle_ambient_bells": self.toggle_ambient_bells,
            "toggle_music": self.toggle_music,
            "open_music_folder": self.open_music_folder,
            "toggle_wallpaper": self.toggle_wallpaper,
            "toggle_accent": self.toggle_accent,
            "toggle_autostart": self.toggle_autostart,
            "toggle_seasonal": self.toggle_seasonal,
            "update_label": lambda: (
                f"Install Update (v{self._update_available['version']})"
                if self._update_available
                else "Check for Updates"
            ),
            "handle_update": lambda: (
                self._install_update()
                if self._update_available
                else self._check_updates_async(True)
            ),
            "shutdown": self.shutdown,
        }

    def _on_advent_toggle(self, on: bool) -> None:
        if on:
            self.advent = AdventCalendar(self.canvas, self.vx, self.vy)
        else:
            for item in getattr(self.advent, "_items", []):
                self.canvas.delete(item)
            if getattr(self.advent, "_message_tag", None):
                self.canvas.delete(self.advent._message_tag)

    def cycle_mode(self) -> None:
        self.state.mode_idx = (self.state.mode_idx + 1) % len(SNOW_MODES)
        if not self.state.snow_enabled:
            self.state.snow_enabled = True
            self.snow.enabled = True
        self.snow.set_target(SNOW_MODES[self.state.mode_idx][1])
        if self.state.audio_enabled:
            self.audio.play_chime()
        self.state.notify()

    def cycle_frost(self) -> None:
        self.state.frost_mode_idx = (self.state.frost_mode_idx + 1) % len(FROST_MODES)
        self.state.notify()

    def cycle_sparkles(self) -> None:
        self.state.sparkle_mode_idx = (self.state.sparkle_mode_idx + 1) % len(SPARKLE_MODES)
        self.state.notify()

    def toggle_music(self) -> None:
        if not self.state.music_enabled:
            if self.state.ambient_bells_enabled:
                self.state.ambient_bells_enabled = False
                self.audio.set_ambient_chimes(False)
            if not self.audio.set_music_enabled(True):
                self.tray.notify("Add .wav files to the music folder first.")
                self.state.notify()
                return
            self.state.music_enabled = True
        else:
            self.audio.set_music_enabled(False)
            self.state.music_enabled = False
        self.state.notify()

    def toggle_ambient_bells(self) -> None:
        if not self.state.ambient_bells_enabled:
            if self.state.music_enabled:
                self.audio.set_music_enabled(False)
                self.state.music_enabled = False
            self.state.ambient_bells_enabled = True
            self.audio.set_ambient_chimes(True)
        else:
            self.state.ambient_bells_enabled = False
            self.audio.set_ambient_chimes(False)
        self.state.notify()

    def open_music_folder(self) -> None:
        try:
            os.makedirs(MUSIC_DIR, exist_ok=True)
            os.startfile(MUSIC_DIR)
        except Exception:
            self.tray.notify("Could not open music folder.")

    def toggle_autostart(self) -> None:
        if not is_frozen():
            self.tray.notify("Auto-start requires the packaged .exe.")
            return
        new = not self.state.start_with_windows
        if set_autostart(new, exe_path()):
            self.state.start_with_windows = new
            self.state.notify()
        else:
            self.tray.notify("Failed to update Windows startup registry.")

    def toggle_seasonal(self) -> None:
        self.state.auto_seasonal = not self.state.auto_seasonal
        if self.state.auto_seasonal and not _is_in_season():
            self.state.visible = False
            self._sync_window_visibility()
        self.state.notify()

    def toggle_wallpaper(self) -> None:
        if not self.state.wallpaper_enabled:
            ok, err = self.theme_mgr.apply_wallpaper(self.vw, self.vh)
            self.state.wallpaper_enabled = ok
            if not ok and err:
                self.tray.notify(err)
        else:
            self.theme_mgr.restore_wallpaper()
            self.state.wallpaper_enabled = False
        self.state.notify()

    def toggle_accent(self) -> None:
        if not self.state.accent_enabled:
            self.theme_mgr.apply_accent()
            self.state.accent_enabled = True
        else:
            self.theme_mgr.restore_accent()
            self.state.accent_enabled = False
        self.state.notify()

    def _apply_win32_styles(self) -> None:
        style = _GetWindowLong(self.hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        _SetWindowLong(self.hwnd, GWL_EXSTYLE, style)
        self._assert_topmost()

    def _rebuild_overlay(self) -> None:
        self.vx, self.vy, self.vw, self.vh = self._query_virtual_screen()
        self.monitors = get_monitors() or [(0, 0, self.vw, self.vh)]
        self.canvas.configure(width=self.vw, height=self.vh)
        self.root.geometry(f"{self.vw}x{self.vh}+{self.vx}+{self.vy}")
        self.tracker.set_origin(self.vx, self.vy)
        self._build_scene()
        self._assert_topmost()
        trim_working_set()

    def _assert_topmost(self) -> None:
        try:
            user32.SetWindowPos(
                self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )
        except Exception:
            pass

    def _sync_window_visibility(self) -> None:
        should_show = self.state.visible and not self._auto_hidden
        is_shown = self.root.state() != "withdrawn"
        if should_show and not is_shown:
            self.root.deiconify()
            self.root.update_idletasks()
            self._apply_win32_styles()
        elif not should_show and is_shown:
            self.root.withdraw()

    def _check_updates_async(self, notify_if_none: bool = False) -> None:
        if self._update_checking:
            return
        self._update_checking = True

        def worker():
            res = updater.check_for_update()

            def done():
                self._update_checking = False
                self._update_available = res
                self.tray.popup.refresh()
                if res:
                    self.tray.notify(f"Version {res['version']} is available.")
                elif notify_if_none:
                    self.tray.notify("You're on the latest version.")

            self.root.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _install_update(self) -> None:
        if not self._update_available:
            return
        url = self._update_available["url"]

        def worker():
            try:
                new_path = updater.download_exe(url)
            except Exception as e:
                self.root.after(0, lambda: self.tray.notify(f"Download failed: {e}"))
                return

            def go():
                self._shutting_down = True
                self.weather.stop()
                self._restore_system_preferences()
                self.tray.stop()
                updater.apply_update_and_restart(new_path)
                self.canvas.delete("all")
                self.root.destroy()

            self.root.after(0, go)

        threading.Thread(target=worker, daemon=True).start()

    def _loop(self) -> None:
        if self._shutting_down:
            return
        try:
            self._loop_inner()
        except Exception:
            traceback.print_exc()
            if not self._shutting_down:
                self.root.after(1000, self._loop)

    def _loop_inner(self) -> None:
        t0 = time.perf_counter()

        while not self.queue.empty():
            try:
                self.queue.get_nowait()()
            except queue.Empty:
                break
            if self._shutting_down:
                return

        if self._shutting_down:
            return

        self.tick += 1
        self.env_counter += 1

        if self.tick % self.FULLSCREEN_INTERVAL == 0:
            self._locked = is_workstation_locked()
            self._idle_sec = get_idle_seconds()
            if not self._locked:
                fs = self.tracker.is_fullscreen_app()
                if fs != self._auto_hidden:
                    self._auto_hidden = fs
                    self._sync_window_visibility()

        if self._locked or self._auto_hidden or not self.state.visible:
            self.root.after(300, self._loop)
            return

        if self.env_counter % self.ENV_INTERVAL == 0:
            if self.env_counter % 60 == 0:
                screen = self._query_virtual_screen()
                mons = get_monitors() or [(0, 0, screen[2], screen[3])]
                if screen != (self.vx, self.vy, self.vw, self.vh) or mons != self.monitors:
                    self._rebuild_overlay()
            self.tracker.update_rects()

        if self.tick % 1800 == 0:
            self.countdown.refresh_if_new_day()

        if self.tick % 180 == 0 and not self.tray.popup.is_open:
            self._assert_topmost()
        if self.state.lights_visible and self.tick % 4 == 0:
            self.lights.update(self.tick)

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        cx, cy = pt.x - self.vx, pt.y - self.vy

        # Left click: sparkles, snowballs, hold-to-condense
        is_down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
        now = time.perf_counter()
        if is_down and not self.mouse_down:
            mode = self.state.sparkle_mode_idx
            if mode == 1 and self.tracker.is_desktop_at(pt.x, pt.y):
                self.sparkles.spawn(cx, cy)
            elif mode == 2:
                self.sparkles.spawn(cx, cy)
            elif mode == 3 and self.tracker.is_desktop_at(pt.x, pt.y):
                self.sparkles.spawn_snowball(cx, cy)
            self.mouse_hold_start = now
            self._condensed_this_hold = False
        elif is_down and not self._condensed_this_hold and now - self.mouse_hold_start > 1.5:
            if self.tracker.is_desktop_at(pt.x, pt.y):
                for _ in range(20):
                    self.sparkles.spawn(
                        cx + random.uniform(-22, 22), cy + random.uniform(-22, 22)
                    )
            self._condensed_this_hold = True
        self.mouse_down = is_down

        # Right click + Ctrl+Shift on desktop → open tray
        r_down = bool(user32.GetAsyncKeyState(VK_RBUTTON) & 0x8000)
        if r_down and not self.rbutton_down:
            ctrl = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
            shift = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
            if ctrl and shift and self.tracker.is_desktop_at(pt.x, pt.y):
                self.tray.popup.show_at(pt.x, pt.y)
        self.rbutton_down = r_down

        env = self.tracker.get_env_rects()
        self.border.update(self.state.frost_mode_idx, self._idle_sec, self.weather.is_cold)
        self.snow.update(self.tick, cx, cy, env)
        self.sparkles.update(env)
        if self.state.advent_enabled:
            self.advent.update(self.tick, cx, cy)
        self.events.update(self.tick, env)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        self.root.after(max(1, int(self.LOOP_MS - elapsed_ms)), self._loop)

    def run(self) -> None:
        self.tray.start()
        self.weather.start()
        self._sync_window_visibility()
        self.root.after(0, self._loop)
        self.root.after(5000, self._check_updates_async)
        self.root.mainloop()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.weather.stop()
        self._restore_system_preferences()
        self.tray.stop()
        try:
            self.hotkey.stop()
        except Exception:
            pass
        try:
            self.canvas.delete("all")
            self.root.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    guard = SingleInstance()
    try:
        if guard.already_running:
            sys.exit(0)
        ChristmasOverlay().run()
    finally:
        guard.release()