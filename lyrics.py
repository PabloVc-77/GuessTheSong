"""Obtención, caché y lectura de letras sincronizadas en formato LRC."""

import re
import sys
from pathlib import Path


def get_app_dir():
    """
    Devuelve la carpeta donde se encuentra la aplicación.

    En un ejecutable PyInstaller:
        carpeta que contiene GuessTheSong.exe

    Durante desarrollo:
        carpeta del proyecto
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()

# Caché persistente y externa a _internal
CACHE_DIR = APP_DIR / "Cache" / "Lyrics"

_TIMESTAMP_RE = re.compile(
    r"\[(?P<minutes>\d+):"
    r"(?P<seconds>\d{1,2}(?:[.:]\d{1,3})?)\]"
)


def _cache_filename(title, artist):
    """Devuelve una ruta de caché segura y estable."""

    def sanitize(value):
        filename = "".join(
            char
            if char.isalnum() or char in " -_"
            else "_"
            for char in value.strip()
        ).strip(" .")

        return filename or "unknown"

    return (
        CACHE_DIR
        / f"{sanitize(artist)} - "
          f"{sanitize(title)}.lrc"
    )


def get_cached_lyrics(title, artist):
    path = _cache_filename(
        title,
        artist
    )

    if not path.is_file():
        return None

    return path.read_text(
        encoding="utf-8"
    )


def save_lyrics(title, artist, lyrics):
    """Guarda una letra LRC en caché."""

    path = _cache_filename(
        title,
        artist
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        lyrics,
        encoding="utf-8"
    )

    return path


def parse_lrc(lyrics):
    """Convierte texto LRC en líneas ordenadas."""

    entries = []

    for line in lyrics.splitlines():
        matches = list(
            _TIMESTAMP_RE.finditer(line)
        )

        if not matches:
            continue

        text = _TIMESTAMP_RE.sub(
            "",
            line
        ).strip()

        if not text:
            continue

        for match in matches:
            seconds = float(
                match.group(
                    "seconds"
                ).replace(
                    ":",
                    "."
                )
            )

            entries.append({
                "time": (
                    int(
                        match.group("minutes")
                    ) * 60
                    + seconds
                ),
                "text": text,
            })

    return sorted(
        entries,
        key=lambda entry: entry["time"]
    )


def _download_lyrics(title, artist):
    """Busca letras sincronizadas."""

    try:
        import syncedlyrics
    except ImportError:
        return None

    try:
        return syncedlyrics.search(
            f"{title} {artist}"
        )
    except Exception:
        return None


def get_lyrics(title, artist):
    """
    Obtiene letras sincronizadas de la caché o
    del proveedor.
    """

    cached = get_cached_lyrics(
        title,
        artist
    )

    if cached is not None:
        return cached

    lyrics = _download_lyrics(
        title,
        artist
    )

    if (
        not isinstance(lyrics, str)
        or not parse_lrc(lyrics)
    ):
        return None

    save_lyrics(
        title,
        artist,
        lyrics
    )

    return lyrics