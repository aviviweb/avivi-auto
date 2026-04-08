# -*- mode: python ; coding: utf-8 -*-
"""Build: pyinstaller packaging/avivi-master.spec (from repo root)."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent.resolve()

block_cipher = None

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("avivi_master")
    + collect_submodules("avivi_shared")
    + [
        "aiosqlite",
        "pydantic.deprecated.decorator",
        "telegram.ext",
        "apscheduler.schedulers.asyncio",
    ]
)

a = Analysis(
    [str(ROOT / "packaging" / "frozen_master.py")],
    pathex=[
        str(ROOT / "Avivi_Master"),
        str(ROOT / "shared"),
        str(ROOT / "Avivi_Client"),
        str(ROOT / "OpenClaw_Launcher"),
    ],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AviviMaster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AviviMaster",
)
