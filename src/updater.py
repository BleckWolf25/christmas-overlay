# src/updater.py
import json
import os
import subprocess
import tempfile
import urllib.request
from version import __version__, GITHUB_API_LATEST, USER_AGENT, EXE_ASSET_NAME
from paths import exe_path, is_frozen

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
    target_dir = os.path.dirname(exe_path())
    new_path = os.path.join(target_dir, "ChristmasOverlay.exe.new")
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


def apply_update_and_restart(new_path: str) -> None:
    if not is_frozen():
        raise RuntimeError("Self-update only works from the packaged .exe")
    cur = exe_path()
    old = cur + ".old"
    pid = os.getpid()
    bat = os.path.join(tempfile.gettempdir(), f"xmas_update_{pid}.bat")

    script = f"""@echo off
set /a tries=0
:wait
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul && (
  ping -n 2 127.0.0.1 >nul
  goto wait
)
:swap
set /a tries+=1
if %tries% GTR 15 goto end
if exist "{old}" del /f /q "{old}" >nul 2>&1
move /y "{cur}" "{old}" >nul 2>&1
if errorlevel 1 (
  ping -n 2 127.0.0.1 >nul
  goto swap
)
move /y "{new_path}" "{cur}" >nul 2>&1
if errorlevel 1 (
  move /y "{old}" "{cur}" >nul 2>&1
  goto end
)
start "" "{cur}"
:end
del /f /q "{old}" >nul 2>&1
(goto) 2>nul & del /f /q "%~f0"
"""
    with open(bat, "w", encoding="ascii", newline="\r\n") as f:
        f.write(script)

    subprocess.Popen(
        ["cmd", "/c", bat],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        close_fds=True,
        cwd=tempfile.gettempdir(),
    )