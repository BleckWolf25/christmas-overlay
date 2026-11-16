# src/state.py
import json
import os
from win32 import get_windows_music_dir

SNOW_MODES = [
    ("Gentle Flurry", 110),
    ("Winter Snowfall", 200),
    ("Cozy Blizzard", 340),
]

SPARKLE_MODES = ["Off", "Desktop Clicks", "Everywhere", "Snowball Fight"]
FROST_MODES = ["Auto (Idle / Cold)", "Always On", "Off"]

CONFIG_DIR = os.path.join(
    os.getenv("LOCALAPPDATA") or os.path.expanduser("~"), "ChristmasOverlay"
)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
MUSIC_DIR = get_windows_music_dir()

class AppState:
    SCHEMA = 4

    def __init__(self):
        self.visible = True
        self.snow_enabled = True
        self.window_snow_enabled = True
        self.mode_idx = 0
        self.lights_visible = True
        self.frost_mode_idx = 0
        self.countdown_visible = True
        self.sparkle_mode_idx = 1
        self.audio_enabled = False
        self.ambient_bells_enabled = False
        self.music_enabled = False
        self.music_volume = 75
        self.wallpaper_enabled = False
        self.lockscreen_enabled = False
        self.accent_enabled = False
        self.cursors_enabled = False
        self.festive_icons_enabled = False
        self.advent_enabled = True
        self.start_with_windows = False
        self.auto_seasonal = True
        self.hotkey_enabled = True
        self.user_name = (os.getenv("USERNAME") or "").capitalize()
        self._listeners = []

    def subscribe(self, fn) -> None:
        if fn not in self._listeners:
            self._listeners.append(fn)

    def notify(self) -> None:
        self.save()
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass

    def to_dict(self) -> dict:
        return {
            "schema": self.SCHEMA,
            "visible": self.visible,
            "snow_enabled": self.snow_enabled,
            "window_snow_enabled": self.window_snow_enabled,
            "mode_idx": self.mode_idx,
            "lights_visible": self.lights_visible,
            "frost_mode_idx": self.frost_mode_idx,
            "countdown_visible": self.countdown_visible,
            "sparkle_mode_idx": self.sparkle_mode_idx,
            "audio_enabled": self.audio_enabled,
            "ambient_bells_enabled": self.ambient_bells_enabled,
            "music_enabled": self.music_enabled,
            "music_volume": self.music_volume,
            "wallpaper_enabled": self.wallpaper_enabled,
            "lockscreen_enabled": self.lockscreen_enabled,
            "accent_enabled": self.accent_enabled,
            "cursors_enabled": self.cursors_enabled,
            "festive_icons_enabled": self.festive_icons_enabled,
            "advent_enabled": self.advent_enabled,
            "start_with_windows": self.start_with_windows,
            "auto_seasonal": self.auto_seasonal,
            "hotkey_enabled": self.hotkey_enabled,
            "user_name": self.user_name,
        }

    @staticmethod
    def _migrate(data: dict, from_schema: int) -> dict:
        return data

    @classmethod
    def load(cls) -> "AppState":
        st = cls()
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return st
            from_schema = int(data.get("schema", 1))
            if from_schema < cls.SCHEMA:
                data = cls._migrate(data, from_schema)

            st.visible = bool(data.get("visible", st.visible))
            st.snow_enabled = bool(data.get("snow_enabled", st.snow_enabled))
            st.window_snow_enabled = bool(data.get("window_snow_enabled", st.window_snow_enabled))
            st.mode_idx = int(data.get("mode_idx", st.mode_idx)) % len(SNOW_MODES)
            st.lights_visible = bool(data.get("lights_visible", st.lights_visible))
            st.frost_mode_idx = int(data.get("frost_mode_idx", st.frost_mode_idx)) % len(FROST_MODES)
            st.countdown_visible = bool(data.get("countdown_visible", st.countdown_visible))
            st.sparkle_mode_idx = int(data.get("sparkle_mode_idx", st.sparkle_mode_idx)) % len(SPARKLE_MODES)
            st.audio_enabled = bool(data.get("audio_enabled", st.audio_enabled))
            st.ambient_bells_enabled = bool(data.get("ambient_bells_enabled", st.ambient_bells_enabled))
            st.music_enabled = bool(data.get("music_enabled", st.music_enabled))
            st.music_volume = max(0, min(100, int(data.get("music_volume", st.music_volume))))
            st.wallpaper_enabled = bool(data.get("wallpaper_enabled", st.wallpaper_enabled))
            st.lockscreen_enabled = bool(data.get("lockscreen_enabled", st.lockscreen_enabled))
            st.accent_enabled = bool(data.get("accent_enabled", st.accent_enabled))
            st.cursors_enabled = bool(data.get("cursors_enabled", st.cursors_enabled))
            st.festive_icons_enabled = bool(data.get("festive_icons_enabled", st.festive_icons_enabled))
            st.advent_enabled = bool(data.get("advent_enabled", st.advent_enabled))
            st.start_with_windows = bool(data.get("start_with_windows", st.start_with_windows))
            st.auto_seasonal = bool(data.get("auto_seasonal", st.auto_seasonal))
            st.hotkey_enabled = bool(data.get("hotkey_enabled", st.hotkey_enabled))
            st.user_name = str(data.get("user_name", st.user_name))
        except Exception:
            pass
        return st

    def save(self) -> None:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2)
            os.replace(tmp, CONFIG_PATH)
        except Exception:
            pass