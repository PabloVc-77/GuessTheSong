import socket
import sys
from pathlib import Path

import threading
import time
import random
from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit

from audio import AudioPlayer
from games.continue_lyrics import ContinueLyricsGame
from games.guess_song import evaluar_respuesta, respuesta_correcta


jugadores_conectados = {}        # sid → nombre
puntuaciones = {}                # nombre → puntos
respuestas = {}                  # nombre → respuesta
respuesta_actual = {"titulo": "", "artista": "", "completa": ""}
pedidores_30s = set()            # nombres que pidieron más tiempo
plus_30s_usado = False           # +30s ya concedido en esta ronda
partida_terminada = False
temporizador_activo = False
tiempo_restante = 0
panel_ranking_texto = ""
panel_ranking_data = []          # [(nombre, pts), ...] ordenado, persiste tras reset()
panel_reveal = None              # {correcta, respuestas: [(nombre, texto, pts_ronda), ...]} tras evaluar
audio_player = AudioPlayer()
continue_lyrics_game = ContinueLyricsGame(audio_player=audio_player)
game_mode = "guess_song"
ronda_en_progreso = False


# ---------- RUTAS DE LA APLICACIÓN ----------

def get_app_dir():
    """
    Directorio donde se encuentra el ejecutable cuando la aplicación
    está empaquetada, o el directorio del proyecto durante el desarrollo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def get_resource_dir():
    """
    Directorio de recursos empaquetados por PyInstaller.

    En PyInstaller moderno (onedir), los recursos internos se encuentran
    dentro de _internal. Durante el desarrollo coinciden con APP_DIR.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)

    return Path(__file__).resolve().parent


APP_DIR = get_app_dir()
RESOURCE_DIR = get_resource_dir()

# Recursos externos/modificables
DATA_DIR = APP_DIR / "data"
LISTA = DATA_DIR / "Olaf.txt"
CACHE_DIR = APP_DIR / "Cache" / "Songs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ---------- PARAMETROS ----------

USAR_CACHE = False
T_FRAGMENT = 5
T_RESP = 45
ROUNDS = 10
MAX_LYRIC_ATTEMPTS = 5
GRACIA_ENVIO_FINAL = 2.0


# ---------- ESTADO ----------

cancion_actual = 0
ronda_actual = 1


# ---------- Flask / SocketIO ----------

app = Flask(
    __name__,
    template_folder=str(RESOURCE_DIR / "templates"),
    static_folder=str(RESOURCE_DIR / "static"),
)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading",
)


# ---------- Funciones auxiliares ----------

def obtener_ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "localhost"
    finally:
        s.close()

    return ip


def obtener_listas():
    """Devuelve las listas .txt disponibles en data."""
    if not DATA_DIR.exists():
        return []

    return sorted(
        archivo for archivo in DATA_DIR.glob("*.txt")
        if archivo.is_file()
    )


def crear_lista(nombre, contenido):
    """Crea una nueva playlist .txt dentro de data."""

    if ronda_en_progreso:
        return False, "No se puede crear una playlist durante una ronda."

    nombre = nombre.strip()

    if not nombre:
        return False, "El nombre de la playlist no puede estar vacío."

    nombre_archivo = Path(nombre).name

    if nombre_archivo != nombre:
        return False, "El nombre de la playlist no es válido."

    if not nombre.lower().endswith(".txt"):
        nombre_archivo += ".txt"

    lista = DATA_DIR / nombre_archivo

    if lista.exists():
        return False, "Ya existe una playlist con ese nombre."

    canciones = []

    for linea in contenido.splitlines():
        linea = linea.strip()

        if not linea:
            continue

        if " - " not in linea:
            continue

        titulo, artista = linea.split(" - ", 1)

        titulo = titulo.strip()
        artista = artista.strip()

        if not titulo or not artista:
            continue

        canciones.append(f"{titulo} - {artista}")

    if not canciones:
        return False, "No se ha encontrado ninguna canción válida."

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(lista, "w", encoding="utf-8") as f:
        f.write("\n".join(canciones) + "\n")

    print(f"Playlist creada: {lista.name} ({len(canciones)} canciones)")

    return True, {
        "nombre": lista.stem,
        "archivo": lista.name,
        "canciones": len(canciones),
    }


def elegir_cancion():
    if USAR_CACHE:
        if not CACHE_DIR.exists():
            raise ValueError("La carpeta de caché no existe.")

        canciones = []

        for carpeta in CACHE_DIR.iterdir():
            if not carpeta.is_dir():
                continue

            archivo_mp3 = carpeta / f"{carpeta.name}.mp3"

            if not archivo_mp3.exists():
                continue

            if " - " not in carpeta.name:
                continue

            artista, titulo = carpeta.name.split(" - ", 1)
            canciones.append((titulo.strip(), artista.strip()))

        if not canciones:
            raise ValueError("No hay canciones disponibles en la caché.")

        return random.choice(canciones)

    if not LISTA.exists():
        raise FileNotFoundError(
            f"No existe la lista de canciones: {LISTA}"
        )

    with open(LISTA, encoding="utf-8") as f:
        canciones = [
            line.strip()
            for line in f
            if " - " in line
        ]

    if not canciones:
        raise ValueError(
            f"La lista está vacía o no tiene un formato válido: {LISTA}"
        )

    seleccionada = random.choice(canciones)

    titulo, artista = [
        s.strip()
        for s in seleccionada.split(" - ", 1)
    ]

    return titulo, artista


def descargar_y_reproducir(titulo, artista):
    try:
        archivo, duracion = audio_player.download_song(
            titulo,
            artista
        )

        max_inicio = max(
            0,
            int(duracion - T_FRAGMENT - 5)
        )

        inicio = random.randint(0, max_inicio)

        audio_player.play_fragment(
            archivo,
            inicio,
            T_FRAGMENT
        )

        return True

    except Exception as e:
        print("Error al reproducir:", e)
        return False


def emit_a_todos(event, data):
    sids = list(jugadores_conectados.keys())

    print(
        f"emit({event!r}) -> "
        f"{len(sids)} jugadores: {sids}"
    )

    for sid in sids:
        socketio.emit(
            event,
            data,
            to=sid,
            namespace="/"
        )


def anadir_30s_extra():
    global tiempo_restante, plus_30s_usado

    if plus_30s_usado:
        return

    plus_30s_usado = True
    tiempo_restante += 30

    emit_a_todos(
        "estado",
        "🕒 Todos solicitaron +30s. Tiempo añadido."
    )


# ---------- Evaluación ----------

def evaluar_respuestas():
    resumen = []
    revelacion = []

    for sid, nombre in jugadores_conectados.items():
        if nombre == "host":
            continue

        respuesta = respuestas.get(nombre, "")

        if game_mode == "continue_lyrics":
            evaluacion = continue_lyrics_game.evaluate_answer(
                respuesta
            )

            puntos = evaluacion["points"]
            resultado = evaluacion

        else:
            evaluacion = evaluar_respuesta(
                respuesta,
                respuesta_actual["titulo"],
                respuesta_actual["artista"],
            )

            puntos = evaluacion["puntos"]
            aciertos = evaluacion["aciertos"]

            resultado = (
                f"{'✅' if puntos else '❌'} "
                f"{nombre}: +{puntos} puntos "
                f"({', '.join(aciertos) or 'ninguno'})\n"
            )

            resultado += (
                "La respuesta correcta era: "
                f"{respuesta_actual['completa']}"
            )

        puntuaciones[nombre] += puntos

        socketio.emit(
            "resultado",
            resultado,
            to=sid
        )

        resumen.append(
            f"{nombre}: {puntuaciones[nombre]} pts"
        )

        revelacion.append({
            "nombre": nombre,
            "texto": respuesta or "(sin respuesta)",
            "puntos": puntos,
            "feedback": (
                evaluacion["word_feedback"]
                if game_mode == "continue_lyrics"
                else None
            ),
        })

    global panel_ranking_texto
    global panel_ranking_data
    global panel_reveal

    sorted_pts = sorted(
        [
            (n, puntuaciones[n])
            for n in puntuaciones
            if n != "host"
        ],
        key=lambda x: x[1],
        reverse=True
    )

    panel_ranking_texto = (
        "📊 Clasificación:\n"
        + "\n".join(
            f"{i+1}. {n}: {p} pts"
            for i, (n, p) in enumerate(sorted_pts)
        )
    )

    panel_ranking_data = sorted_pts

    orden = {
        n: i
        for i, (n, _) in enumerate(sorted_pts)
    }

    revelacion.sort(
        key=lambda item: orden.get(
            item["nombre"],
            999
        )
    )

    if game_mode == "continue_lyrics":
        max_words = max(
            (
                continue_lyrics_game.count_words(
                    respuesta
                )
                for respuesta in respuestas.values()
            ),
            default=0,
        )

        correcta = (
            continue_lyrics_game.get_answer_prefix(
                max_words
            )
        )

    else:
        correcta = respuesta_actual["completa"]

    panel_reveal = {
        "correcta": correcta,
        "respuestas": revelacion,
    }


# ---------- Temporizador ----------

def iniciar_ronda(intentos=0):
    global respuestas
    global temporizador_activo
    global panel_reveal
    global ronda_en_progreso

    respuestas = {}
    temporizador_activo = False
    panel_reveal = None
    ronda_en_progreso = True

    titulo, artista = elegir_cancion()

    emit_a_todos(
        "estado",
        "🎵 Preparando fragmento de audio..."
    )

    def reproduccion_y_luego():
        if game_mode == "continue_lyrics":
            try:
                archivo, duracion = audio_player.download_song(
                    titulo,
                    artista
                )

                round_data = (
                    continue_lyrics_game.prepare_round(
                        titulo,
                        artista,
                        duracion
                    )
                )

                if round_data is None:
                    raise ValueError(
                        "No hay letra sincronizada válida"
                    )

                respuesta_actual["titulo"] = titulo
                respuesta_actual["artista"] = artista
                respuesta_actual["completa"] = (
                    round_data["continuation"]
                )

                emit_a_todos(
                    "nueva_ronda_letra",
                    {
                        "titulo": titulo,
                        "artista": artista,
                        "cut_time": round_data["cut_time"],
                    }
                )

                continue_lyrics_game.play_fragment(
                    archivo
                )

            except Exception as error:
                print(
                    "Error al preparar letras:",
                    error
                )

                if intentos + 1 < MAX_LYRIC_ATTEMPTS:
                    iniciar_ronda(intentos + 1)
                else:
                    ronda_fallida(
                        "No se encontraron canciones "
                        "con letra sincronizada."
                    )

                return

        else:
            respuesta_actual["titulo"] = titulo
            respuesta_actual["artista"] = artista
            respuesta_actual["completa"] = (
                respuesta_correcta(
                    titulo,
                    artista
                )
            )

            if not descargar_y_reproducir(
                titulo,
                artista
            ):
                ronda_fallida(
                    "No se pudo preparar el audio "
                    "de la canción."
                )
                return

        iniciar_temporizador()

    threading.Thread(
        target=reproduccion_y_luego,
        daemon=True
    ).start()


def ronda_fallida(message):
    global ronda_en_progreso
    global temporizador_activo

    ronda_en_progreso = False
    temporizador_activo = False

    emit_a_todos(
        "estado",
        f"⚠️ {message}"
    )


def iniciar_temporizador():
    global temporizador_activo
    global tiempo_restante
    global pedidores_30s
    global plus_30s_usado

    temporizador_activo = True
    tiempo_restante = T_RESP

    pedidores_30s.clear()
    plus_30s_usado = False

    emit_a_todos(
        "nueva_ronda_jugador",
        {}
    )

    emit_a_todos(
        "estado",
        "🎵 ¡Responde ahora! Tienes "
        + str(T_RESP)
        + " segundos..."
    )

    def cuenta_atras():
        global temporizador_activo
        global tiempo_restante
        global ronda_en_progreso

        while tiempo_restante > 0:
            emit_a_todos(
                "temporizador",
                tiempo_restante
            )

            time.sleep(1)
            tiempo_restante -= 1

        emit_a_todos(
            "temporizador",
            0
        )

        emit_a_todos(
            "tiempo_agotado",
            {}
        )

        emit_a_todos(
            "estado",
            "⏰ ¡Tiempo terminado! "
            "Recogiendo últimas respuestas..."
        )

        total_jugadores = len([
            n
            for n in puntuaciones
            if n != "host"
        ])

        pasos = max(
            1,
            int(GRACIA_ENVIO_FINAL / 0.2)
        )

        for _ in range(pasos):
            if (
                total_jugadores
                and len(respuestas) >= total_jugadores
            ):
                break

            time.sleep(0.2)

        emit_a_todos(
            "estado",
            "⏰ ¡Tiempo terminado!"
        )

        temporizador_activo = False
        ronda_en_progreso = False

        evaluar_respuestas()

    socketio.start_background_task(
        cuenta_atras
    )


def reset():
    for n in puntuaciones:
        if n != "host":
            puntuaciones[n] = 0

    for sid in jugadores_conectados:
        socketio.emit(
            "mostrar_popup_ronda",
            (
                f"Ronda {ronda_actual - 1} terminada. "
                f"¡Prepárate para la ronda {ronda_actual}!"
            ),
            to=sid
        )


def reset_all():
    global jugadores_conectados
    global puntuaciones
    global respuestas
    global respuesta_actual
    global pedidores_30s
    global plus_30s_usado
    global partida_terminada
    global temporizador_activo
    global tiempo_restante
    global cancion_actual
    global ronda_actual
    global panel_reveal
    global ronda_en_progreso

    respuestas = {}

    respuesta_actual = {
        "titulo": "",
        "artista": "",
        "completa": ""
    }

    pedidores_30s.clear()
    plus_30s_usado = False
    panel_reveal = None

    temporizador_activo = False
    ronda_en_progreso = False
    tiempo_restante = 0

    partida_terminada = False
    cancion_actual = 0
    ronda_actual = 1

    for n in puntuaciones:
        if n != "host":
            puntuaciones[n] = 0

    audio_player.cleanup()

    print("Juego reseteado completamente.")


# ---------- Acciones del host ----------

def action_nueva_ronda():
    global cancion_actual
    global ronda_actual

    cancion_actual += 1

    if cancion_actual > ROUNDS:
        cancion_actual = 0
        ronda_actual += 1

        emit_a_todos(
            "estado",
            (
                f"🎯 ¡Ronda {ronda_actual - 1} terminada! "
                "Se reinician los puntos."
            )
        )

        print(
            f"Ronda {ronda_actual - 1} terminada, "
            "reiniciando puntuaciones..."
        )

        reset()
        return

    print(
        f"Canción {cancion_actual}/{ROUNDS} "
        f"de la ronda {ronda_actual}"
    )

    emit_a_todos(
        "estado",
        (
            f"🎵 Ronda {ronda_actual}, "
            f"canción {cancion_actual}/{ROUNDS}"
        )
    )

    iniciar_ronda()


def action_cambiar_lista(nombre_lista):
    global LISTA
    global USAR_CACHE

    if ronda_en_progreso:
        print(
            "No se puede cambiar la lista durante una ronda."
        )
        return False

    if nombre_lista == "__CACHE__":
        USAR_CACHE = True

        print(
            "Fuente seleccionada: canciones en caché"
        )

        emit_a_todos(
            "estado",
            "🎧 Fuente seleccionada: "
            "canciones en caché"
        )

        return True

    lista = DATA_DIR / nombre_lista

    if lista.parent.resolve() != DATA_DIR.resolve():
        print("Lista no válida.")
        return False

    if (
        not lista.is_file()
        or lista.suffix.lower() != ".txt"
    ):
        print(
            f"Lista no válida: {nombre_lista}"
        )
        return False

    LISTA = lista
    USAR_CACHE = False

    print(
        f"Lista seleccionada: {LISTA.name}"
    )

    emit_a_todos(
        "estado",
        f"📋 Lista seleccionada: {LISTA.stem}"
    )

    return True


def action_crear_lista(nombre, contenido):
    """Crea una playlist y la selecciona automáticamente."""

    resultado = crear_lista(
        nombre,
        contenido
    )

    if not resultado[0]:
        return resultado

    datos = resultado[1]

    lista = DATA_DIR / datos["archivo"]

    global LISTA
    global USAR_CACHE

    LISTA = lista
    USAR_CACHE = False

    print(
        f"Playlist creada y seleccionada: "
        f"{LISTA.name}"
    )

    emit_a_todos(
        "estado",
        (
            f"📋 Playlist creada: {LISTA.stem} "
            f"({datos['canciones']} canciones)"
        )
    )

    return True, datos


def action_eliminar_lista(nombre_lista):
    """Elimina una playlist .txt de data."""

    global LISTA
    global USAR_CACHE

    if ronda_en_progreso:
        return (
            False,
            "No se puede eliminar una playlist "
            "durante una ronda."
        )

    if (
        not nombre_lista
        or nombre_lista in {
            "__CACHE__",
            "__CREATE__",
            "__DELETE__"
        }
    ):
        return (
            False,
            "No se puede eliminar esta opción."
        )

    lista = DATA_DIR / nombre_lista

    if lista.parent.resolve() != DATA_DIR.resolve():
        return False, "Lista no válida."

    if (
        not lista.is_file()
        or lista.suffix.lower() != ".txt"
    ):
        return False, "Lista no válida."

    if lista.resolve() == LISTA.resolve():
        return (
            False,
            "No puedes eliminar la playlist "
            "que está seleccionada."
        )

    try:
        lista.unlink()
    except OSError as e:
        print(
            f"Error eliminando playlist: {e}"
        )

        return (
            False,
            "No se pudo eliminar la playlist."
        )

    print(
        f"Playlist eliminada: {lista.name}"
    )

    emit_a_todos(
        "estado",
        f"🗑️ Playlist eliminada: {lista.stem}"
    )

    return True, lista.stem


def action_editar_lista(
    nombre_lista,
    nuevo_nombre,
    contenido
):
    """Edita una playlist existente."""

    global LISTA
    global USAR_CACHE

    if ronda_en_progreso:
        return (
            False,
            "No se puede editar una playlist "
            "durante una ronda."
        )

    if (
        not nombre_lista
        or not nuevo_nombre.strip()
    ):
        return (
            False,
            "El nombre de la playlist "
            "no puede estar vacío."
        )

    lista = DATA_DIR / nombre_lista

    if lista.parent.resolve() != DATA_DIR.resolve():
        return False, "Lista no válida."

    if (
        not lista.is_file()
        or lista.suffix.lower() != ".txt"
    ):
        return False, "Lista no válida."

    nuevo_nombre = Path(
        nuevo_nombre.strip()
    ).name

    if not nuevo_nombre.lower().endswith(".txt"):
        nuevo_nombre += ".txt"

    nueva_lista = DATA_DIR / nuevo_nombre

    if (
        nueva_lista.resolve() != lista.resolve()
        and nueva_lista.exists()
    ):
        return (
            False,
            "Ya existe una playlist con ese nombre."
        )

    canciones = []

    for linea in contenido.splitlines():
        linea = linea.strip()

        if not linea:
            continue

        if " - " not in linea:
            continue

        titulo, artista = linea.split(
            " - ",
            1
        )

        titulo = titulo.strip()
        artista = artista.strip()

        if titulo and artista:
            canciones.append(
                f"{titulo} - {artista}"
            )

    if not canciones:
        return (
            False,
            "No se ha encontrado ninguna "
            "canción válida."
        )

    with open(
        nueva_lista,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(
            "\n".join(canciones)
            + "\n"
        )

    if nueva_lista.resolve() != lista.resolve():
        lista.unlink()

    LISTA = nueva_lista
    USAR_CACHE = False

    emit_a_todos(
        "estado",
        f"✏️ Playlist editada: {nueva_lista.stem}"
    )

    return True, {
        "nombre": nueva_lista.stem,
        "archivo": nueva_lista.name,
        "canciones": len(canciones),
    }


def action_cambiar_modo(mode):
    global game_mode

    if mode not in {
        "guess_song",
        "continue_lyrics"
    }:
        return False

    if ronda_en_progreso:
        print(
            "No se puede cambiar de modo "
            "durante una ronda."
        )
        return False

    game_mode = mode

    mode_name = (
        "Adivina la canción"
        if mode == "guess_song"
        else "Continúa la letra"
    )

    print(
        f"Modo seleccionado: {mode_name}"
    )

    emit_a_todos(
        "modo_juego",
        mode
    )

    return True


def action_terminar_partida():
    global partida_terminada
    global cancion_actual
    global ronda_actual
    global panel_ranking_texto
    global panel_ranking_data
    global panel_reveal
    global ronda_en_progreso

    partida_terminada = True
    ronda_en_progreso = False

    ranking = [
        (n, p)
        for n, p in sorted(
            puntuaciones.items(),
            key=lambda x: x[1],
            reverse=True
        )
        if n != "host"
    ]

    texto = (
        "\n🏆 Ranking final:\n"
        + "\n".join(
            f"{i+1}. {n}: {p} pts"
            for i, (n, p) in enumerate(ranking)
        )
    )

    panel_ranking_texto = texto
    panel_ranking_data = ranking
    panel_reveal = None

    print("Partida terminada.")

    for sid in list(jugadores_conectados.keys()):
        socketio.emit(
            "estado",
            texto,
            to=sid
        )

    cancion_actual = 0
    ronda_actual = 1

    reset()
    audio_player.cleanup()


# ---------- Flask / SocketIO ----------

@app.route("/")
def index():
    template = (
        "continue_lyrics.html"
        if game_mode == "continue_lyrics"
        else "guess_song.html"
    )

    return render_template(template)


@app.route("/guess-song")
def guess_song_page():
    return render_template("guess_song.html")


@app.route("/continue-lyrics")
def continue_lyrics_page():
    return render_template("continue_lyrics.html")


@socketio.on("connect")
def conectar(auth=None):
    print(
        f"Conectado: {request.sid}"
    )


@socketio.on("disconnect")
def desconectar():
    nombre = jugadores_conectados.pop(
        request.sid,
        None
    )

    if nombre:
        pedidores_30s.discard(nombre)

        print(
            f"Desconectado: {nombre}"
        )


@socketio.on("registrar")
def registrar(nombre):
    for old_sid in [
        s
        for s, n in jugadores_conectados.items()
        if n == nombre
    ]:
        jugadores_conectados.pop(
            old_sid,
            None
        )

    jugadores_conectados[request.sid] = nombre
    puntuaciones.setdefault(
        nombre,
        0
    )

    print(
        f"Registrado: {nombre} "
        f"(sid={request.sid})"
    )

    emit(
        "registrado",
        f"Bienvenido, {nombre}!"
    )

    emit(
        "estado",
        "Esperando inicio de la ronda...",
        to=request.sid
    )


@socketio.on("respuesta")
def recibir_respuesta(data):
    if not temporizador_activo:
        emit(
            "resultado",
            "⏳ La ronda no está activa.",
            to=request.sid
        )
        return

    nombre = data.get(
        "nombre",
        ""
    )

    texto = data.get(
        "respuesta",
        ""
    )

    respuestas[nombre] = texto

    emit(
        "resultado",
        "✅ Respuesta registrada.",
        to=request.sid
    )

    if len(respuestas) == len([
        n
        for n in puntuaciones
        if n != "host"
    ]):
        print(
            "Todos han respondido. "
            "Finalizando ronda..."
        )

        global tiempo_restante
        tiempo_restante = 0


@socketio.on("nueva_ronda")
def desde_host():
    if jugadores_conectados.get(
        request.sid
    ) != "host":
        return

    socketio.start_background_task(
        action_nueva_ronda
    )


@socketio.on("terminar_partida")
def terminar_partida():
    if jugadores_conectados.get(
        request.sid
    ) != "host":
        return

    socketio.start_background_task(
        action_terminar_partida
    )


@socketio.on("pedir_30s")
def pedir_30s(nombre):
    if (
        not temporizador_activo
        or plus_30s_usado
    ):
        return

    jugador = jugadores_conectados.get(
        request.sid
    )

    if not jugador or jugador == "host":
        return

    jugadores = {
        nombre_jugador
        for nombre_jugador
        in jugadores_conectados.values()
        if nombre_jugador != "host"
    }

    if not jugadores:
        return

    if jugador in pedidores_30s:
        return

    pedidores_30s.add(jugador)

    solicitados = len(
        pedidores_30s
    )

    total_jugadores = len(
        jugadores
    )

    print(
        f"{jugador} ha solicitado +30s "
        f"({solicitados}/{total_jugadores})"
    )

    emit_a_todos(
        "estado",
        (
            f"🕒 {jugador} ha solicitado +30s "
            f"({solicitados}/{total_jugadores})"
        )
    )

    socketio.emit(
        "plus_30s_solicitado",
        to=request.sid
    )

    if solicitados >= total_jugadores:
        print(
            "Todos han pedido +30s. "
            "Añadiendo tiempo."
        )

        socketio.start_background_task(
            anadir_30s_extra
        )


# ---------- Ejecutar ----------

if __name__ == "__main__":
    threading.Thread(
        target=lambda: socketio.run(
            app,
            host="0.0.0.0",
            port=7777,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True
        ),
        daemon=True
    ).start()

    time.sleep(0.5)

    import gui

    gui.crear_panel_host()