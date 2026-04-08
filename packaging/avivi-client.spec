# -*- mode: python ; coding: utf-8 -*-
"""Build: pyinstaller packaging/avivi-client.spec (from repo root)."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent.resolve()

block_cipher = None

hiddenimports = collect_submodules("avivi_client") + collect_submodules("avivi_shared")
hiddenimports += [
    "aiosqlite",
    "pydantic.deprecated.decorator",
    # DB drivers declared in pyproject (Mongo/ODBC optional — add dep + rebuild if needed)
    "pymysql",
    "psycopg2",
    # Owner bot
    "telegram.ext",
]

a = Analysis(
    [str(ROOT / "packaging" / "frozen_client.py")],
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
    [],
    exclude_binaries=True,
    name="AviviClient",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name="AviviClient",
)
