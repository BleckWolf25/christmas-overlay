# ChristmasOverlay.spec
# -*- mode: python ; coding: utf-8 -*-
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..")) if os.path.basename(SPECPATH).lower() == "tests" else os.path.abspath(SPECPATH)
SRC_DIR = os.path.join(ROOT, "src")
ASSETS_DIR = os.path.join(ROOT, "assets")

a = Analysis(
    [os.path.join(SRC_DIR, "main.pyw")],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[
        (os.path.join(ASSETS_DIR, "icon.png"), "."),
        (os.path.join(ASSETS_DIR, "icon.ico"), "."),
    ],
    hiddenimports=["PIL._tkinter_finder", "pystray._win32"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ChristmasOverlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ASSETS_DIR, "icon.ico"),
)