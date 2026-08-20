from PyInstaller.utils.hooks import collect_submodules


hiddenimports = [
    "socketio",
    "flask_socketio",
    "engineio",
    "engineio.async_drivers",
    "engineio.async_drivers.threading",
    "syncedlyrics",
]

hiddenimports += collect_submodules("syncedlyrics")


a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("data", "data"),
        ("templates", "templates"),
        ("static", "static"),
        ("ffmpeg", "ffmpeg"),
    ],
    hiddenimports=hiddenimports,
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
    name="GuessTheSong",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="GuessTheSong",
)