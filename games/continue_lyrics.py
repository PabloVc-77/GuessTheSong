"""Reglas del modo de juego «Continúa la letra»."""

import random
import re
import unicodedata

from audio import AudioPlayer
from lyrics import get_lyrics, parse_lrc
from difflib import SequenceMatcher

MAX_CONSECUTIVE_ERRORS = 2
PERFECT_BONUS = 5
MIN_MATCHING_ANCHOR = 0

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

        self.answer_display_words = self._display_words(self.answer_lyrics)
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
        """Evalúa una respuesta permitiendo hasta dos errores consecutivos.

        Al alcanzar el tercer error consecutivo, la evaluación termina:
        el tercer error se muestra con su tipo correspondiente y todas las
        palabras escritas posteriormente por el jugador se muestran en rojo,
        sin volver a comprobar si coinciden con la letra.
        """

        if self.cut_time is None:
            raise RuntimeError("No hay una ronda preparada.")

        submitted_words = self._display_words(answer)
        normalized_words = self._words(answer)

        matcher = SequenceMatcher(
            None,
            self.answer_words,
            normalized_words,
            autojunk=False,
        )

        # ---------------------------------------------------------
        # Validar que la respuesta realmente está alineada con
        # el comienzo de la letra.
        # ---------------------------------------------------------

        if len(normalized_words) == 1:
            valid_alignment = (
                normalized_words[0] == self.answer_words[0]
            )

        else:
            matching_blocks = matcher.get_matching_blocks()

            valid_alignment = False

            for answer_start, submitted_start, size in matching_blocks:
                if size < MIN_MATCHING_ANCHOR:
                    continue

                if submitted_start < MAX_CONSECUTIVE_ERRORS:
                    valid_alignment = True
                    break

        # Si no existe una alineación válida, toda la respuesta
        # se considera incorrecta.
        if not valid_alignment:
            return {
                "points": 0,
                "correct_words": 0,
                "bonus": 0,
                "perfect": False,
                "answer": answer,
                "word_feedback": [
                    {
                        "word": word,
                        "correct": False,
                        "omitted": False,
                    }
                    for word in submitted_words
                ],
            }

        feedback = []
        correct_words = 0
        consecutive_errors = 0
        evaluation_finished = False

        # Procesamos los bloques de SequenceMatcher, pero una vez que
        # llegamos al tercer error consecutivo la evaluación queda
        # definitivamente terminada.
        opcodes = matcher.get_opcodes()
        finished_submitted_index = 0

        for _, (
            tag,
            answer_start,
            answer_end,
            submitted_start,
            submitted_end,
        ) in enumerate(opcodes):

            finished_submitted_index = max(finished_submitted_index, submitted_end)

            # ---------------------------------------------------------
            # Una vez terminada la tarea:
            # lo que el jugador haya escrito posteriormente es rojo.
            # No se comprueba si coincide con la letra.
            # ---------------------------------------------------------
            if evaluation_finished:
                for i in range(submitted_start, submitted_end):
                    feedback.append({
                        "word": submitted_words[i],
                        "correct": False,
                        "omitted": False,
                    })
                continue

            # ---------------------------------------------------------
            # Palabras que coinciden exactamente
            # ---------------------------------------------------------
            if tag == "equal":
                for i in range(submitted_start, submitted_end):
                    feedback.append({
                        "word": submitted_words[i],
                        "correct": True,
                        "omitted": False,
                    })
                    correct_words += 1

                # Una coincidencia correcta rompe la cadena de errores.
                consecutive_errors = 0

            # ---------------------------------------------------------
            # Palabras que aparecen en la letra pero el jugador no
            # escribió -> AMARILLO
            # ---------------------------------------------------------
            elif tag == "delete":
                # Una eliminación al final de la respuesta no es una
                # omisión del jugador: simplemente ha terminado su respuesta.
                # SequenceMatcher la genera porque answer_words contiene
                # toda la continuación de la letra.
                #
                # Ejemplo:
                #   letra:     "we are young tonight"
                #   respuesta: "we are young"
                #
                # "tonight" no debe mostrarse como omitido ni impedir
                # el bonus de respuesta perfecta.

                for i in range(answer_start, answer_end):
                    feedback.append({
                        "word": self.answer_display_words[i],
                        "correct": False,
                        "omitted": True,
                    })

                    consecutive_errors += 1

                    # La tercera omisión es válida y se muestra amarilla,
                    # pero a partir de aquí la tarea queda terminada.
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS + 1:
                        evaluation_finished = True
                        for j in range(i + 1, submitted_end):
                            feedback.append({
                                "word": submitted_words[j],
                                "correct": False,
                                "omitted": False,
                            })
                        break

                if evaluation_finished:
                    continue

            # ---------------------------------------------------------
            # Palabras que el jugador escribió pero no aparecen en
            # este punto de la letra -> ROJO
            # ---------------------------------------------------------
            elif tag == "insert":
                for i in range(submitted_start, submitted_end):
                    feedback.append({
                        "word": submitted_words[i],
                        "correct": False,
                        "omitted": False,
                    })

                    consecutive_errors += 1

                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS + 1:
                        evaluation_finished = True
                        for j in range(i + 1, submitted_end):
                            feedback.append({
                                "word": submitted_words[j],
                                "correct": False,
                                "omitted": False,
                            })
                        break

                if evaluation_finished:
                    continue

            # ---------------------------------------------------------
            # Sustitución:
            #
            #   delete -> palabras omitidas (AMARILLO)
            #   insert -> palabras escritas incorrectamente (ROJO)
            # ---------------------------------------------------------
            elif tag == "replace":
                # Procesamos primero las palabras omitidas.
                auxiliary_consecutive_errors = consecutive_errors
                for i in range(answer_start, answer_end):
                    feedback.append({
                        "word": self.answer_display_words[i],
                        "correct": False,
                        "omitted": True,
                    })

                    consecutive_errors += 1

                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS + 1:
                        evaluation_finished = True
                        # Indicar que las palabras escritas incorrectamente también son rojas.
                        for i in range(submitted_start, submitted_end):
                            feedback.append({
                                "word": submitted_words[i],
                                "correct": False,
                                "omitted": False,
                            })
                        break

                if evaluation_finished:
                    continue

                # Después procesamos las palabras escritas incorrectamente.
                for i in range(submitted_start, submitted_end):
                    feedback.append({
                        "word": submitted_words[i],
                        "correct": False,
                        "omitted": False,
                    })

                    auxiliary_consecutive_errors += 1

                    if auxiliary_consecutive_errors >= MAX_CONSECUTIVE_ERRORS + 1:
                        evaluation_finished = True
                        break

                consecutive_errors = max(consecutive_errors, auxiliary_consecutive_errors)

            if submitted_end >= len(submitted_words):
                evaluation_finished = True
                break

        # -------------------------------------------------------------
        # Si la evaluación terminó dentro de un bloque y todavía quedan
        # palabras del jugador que no han sido visitadas por los opcodes,
        # también deben aparecer en rojo.
        # -------------------------------------------------------------
        for i in range(finished_submitted_index, len(submitted_words)):
            feedback.append({
                "word": submitted_words[i],
                "correct": False,
                "omitted": False,
            })

        # -------------------------------------------------------------
        # Bonus por respuesta perfecta
        # -------------------------------------------------------------
        perfect = (
            len(normalized_words) > 0
            and correct_words == len(normalized_words)
            and not any(item.get("omitted", False) for item in feedback)
            and all(
                item["correct"]
                for item in feedback
                if not item.get("omitted", False)
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