import os
import tempfile
import subprocess
import time

import pygame
from yt_dlp import YoutubeDL


pygame.mixer.init()


class AudioPlayer:
    def __init__(self):
        self.temp_files = []

        self.download_active = False
        self.download_progress = 0.0
        self.download_phase = ""

    def download_song(self, title, artist):
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

                audio_file = os.path.join(
                    temp_dir,
                    entry["id"] + ".mp3"
                )

                duration = entry.get("duration", 180)

            self.temp_files.append(audio_file)
            self.download_phase = "processing"
            self.download_active = False
            self.download_phase = ""

            return audio_file, duration

        except Exception:
            self.download_active = False
            self.download_phase = ""
            raise

    def play_fragment(
        self,
        audio_file,
        start,
        duration
    ):
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

        self.temp_files.append(wav_file)
        pygame.mixer.music.load(wav_file)
        pygame.mixer.music.play()

        try:
            time.sleep(duration)
        finally:
            pygame.mixer.music.unload()

    def cleanup(self):
        for path in self.temp_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

        self.temp_files.clear()
