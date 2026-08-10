import unittest

from games.guess_song import evaluar_respuesta, respuesta_correcta


class GuessSongScoringTests(unittest.TestCase):
    def test_title_is_worth_two_points(self):
        result = evaluar_respuesta("Mi canción", "Mi canción", "Artista")
        self.assertEqual(result["puntos"], 2)
        self.assertEqual(result["aciertos"], ["🎵 título"])

    def test_artist_is_worth_one_point(self):
        result = evaluar_respuesta("Artista", "Mi canción", "Artista")
        self.assertEqual(result["puntos"], 1)
        self.assertEqual(result["aciertos"], ["👤 artista"])

    def test_title_and_artist_are_worth_four_points(self):
        result = evaluar_respuesta("MI CANCION - artista", "Mi canción", "Artista")
        self.assertEqual(result["puntos"], 4)
        self.assertEqual(result["aciertos"], ["🎵 título", "👤 artista"])

    def test_correct_answer_format(self):
        self.assertEqual(respuesta_correcta("Título", "Artista"), "Título - Artista")
