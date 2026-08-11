import socket

import threading
import time
import random
from flask import Flask, request, render_template
from flask_socketio import SocketIO, emit

from audio import AudioPlayer
from games.continue_lyrics import ContinueLyricsGame
from games.guess_song import evaluar_respuesta, respuesta_correcta


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

jugadores_conectados = {}        # sid → nombre
puntuaciones = {}                # nombre → puntos
respuestas = {}                  # nombre → respuesta
respuesta_actual = {"titulo": "", "artista": "", "completa": ""}
pedidores_30s = set()            # nombres que pidieron más tiempo
plus_30s_usado = False              # +30s ya concedido en esta ronda
partida_terminada = False
temporizador_activo = False
tiempo_restante = 0
panel_ranking_texto = ""
panel_ranking_data  = []   # [(nombre, pts), ...] ordenado, persiste tras reset()
panel_reveal = None        # {correcta, respuestas: [(nombre, texto, pts_ronda), ...]} tras evaluar
audio_player = AudioPlayer()
continue_lyrics_game = ContinueLyricsGame(audio_player=audio_player)
game_mode = "guess_song"
ronda_en_progreso = False

# ---------- PARAMETROS ----------
LISTA = 'prueba.txt'    # Lista de canciones
T_FRAGMENT = 5        # Duracion del fragmento
T_RESP = 45           # Tiempo para responder
ROUNDS = 10  # Número de canciones por ronda
MAX_LYRIC_ATTEMPTS = 5

# ---------- ESTADO ----------
cancion_actual = 0
ronda_actual = 1

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

def elegir_cancion():
    with open(LISTA, encoding="utf-8") as f:
        canciones = [line.strip() for line in f if " - " in line]
    seleccionada = random.choice(canciones)
    titulo, artista = [s.strip() for s in seleccionada.split(" - ", 1)]
    return titulo, artista

def descargar_y_reproducir(titulo, artista):
    try:
        archivo, duracion = audio_player.download_song(titulo, artista)
        # ffprobe devuelve la duración como float cuando la canción
        # procede de la caché. randint necesita límites enteros.
        max_inicio = max(0, int(duracion - T_FRAGMENT - 5))
        inicio = random.randint(0, max_inicio)
        audio_player.play_fragment(archivo, inicio, T_FRAGMENT)
        return True

    except Exception as e:
        print("Error al reproducir:", e)
        return False

def emit_a_todos(event, data):
    sids = list(jugadores_conectados.keys())
    print(f"emit({event!r}) -> {len(sids)} jugadores: {sids}")
    for sid in sids:
        socketio.emit(event, data, to=sid, namespace='/')

def anadir_30s_extra():
    global tiempo_restante, plus_30s_usado

    if plus_30s_usado:
        return

    plus_30s_usado = True
    tiempo_restante += 30
    emit_a_todos("estado", "🕒 Todos solicitaron +30s. Tiempo añadido.")


# ---------- Evaluación ----------

def evaluar_respuestas():
    resumen = []
    revelacion = []

    for sid, nombre in jugadores_conectados.items():
        if nombre == "host":
            continue

        respuesta = respuestas.get(nombre, "")
        if game_mode == "continue_lyrics":
            evaluacion = continue_lyrics_game.evaluate_answer(respuesta)
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
            resultado = f"{'✅' if puntos else '❌'} {nombre}: +{puntos} puntos ({', '.join(aciertos) or 'ninguno'})\n"
            resultado += f"La respuesta correcta era: {respuesta_actual['completa']}"

        puntuaciones[nombre] += puntos
        socketio.emit("resultado", resultado, to=sid)
        resumen.append(f"{nombre}: {puntuaciones[nombre]} pts")
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

    global panel_ranking_texto, panel_ranking_data, panel_reveal
    sorted_pts = sorted([(n, puntuaciones[n]) for n in puntuaciones if n != "host"],
                        key=lambda x: x[1], reverse=True)
    panel_ranking_texto = "📊 Clasificación:\n" + "\n".join(
        f"{i+1}. {n}: {p} pts" for i, (n, p) in enumerate(sorted_pts))
    panel_ranking_data = sorted_pts
    # Ordenar revelación igual que el ranking
    orden = {n: i for i, (n, _) in enumerate(sorted_pts)}
    revelacion.sort(key=lambda item: orden.get(item["nombre"], 999))
    if game_mode == "continue_lyrics":
        max_words = max(
            (
                continue_lyrics_game.count_words(respuesta)
                for respuesta in respuestas.values()
            ),
            default=0,
        )

        correcta = continue_lyrics_game.get_answer_prefix(max_words)
    else:
        correcta = respuesta_actual["completa"]

    panel_reveal = {
        "correcta": correcta,
        "respuestas": revelacion,
    }

# ---------- Temporizador ----------

def iniciar_ronda(intentos=0):
    global respuestas, temporizador_activo, panel_reveal, ronda_en_progreso
    respuestas = {}
    temporizador_activo = False
    panel_reveal = None
    ronda_en_progreso = True

    titulo, artista = elegir_cancion()
    emit_a_todos("estado", "🎵 Preparando fragmento de audio...")

    def reproduccion_y_luego():
        if game_mode == "continue_lyrics":
            try:
                archivo, duracion = audio_player.download_song(titulo, artista)
                round_data = continue_lyrics_game.prepare_round(
                    titulo, artista, duracion
                )
                if round_data is None:
                    raise ValueError("No hay letra sincronizada válida")

                respuesta_actual["titulo"] = titulo
                respuesta_actual["artista"] = artista
                respuesta_actual["completa"] = round_data["continuation"]
                emit_a_todos("nueva_ronda_letra", {})
                continue_lyrics_game.play_fragment(archivo)
            except Exception as error:
                print("Error al preparar letras:", error)
                if intentos + 1 < MAX_LYRIC_ATTEMPTS:
                    iniciar_ronda(intentos + 1)
                else:
                    ronda_fallida("No se encontraron canciones con letra sincronizada.")
                return
        else:
            respuesta_actual["titulo"] = titulo
            respuesta_actual["artista"] = artista
            respuesta_actual["completa"] = respuesta_correcta(titulo, artista)
            if not descargar_y_reproducir(titulo, artista):
                ronda_fallida("No se pudo preparar el audio de la canción.")
                return
        iniciar_temporizador()

    threading.Thread(target=reproduccion_y_luego, daemon=True).start()


def ronda_fallida(message):
    global ronda_en_progreso, temporizador_activo
    ronda_en_progreso = False
    temporizador_activo = False
    emit_a_todos("estado", f"⚠️ {message}")

def iniciar_temporizador():
    global temporizador_activo, tiempo_restante, pedidores_30s, plus_30s_usado
    temporizador_activo = True
    tiempo_restante = T_RESP
    pedidores_30s.clear()
    plus_30s_usado = False

    emit_a_todos("estado", "🎵 ¡Responde ahora! Tienes " + str(T_RESP) + " segundos...")

    def cuenta_atras():
        global temporizador_activo, tiempo_restante, ronda_en_progreso
        while tiempo_restante > 0:
            emit_a_todos("temporizador", tiempo_restante)
            time.sleep(1)
            tiempo_restante -= 1
        emit_a_todos("temporizador", 0)
        emit_a_todos("estado", "⏰ ¡Tiempo terminado!")
        temporizador_activo = False
        ronda_en_progreso = False
        evaluar_respuestas()

    socketio.start_background_task(cuenta_atras)

def reset():
    # Reset scores
    for n in puntuaciones:
        if n != "host":
            puntuaciones[n] = 0

    # Send modal popup signal
    for sid in jugadores_conectados:
        socketio.emit("mostrar_popup_ronda", f"Ronda {ronda_actual - 1} terminada. ¡Prepárate para la ronda {ronda_actual}!", to=sid)

def reset_all():
    global jugadores_conectados, puntuaciones, respuestas
    global respuesta_actual, pedidores_30s, plus_30s_usado
    global partida_terminada
    global temporizador_activo, tiempo_restante
    global cancion_actual, ronda_actual, panel_reveal, ronda_en_progreso

    respuestas = {}
    respuesta_actual = {"titulo": "", "artista": "", "completa": ""}
    pedidores_30s.clear()
    plus_30s_usado = False
    panel_reveal = None

    temporizador_activo = False
    ronda_en_progreso = False
    tiempo_restante = 0

    partida_terminada = False
    cancion_actual = 0
    ronda_actual = 1

    # Reset scores except host
    for n in puntuaciones:
        if n != "host":
            puntuaciones[n] = 0

    audio_player.cleanup()

    print("Juego reseteado completamente.")


# ---------- Acciones del host ----------

def action_nueva_ronda():
    global cancion_actual, ronda_actual
    cancion_actual += 1
    if cancion_actual > ROUNDS:
        cancion_actual = 0
        ronda_actual += 1
        emit_a_todos("estado", f"🎯 ¡Ronda {ronda_actual - 1} terminada! Se reinician los puntos.")
        print(f"Ronda {ronda_actual - 1} terminada, reiniciando puntuaciones...")
        reset()
        return
    print(f"Canción {cancion_actual}/{ROUNDS} de la ronda {ronda_actual}")
    emit_a_todos("estado", f"🎵 Ronda {ronda_actual}, canción {cancion_actual}/{ROUNDS}")
    iniciar_ronda()


def action_cambiar_modo(mode):
    global game_mode
    if mode not in {"guess_song", "continue_lyrics"}:
        return False
    if ronda_en_progreso:
        print("No se puede cambiar de modo durante una ronda.")
        return False

    game_mode = mode
    mode_name = "Adivina la canción" if mode == "guess_song" else "Continúa la letra"
    print(f"Modo seleccionado: {mode_name}")
    emit_a_todos("modo_juego", mode)
    return True

def action_terminar_partida():
    global partida_terminada, cancion_actual, ronda_actual, panel_ranking_texto, panel_ranking_data, panel_reveal, ronda_en_progreso
    partida_terminada = True
    ronda_en_progreso = False
    ranking = [(n, p) for n, p in sorted(puntuaciones.items(), key=lambda x: x[1], reverse=True) if n != "host"]
    texto = "\n🏆 Ranking final:\n" + "\n".join(f"{i+1}. {n}: {p} pts" for i, (n, p) in enumerate(ranking))
    panel_ranking_texto = texto
    panel_ranking_data  = ranking
    panel_reveal = None
    print("Partida terminada.")
    for sid in list(jugadores_conectados.keys()):
        socketio.emit("estado", texto, to=sid)
    cancion_actual = 0
    ronda_actual = 1
    reset()
    audio_player.cleanup()

# ---------- Flask / SocketIO ----------

@app.route("/")
def index():
    template = "continue_lyrics.html" if game_mode == "continue_lyrics" else "guess_song.html"
    return render_template(template)


@app.route("/guess-song")
def guess_song_page():
    return render_template("guess_song.html")


@app.route("/continue-lyrics")
def continue_lyrics_page():
    return render_template("continue_lyrics.html")

@socketio.on("connect")
def conectar(auth=None):
    print(f"Conectado: {request.sid}")

@socketio.on("disconnect")
def desconectar():
    nombre = jugadores_conectados.pop(request.sid, None)
    if nombre:
        pedidores_30s.discard(nombre)
        print(f"Desconectado: {nombre}")

@socketio.on("registrar")
def registrar(nombre):
    # Eliminar SID antiguo si el mismo jugador reconecta
    for old_sid in [s for s, n in jugadores_conectados.items() if n == nombre]:
        jugadores_conectados.pop(old_sid, None)
    jugadores_conectados[request.sid] = nombre
    puntuaciones.setdefault(nombre, 0)
    print(f"Registrado: {nombre} (sid={request.sid})")
    emit("registrado", f"Bienvenido, {nombre}!")
    emit("estado", "Esperando inicio de la ronda...", to=request.sid)


@socketio.on("respuesta")
def recibir_respuesta(data):
    if not temporizador_activo:
        emit("resultado", "⏳ La ronda no está activa.", to=request.sid)
        return
    nombre = data.get("nombre", "")
    texto = data.get("respuesta", "")
    respuestas[nombre] = texto
    emit("resultado", "✅ Respuesta registrada.", to=request.sid)

    if len(respuestas) == len([n for n in puntuaciones if n != "host"]):
        print("Todos han respondido. Finalizando ronda...")
        global tiempo_restante
        tiempo_restante = 0  # Esto hará que el temporizador termine

@socketio.on("nueva_ronda")
def desde_host():
    if jugadores_conectados.get(request.sid) != "host":
        return
    socketio.start_background_task(action_nueva_ronda)

@socketio.on("terminar_partida")
def terminar_partida():
    if jugadores_conectados.get(request.sid) != "host":
        return
    socketio.start_background_task(action_terminar_partida)

@socketio.on("pedir_30s")
def pedir_30s(nombre):
    if not temporizador_activo or plus_30s_usado:
        return

    jugador = jugadores_conectados.get(request.sid)

    # El host no participa en la votación de +30s.
    if not jugador or jugador == "host":
        return

    jugadores = {
        nombre_jugador
        for nombre_jugador in jugadores_conectados.values()
        if nombre_jugador != "host"
    }

    if not jugadores:
        return

    # Un jugador solo puede solicitar +30s una vez por ronda.
    if jugador in pedidores_30s:
        return

    pedidores_30s.add(jugador)
    solicitados = len(pedidores_30s)
    total_jugadores = len(jugadores)

    print(
        f"{jugador} ha solicitado +30s "
        f"({solicitados}/{total_jugadores})"
    )

    emit_a_todos(
        "estado",
        f"🕒 {jugador} ha solicitado +30s "
        f"({solicitados}/{total_jugadores})"
    )

    # Confirmación explícita al jugador que hizo la petición.
    socketio.emit("plus_30s_solicitado", to=request.sid)

    if solicitados >= total_jugadores:
        print("Todos han pedido +30s. Añadiendo tiempo.")
        socketio.start_background_task(anadir_30s_extra)


# ---------- Ejecutar ----------

if __name__ == "__main__":
    threading.Thread(
        target=lambda: socketio.run(app, host="0.0.0.0", port=7777, debug=False, use_reloader=False, allow_unsafe_werkzeug=True),
        daemon=True
    ).start()
    time.sleep(0.5)
    import gui
    gui.crear_panel_host()
