# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Bundle icon.ico and any assets/sprites directories if present
datas = []
for candidate in ("icon.ico", os.path.join("src", "icon.ico"), os.path.join("assets", "icon.ico")):
    if os.path.exists(candidate):
        datas.append((candidate, "."))
        break

for folder in ("assets", "sprites", os.path.join("src", "assets")):
    if os.path.isdir(folder):
        datas.append((folder, os.path.basename(folder)))

hiddenimports = [
    "pystray._win32",
    "PIL._tkinter_finder",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFilter",
    "PIL.ImageTk",
] + collect_submodules("pystray")

icon_file = next(
    (p for p in ("icon.ico", os.path.join("src", "icon.ico"), os.path.join("assets", "icon.ico")) if os.path.exists(p)),
    None,
)

a = Analysis(
    [os.path.join("src", "main.pyw")],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ChristmasOverlay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)