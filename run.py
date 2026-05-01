import eventlet
eventlet.monkey_patch()

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

import qrcode
import base64
from io import BytesIO


app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

jugadores_conectados = {}        # sid → nombre
puntuaciones = {}                # nombre → puntos
respuestas = {}                  # nombre → respuesta
respuesta_actual = {"titulo": "", "artista": "", "completa": ""}
pedidores_30s = set()            # nombres que pidieron más tiempo
fragmentos_temporales = []       # archivos a borrar al final
partida_terminada = False
sid_host = None
temporizador_activo = False
tiempo_restante = 0

# ---------- PARAMETROS ----------
LISTA = 'Olaf.txt'    # Lista de canciones
T_FRAGMENT = 5        # Duracion del fragmento
T_RESP = 45           # Tiempo para responder
ROUNDS = 3  # Número de canciones por ronda

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
    busqueda = f"{titulo} {artista} audio"

    temp_dir = tempfile.mkdtemp()
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
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{busqueda}", download=True)
            entry = info['entries'][0]
            archivo = os.path.join(temp_dir, entry['id'] + '.mp3')
            duracion = entry.get('duration', 180)

        inicio = random.randint(0, max(0, duracion - T_FRAGMENT - 5))
        wav_temp = os.path.join(temp_dir, "frag.wav")

        result = subprocess.run([
            "ffmpeg", "-y", "-ss", str(inicio), "-i", archivo,
            "-t", str(T_FRAGMENT), "-acodec", "pcm_s16le", "-ar", "44100", wav_temp
        ], capture_output=True)

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
        return False

def anadir_30s_extra():
    global tiempo_restante
    tiempo_restante += 30
    socketio.emit("estado", "🕒 Todos solicitaron +30s. Tiempo añadido.")


# ---------- Evaluación ----------

def evaluar_respuestas():
    resumen = []

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

    if sid_host:
        detalles = []
        for nombre in puntuaciones:
            if nombre == "host":
                continue
            detalles.append(f"{nombre} dijo: {respuestas.get(nombre, '⏳ Sin respuesta')}")
        socketio.emit("estado", "\n".join(detalles), to=sid_host)

    if sid_host:
        socketio.emit("puntuaciones", "\n".join(resumen), to=sid_host)

# ---------- Temporizador ----------

def iniciar_ronda():
    global respuestas, temporizador_activo
    respuestas = {}
    temporizador_activo = False

    titulo, artista = elegir_cancion()
    respuesta_actual["titulo"] = titulo
    respuesta_actual["artista"] = artista
    respuesta_actual["completa"] = f"{titulo} - {artista}"

    socketio.emit("estado", "🎵 Preparando fragmento de audio...")

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

    socketio.emit("estado", "🎵 ¡Responde ahora! Tienes " + str(T_RESP) + " segundos...")

    def cuenta_atras():
        global temporizador_activo, tiempo_restante
        while tiempo_restante > 0:
            socketio.emit("temporizador", tiempo_restante)
            time.sleep(1)
            tiempo_restante -= 1
        socketio.emit("temporizador", 0)
        socketio.emit("estado", "⏰ ¡Tiempo terminado!")
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

    # Update score panel for host
    if sid_host:
        resumen = [f"{n}: {puntuaciones.get(n, 0)} pts" for n in puntuaciones if n != "host"]
        socketio.emit("puntuaciones", "\n".join(resumen), to=sid_host)
        socketio.emit("round", f"Canción {cancion_actual}/{ROUNDS} de la ronda {ronda_actual}", to=sid_host)

def reset_all():
    global jugadores_conectados, puntuaciones, respuestas
    global respuesta_actual, pedidores_30s, fragmentos_temporales
    global partida_terminada, sid_host
    global temporizador_activo, tiempo_restante
    global cancion_actual, ronda_actual

    respuestas = {}
    respuesta_actual = {"titulo": "", "artista": "", "completa": ""}
    pedidores_30s.clear()

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


# ---------- Flask / SocketIO ----------
from flask import render_template

@app.route("/")
def index():
    url = f"http://{obtener_ip_local()}:7777"

    # Generar QR
    qr = qrcode.make(url)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return render_template("host.html", URL=url, QR=qr_b64)

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
    global sid_host
    jugadores_conectados[request.sid] = nombre
    puntuaciones.setdefault(nombre, 0)

    if nombre == "host":
        sid_host = request.sid

    print(f"🟢 Registrado: {nombre}")
    if(nombre != "host"):
      emit("registrado", f"Bienvenido, {nombre}!")
    else:
        emit("registrado", f"Canción {cancion_actual}/{ROUNDS} de la ronda {ronda_actual}")
    emit("estado", "Esperando inicio de la ronda...", to=request.sid)

    # Enviar ranking al host
    if sid_host:
        resumen = [f"{n}: {puntuaciones.get(n, 0)} pts" for n in puntuaciones if n != "host"]
        socketio.emit("puntuaciones", "\n".join(resumen), to=sid_host)


@socketio.on("respuesta")
def recibir_respuesta(data):
    if not temporizador_activo:
        emit("resultado", "⏳ La ronda no está activa.", to=request.sid)
        return
    nombre = data.get("nombre", "")
    texto = data.get("respuesta", "")
    respuestas[nombre] = texto
    emit("resultado", f"✅ Respuesta registrada.", to=request.sid)

    # Emitir actualización del ranking
    if sid_host:
        resumen = []
        for n in puntuaciones:
            if n == "host":
                continue
            check = "✅" if n in respuestas else "❌"
            resumen.append(f"{check} {n}: {puntuaciones.get(n, 0)} pts")
        socketio.emit("puntuaciones", "\n".join(resumen), to=sid_host)

    if len(respuestas) == len([n for n in puntuaciones if n != "host"]):
        print("📩 Todos han respondido. Finalizando ronda...")
        global tiempo_restante
        tiempo_restante = 0  # Esto hará que el temporizador termine

@socketio.on("nueva_ronda")
def desde_host():
    global cancion_actual, ronda_actual

    if jugadores_conectados.get(request.sid) != "host":
        return

    # Increment song counter
    cancion_actual += 1

    if cancion_actual > ROUNDS:
        # Round finished
        cancion_actual = 0
        ronda_actual += 1
        socketio.emit("estado", f"🎯 ¡Ronda {ronda_actual - 1} terminada! Se reinician los puntos.")
        print(f"🎯 Ronda {ronda_actual - 1} terminada, reiniciando puntuaciones...")

        reset()
            
        return

    print(f"▶️ Canción {cancion_actual}/{ROUNDS} de la ronda {ronda_actual}")
    socketio.emit("estado", f"🎵 Ronda {ronda_actual}, canción {cancion_actual}/{ROUNDS}")
    socketio.emit("round", f"Canción {cancion_actual}/{ROUNDS} de la ronda {ronda_actual}", to=sid_host)
    iniciar_ronda()


@socketio.on("terminar_partida")
def terminar_partida():
    global partida_terminada, cancion_actual, ronda_actual
    if jugadores_conectados.get(request.sid) != "host":
        return
    partida_terminada = True

    ranking = sorted(puntuaciones.items(), key=lambda x: x[1], reverse=True)
    texto = "\n🏆 Ranking final:\n" + "\n".join(f"{n}: {p} pts" for n, p in ranking if n != "host")
    print(texto)

    # Enviar a todos
    for sid in jugadores_conectados:
        socketio.emit("estado", texto, to=sid)

    cancion_actual = 0
    ronda_actual = 1

    reset()

    # Eliminar fragmentos
    for ruta in fragmentos_temporales:
        try:
            if os.path.exists(ruta):
                os.remove(ruta)
                print(f"🗑️ Eliminado: {ruta}")
        except Exception as e:
            print(f"❌ Error al borrar {ruta}:", e)

    fragmentos_temporales.clear()

@socketio.on("pedir_30s")
def pedir_30s(nombre):
    if not temporizador_activo:
        return

    if nombre in puntuaciones:
        pedidores_30s.add(nombre)
        print(f"🕒 {nombre} ha solicitado +30s ({len(pedidores_30s)}/{len(puntuaciones)-1})")
        socketio.emit("estado", f"🕒 {nombre} ha solicitado +30s ({len(pedidores_30s)}/{len(puntuaciones)-1})")

        if len(pedidores_30s) == len(puntuaciones)-1:
            print("🕒 TODOS han pedido +30s. Añadiendo tiempo.")
            socketio.start_background_task(anadir_30s_extra)


# ---------- Ejecutar ----------

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=7777, debug=False, use_reloader=False)
