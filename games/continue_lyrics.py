"""Reglas del modo de juego «Continúa la letra»."""

import random
import re
import unicodedata

from audio import AudioPlayer
from lyrics import get_lyrics, parse_lrc
from lyrics_scorer import LyricsScorer

MAX_CONSECUTIVE_ERRORS = 2
PERFECT_BONUS = 5
MIN_MATCHING_ANCHOR = 0
# No escoger cortes demasiado cerca del final de la canción.
MIN_REMAINING_AFTER_CUT = 10

class ContinueLyricsGame:
    """Prepara y evalúa rondas a partir de letras LRC sincronizadas."""

    def __init__(self, audio_player=None, lyrics_provider=get_lyrics,
                 fragment_duration=8, random_choice=None):
        self.audio_player = audio_player or AudioPlayer()
        self.lyrics_provider = lyrics_provider
        self.fragment_duration = fragment_duration
        self.random_choice = random_choice or random.choice
        self.lyrics = []
        self.cut_time = None
        self.audio_start = None
        self.audio_duration = None
        self.answer_lyrics = ""
        self.last_played_line = ""
        self.answer_words = []
        self.answer_display_words = []
        self._scorer = None

    def prepare_round(self, title, artist, duration):
        """Prepara una ronda y devuelve sus datos, o ``None`` si no es viable.

        El corte coincide con el inicio de una línea de la letra. Esa línea y
        las posteriores forman la continuación correcta.
        """
        raw_lyrics = self.lyrics_provider(title, artist)
        lines = parse_lrc(raw_lyrics) if raw_lyrics else []

        latest_allowed_cut = duration - MIN_REMAINING_AFTER_CUT
        candidates = [
            index for index, line in enumerate(lines[1:], start=1)
            if line["time"] <= latest_allowed_cut
        ]
        if not candidates:
            return None

        selected_index = self.random_choice(candidates)
        selected_line = lines[selected_index]
        self.lyrics = lines
        self.cut_time = selected_line["time"]
        self.audio_duration = min(self.fragment_duration, self.cut_time)
        self.audio_start = self.cut_time - self.audio_duration

        self.answer_lyrics = "\n".join(
            line["text"] for line in lines[selected_index:]
        )

        self.answer_display_words = self._display_words(self.answer_lyrics)
        self.answer_words = self._words(self.answer_lyrics)

        self._scorer = LyricsScorer(
            answer_words=self.answer_words,
            max_consecutive_errors=MAX_CONSECUTIVE_ERRORS,
            answer_display_words=self.answer_display_words,
        )

        if selected_index > 0:
            self.last_played_line = lines[selected_index - 1]["text"]
        else:
            self.last_played_line = ""

        return {
            "title": title,
            "artist": artist,
            "cut_time": self.cut_time,
            "audio_start": self.audio_start,
            "audio_duration": self.audio_duration,
            "continuation": self.answer_lyrics,
        }

    def play_fragment(self, audio_file):
        """Reproduce el fragmento preparado con la infraestructura común."""
        if self.audio_start is None or self.audio_duration is None:
            raise RuntimeError("Primero hay que preparar una ronda.")
        self.audio_player.play_fragment(
            audio_file,
            self.audio_start,
            self.audio_duration,
        )

    def evaluate_answer(self, answer):
        """Evalúa la respuesta buscando la alineación que maximiza la
        puntuación del jugador (no una simple comparación izquierda a
        derecha ni una heurística de ventana fija).

        Reglas:
        - Coincidencia exacta -> verde y +1 punto.
        - Palabra escrita de más -> rojo.
        - Palabra de la letra omitida -> amarillo.
        - Sustitución/typo -> amarillo (palabra correcta) seguido de
          naranja (lo escrito), como un único error.
        - Al tercer error consecutivo se termina la evaluación.
        - Todo lo escrito posteriormente se muestra en rojo.
        - Las palabras de la letra que quedan después de terminar la
        respuesta del jugador no se consideran omitidas.
        - Una respuesta completamente correcta recibe el bonus de +5.

        La alineación en sí (qué es acierto, qué es typo, qué se omite y
        qué sobra) la resuelve ``LyricsScorer``, que prueba todas las
        interpretaciones válidas y se queda con la de mayor puntuación,
        en vez de asumir que la primera alineación aparente es la mejor.
        """

        if self.cut_time is None:
            raise RuntimeError("No hay una ronda preparada.")

        submitted_words = self._display_words(answer)
        normalized_words = self._words(answer)

        result = self._scorer.score(
            normalized_words, submitted_display_words=submitted_words
        )

        feedback = result.feedback
        correct_words = result.score
        evaluation_finished = result.broken

        # =============================================================
        # BONUS DE RESPUESTA PERFECTA
        #
        #    Una respuesta puede ser un prefijo correcto de la letra.
        #    Las palabras restantes de la letra NO cuentan como omitidas.
        # =============================================================

        perfect = (
            len(normalized_words) > 0
            and not evaluation_finished
            and correct_words == len(normalized_words)
            and all(
                item["correct"]
                for item in feedback
                if not item.get("omitted", False)
            )
            and not any(
                item.get("omitted", False)
                for item in feedback
            )
        )

        bonus = PERFECT_BONUS if perfect else 0

        return {
            "points": correct_words + bonus,
            "correct_words": correct_words,
            "bonus": bonus,
            "perfect": perfect,
            "answer": answer,
            "word_feedback": feedback,
        }

    @staticmethod
    def _words(text):
        words = []

        for word in ContinueLyricsGame._display_words(text):
            normalized = unicodedata.normalize("NFD", word.lower())
            normalized = normalized.encode("ascii", "ignore").decode("ascii")
            normalized = re.sub(r"[^a-z0-9]", "", normalized)

            if normalized:
                words.append(normalized)

        return words

    @staticmethod
    def _display_words(text):
        return re.findall(r"[^\W_]+", text, flags=re.UNICODE)

    def count_words(self, text):
        """Cuenta las palabras de una respuesta usando las mismas reglas del juego."""
        return len(self._display_words(text))

    def get_answer_prefix(self, word_count):
        """Devuelve las primeras ``word_count`` palabras de la continuación correcta."""
        if word_count <= 0:
            return ""

        words = self._display_words(self.answer_lyrics)
        return " ".join(words[:word_count])