import unittest
from unittest.mock import patch

import lyrics


class LyricsTests(unittest.TestCase):
    def test_cache_filename_uses_artist_and_title(self):
        path = lyrics._cache_filename("A Song?", "An/Artist")
        self.assertEqual(path.name, "An_Artist - A Song_.lrc")

    def test_parse_lrc_reads_and_orders_timestamps(self):
        parsed = lyrics.parse_lrc(
            "[ar:Artist]\n[00:20.50]Second line\n"
            "[00:03.25][00:10:75]First line\n[00:30.00]"
        )

        self.assertEqual(parsed, [
            {"time": 3.25, "text": "First line"},
            {"time": 10.75, "text": "First line"},
            {"time": 20.5, "text": "Second line"},
        ])

    def test_get_lyrics_uses_cache_without_download(self):
        with (
            patch.object(lyrics, "get_cached_lyrics", return_value="[00:01.00]Cached"),
            patch.object(lyrics, "_download_lyrics") as download,
        ):
            result = lyrics.get_lyrics("Song", "Artist")

        self.assertEqual(result, "[00:01.00]Cached")
        download.assert_not_called()

    def test_get_lyrics_downloads_valid_lrc_and_caches_it(self):
        text = "[00:01.50]Downloaded line"
        with (
            patch.object(lyrics, "get_cached_lyrics", return_value=None),
            patch.object(lyrics, "_download_lyrics", return_value=text) as download,
            patch.object(lyrics, "save_lyrics") as save,
        ):
            result = lyrics.get_lyrics("Song", "Artist")

        self.assertEqual(result, text)
        download.assert_called_once_with("Song", "Artist")
        save.assert_called_once_with("Song", "Artist", text)

    def test_get_lyrics_rejects_unsynchronised_text(self):
        with (
            patch.object(lyrics, "get_cached_lyrics", return_value=None),
            patch.object(lyrics, "_download_lyrics", return_value="Plain lyrics"),
            patch.object(lyrics, "save_lyrics") as save,
        ):
            result = lyrics.get_lyrics("Song", "Artist")

        self.assertIsNone(result)
        save.assert_not_called()
