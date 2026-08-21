# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules


PROJECT_DIR = Path(SPECPATH)


# ============================================================
# Dependencias de Python
# ============================================================

yt_dlp_datas, yt_dlp_binaries, yt_dlp_hiddenimports = collect_all("yt_dlp")
yt_dlp_ejs_datas, yt_dlp_ejs_binaries, yt_dlp_ejs_hiddenimports = collect_all(
    "yt_dlp_ejs"
)

syncedlyrics_datas, syncedlyrics_binaries, syncedlyrics_hiddenimports = collect_all(
    "syncedlyrics"
)


# ============================================================
# Flask-SocketIO / SocketIO / EngineIO
# ============================================================

flask_socketio_hiddenimports = collect_submodules("flask_socketio")
socketio_hiddenimports = collect_submodules("socketio")
engineio_hiddenimports = collect_submodules("engineio")


# ============================================================
# Hidden imports
# ============================================================

hiddenimports = (
    yt_dlp_hiddenimports
    + yt_dlp_ejs_hiddenimports
    + syncedlyrics_hiddenimports
    + flask_socketio_hiddenimports
    + socketio_hiddenimports
    + engineio_hiddenimports
    + collect_submodules("games")
)


# ============================================================
# Recursos internos
# ============================================================

datas = []

datas += yt_dlp_datas
datas += yt_dlp_ejs_datas
datas += syncedlyrics_datas


# Flask
datas += [
    (str(PROJECT_DIR / "templates"), "templates"),
    (str(PROJECT_DIR / "static"), "static"),
]


# ============================================================
# Análisis
# ============================================================

a = Analysis(
    ["run.py"],
    pathex=[
        str(PROJECT_DIR)
    ],
    binaries=(
        yt_dlp_binaries
        + yt_dlp_ejs_binaries
        + syncedlyrics_binaries
    ),
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)


# ============================================================
# PYZ
# ============================================================

pyz = PYZ(
    a.pure,
    a.zipped_data,
)


# ============================================================
# EXE
# ============================================================

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GuessTheSong",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(PROJECT_DIR / "icon.ico"),
)


# ============================================================
# COLLECT
# ============================================================

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GuessTheSong",
)