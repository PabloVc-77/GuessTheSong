"""Reglas del modo de juego «Continúa la letra»."""

import random
import re
import unicodedata

from audio import AudioPlayer
from lyrics import get_lyrics, parse_lrc

MAX_CONSECUTIVE_ERRORS = 2
PERFECT_BONUS = 5

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

    def prepare_round(self, title, artist, duration):
        """Prepara una ronda y devuelve sus datos, o ``None`` si no es viable.

        El corte coincide con el inicio de una línea de la letra. Esa línea y
        las posteriores forman la continuación correcta.
        """
        raw_lyrics = self.lyrics_provider(title, artist)
        lines = parse_lrc(raw_lyrics) if raw_lyrics else []
        candidates = [
            index for index, line in enumerate(lines[1:], start=1)
            if line["time"] <= duration
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
        self.answer_words = self._words(self.answer_lyrics)
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
        """Evalúa la continuación tolerando un número limitado de errores consecutivos."""

        if self.cut_time is None:
            raise RuntimeError("No hay una ronda preparada.")

        submitted_words = self._display_words(answer)
        normalized_words = self._words(answer)

        feedback = []
        correct_words = 0
        consecutive_errors = 0

        answer_index = 0
        scoring_active = True

        for submitted_index, submitted_word in enumerate(normalized_words):

            # ---------------------------------------------------------
            # Una vez superado el límite de errores, seguimos generando
            # feedback, pero ya no damos más puntos.
            # ---------------------------------------------------------
            if not scoring_active:
                feedback.append({
                    "word": submitted_words[submitted_index],
                    "correct": False,
                })
                continue

            # Si ya hemos llegado al final de la letra
            if answer_index >= len(self.answer_words):
                feedback.append({
                    "word": submitted_words[submitted_index],
                    "correct": False,
                })
                continue

            correct_word = self.answer_words[answer_index]

            # ---------------------------------------------------------
            # 1. Coincidencia directa
            # ---------------------------------------------------------
            if submitted_word == correct_word:
                feedback.append({
                    "word": submitted_words[submitted_index],
                    "correct": True,
                })

                correct_words += 1
                consecutive_errors = 0
                answer_index += 1
                continue

            # ---------------------------------------------------------
            # 2. Buscar si el jugador se ha saltado alguna palabra
            # ---------------------------------------------------------
            found_at = None

            for offset in range(1, MAX_CONSECUTIVE_ERRORS + 1):
                candidate_index = answer_index + offset

                if candidate_index >= len(self.answer_words):
                    break

                if submitted_word == self.answer_words[candidate_index]:
                    found_at = candidate_index
                    break

            if found_at is not None:
                skipped = found_at - answer_index
                consecutive_errors += skipped

                if consecutive_errors > MAX_CONSECUTIVE_ERRORS:
                    feedback.append({
                        "word": submitted_words[submitted_index],
                        "correct": False,
                    })
                    scoring_active = False
                    continue

                # Las palabras omitidas cuentan como errores,
                # pero no forman parte de la respuesta escrita.
                feedback.append({
                    "word": submitted_words[submitted_index],
                    "correct": True,
                })

                correct_words += 1
                consecutive_errors = 0
                answer_index = found_at + 1
                continue

            # ---------------------------------------------------------
            # 3. Palabra incorrecta
            # ---------------------------------------------------------
            feedback.append({
                "word": submitted_words[submitted_index],
                "correct": False,
            })

            consecutive_errors += 1

            if consecutive_errors > MAX_CONSECUTIVE_ERRORS:
                scoring_active = False

        # -------------------------------------------------------------
        # Bonus por respuesta perfecta
        # -------------------------------------------------------------
        perfect = (
            len(normalized_words) == len(self.answer_words)
            and correct_words == len(self.answer_words)
            and consecutive_errors == 0
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
            words.extend(re.findall(r"[a-z0-9]+", normalized))
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
