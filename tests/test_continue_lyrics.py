import unittest

from games.continue_lyrics import ContinueLyricsGame


class FakeAudioPlayer:
    def __init__(self):
        self.calls = []

    def play_fragment(self, audio_file, start, duration):
        self.calls.append((audio_file, start, duration))


LRC = """[00:02.00]An earlier line
[00:10.00]I see trees of green
[00:14.50]Red roses too
[00:19.00]I see them bloom
"""


class ContinueLyricsGameTests(unittest.TestCase):
    def setUp(self):
        self.player = FakeAudioPlayer()
        self.game = ContinueLyricsGame(
            audio_player=self.player,
            lyrics_provider=lambda title, artist: LRC,
            fragment_duration=8,
            random_choice=lambda options: options[0],
        )

    def test_prepare_round_cuts_at_a_lyrics_timestamp(self):
        round_data = self.game.prepare_round("What a Wonderful World", "Louis", 60)

        self.assertEqual(round_data["cut_time"], 10.0)
        self.assertEqual(round_data["audio_start"], 2.0)
        self.assertEqual(round_data["audio_duration"], 8)
        self.assertTrue(round_data["continuation"].startswith("I see trees"))

    def test_prepare_round_returns_none_without_valid_cut(self):
        game = ContinueLyricsGame(
            audio_player=self.player,
            lyrics_provider=lambda title, artist: "[00:02.00]Only line",
        )
        self.assertIsNone(game.prepare_round("Song", "Artist", 60))

    def test_play_fragment_reuses_the_shared_audio_player(self):
        self.game.prepare_round("Song", "Artist", 60)
        self.game.play_fragment("song.mp3")
        self.assertEqual(self.player.calls, [("song.mp3", 2.0, 8)])

    def test_evaluation_stops_at_the_first_wrong_word(self):
        self.game.prepare_round("Song", "Artist", 60)
        result = self.game.evaluate_answer("I see trees of blue red roses too")

        self.assertEqual(result["points"], 4)
        self.assertEqual(result["correct_words"], 4)
        self.assertEqual(
            result["word_feedback"],
            [
                {"word": "I", "correct": True},
                {"word": "see", "correct": True},
                {"word": "trees", "correct": True},
                {"word": "of", "correct": True},
                {"word": "blue", "correct": False},
                {"word": "red", "correct": False},
                {"word": "roses", "correct": False},
                {"word": "too", "correct": False},
            ],
        )

    def test_evaluation_normalizes_accents_and_punctuation(self):
        self.game.prepare_round("Song", "Artist", 60)
        self.game.answer_lyrics = "Canción número uno"
        self.game.answer_words = self.game._words(self.game.answer_lyrics)

        result = self.game.evaluate_answer("cancion, NUMERO uno!")
        self.assertEqual(result["points"], 3)
