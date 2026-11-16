# src/updater.py
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from paths import exe_path, is_frozen
from version import __version__, EXE_ASSET_NAME, GITHUB_API_LATEST, USER_AGENT

_TIMEOUT = 12


def _parse_ver(v: str) -> tuple:
    v = v.strip().lstrip("vV")
    parts = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def recover_previous_install() -> None:
    """Restores ChristmasOverlay.exe from .old if an interrupted swap left it missing."""
    if not is_frozen():
        return
    cur = exe_path()
    old = cur + ".old"
    if not os.path.exists(cur) and os.path.exists(old):
        try:
            os.replace(old, cur)
        except Exception:
            pass
    elif os.path.exists(old):
        try:
            os.remove(old)
        except Exception:
            pass


def check_for_update() -> dict | None:
    req = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            data = json.load(r)
    except Exception:
        return None

    latest = data.get("tag_name") or data.get("name") or ""
    if _parse_ver(latest) <= _parse_ver(__version__):
        return None

    url = None
    for asset in data.get("assets", []):
        if asset.get("name") == EXE_ASSET_NAME:
            url = asset.get("browser_download_url")
            break
    if not url:
        return None

    return {
        "version": latest.lstrip("vV"),
        "url": url,
        "notes": (data.get("body") or "")[:500],
    }


def download_exe(url: str) -> str:
    new_path = exe_path() + ".new"
    if os.path.exists(new_path):
        try:
            os.remove(new_path)
        except Exception:
            pass

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(new_path, "wb") as f:
        while chunk := r.read(64 * 1024):
            f.write(chunk)

    with open(new_path, "rb") as f:
        if f.read(2) != b"MZ":
            os.remove(new_path)
            raise RuntimeError("Downloaded file is not a valid executable")
    return new_path


def _clean_spawn_env() -> dict[str, str]:
    """Removes PyInstaller 6+ bootloader env vars and _MEIPASS from PATH so the restarted exe unpacks fresh."""
    env = os.environ.copy()
    for key in list(env.keys()):
        if key.startswith("_PYI_") or key in (
            "_MEIPASS2",
            "TCL_LIBRARY",
            "TK_LIBRARY",
            "PYTHONHOME",
            "PYTHONPATH",
        ):
            env.pop(key, None)

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and "PATH" in env:
        norm_mei = os.path.normcase(os.path.normpath(meipass))
        env["PATH"] = os.pathsep.join(
            p for p in env["PATH"].split(os.pathsep)
            if p and os.path.normcase(os.path.normpath(p)) != norm_mei
        )
    return env


def apply_update_and_restart(new_path: str) -> None:
    if not is_frozen():
        raise RuntimeError("Self-update only works from the packaged .exe")
    cur = exe_path()
    old = cur + ".old"
    pid = os.getpid()
    tmp_dir = tempfile.gettempdir()
    bat = os.path.join(tmp_dir, f"xmas_update_{pid}.bat")
    log = os.path.join(tmp_dir, "xmas_update.log")

    script = f"""@echo off
chcp 65001 >nul
set /a tries=0
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul && (
  ping -n 2 127.0.0.1 >nul
  goto wait
)
ping -n 2 127.0.0.1 >nul

:move_old
set /a tries+=1
if %tries% GTR 30 (
  echo [%date% %time%] Failed to move current exe to .old > "{log}"
  goto relaunch
)
if exist "{old}" del /f /q "{old}" >nul 2>&1
move /y "{cur}" "{old}" >nul 2>&1
if errorlevel 1 (
  ping -n 2 127.0.0.1 >nul
  goto move_old
)

set /a tries=0
:move_new
set /a tries+=1
if %tries% GTR 30 (
  echo [%date% %time%] Failed to move .new to current exe; rolling back > "{log}"
  move /y "{old}" "{cur}" >nul 2>&1
  goto relaunch
)
move /y "{new_path}" "{cur}" >nul 2>&1
if errorlevel 1 (
  ping -n 2 127.0.0.1 >nul
  goto move_new
)

:relaunch
set "_PYI_PARENT_PROCESS_LEVEL="
set "_PYI_APPLICATION_HOME_DIR="
set "_PYI_ARCHIVE_FILE="
set "_PYI_SPLASH_IPC="
set "_MEIPASS2="
if exist "{cur}" start "" "{cur}"
del /f /q "{old}" >nul 2>&1
(goto) 2>nul & del /f /q "%~f0"
"""
    with open(bat, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(script)

    subprocess.Popen(
        ["cmd.exe", "/c", bat],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
        cwd=tmp_dir,
        env=_clean_spawn_env(),
    )