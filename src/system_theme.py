import ctypes
from ctypes import POINTER, byref, c_int, c_uint, c_void_p, c_wchar_p, wintypes
import datetime
import json
import math
import os
import random
import subprocess
import threading
import traceback
import winreg
import random
import struct
import subprocess
import threading
import time

from PIL import Image, ImageDraw, ImageFilter

from festive_assets import (
    render_candy_arrow_cursor,
    render_festive_app_icon,
    render_ibeam_cursor,
    render_recycle_bin_icon,
    render_santa_mitten_cursor,
    render_winter_backdrop,
    render_wreath_cursor,
    save_cur,
)
from state import CONFIG_DIR
from win32 import (
    OCR_APPSTARTING,
    OCR_HAND,
    OCR_IBEAM,
    OCR_NO,
    OCR_NORMAL,
    OCR_WAIT,
    SPIF_SENDCHANGE,
    SPIF_UPDATEINIFILE,
    SPI_GETDESKWALLPAPER,
    SPI_SETDESKWALLPAPER,
    apply_dwm_colorization,
    apply_system_cursors,
    broadcast_setting_change,
    get_preferred_cursor_size,
    notify_shell_icons_changed,
    restore_system_cursors,
    set_windows_accent,
    user32,
)

_PUBLIC_ROOT = os.environ.get("PUBLIC") or r"C:\Users\Public"
PUBLIC_THEME_DIR = os.path.join(_PUBLIC_ROOT, "Pictures", "ChristmasOverlay")
BACKUP_PATH = os.path.join(PUBLIC_THEME_DIR, "theme_backup.json")
WALLPAPER_PATH = os.path.join(PUBLIC_THEME_DIR, "festive_wallpaper.png")
LOCKSCREEN_PATH = os.path.join(PUBLIC_THEME_DIR, "festive_lockscreen.png")

# Festive Crimson Red (#DC2626 -> R=220, G=38, B=38)
FESTIVE_RGB = (220, 38, 38)

_RECYCLE_BIN_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\CLSID"
    r"\{645FF040-5081-101B-9F08-00AA002F954E}\DefaultIcon"
)
_LOCKSCREEN_CREATIVE_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Lock Screen\Creative"
)
_LOCKSCREEN_POLICY_KEY = (
    r"SOFTWARE\Policies\Microsoft\Windows\Personalization"
)

_ole32 = ctypes.WinDLL("ole32", use_last_error=True)


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_str(cls, s: str) -> "_GUID":
        s = s.strip("{}")
        parts = s.split("-")
        d4 = bytes.fromhex(parts[3] + parts[4])
        return cls(
            int(parts[0], 16),
            int(parts[1], 16),
            int(parts[2], 16),
            (ctypes.c_ubyte * 8)(*d4),
        )


_CLSID_DesktopWallpaper = _GUID.from_str("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")
_IID_IDesktopWallpaper = _GUID.from_str("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")

_ole32.CoInitializeEx.argtypes = [c_void_p, wintypes.DWORD]
_ole32.CoInitializeEx.restype = ctypes.HRESULT
_ole32.CoUninitialize.argtypes = []
_ole32.CoUninitialize.restype = None
_ole32.CoCreateInstance.argtypes = [
    POINTER(_GUID),
    c_void_p,
    wintypes.DWORD,
    POINTER(_GUID),
    POINTER(c_void_p),
]
_ole32.CoCreateInstance.restype = ctypes.HRESULT
_ole32.CoTaskMemFree.argtypes = [c_void_p]
_ole32.CoTaskMemFree.restype = None


def _is_managed_wallpaper(path: str) -> bool:
    if not path:
        return False
    norm = os.path.normcase(os.path.abspath(path))
    managed_dir = os.path.normcase(os.path.abspath(PUBLIC_THEME_DIR))
    return norm.startswith(managed_dir + os.sep) or "festive_wallpaper" in norm


def _with_desktop_wallpaper(fn):
    hr_init = _ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    punk = c_void_p()
    try:
        hr = _ole32.CoCreateInstance(
            byref(_CLSID_DesktopWallpaper),
            None,
            0x4,  # CLSCTX_LOCAL_SERVER
            byref(_IID_IDesktopWallpaper),
            byref(punk),
        )
        if hr != 0 or not punk.value:
            return None
        vtable = ctypes.cast(
            ctypes.cast(punk, POINTER(POINTER(c_void_p))).contents,
            POINTER(c_void_p),
        )
        release_fn = ctypes.WINFUNCTYPE(c_uint, c_void_p)(vtable[2])
        try:
            return fn(punk, vtable)
        finally:
            release_fn(punk)
    except Exception:
        traceback.print_exc()
        return None
    finally:
        if hr_init in (0, 1):
            _ole32.CoUninitialize()


def _find_previous_user_wallpaper() -> str:
    """Finds the user's real wallpaper from Windows 10/11 BackgroundHistoryPath0..4."""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers",
            0,
            winreg.KEY_READ,
        ) as k:
            for i in range(5):
                try:
                    val, _ = winreg.QueryValueEx(k, f"BackgroundHistoryPath{i}")
                    if (
                        isinstance(val, str)
                        and val
                        and not _is_managed_wallpaper(val)
                        and os.path.exists(val)
                    ):
                        return val
                except FileNotFoundError:
                    continue
    except Exception:
        pass
    return ""


def _get_current_wallpaper() -> str:
    def _query(punk, vtable):
        get_wp_fn = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, c_void_p, c_wchar_p, POINTER(c_void_p)
        )(vtable[4])
        get_path_at_fn = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, c_void_p, c_uint, POINTER(c_void_p)
        )(vtable[5])
        get_count_fn = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, c_void_p, POINTER(c_uint)
        )(vtable[6])

        count = c_uint(0)
        if get_count_fn(punk, byref(count)) == 0 and count.value > 0:
            mon_ptr = c_void_p()
            if get_path_at_fn(punk, 0, byref(mon_ptr)) == 0 and mon_ptr.value:
                try:
                    mon_id = ctypes.wstring_at(mon_ptr.value)
                    wp_ptr = c_void_p()
                    if get_wp_fn(punk, mon_id, byref(wp_ptr)) == 0 and wp_ptr.value:
                        try:
                            return ctypes.wstring_at(wp_ptr.value)
                        finally:
                            _ole32.CoTaskMemFree(wp_ptr)
                finally:
                    _ole32.CoTaskMemFree(mon_ptr)
        return None

    res = _with_desktop_wallpaper(_query)
    if res:
        return res

    buf = ctypes.create_unicode_buffer(512)
    user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 512, buf, 0)
    return buf.value


def _set_wallpaper_com(abs_path: str) -> bool:
    if not os.path.exists(abs_path):
        return False

    def _apply(punk, vtable):
        set_wp_fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, c_wchar_p, c_wchar_p)(
            vtable[3]
        )
        get_path_at_fn = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, c_void_p, c_uint, POINTER(c_void_p)
        )(vtable[5])
        get_count_fn = ctypes.WINFUNCTYPE(
            ctypes.HRESULT, c_void_p, POINTER(c_uint)
        )(vtable[6])
        set_pos_fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, c_int)(vtable[10])
        enable_fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, wintypes.BOOL)(vtable[18])

        enable_fn(punk, True)
        set_pos_fn(punk, 4)  # DWPOS_FILL

        count = c_uint(0)
        if get_count_fn(punk, byref(count)) != 0 or count.value == 0:
            return False

        applied = False
        for idx in range(count.value):
            mon_ptr = c_void_p()
            if get_path_at_fn(punk, idx, byref(mon_ptr)) == 0 and mon_ptr.value:
                try:
                    mon_id = ctypes.wstring_at(mon_ptr.value)
                    if set_wp_fn(punk, mon_id, abs_path) == 0:
                        applied = True
                finally:
                    _ole32.CoTaskMemFree(mon_ptr)
        return applied

    return bool(_with_desktop_wallpaper(_apply))


def _set_wallpaper_mode_picture() -> None:
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers",
            0,
            winreg.KEY_SET_VALUE,
        ) as k:
            winreg.SetValueEx(k, "BackgroundType", 0, winreg.REG_DWORD, 0)
    except Exception:
        pass


def _set_solid_color_wallpaper() -> bool:
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers",
            0,
            winreg.KEY_SET_VALUE,
        ) as k:
            winreg.SetValueEx(k, "BackgroundType", 0, winreg.REG_DWORD, 1)
    except Exception:
        pass

    def _disable(punk, vtable):
        enable_fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, wintypes.BOOL)(vtable[18])
        return enable_fn(punk, False) == 0

    if _with_desktop_wallpaper(_disable):
        return True

    buf = ctypes.create_unicode_buffer("")
    return bool(
        user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, buf, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
    )


def _set_wallpaper(path: str) -> bool:
    if not path:
        return _set_solid_color_wallpaper()

    abs_path = os.path.abspath(path)
    _set_wallpaper_mode_picture()

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.SetValueEx(k, "WallPaper", 0, winreg.REG_SZ, abs_path)
            winreg.SetValueEx(k, "WallpaperStyle", 0, winreg.REG_SZ, "10")
            winreg.SetValueEx(k, "TileWallpaper", 0, winreg.REG_SZ, "0")
    except Exception:
        pass

    if _set_wallpaper_com(abs_path):
        return True

    buf = ctypes.create_unicode_buffer(abs_path)
    return bool(
        user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            buf,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE,
        )
    )


def _load_backup() -> dict:
    for candidate in (BACKUP_PATH, os.path.join(CONFIG_DIR, "theme_backup.json")):
        try:
            with open(candidate, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_backup(data: dict) -> None:
    try:
        os.makedirs(PUBLIC_THEME_DIR, exist_ok=True)
        tmp = BACKUP_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, BACKUP_PATH)
    except Exception:
        pass


def _read_reg_typed(root, subkey: str, name: str):
    """Reads any registry value into a JSON-serializable dict."""
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as k:
            val, reg_type = winreg.QueryValueEx(k, name)
            if reg_type == winreg.REG_BINARY and isinstance(val, (bytes, bytearray)):
                return {"type": "bin", "val": val.hex()}
            if reg_type == winreg.REG_DWORD:
                return {"type": "dword", "val": int(val)}
            if reg_type in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) and isinstance(val, str):
                return {"type": "str", "reg_type": reg_type, "val": val}
    except Exception:
        pass
    return None


def _write_reg_typed(root, subkey: str, name: str, entry: dict | None) -> None:
    """Restores a registry value serialized by _read_reg_typed (or deletes if None)."""
    try:
        with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_SET_VALUE) as k:
            if entry is None:
                try:
                    winreg.DeleteValue(k, name)
                except FileNotFoundError:
                    pass
                return
            t = entry.get("type")
            if t == "bin":
                winreg.SetValueEx(
                    k, name, 0, winreg.REG_BINARY, bytes.fromhex(entry["val"])
                )
            elif t == "dword":
                winreg.SetValueEx(
                    k, name, 0, winreg.REG_DWORD, int(entry["val"]) & 0xFFFFFFFF
                )
            elif t == "str":
                rtype = int(entry.get("reg_type", winreg.REG_SZ))
                winreg.SetValueEx(k, name, 0, rtype, str(entry["val"]))
    except Exception:
        pass


def _write_reg_raw(root, subkey: str, name: str, val, reg_type: int) -> None:
    with winreg.CreateKeyEx(root, subkey, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, name, 0, reg_type, val)

def _render_festive_wallpaper(width: int, height: int, out_path: str) -> None:
    target_w = max(800, int(width))
    target_h = max(600, int(height))
    w = target_w // 2
    h = target_h // 2

    top_rgb = (6, 11, 24)
    mid_rgb = (13, 25, 48)
    hor_rgb = (26, 46, 76)

    grad = Image.new("RGB", (1, h))
    g_px = grad.load()
    for y in range(h):
        t = y / max(1, h - 1)
        if t < 0.55:
            k = t / 0.55
            c0, c1 = top_rgb, mid_rgb
        else:
            k = (t - 0.55) / 0.45
            c0, c1 = mid_rgb, hor_rgb
        g_px[0, y] = (
            int(c0[0] + (c1[0] - c0[0]) * k),
            int(c0[1] + (c1[1] - c0[1]) * k),
            int(c0[2] + (c1[2] - c0[2]) * k),
        )
    base = grad.resize((w, h), Image.Resampling.BILINEAR).convert("RGBA")

    vig = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vig)
    v_draw.rectangle([0, 0, int(w * 0.36), h], fill=(4, 8, 18, 75))
    vig = vig.filter(ImageFilter.GaussianBlur(radius=max(20, w // 14)))
    base = Image.alpha_composite(base, vig)

    sky_fx = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(sky_fx)
    rng = random.Random(20261225)
    for _ in range(200):
        sx = rng.randint(0, w - 1)
        sy = rng.randint(0, int(h * 0.62))
        icon_dim = 0.45 if sx < w * 0.28 else 1.0
        alpha = int(rng.randint(70, 220) * icon_dim)
        r = 1 if rng.random() > 0.88 else 0
        col = (255, 248, 225, alpha) if rng.random() > 0.3 else (190, 225, 255, alpha)
        s_draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=col)

    mx, my = int(w * 0.80), int(h * 0.20)
    moon_r = max(10, min(w, h) // 34)
    halo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    h_draw = ImageDraw.Draw(halo)
    h_draw.ellipse(
        [mx - moon_r * 4, my - moon_r * 4, mx + moon_r * 4, my + moon_r * 4],
        fill=(226, 238, 255, 44),
    )
    halo = halo.filter(ImageFilter.GaussianBlur(radius=max(8, int(moon_r * 1.5))))
    base = Image.alpha_composite(base, halo)
    s_draw.ellipse(
        [mx - moon_r, my - moon_r, mx + moon_r, my + moon_r],
        fill=(248, 250, 252, 240),
    )
    base = Image.alpha_composite(base, sky_fx)

    aurora = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    a_draw = ImageDraw.Draw(aurora)
    ribbons = [
        (0.24, 0.045, (16, 185, 129, 64), 26),
        (0.30, 0.038, (52, 211, 153, 50), 18),
        (0.21, 0.050, (129, 140, 248, 42), 22),
    ]
    for y_frac, amp_frac, color, thickness in ribbons:
        pts = []
        steps = 40
        for i in range(steps + 1):
            t = i / steps
            px = int(w * (0.28 + 0.74 * t))
            py = int(
                h * y_frac
                + math.sin(t * math.pi * 2.2 + y_frac * 12.0) * (h * amp_frac)
                - t * (h * 0.05)
            )
            pts.append((px, py))
        a_draw.line(pts, fill=color, width=max(8, int(h * thickness / 720)))
    aurora = aurora.filter(ImageFilter.GaussianBlur(radius=max(14, h // 22)))
    base = Image.alpha_composite(base, aurora)

    land = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    l_draw = ImageDraw.Draw(land)
    mtn_pts = [(0, h)]
    peaks = [
        (0.0, 0.72),
        (0.14, 0.64),
        (0.28, 0.70),
        (0.45, 0.60),
        (0.62, 0.68),
        (0.76, 0.58),
        (0.90, 0.65),
        (1.0, 0.61),
    ]
    for xf, yf in peaks:
        mtn_pts.append((int(w * xf), int(h * yf)))
    mtn_pts.append((w, h))
    l_draw.polygon(mtn_pts, fill=(15, 26, 46, 255))

    def draw_pine(draw_ctx, cx: int, base_y: int, tree_h: int, color: tuple):
        tiers = 4
        for tier in range(tiers):
            t0 = tier / tiers
            t1 = (tier + 1.35) / tiers
            top_y = base_y - int(tree_h * (1.0 - t0 * 0.78))
            bot_y = base_y - int(tree_h * (1.0 - min(1.0, t1 * 0.85)))
            half_w = int(tree_h * (0.14 + t0 * 0.11))
            draw_ctx.polygon(
                [(cx, top_y), (cx - half_w, bot_y), (cx + half_w, bot_y)],
                fill=color,
            )

    back_hill = [(0, h)]
    for i in range(41):
        t = i / 40.0
        hy = h * (0.76 + 0.025 * math.sin(t * math.pi * 2.4 + 0.6))
        back_hill.append((int(w * t), int(hy)))
    back_hill.append((w, h))
    l_draw.polygon(back_hill, fill=(20, 34, 58, 255))

    far_tree_col = (12, 22, 39, 255)
    for tx in range(int(w * 0.03), w, max(14, w // 42)):
        t = tx / w
        hy = int(h * (0.76 + 0.025 * math.sin(t * math.pi * 2.4 + 0.6)))
        th = rng.randint(int(h * 0.045), int(h * 0.085))
        draw_pine(l_draw, tx + rng.randint(-3, 3), hy + 2, th, far_tree_col)

    front_hill = [(0, h)]
    for i in range(41):
        t = i / 40.0
        hy = h * (0.835 + 0.022 * math.cos(t * math.pi * 2.0 - 0.5))
        front_hill.append((int(w * t), int(hy)))
    front_hill.append((w, h))
    l_draw.polygon(front_hill, fill=(34, 52, 80, 255))

    near_tree_col = (8, 16, 30, 255)
    for tx in range(int(w * 0.02), int(w * 0.98), max(18, w // 32)):
        t = tx / w
        if 0.32 < t < 0.68 and rng.random() > 0.25:
            continue
        hy = int(h * (0.835 + 0.022 * math.cos(t * math.pi * 2.0 - 0.5)))
        th = rng.randint(int(h * 0.07), int(h * 0.14))
        draw_pine(l_draw, tx, hy + 4, th, near_tree_col)

    # Cozy cabin + warm window glow + chimney smoke
    cab_x = int(w * 0.72)
    cab_y = int(h * (0.835 + 0.022 * math.cos(0.72 * math.pi * 2.0 - 0.5))) + 1
    cw = max(18, w // 44)
    ch = max(12, int(cw * 0.62))

    spill = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sp_draw = ImageDraw.Draw(spill)
    sp_draw.ellipse(
        [cab_x - cw * 2, cab_y - ch * 2, cab_x + cw * 3, cab_y + ch * 2],
        fill=(251, 191, 36, 52),
    )
    spill = spill.filter(ImageFilter.GaussianBlur(radius=max(6, int(cw * 0.8))))
    land = Image.alpha_composite(land, spill)
    l_draw = ImageDraw.Draw(land)

    chim_x = cab_x + int(cw * 0.68)
    l_draw.rectangle(
        [chim_x, cab_y - ch - int(ch * 0.55), chim_x + max(2, cw // 7), cab_y - ch + 1],
        fill=(18, 24, 38, 255),
    )
    smoke = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sm_draw = ImageDraw.Draw(smoke)
    for step in range(1, 7):
        sy = cab_y - ch - int(ch * 0.55) - step * max(3, ch // 3)
        sx = chim_x + int(math.sin(step * 0.9) * (cw * 0.16)) + step
        sr = max(2, cw // 10) + (step // 2)
        sm_draw.ellipse(
            [sx - sr, sy - sr, sx + sr, sy + sr],
            fill=(226, 232, 240, max(12, 56 - step * 7)),
        )
    smoke = smoke.filter(ImageFilter.GaussianBlur(radius=2))
    land = Image.alpha_composite(land, smoke)
    l_draw = ImageDraw.Draw(land)

    l_draw.rectangle([cab_x, cab_y - ch, cab_x + cw, cab_y], fill=(22, 28, 42, 255))
    roof_pts = [
        (cab_x - 2, cab_y - ch + 1),
        (cab_x + cw // 2, cab_y - ch - int(ch * 0.65)),
        (cab_x + cw + 2, cab_y - ch + 1),
    ]
    l_draw.polygon(roof_pts, fill=(14, 20, 32, 255))
    l_draw.line(roof_pts, fill=(226, 236, 248, 235), width=max(1, ch // 11))

    win_w = max(3, cw // 5)
    win_h = max(3, ch // 3)
    wy = cab_y - int(ch * 0.62)
    for wx in (cab_x + int(cw * 0.22), cab_x + int(cw * 0.58)):
        l_draw.rectangle([wx, wy, wx + win_w, wy + win_h], fill=(253, 224, 71, 255))

    base = Image.alpha_composite(base, land)

    bokeh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(bokeh)
    bokeh_colors = [
        (251, 191, 36, 48),
        (239, 68, 68, 40),
        (56, 189, 248, 38),
        (16, 185, 129, 36),
    ]
    for _ in range(26):
        bx = rng.randint(int(w * 0.04), int(w * 0.96))
        by = rng.randint(int(h * 0.86), int(h * 0.98))
        br = rng.randint(max(4, h // 85), max(10, h // 42))
        b_draw.ellipse(
            [bx - br, by - br, bx + br, by + br],
            fill=rng.choice(bokeh_colors),
        )
    bokeh = bokeh.filter(ImageFilter.GaussianBlur(radius=max(4, h // 110)))
    base = Image.alpha_composite(base, bokeh)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    final = base.convert("RGB").resize((target_w, target_h), Image.Resampling.BICUBIC)
    final.save(out_path, "PNG")

def _save_win32_ico(img: Image.Image, out_path: str) -> None:
    """Writes a native 32-bit BGRA DIB .ico file that Windows Shell never rejects."""
    sizes = (16, 24, 32, 48, 64, 128, 256)
    src = img.convert("RGBA")
    entries = []

    for sz in sizes:
        frame = src.resize((sz, sz), Image.Resampling.LANCZOS)
        r, g, b, a = frame.split()
        bgra = Image.merge("RGBA", (b, g, r, a)).tobytes()
        alpha_bytes = a.tobytes()

        row_bytes = sz * 4
        xor_rows = [
            bgra[y * row_bytes : (y + 1) * row_bytes]
            for y in range(sz - 1, -1, -1)
        ]
        xor_data = b"".join(xor_rows)

        and_stride = ((sz + 31) // 32) * 4
        and_rows = []
        for y in range(sz - 1, -1, -1):
            row = bytearray(and_stride)
            row_off = y * sz
            for x in range(sz):
                if alpha_bytes[row_off + x] < 128:
                    row[x >> 3] |= 0x80 >> (x & 7)
            and_rows.append(bytes(row))
        and_data = b"".join(and_rows)

        bih = struct.pack(
            "<IIIHHIIIIII",
            40,
            sz,
            sz * 2,
            1,
            32,
            0,
            len(xor_data) + len(and_data),
            0,
            0,
            0,
            0,
        )
        entries.append((sz, bih + xor_data + and_data))

    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    dir_entries = []
    for sz, blob in entries:
        dim = 0 if sz >= 256 else sz
        dir_entries.append(
            struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        )
        offset += len(blob)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(header)
        for d in dir_entries:
            f.write(d)
        for _, blob in entries:
            f.write(blob)

class SystemThemeManager:
    DWM_KEY = r"Software\Microsoft\Windows\DWM"
    ACCENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Accent"
    WALLPAPERS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers"

    _ACCENT_FIELDS = (
        (DWM_KEY, "AccentColor"),
        (DWM_KEY, "AccentColorInactive"),
        (DWM_KEY, "ColorPrevalence"),
        (DWM_KEY, "ColorizationColor"),
        (DWM_KEY, "ColorizationAfterglow"),
        (ACCENT_KEY, "AccentColorMenu"),
        (ACCENT_KEY, "StartColorMenu"),
        (ACCENT_KEY, "AccentPalette"),
    )

    def __init__(self):
        self._wallpaper_active = False
        self._accent_active = False
        self._cursors_active = False
        self._icons_active = False
        self._lockscreen_active = False

        self._wp_lock = threading.Lock()
        self._accent_lock = threading.Lock()
        self._state_lock = threading.Lock()

    def apply_wallpaper(self, vw: int, vh: int) -> tuple[bool, str | None]:
        self._wallpaper_active = True

        def worker():
            with self._wp_lock:
                if not self._wallpaper_active:
                    return
                try:
                    with self._state_lock:
                        backup = _load_backup()
                        saved_wp = backup.get("wallpaper", "")
                        if "wallpaper" not in backup or _is_managed_wallpaper(saved_wp):
                            cur = _get_current_wallpaper()
                            if _is_managed_wallpaper(cur) or not cur:
                                cur = _find_previous_user_wallpaper()
                            backup["wallpaper"] = cur
                            backup["bg_type"] = _read_reg_typed(
                                winreg.HKEY_CURRENT_USER,
                                self.WALLPAPERS_KEY,
                                "BackgroundType",
                            )
                            _save_backup(backup)

                    os.makedirs(PUBLIC_THEME_DIR, exist_ok=True)
                    _render_festive_wallpaper(vw, vh, WALLPAPER_PATH)
                    if self._wallpaper_active:
                        _set_wallpaper(WALLPAPER_PATH)
                except Exception:
                    traceback.print_exc()

        threading.Thread(target=worker, daemon=True).start()
        return True, None

    def _restore_wallpaper_sync(self) -> None:
        with self._wp_lock:
            with self._state_lock:
                backup = _load_backup()
                has_backup = "wallpaper" in backup
                orig = backup.pop("wallpaper", "")
                bg_type = backup.pop("bg_type", None)
                if has_backup:
                    _save_backup(backup)

            if not orig or _is_managed_wallpaper(orig) or not os.path.exists(orig):
                orig = _find_previous_user_wallpaper()

            if orig and os.path.exists(orig):
                _set_wallpaper(orig)
            elif has_backup:
                _set_solid_color_wallpaper()

            if bg_type is not None:
                _write_reg_typed(
                    winreg.HKEY_CURRENT_USER,
                    self.WALLPAPERS_KEY,
                    "BackgroundType",
                    bg_type,
                )

    def restore_wallpaper(self) -> None:
        self._wallpaper_active = False
        threading.Thread(target=self._restore_wallpaper_sync, daemon=True).start()

    def apply_accent(self) -> None:
        self._accent_active = True

        def worker():
            with self._accent_lock:
                if not self._accent_active:
                    return
                try:
                    with self._state_lock:
                        backup = _load_backup()
                        if "accent_v2" not in backup:
                            saved = {}
                            for subkey, name in self._ACCENT_FIELDS:
                                saved[f"{subkey}\\{name}"] = _read_reg_typed(
                                    winreg.HKEY_CURRENT_USER, subkey, name
                                )
                            backup["accent_v2"] = saved
                            _save_backup(backup)

                    if self._accent_active:
                        set_windows_accent(*FESTIVE_RGB, prevalence=1)
                except Exception:
                    traceback.print_exc()

        threading.Thread(target=worker, daemon=True).start()

    def _restore_accent_sync(self) -> None:
        with self._accent_lock:
            with self._state_lock:
                backup = _load_backup()
                saved = backup.pop("accent_v2", None)
                _save_backup(backup)

            if isinstance(saved, dict):
                for subkey, name in self._ACCENT_FIELDS:
                    full_key = f"{subkey}\\{name}"
                    if full_key in saved:
                        _write_reg_typed(
                            winreg.HKEY_CURRENT_USER, subkey, name, saved[full_key]
                        )
                col_entry = saved.get(f"{self.DWM_KEY}\\ColorizationColor")
                if isinstance(col_entry, dict) and col_entry.get("type") == "dword":
                    apply_dwm_colorization(int(col_entry["val"]))
                broadcast_setting_change()

    def restore_accent(self) -> None:
        self._accent_active = False
        threading.Thread(target=self._restore_accent_sync, daemon=True).start()

    def apply_cursors(self) -> tuple[bool, str | None]:
        try:
            cur_dir = os.path.join(CONFIG_DIR, "cursors")
            os.makedirs(cur_dir, exist_ok=True)
            sz = get_preferred_cursor_size()

            specs = {
                "arrow.cur": (render_candy_arrow_cursor(sz), [OCR_NORMAL]),
                "hand.cur": (render_santa_mitten_cursor(sz), [OCR_HAND]),
                "wreath.cur": (
                    render_wreath_cursor(sz),
                    [OCR_WAIT, OCR_APPSTARTING, OCR_NO],
                ),
                "ibeam.cur": (render_ibeam_cursor(sz), [OCR_IBEAM]),
            }
            cursor_map: dict[int, str] = {}
            for filename, ((img, hx, hy), ocr_ids) in specs.items():
                path = os.path.join(cur_dir, filename)
                save_cur(img, path, hx, hy)
                for oid in ocr_ids:
                    cursor_map[oid] = path

            ok = apply_system_cursors(cursor_map)
            self._cursors_active = ok
            return (True, None) if ok else (False, "Could not apply festive cursors.")
        except Exception as e:
            return False, f"Cursor error: {e}"

    def restore_cursors(self) -> None:
        if not self._cursors_active:
            return
        self._cursors_active = False
        restore_system_cursors()

    def apply_festive_icons(self) -> tuple[bool, str | None]:
        try:
            icon_dir = os.path.join(PUBLIC_THEME_DIR, "icons")
            os.makedirs(icon_dir, exist_ok=True)

            # Remove previous icons so Explorer doesn't reuse stale IconCache entries
            for old in os.listdir(icon_dir):
                if old.startswith("recycle_") and old.endswith(".ico"):
                    try:
                        os.remove(os.path.join(icon_dir, old))
                    except Exception:
                        pass

            tag = int(time.time() * 1000) % 10_000_000
            empty_ico = os.path.abspath(
                os.path.join(icon_dir, f"recycle_empty_{tag}.ico")
            )
            full_ico = os.path.abspath(
                os.path.join(icon_dir, f"recycle_full_{tag}.ico")
            )
            app_ico = os.path.abspath(os.path.join(icon_dir, "festive_app.ico"))

            _save_win32_ico(render_recycle_bin_icon(full=False), empty_ico)
            _save_win32_ico(render_recycle_bin_icon(full=True), full_ico)
            _save_win32_ico(render_festive_app_icon(), app_ico)

            with self._state_lock:
                backup = _load_backup()
                if "recycle_bin" not in backup:
                    saved = {}
                    for val_name in ("", "empty", "full"):
                        saved[val_name] = _read_reg_typed(
                            winreg.HKEY_CURRENT_USER, _RECYCLE_BIN_KEY, val_name
                        )
                    backup["recycle_bin"] = saved
                    _save_backup(backup)

            _write_reg_raw(
                winreg.HKEY_CURRENT_USER,
                _RECYCLE_BIN_KEY,
                "",
                f"{empty_ico},0",
                winreg.REG_EXPAND_SZ,
            )
            _write_reg_raw(
                winreg.HKEY_CURRENT_USER,
                _RECYCLE_BIN_KEY,
                "empty",
                f"{empty_ico},0",
                winreg.REG_EXPAND_SZ,
            )
            _write_reg_raw(
                winreg.HKEY_CURRENT_USER,
                _RECYCLE_BIN_KEY,
                "full",
                f"{full_ico},0",
                winreg.REG_EXPAND_SZ,
            )
            notify_shell_icons_changed()
            self._icons_active = True
            return True, app_ico
        except Exception as e:
            return False, f"Icon error: {e}"
        
    def restore_festive_icons(self) -> None:
        with self._state_lock:
            backup = _load_backup()
            saved = backup.pop("recycle_bin", None)
            _save_backup(backup)

        was_active = self._icons_active
        self._icons_active = False
        if not saved and not was_active:
            return
        if isinstance(saved, dict):
            for val_name in ("", "empty", "full"):
                if val_name in saved:
                    _write_reg_typed(
                        winreg.HKEY_CURRENT_USER,
                        _RECYCLE_BIN_KEY,
                        val_name,
                        saved[val_name],
                    )
        notify_shell_icons_changed()

    @staticmethod
    def _set_winrt_lockscreen_async(image_path: str) -> None:
        """Applies a Lock Screen image via WinRT on a background thread."""
        escaped = image_path.replace("'", "''")
        ps_script = (
            "$ErrorActionPreference='Stop';"
            "Add-Type -AssemblyName System.Runtime.WindowsRuntime;"
            "$asTaskOp=([System.WindowsRuntimeSystemExtensions].GetMethods()|"
            "Where-Object{$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
            "$_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'})[0];"
            "$asTaskAct=([System.WindowsRuntimeSystemExtensions].GetMethods()|"
            "Where-Object{$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and "
            "$_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'})[0];"
            "Function AwaitOp($t,$r){$m=$asTaskOp.MakeGenericMethod($r);$nt=$m.Invoke($null,@($t));$nt.Wait(-1)|Out-Null;$nt.Result};"
            "Function AwaitAct($t){$nt=$asTaskAct.Invoke($null,@($t));$nt.Wait(-1)|Out-Null};"
            "[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]|Out-Null;"
            "[Windows.System.UserProfile.LockScreen,Windows.System.UserProfile,ContentType=WindowsRuntime]|Out-Null;"
            f"$f=AwaitOp([Windows.Storage.StorageFile]::GetFileFromPathAsync('{escaped}'))([Windows.Storage.StorageFile]);"
            "AwaitAct([Windows.System.UserProfile.LockScreen]::SetImageFileAsync($f));"
        )

        def worker():
            try:
                subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-WindowStyle",
                        "Hidden",
                        "-Command",
                        ps_script,
                    ],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=20,
                    check=False,
                )
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def apply_lockscreen(self, vw: int, vh: int) -> tuple[bool, str | None]:
        no_ls = _read_reg_typed(
            winreg.HKEY_LOCAL_MACHINE, _LOCKSCREEN_POLICY_KEY, "NoLockScreen"
        )
        pol_img = _read_reg_typed(
            winreg.HKEY_LOCAL_MACHINE, _LOCKSCREEN_POLICY_KEY, "LockScreenImage"
        )
        if (no_ls and no_ls.get("val")) or (pol_img and pol_img.get("val")):
            return False, "Lock screen is locked by Windows policy."

        try:
            with self._state_lock:
                backup = _load_backup()
                if "lockscreen" not in backup:
                    saved = {}
                    for name in (
                        "LandscapeAssetPath",
                        "PortraitAssetPath",
                        "RotatingLockScreenEnabled",
                        "RotatingLockScreenOverlayEnabled",
                    ):
                        saved[name] = _read_reg_typed(
                            winreg.HKEY_CURRENT_USER, _LOCKSCREEN_CREATIVE_KEY, name
                        )
                    backup["lockscreen"] = saved
                    _save_backup(backup)

            os.makedirs(PUBLIC_THEME_DIR, exist_ok=True)
            render_winter_backdrop(
                min(2560, vw), min(1440, vh), LOCKSCREEN_PATH, lockscreen=True
            )
            self._set_winrt_lockscreen_async(LOCKSCREEN_PATH)
            self._lockscreen_active = True
            return True, None
        except Exception as e:
            return False, f"Lock screen error: {e}"

    def restore_lockscreen(self) -> None:
        with self._state_lock:
            backup = _load_backup()
            saved = backup.pop("lockscreen", None)
            _save_backup(backup)

        was_active = self._lockscreen_active
        self._lockscreen_active = False
        if not saved and not was_active:
            return

        orig_asset = None
        if isinstance(saved, dict):
            for name in (
                "LandscapeAssetPath",
                "PortraitAssetPath",
                "RotatingLockScreenEnabled",
                "RotatingLockScreenOverlayEnabled",
            ):
                if name in saved:
                    _write_reg_typed(
                        winreg.HKEY_CURRENT_USER,
                        _LOCKSCREEN_CREATIVE_KEY,
                        name,
                        saved[name],
                    )
            la = saved.get("LandscapeAssetPath")
            if isinstance(la, dict) and isinstance(la.get("val"), str):
                if os.path.exists(la["val"]):
                    orig_asset = la["val"]

        if orig_asset:
            self._set_winrt_lockscreen_async(orig_asset)

    # --- Global Synchronous Restore (for App Shutdown / Exit Hooks) ---

    def restore_all(self) -> None:
        self._wallpaper_active = False
        self._accent_active = False
        self.restore_cursors()
        self.restore_festive_icons()

        backup = _load_backup()
        if "wallpaper" in backup or _is_managed_wallpaper(_get_current_wallpaper()):
            self._restore_wallpaper_sync()
        if "accent_v2" in backup:
            self._restore_accent_sync()
        if "lockscreen" in backup or self._lockscreen_active:
            self.restore_lockscreen()