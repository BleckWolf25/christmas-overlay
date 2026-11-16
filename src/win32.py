# src/win32.py
import ctypes
from ctypes import wintypes
import os
import threading
import winreg

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

user32.SystemParametersInfoW.argtypes = [
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    wintypes.UINT,
]
user32.SystemParametersInfoW.restype = wintypes.BOOL

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = -1
HWND_BOTTOM = 1
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010

SM_CXCURSOR = 13
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

MONITOR_DEFAULTTONEAREST = 2

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_X = 0x58

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 0x0014
SPI_GETWORKAREA = 0x0030
SPI_SETCURSORS = 0x0057
SPI_GETCLIENTAREAANIMATION = 0x1042
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

IMAGE_CURSOR = 2
LR_LOADFROMFILE = 0x00000010

OCR_NORMAL = 32512
OCR_IBEAM = 32513
OCR_WAIT = 32514
OCR_NO = 32648
OCR_HAND = 32649
OCR_APPSTARTING = 32650

SHCNE_ASSOCCHANGED = 0x08000000
SHCNE_UPDATEITEM = 0x00002000
SHCNF_IDLIST = 0x0000
SHCNF_PATHW = 0x0005
SHCNF_FLUSH = 0x1000

HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
WM_DWMCOLORIZATIONCOLORCHANGED = 0x0320
SMTO_ABORTIFHUNG = 0x0002

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

if ctypes.sizeof(ctypes.c_void_p) == 8:
    _GetWindowLong = user32.GetWindowLongPtrW
    _SetWindowLong = user32.SetWindowLongPtrW
    _GetWindowLong.restype = ctypes.c_ssize_t
    _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    _SetWindowLong.restype = ctypes.c_ssize_t
    _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
else:
    _GetWindowLong = user32.GetWindowLongW
    _SetWindowLong = user32.SetWindowLongW

_MONITOR_ENUM_PROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL,
    wintypes.HMONITOR,
    wintypes.HDC,
    ctypes.POINTER(wintypes.RECT),
    wintypes.LPARAM,
)


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


class _KNOWNFOLDERID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def get_windows_music_dir() -> str:
    """Resolves the standard Windows Music library folder (FOLDERID_Music)."""
    try:
        # FOLDERID_Music = {4BD8D571-6D19-48D3-BE97-422220080E43}
        fid = _KNOWNFOLDERID(
            0x4BD8D571,
            0x6D19,
            0x48D3,
            (ctypes.c_ubyte * 8)(0xBE, 0x97, 0x42, 0x22, 0x20, 0x08, 0x0E, 0x43),
        )
        p_path = ctypes.c_void_p()
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_KNOWNFOLDERID),
            wintypes.DWORD,
            wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT
        hr = shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(p_path))
        if hr == 0 and p_path.value:
            try:
                path = ctypes.wstring_at(p_path.value)
                if path:
                    return path
            finally:
                ctypes.windll.ole32.CoTaskMemFree(p_path)
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Music")

def place_window_on_desktop(hwnd: int) -> None:
    """Keeps a window at the bottom of normal Z-order (above desktop, below all apps)."""
    try:
        user32.SetWindowPos(
            hwnd,
            HWND_BOTTOM,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
    except Exception:
        pass

def get_preferred_cursor_size() -> int:
    """Returns a DPI-appropriate cursor size (24..96 px)."""
    try:
        sz = int(user32.GetSystemMetrics(SM_CXCURSOR))
        if 24 <= sz <= 96:
            return sz
    except Exception:
        pass
    return 36


def apply_system_cursors(cursor_map: dict[int, str]) -> bool:
    """Loads .cur files and assigns them to system OCR_* cursor slots."""
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE,
        wintypes.LPCWSTR,
        wintypes.UINT,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SetSystemCursor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    user32.SetSystemCursor.restype = wintypes.BOOL

    applied = 0
    for ocr_id, cur_path in cursor_map.items():
        if not os.path.exists(cur_path):
            continue
        hcur = user32.LoadImageW(None, cur_path, IMAGE_CURSOR, 0, 0, LR_LOADFROMFILE)
        if hcur:
            # SetSystemCursor takes ownership and destroys hcur automatically
            if user32.SetSystemCursor(hcur, ocr_id):
                applied += 1
    return applied > 0


def restore_system_cursors() -> None:
    """Reloads the user's saved Windows cursor scheme from the registry."""
    try:
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
    except Exception:
        pass


def notify_shell_icons_changed() -> None:
    """Forces Windows Explorer to refresh desktop & Recycle Bin icons immediately."""
    try:
        shell32.SHChangeNotify.argtypes = [
            wintypes.LONG,
            wintypes.UINT,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        shell32.SHChangeNotify(
            SHCNE_UPDATEITEM,
            SHCNF_PATHW | SHCNF_FLUSH,
            ctypes.c_wchar_p("::{645FF040-5081-101B-9F08-00AA002F954E}"),
            None,
        )
        shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED,
            SHCNF_IDLIST | SHCNF_FLUSH,
            None,
            None,
        )
    except Exception:
        pass

def enable_per_monitor_dpi() -> None:
    try:
        fn = user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        fn.restype = wintypes.BOOL
        fn(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass


def trim_working_set() -> None:
    try:
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
        psapi.EmptyWorkingSet.restype = wintypes.BOOL
        psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
    except Exception:
        pass


def is_workstation_locked() -> bool:
    try:
        DESKTOP_SWITCHDESKTOP = 0x0100
        user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_SWITCHDESKTOP)
        if not hdesk:
            return True
        user32.CloseDesktop(hdesk)
        return False
    except Exception:
        return False


def get_idle_seconds() -> float:
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            kernel32.GetTickCount64.restype = ctypes.c_uint64
            now_ms = kernel32.GetTickCount64() & 0xFFFFFFFF
            elapsed_ms = (now_ms - lii.dwTime) & 0xFFFFFFFF
            return elapsed_ms / 1000.0
    except Exception:
        pass
    return 0.0


def uses_fahrenheit() -> bool:
    try:
        LOCALE_USER_DEFAULT = 0x0400
        LOCALE_IMEASURE = 0x0000000D
        buf = ctypes.create_unicode_buffer(4)
        if kernel32.GetLocaleInfoW(LOCALE_USER_DEFAULT, LOCALE_IMEASURE, buf, 4):
            return buf.value == "1"
    except Exception:
        pass
    return False


def is_reduce_motion_enabled() -> bool:
    """True if the user has animations turned off in Windows accessibility settings."""
    try:
        BOOL = ctypes.c_int(1)
        if user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(BOOL), 0
        ):
            return not BOOL.value
    except Exception:
        pass
    return False


def get_monitors() -> list:
    monitors = []

    def cb(hmon, hdc, lprect, lparam):
        r = lprect.contents
        monitors.append((r.left, r.top, r.right, r.bottom))
        return True

    user32.EnumDisplayMonitors(None, None, _MONITOR_ENUM_PROC(cb), 0)
    return monitors


def get_monitor_rect_for_hwnd(hwnd: int) -> tuple[int, int, int, int] | None:
    try:
        hmon = user32.MonitorFromWindow(wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    return None


def get_work_area_for_point(x: int, y: int) -> tuple[int, int, int, int]:
    try:
        pt = wintypes.POINT(int(x), int(y))
        hmon = user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
        if hmon:
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                w = mi.rcWork
                return (w.left, w.top, w.right, w.bottom)
    except Exception:
        pass
    wa = wintypes.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(wa), 0)
    return (wa.left, wa.top, wa.right, wa.bottom)


def get_process_name(hwnd) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        h_process = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        if h_process:
            buf = ctypes.create_unicode_buffer(260)
            kernel32.QueryFullProcessImageNameW(
                h_process, 0, buf, ctypes.byref(ctypes.c_uint(260))
            )
            kernel32.CloseHandle(h_process)
            return buf.value.split("\\")[-1].lower()
    except Exception:
        pass
    return ""


def is_windows_light_theme() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return bool(val)
    except Exception:
        return False


def apply_rounded_corners(hwnd: int) -> None:
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        pref = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(pref),
            ctypes.sizeof(pref),
        )
    except Exception:
        pass


_AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "ChristmasOverlay"


def set_autostart(enabled: bool, exe: str) -> bool:
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            if enabled:
                winreg.SetValueEx(
                    k, _AUTOSTART_NAME, 0, winreg.REG_SZ, f'"{exe}"'
                )
            else:
                try:
                    winreg.DeleteValue(k, _AUTOSTART_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_KEY, 0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, _AUTOSTART_NAME)
            return bool(val)
    except Exception:
        return False


class GlobalHotkey:
    """Registers a global hotkey on a dedicated message-pump thread."""

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    def __init__(self, callback):
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None

    def register(self, mods: int, vk: int) -> None:
        self._thread = threading.Thread(
            target=self._run, args=(mods, vk), daemon=True
        )
        self._thread.start()

    def _run(self, mods: int, vk: int) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, mods, vk):
            return
        msg = wintypes.MSG()
        try:
            while True:
                ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                if msg.message == self.WM_HOTKEY:
                    try:
                        self._callback()
                    except Exception:
                        pass
        finally:
            try:
                user32.UnregisterHotKey(None, 1)
            except Exception:
                pass

    def stop(self) -> None:
        if self._thread_id:
            try:
                user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
            except Exception:
                pass


class DWM_COLORIZATION_PARAMS(ctypes.Structure):
    _fields_ = [
        ("clrColor", wintypes.DWORD),
        ("clrAfterGlow", wintypes.DWORD),
        ("nIntensity", wintypes.UINT),
        ("clrAfterGlowBalance", wintypes.UINT),
        ("clrBlurBalance", wintypes.UINT),
        ("clrGlassReflectionIntensity", wintypes.UINT),
        ("fOpaque", wintypes.BOOL),
    ]


def _build_accent_palette(r: int, g: int, b: int) -> bytes:
    factors = [1.45, 1.30, 1.15, 1.0, 0.85, 0.70, 0.55, 0.40]
    out = bytearray()
    for f in factors:
        out.extend(
            (min(255, int(r * f)), min(255, int(g * f)), min(255, int(b * f)), 0xFF)
        )
    return bytes(out)


def set_windows_accent(r: int, g: int, b: int, prevalence: int = 1) -> None:
    abgr = (0xFF << 24) | (b << 16) | (g << 8) | r
    argb = (0xC4 << 24) | (r << 16) | (g << 8) | b
    palette = _build_accent_palette(r, g, b)

    try:
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM"
        ) as k:
            winreg.SetValueEx(k, "AccentColor", 0, winreg.REG_DWORD, abgr)
            winreg.SetValueEx(k, "AccentColorInactive", 0, winreg.REG_DWORD, abgr)
            winreg.SetValueEx(k, "ColorPrevalence", 0, winreg.REG_DWORD, prevalence)
            winreg.SetValueEx(k, "ColorizationColor", 0, winreg.REG_DWORD, argb)
            winreg.SetValueEx(k, "ColorizationAfterglow", 0, winreg.REG_DWORD, argb)
    except Exception:
        pass

    try:
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent",
        ) as k:
            winreg.SetValueEx(k, "AccentColorMenu", 0, winreg.REG_DWORD, abgr)
            winreg.SetValueEx(k, "StartColorMenu", 0, winreg.REG_DWORD, abgr)
            winreg.SetValueEx(k, "AccentPalette", 0, winreg.REG_BINARY, palette)
    except Exception:
        pass

    apply_dwm_colorization(argb)
    broadcast_setting_change()


def apply_dwm_colorization(argb: int) -> None:
    try:
        dwmapi = ctypes.windll.dwmapi
        fn = getattr(dwmapi, "DwmSetColorizationParameters", None) or dwmapi[127]
        fn.argtypes = [ctypes.POINTER(DWM_COLORIZATION_PARAMS), wintypes.BOOL]
        fn.restype = ctypes.c_long
        p = DWM_COLORIZATION_PARAMS()
        p.clrColor = argb & 0xFFFFFFFF
        p.clrAfterGlow = argb & 0xFFFFFFFF
        p.nIntensity = 50
        p.fOpaque = False
        fn(ctypes.byref(p), True)
    except Exception:
        pass


def broadcast_setting_change() -> None:
    try:
        s = ctypes.c_wchar_p("ImmersiveColorSet")
        lp = ctypes.cast(s, ctypes.c_void_p).value or 0
        result = ctypes.c_size_t()
        user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, lp, SMTO_ABORTIFHUNG, 1000, ctypes.byref(result)
        )
        user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_DWMCOLORIZATIONCOLORCHANGED, 0, 0, SMTO_ABORTIFHUNG, 1000, ctypes.byref(result)
        )
    except Exception:
        pass