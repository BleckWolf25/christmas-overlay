# src/window_tracker.py
import ctypes
from ctypes import wintypes
from win32 import user32, shell32, get_process_name, get_monitor_rect_for_hwnd

SCREENSHOT_TOOLS = {
    "snippingtool.exe",
    "screensketch.exe",
    "screenclippinghost.exe",
    "lightshot.exe",
    "sharex.exe",
    "greenshot.exe",
}


class WindowTracker:
    def __init__(self, overlay_hwnd: int, vx: int, vy: int):
        self.overlay_hwnd = overlay_hwnd
        self.vx = vx
        self.vy = vy
        self.cached_foreground = None
        self.cached_foreground_rect = None
        self.cached_taskbar_rect = None

    def set_origin(self, vx: int, vy: int) -> None:
        self.vx = vx
        self.vy = vy
        self.cached_foreground = None
        self.cached_foreground_rect = None

    def update_rects(self) -> dict:
        fg = user32.GetForegroundWindow()
        if not fg or fg == self.overlay_hwnd:
            self.cached_foreground = None
            self.cached_foreground_rect = None
        else:
            self.cached_foreground = fg
            rect = wintypes.RECT()
            user32.GetWindowRect(fg, ctypes.byref(rect))
            if rect.right - rect.left > 200 and rect.bottom - rect.top > 80:
                self.cached_foreground_rect = (
                    rect.left - self.vx,
                    rect.top - self.vy,
                    rect.right - self.vx,
                    rect.bottom - self.vy,
                )
            else:
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