# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules


PROJECT_DIR = Path(SPECPATH)


# ============================================================
# Dependencias de Python
# ============================================================

yt_dlp_datas, yt_dlp_binaries, yt_dlp_hiddenimports = collect_all("yt_dlp")
yt_dlp_ejs_datas, yt_dlp_ejs_binaries, yt_dlp_ejs_hiddenimports = collect_all("yt_dlp_ejs")

syncedlyrics_datas, syncedlyrics_binaries, syncedlyrics_hiddenimports = collect_all(
    "syncedlyrics"
)


hiddenimports = (
    yt_dlp_hiddenimports
    + yt_dlp_ejs_hiddenimports
    + syncedlyrics_hiddenimports
    + collect_submodules("games")
)


# ============================================================
# Archivos externos que deben acompañar al .exe
# ============================================================

datas = []

# yt-dlp
datas += yt_dlp_datas

# yt-dlp-ejs
datas += yt_dlp_ejs_datas

# syncedlyrics
datas += syncedlyrics_datas


# ============================================================
# Recursos de la aplicación
# ============================================================

# Flask
datas += [
    (str(PROJECT_DIR / "templates"), "templates"),
    (str(PROJECT_DIR / "static"), "static"),
]


# Playlists iniciales.
#
# Se copian al lado del ejecutable para que:
#   dist/GuessTheSong/data/
#
# sea una carpeta normal y modificable.
data_dir = PROJECT_DIR / "data"

if data_dir.exists():
    datas.append(
        (str(data_dir), "data")
    )


# ============================================================
# FFmpeg
# ============================================================

ffmpeg_dir = PROJECT_DIR / "ffmpeg"

binaries = []

if ffmpeg_dir.exists():
    for filename in ("ffmpeg.exe", "ffprobe.exe"):
        filepath = ffmpeg_dir / filename

        if filepath.exists():
            binaries.append(
                (str(filepath), "ffmpeg")
            )
        else:
            print(f"WARNING: No encontrado: {filepath}")


# ============================================================
# Deno
# ============================================================

deno_dir = PROJECT_DIR / "deno"
deno_path = deno_dir / "deno.exe"

if deno_path.exists():
    binaries.append(
        (str(deno_path), "deno")
    )
else:
    print(f"WARNING: No encontrado: {deno_path}")


# ============================================================
# Análisis
# ============================================================

a = Analysis(
    ["run.py"],
    pathex=[
        str(PROJECT_DIR)
    ],
    binaries=binaries,
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
    console=True,
    disable_windowed_traceback=False,
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