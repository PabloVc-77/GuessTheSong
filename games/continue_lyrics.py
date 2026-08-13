"""Reglas del modo de juego «Continúa la letra»."""

import random
import re
import unicodedata

from audio import AudioPlayer
from lyrics import get_lyrics, parse_lrc

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
        """Evalúa la respuesta recorriendo la letra de izquierda a derecha.

        Reglas:
        - Coincidencia exacta -> verde y +1 punto.
        - Palabra escrita de más -> rojo.
        - Palabra de la letra omitida -> amarillo.
        - Al tercer error consecutivo se termina la evaluación.
        - Todo lo escrito posteriormente se muestra en rojo.
        - Las palabras de la letra que quedan después de terminar la
        respuesta del jugador no se consideran omitidas.
        - Una respuesta completamente correcta recibe el bonus de +5.
        """

        if self.cut_time is None:
            raise RuntimeError("No hay una ronda preparada.")

        submitted_words = self._display_words(answer)
        normalized_words = self._words(answer)

        feedback = []
        correct_words = 0

        answer_index = 0
        submitted_index = 0

        consecutive_errors = 0
        evaluation_finished = False

        ERROR_LIMIT = MAX_CONSECUTIVE_ERRORS + 1

        while (
            answer_index < len(self.answer_words)
            and submitted_index < len(normalized_words)
        ):

            expected = self.answer_words[answer_index]
            submitted = normalized_words[submitted_index]

            # =========================================================
            # 1. PALABRA CORRECTA
            # =========================================================
            if submitted == expected:
                feedback.append({
                    "word": submitted_words[submitted_index],
                    "correct": True,
                    "omitted": False,
                })

                correct_words += 1

                # Una palabra correcta rompe la cadena de errores.
                consecutive_errors = 0

                answer_index += 1
                submitted_index += 1

                continue

            # =========================================================
            # 2. BUSCAR SI LA PALABRA ESPERADA APARECE MUY PRONTO
            #    EN LA RESPUESTA.
            #
            #    Ejemplo:
            #
            #    LETRA:
            #        ... gonna crack
            #
            #    RESPUESTA:
            #        ... I m not gonna crack
            #
            #    "gonna" aparece 3 posiciones más adelante.
            #
            #    Por tanto:
            #        I   -> rojo
            #        m   -> rojo
            #        not -> rojo
            #
            #    y al tercer error terminamos.
            #
            #    Esto evita interpretar "gonna crack" como omitido.
            # =========================================================

            expected_found_ahead = None

            for distance in range(
                1,
                ERROR_LIMIT + 1,
            ):
                index = submitted_index + distance

                if index >= len(normalized_words):
                    break

                if normalized_words[index] == expected:
                    expected_found_ahead = distance
                    break

            if expected_found_ahead is not None:
                # La palabra actual es incorrecta.
                feedback.append({
                    "word": submitted_words[submitted_index],
                    "correct": False,
                    "omitted": False,
                })

                consecutive_errors += 1
                submitted_index += 1

                # Tercer error -> terminamos.
                if consecutive_errors >= ERROR_LIMIT:
                    evaluation_finished = True
                    break

                continue

            # =========================================================
            # 3. BUSCAR SI LA PALABRA ESCRITA APARECE MUY PRONTO
            #    EN LA LETRA.
            #
            #    Ejemplo:
            #
            #    LETRA:
            #        I surrender oh I surrender
            #
            #    RESPUESTA:
            #        I surrender I surrender
            #
            #    Al llegar a "oh":
            #
            #        oh -> amarillo
            #
            #    porque la siguiente palabra escrita ("I") aparece
            #    inmediatamente después en la letra.
            #
            #    También permite hasta dos omisiones consecutivas.
            # =========================================================

            submitted_found_ahead = None

            for distance in range(
                1,
                ERROR_LIMIT + 1,
            ):
                index = answer_index + distance

                if index >= len(self.answer_words):
                    break

                if self.answer_words[index] == submitted:
                    submitted_found_ahead = distance
                    break

            if submitted_found_ahead is not None:
                # La palabra actual de la letra ha sido omitida.
                feedback.append({
                    "word": self.answer_display_words[answer_index],
                    "correct": False,
                    "omitted": True,
                })

                consecutive_errors += 1
                answer_index += 1

                # Tercer error -> terminamos.
                if consecutive_errors >= ERROR_LIMIT:
                    evaluation_finished = True
                    break

                continue

            # =========================================================
            # 4. NO HAY UNA ALINEACIÓN CLARA
            #
            #    Ni la palabra esperada aparece pronto en lo escrito, ni
            #    lo escrito aparece pronto en la letra. Se trata como una
            #    sustitución directa de una palabra por otra en la misma
            #    posición: UN solo error, sin importar si se parecen o
            #    no ("wlking" por "walking", o incluso una palabra
            #    totalmente distinta). Por eso avanzamos los DOS índices
            #    a la vez; si solo avanzáramos el de lo escrito, la
            #    palabra de la letra quedaría pendiente y un caso
            #    posterior podría marcarla también como omitida,
            #    contando el mismo fallo dos veces.
            # =========================================================

            feedback.append({
                "word": submitted_words[submitted_index],
                "correct": False,
                "omitted": False,
            })

            consecutive_errors += 1
            answer_index += 1
            submitted_index += 1

            # Tercer error -> terminamos.
            if consecutive_errors >= ERROR_LIMIT:
                evaluation_finished = True
                break

        # =============================================================
        # 5. SI SE HAN ACABADO LAS PALABRAS DEL JUGADOR
        #
        #    No marcamos como omitidas las palabras restantes de la
        #    letra. El jugador simplemente ha terminado su respuesta.
        # =============================================================

        # =============================================================
        # 6. SI LA EVALUACIÓN TERMINÓ POR EL TERCER ERROR
        #
        #    Todo lo que haya escrito el jugador después es ROJO,
        #    independientemente de si coincide o no con la letra.
        # =============================================================

        if evaluation_finished:
            while submitted_index < len(submitted_words):
                feedback.append({
                    "word": submitted_words[submitted_index],
                    "correct": False,
                    "omitted": False,
                })

                submitted_index += 1

        # =============================================================
        # 7. BONUS DE RESPUESTA PERFECTA
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