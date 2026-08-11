import os
import shutil
import tempfile
import subprocess
import time

import pygame
from yt_dlp import YoutubeDL


pygame.mixer.init()


CACHE_DIR = os.path.join("Cache", "Songs")


class AudioPlayer:
    def __init__(self):
        self.temp_files = []

        self.download_active = False
        self.download_progress = 0.0
        self.download_phase = ""

    @staticmethod
    def _safe_name(value):
        # Keep the same readable names used by the rest of the project,
        # while avoiding characters that are invalid in Windows paths.
        invalid = '<>:"/\\|?*'
        value = "".join("_" if char in invalid else char for char in value)
        return value.strip().strip(".")

    def _song_dir(self, title, artist):
        return os.path.join(
            CACHE_DIR,
            f"{self._safe_name(artist)} - {self._safe_name(title)}"
        )

    def _song_file(self, title, artist):
        return os.path.join(
            self._song_dir(title, artist),
            f"{self._safe_name(artist)} - {self._safe_name(title)}.mp3"
        )

    def download_song(self, title, artist):
        song_file = self._song_file(title, artist)

        # Reutilizar el MP3 persistente si ya está en caché.
        # Aunque no haya descarga, mantenemos una fase de carga de 3 segundos
        # para que la interfaz pueda mostrar la barra de progreso.
        if os.path.exists(song_file):
            self.download_active = True
            self.download_progress = 0.0
            self.download_phase = "downloading"

            cache_load_start = time.monotonic()
            cache_load_duration = 3.0

            while True:
                elapsed = time.monotonic() - cache_load_start
                self.download_progress = min(
                    elapsed / cache_load_duration,
                    1.0
                )

                if elapsed >= cache_load_duration:
                    break

                time.sleep(0.05)

            # Dejar un poco de tiempo antes de reproducir el fragmento
            time.sleep(0.05)

            duration_result = subprocess.run([
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                song_file
            ], capture_output=True, text=True)

            if duration_result.returncode != 0:
                raise RuntimeError(
                    duration_result.stderr.strip()
                    or "No se pudo obtener la duración del MP3 en caché."
                )

            try:
                duration = float(duration_result.stdout.strip())
            except ValueError as error:
                self.download_active = False
                self.download_phase = ""
                raise RuntimeError(
                    "No se pudo interpretar la duración del MP3 en caché."
                ) from error

            self.download_progress = 1.0
            self.download_active = False
            self.download_phase = ""

            return song_file, duration

        search = f"{title} {artist} audio"
        temp_dir = tempfile.mkdtemp()

        self.download_active = True
        self.download_progress = 0.0
        self.download_phase = "downloading"

        def progress_hook(data):
            if data["status"] == "downloading":
                total = (
                    data.get("total_bytes")
                    or data.get("total_bytes_estimate", 0)
                )

                if total > 0:
                    self.download_progress = (
                        data["downloaded_bytes"] / total
                    )

            elif data["status"] == "finished":
                self.download_progress = 1.0

        try:
            # Este es el mismo flujo que funcionaba originalmente:
            # yt-dlp descarga a una carpeta temporal y FFmpeg lo convierte
            # a MP3. Usamos entry["id"] para localizar el resultado exacto.
            ydl_opts = {
                "format": "bestaudio/best",
                "quiet": True,
                "outtmpl": os.path.join(
                    temp_dir,
                    "%(id)s.%(ext)s"
                ),
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }],
                "progress_hooks": [progress_hook],
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"ytsearch1:{search}",
                    download=True
                )

                entry = info["entries"][0]

                downloaded_file = os.path.join(
                    temp_dir,
                    entry["id"] + ".mp3"
                )

                duration = entry.get("duration", 180)

            if not os.path.exists(downloaded_file):
                raise RuntimeError(
                    f"yt-dlp no generó el MP3 esperado: {downloaded_file}"
                )

            os.makedirs(os.path.dirname(song_file), exist_ok=True)

            # Copiar el resultado a la caché persistente.
            shutil.copy2(downloaded_file, song_file)

            self.download_progress = 1.0
            self.download_phase = "processing"
            self.download_active = False
            self.download_phase = ""

            return song_file, duration

        except Exception:
            self.download_active = False
            self.download_phase = ""
            raise

        finally:
            # La carpeta temporal solo se usa durante la descarga.
            shutil.rmtree(temp_dir, ignore_errors=True)

    def play_fragment(
        self,
        audio_file,
        start,
        duration
    ):
        # El WAV vive junto al MP3 y se sobrescribe en cada reproducción.
        temp_dir = os.path.dirname(audio_file)
        wav_file = os.path.join(
            temp_dir,
            "fragment.wav"
        )

        result = subprocess.run([
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            audio_file,
            "-t",
            str(duration),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            wav_file
        ], capture_output=True)

        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.decode(errors="ignore")
            )

        pygame.mixer.music.load(wav_file)
        pygame.mixer.music.play()

        try:
            time.sleep(duration)
        finally:
            pygame.mixer.music.unload()

    def cleanup(self):
        # La caché de canciones es persistente. No se elimina al terminar
        # una ronda ni al llamar a cleanup().
        self.temp_files.clear()
