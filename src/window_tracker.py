# src/window_tracker.py
import ctypes
from ctypes import wintypes
import os
from win32 import user32, shell32, get_process_name, get_monitor_rect_for_hwnd

dwmapi = ctypes.windll.dwmapi

DWMWA_EXTENDED_FRAME_BOUNDS = 9
DWMWA_CLOAKED = 14

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000

_OWN_PID = os.getpid()

_IGNORED_CLASSES = {
    "Progman",
    "WorkerW",
    "SHELLDLL_DefView",
    "SysListView32",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
    "Windows.UI.Core.CoreWindow",
    "MultitaskingViewFrame",
    "ForegroundStaging",
}

SCREENSHOT_TOOLS = {
    "snippingtool.exe",
    "screensketch.exe",
    "screenclippinghost.exe",
    "lightshot.exe",
    "sharex.exe",
    "greenshot.exe",
}

_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def _is_window_cloaked(hwnd: int) -> bool:
    try:
        cloaked = ctypes.c_int(0)
        hr = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_CLOAKED),
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
        return hr == 0 and cloaked.value != 0
    except Exception:
        return False


def _get_visual_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    rect = wintypes.RECT()
    try:
        hr = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_EXTENDED_FRAME_BOUNDS),
            ctypes.byref(rect),
            ctypes.sizeof(rect),
        )
        if hr == 0:
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    if user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


class WindowTracker:
    def __init__(self, overlay_hwnd: int, vx: int, vy: int):
        self.overlay_hwnd = overlay_hwnd
        self.vx = vx
        self.vy = vy
        self.cached_foreground = None
        self.cached_foreground_rect = None
        self.cached_taskbar_rect = None
        self.cached_windows: list[tuple[int, int, int, int]] = []
        self.cached_window_entries: list[tuple[int, tuple[int, int, int, int]]] = []

    def set_origin(self, vx: int, vy: int) -> None:
        self.vx = vx
        self.vy = vy
        self.cached_foreground = None
        self.cached_foreground_rect = None
        self.cached_windows.clear()
        self.cached_window_entries.clear()

    def _is_trackable_window(self, hwnd: int, cls_buf=None) -> bool:
        if not hwnd or hwnd == self.overlay_hwnd:
            return False
        if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
            return False

        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == _OWN_PID:
            return False

        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
            return False

        if cls_buf is None:
            cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls_buf, 256)
        if cls_buf.value in _IGNORED_CLASSES:
            return False

        if _is_window_cloaked(hwnd):
            return False

        return True

    def _enumerate_windows(self) -> list[tuple[int, tuple[int, int, int, int]]]:
        entries: list[tuple[int, tuple[int, int, int, int]]] = []
        cls_buf = ctypes.create_unicode_buffer(256)

        def cb(hwnd, _lparam):
            if not self._is_trackable_window(hwnd, cls_buf):
                return True

            raw = _get_visual_rect(hwnd)
            if not raw:
                return True

            x1 = raw[0] - self.vx
            y1 = raw[1] - self.vy
            x2 = raw[2] - self.vx
            y2 = raw[3] - self.vy
            if (x2 - x1) >= 160 and (y2 - y1) >= 80:
                entries.append((int(hwnd), (x1, y1, x2, y2)))
            return True

        try:
            user32.EnumWindows(_WNDENUMPROC(cb), 0)
        except Exception:
            pass
        return entries

    def update_rects(self) -> dict:
        entries = self._enumerate_windows()
        self.cached_window_entries = entries
        self.cached_windows = [r for _, r in entries]

        fg = user32.GetForegroundWindow()
        if not self._is_trackable_window(fg):
            self.cached_foreground = None
            self.cached_foreground_rect = None
        else:
            raw = _get_visual_rect(fg)
            if raw and (raw[2] - raw[0]) >= 160 and (raw[3] - raw[1]) >= 80:
                self.cached_foreground = int(fg)
                self.cached_foreground_rect = (
                    raw[0] - self.vx,
                    raw[1] - self.vy,
                    raw[2] - self.vx,
                    raw[3] - self.vy,
                )
            else:
                self.cached_foreground = None
                self.cached_foreground_rect = None

        tb = user32.FindWindowW("Shell_TrayWnd", None)
        if tb:
            rect = wintypes.RECT()
            user32.GetWindowRect(tb, ctypes.byref(rect))
            if rect.bottom - rect.top > 10:
                self.cached_taskbar_rect = (
                    rect.left - self.vx,
                    rect.top - self.vy,
                    rect.right - self.vx,
                    rect.bottom - self.vy,
                )

        return self.get_env_rects()

    def get_env_rects(self) -> dict:
        return {
            "taskbar": self.cached_taskbar_rect,
            "fg": self.cached_foreground_rect,
            "fg_hwnd": self.cached_foreground,
            "windows": self.cached_windows,
            "window_entries": self.cached_window_entries,
        }

    def is_fullscreen_app(self) -> bool:
        try:
            state = ctypes.c_int(0)
            hr = shell32.SHQueryUserNotificationState(ctypes.byref(state))
            if hr == 0 and state.value in (3, 4):
                return True
        except Exception:
            pass

        fg = user32.GetForegroundWindow()
        if not fg or fg == self.overlay_hwnd:
            return False

        if get_process_name(fg) in SCREENSHOT_TOOLS:
            return False

        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(fg, buf, 256)
        if buf.value in ("Progman", "WorkerW"):
            return False

        mon_rect = get_monitor_rect_for_hwnd(fg)
        if not mon_rect:
            return False

        m_left, m_top, m_right, m_bottom = mon_rect
        rect = wintypes.RECT()
        user32.GetWindowRect(fg, ctypes.byref(rect))
        return (
            rect.left <= m_left
            and rect.top <= m_top
            and rect.right >= m_right
            and rect.bottom >= m_bottom
        )

    @staticmethod
    def is_desktop_at(sx: int, sy: int) -> bool:
        pt = wintypes.POINT()
        pt.x, pt.y = int(sx), int(sy)
        hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value in ("Progman", "WorkerW", "SHELLDLL_DefView", "SysListView32")