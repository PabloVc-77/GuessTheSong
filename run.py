import tempfile
import pygame

pygame.mixer.init()

import socket

import os
import threading
import time
import random
import unicodedata
from flask import Flask, request
from flask_socketio import SocketIO, emit
from yt_dlp import YoutubeDL
import subprocess


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

jugadores_conectados = {}        # sid → nombre
puntuaciones = {}                # nombre → puntos
respuestas = {}                  # nombre → respuesta
respuesta_actual = {"titulo": "", "artista": "", "completa": ""}
pedidores_30s = set()            # nombres que pidieron más tiempo
fragmentos_temporales = []       # archivos a borrar al final
partida_terminada = False
temporizador_activo = False
tiempo_restante = 0
panel_ranking_texto = ""
panel_ranking_data  = []   # [(nombre, pts), ...] ordenado, persiste tras reset()
panel_reveal = None        # {correcta, respuestas: [(nombre, texto, pts_ronda), ...]} tras evaluar
descarga_activa = False
descarga_progreso = 0.0   # 0.0 – 1.0
descarga_fase = ""        # "descargando" | "procesando" | ""

# ---------- PARAMETROS ----------
LISTA = 'Olaf.txt'    # Lista de canciones
T_FRAGMENT = 5        # Duracion del fragmento
T_RESP = 45           # Tiempo para responder
ROUNDS = 10  # Número de canciones por ronda

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

def normalizar(texto):
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto

def elegir_cancion():
    with open(LISTA, encoding="utf-8") as f:
        canciones = [line.strip() for line in f if " - " in line]
    seleccionada = random.choice(canciones)
    titulo, artista = [s.strip() for s in seleccionada.split(" - ", 1)]
    return titulo, artista

def descargar_y_reproducir(titulo, artista):
    global descarga_activa, descarga_progreso, descarga_fase
    busqueda = f"{titulo} {artista} audio"
    temp_dir = tempfile.mkdtemp()

    descarga_activa = True
    descarga_progreso = 0.0
    descarga_fase = "descargando"

    def _progress_hook(d):
        global descarga_progreso
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            if total > 0:
                descarga_progreso = d['downloaded_bytes'] / total
        elif d['status'] == 'finished':
            descarga_progreso = 1.0

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'progress_hooks': [_progress_hook],
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{busqueda}", download=True)
            entry = info['entries'][0]
            archivo = os.path.join(temp_dir, entry['id'] + '.mp3')
            duracion = entry.get('duration', 180)

        descarga_fase = "procesando"

        inicio = random.randint(0, max(0, duracion - T_FRAGMENT - 5))
        wav_temp = os.path.join(temp_dir, "frag.wav")

        result = subprocess.run([
            "ffmpeg", "-y", "-ss", str(inicio), "-i", archivo,
            "-t", str(T_FRAGMENT), "-acodec", "pcm_s16le", "-ar", "44100", wav_temp
        ], capture_output=True)

        descarga_activa = False
        descarga_fase = ""

        if result.returncode != 0:
            print("❌ ffmpeg error:", result.stderr.decode(errors="ignore"))
            return False

        pygame.mixer.music.load(wav_temp)
        pygame.mixer.music.play()
        time.sleep(T_FRAGMENT)
        pygame.mixer.music.unload()

        fragmentos_temporales.append(wav_temp)
        fragmentos_temporales.append(archivo)
        return True

    except Exception as e:
        print("❌ Error al reproducir:", e)
        descarga_activa = False
        descarga_fase = ""
        return False

def emit_a_todos(event, data):
    sids = list(jugadores_conectados.keys())
    print(f"📡 emit({event!r}) → {len(sids)} jugadores: {sids}")
    for sid in sids:
        socketio.emit(event, data, to=sid, namespace='/')

def anadir_30s_extra():
    global tiempo_restante
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
        r_norm = normalizar(respuesta)
        t_norm = normalizar(respuesta_actual["titulo"])
        a_norm = normalizar(respuesta_actual["artista"])
        puntos = 0
        aciertos = []

        if t_norm in r_norm:
            puntos += 2
            aciertos.append("🎵 título")
        if a_norm in r_norm:
            puntos += 1
            aciertos.append("👤 artista")
        if puntos == 3:
            puntos = 4

        puntuaciones[nombre] += puntos
        resultado = f"{'✅' if puntos else '❌'} {nombre}: +{puntos} puntos ({', '.join(aciertos) or 'ninguno'})\n"
        resultado += f"La respuesta correcta era: {respuesta_actual['completa']}"
        socketio.emit("resultado", resultado, to=sid)
        resumen.append(f"{nombre}: {puntuaciones[nombre]} pts")
        revelacion.append((nombre, respuesta or "(sin respuesta)", puntos))

    global panel_ranking_texto, panel_ranking_data, panel_reveal
    sorted_pts = sorted([(n, puntuaciones[n]) for n in puntuaciones if n != "host"],
                        key=lambda x: x[1], reverse=True)
    panel_ranking_texto = "📊 Clasificación:\n" + "\n".join(
        f"{i+1}. {n}: {p} pts" for i, (n, p) in enumerate(sorted_pts))
    panel_ranking_data = sorted_pts
    # Ordenar revelación igual que el ranking
    orden = {n: i for i, (n, _) in enumerate(sorted_pts)}
    revelacion.sort(key=lambda x: orden.get(x[0], 999))
    panel_reveal = {
        "correcta": respuesta_actual["completa"],
        "respuestas": revelacion,
    }

# ---------- Temporizador ----------

def iniciar_ronda():
    global respuestas, temporizador_activo, panel_reveal
    respuestas = {}
    temporizador_activo = False
    panel_reveal = None

    titulo, artista = elegir_cancion()
    respuesta_actual["titulo"] = titulo
    respuesta_actual["artista"] = artista
    respuesta_actual["completa"] = f"{titulo} - {artista}"

    emit_a_todos("estado", "🎵 Preparando fragmento de audio...")

    def reproduccion_y_luego():
        flag = descargar_y_reproducir(titulo, artista)
        if not flag:
            # 🔁 Reintentar con otra canción
            iniciar_ronda()
            return
        iniciar_temporizador()

    threading.Thread(target=reproduccion_y_luego, daemon=True).start()

def iniciar_temporizador():
    global temporizador_activo, tiempo_restante, pedidores_30s
    temporizador_activo = True
    tiempo_restante = T_RESP
    pedidores_30s.clear()

    emit_a_todos("estado", "🎵 ¡Responde ahora! Tienes " + str(T_RESP) + " segundos...")

    def cuenta_atras():
        global temporizador_activo, tiempo_restante
        while tiempo_restante > 0:
            emit_a_todos("temporizador", tiempo_restante)
            time.sleep(1)
            tiempo_restante -= 1
        emit_a_todos("temporizador", 0)
        emit_a_todos("estado", "⏰ ¡Tiempo terminado!")
        temporizador_activo = False
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
    global respuesta_actual, pedidores_30s, fragmentos_temporales
    global partida_terminada
    global temporizador_activo, tiempo_restante
    global cancion_actual, ronda_actual, panel_reveal

    respuestas = {}
    respuesta_actual = {"titulo": "", "artista": "", "completa": ""}
    pedidores_30s.clear()
    panel_reveal = None

    temporizador_activo = False
    tiempo_restante = 0

    partida_terminada = False
    cancion_actual = 0
    ronda_actual = 1

    # Reset scores except host
    for n in puntuaciones:
        if n != "host":
            puntuaciones[n] = 0

    # Clear temporary fragment files
    for ruta in fragmentos_temporales:
        try:
            if os.path.exists(ruta):
                os.remove(ruta)
                print(f"🗑️ Eliminado: {ruta}")
        except Exception as e:
            print(f"❌ Error al borrar {ruta}:", e)
    fragmentos_temporales.clear()

    print("🔄 Juego reseteado completamente.")


# ---------- Acciones del host ----------

def action_nueva_ronda():
    global cancion_actual, ronda_actual
    cancion_actual += 1
    if cancion_actual > ROUNDS:
        cancion_actual = 0
        ronda_actual += 1
        emit_a_todos("estado", f"🎯 ¡Ronda {ronda_actual - 1} terminada! Se reinician los puntos.")
        print(f"🎯 Ronda {ronda_actual - 1} terminada, reiniciando puntuaciones...")
        reset()
        return
    print(f"▶️ Canción {cancion_actual}/{ROUNDS} de la ronda {ronda_actual}")
    emit_a_todos("estado", f"🎵 Ronda {ronda_actual}, canción {cancion_actual}/{ROUNDS}")
    iniciar_ronda()

def action_terminar_partida():
    global partida_terminada, cancion_actual, ronda_actual, panel_ranking_texto, panel_ranking_data, panel_reveal
    partida_terminada = True
    ranking = [(n, p) for n, p in sorted(puntuaciones.items(), key=lambda x: x[1], reverse=True) if n != "host"]
    texto = "\n🏆 Ranking final:\n" + "\n".join(f"{i+1}. {n}: {p} pts" for i, (n, p) in enumerate(ranking))
    panel_ranking_texto = texto
    panel_ranking_data  = ranking
    panel_reveal = None
    print(texto)
    for sid in list(jugadores_conectados.keys()):
        socketio.emit("estado", texto, to=sid)
    cancion_actual = 0
    ronda_actual = 1
    reset()
    for ruta in fragmentos_temporales:
        try:
            if os.path.exists(ruta):
                os.remove(ruta)
                print(f"🗑️ Eliminado: {ruta}")
        except Exception as e:
            print(f"❌ Error al borrar {ruta}:", e)
    fragmentos_temporales.clear()

# ---------- Flask / SocketIO ----------
from flask import render_template

@app.route("/")
def index():
    return render_template("host.html")

@socketio.on("connect")
def conectar():
    print(f"🔌 Conectado: {request.sid}")

@socketio.on("disconnect")
def desconectar():
    nombre = jugadores_conectados.pop(request.sid, None)
    if nombre:
        print(f"❌ Desconectado: {nombre}")

@socketio.on("registrar")
def registrar(nombre):
    # Eliminar SID antiguo si el mismo jugador reconecta
    for old_sid in [s for s, n in jugadores_conectados.items() if n == nombre]:
        jugadores_conectados.pop(old_sid, None)
    jugadores_conectados[request.sid] = nombre
    puntuaciones.setdefault(nombre, 0)
    print(f"🟢 Registrado: {nombre} (sid={request.sid})")
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
    emit("resultado", f"✅ Respuesta registrada.", to=request.sid)

    if len(respuestas) == len([n for n in puntuaciones if n != "host"]):
        print("📩 Todos han respondido. Finalizando ronda...")
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
    if not temporizador_activo:
        return

    if nombre in puntuaciones:
        pedidores_30s.add(nombre)
        print(f"🕒 {nombre} ha solicitado +30s ({len(pedidores_30s)}/{len(puntuaciones)-1})")
        emit_a_todos("estado", f"🕒 {nombre} ha solicitado +30s ({len(pedidores_30s)}/{len(puntuaciones)-1})")

        if len(pedidores_30s) == len(puntuaciones)-1:
            print("🕒 TODOS han pedido +30s. Añadiendo tiempo.")
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
