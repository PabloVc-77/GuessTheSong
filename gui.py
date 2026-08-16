import tkinter as tk
import customtkinter as ctk
from PIL import Image
import qrcode
import traceback
import sys

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

BG      = "#0f0f0f"
SURFACE = "#1a1a1a"
ACCENT  = "#1db954"
TEXT    = "#e0e0e0"
MUTED   = "#666666"
WARN    = "#ffaa00"


def crear_panel_host():
    run = sys.modules['__main__']
    url = f"http://{run.obtener_ip_local()}:7777"

    root = ctk.CTk()
    root.title("Panel de Control · Adivina la Canción")
    root.configure(fg_color=BG)
    root.resizable(True, True)
    root.minsize(640, 640)

    # ── TOP: QR (izq) + info (der) ───────────────────────────────
    top = ctk.CTkFrame(root, fg_color="transparent")
    top.pack(fill="x", padx=20, pady=(20, 0))
    top.columnconfigure(0, weight=0)
    top.columnconfigure(1, weight=1)

    # — Columna izquierda: QR + URL —
    left = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=12)
    left.grid(row=0, column=0, sticky="ns", padx=(0, 14))

    qr_pil = qrcode.make(url).resize((150, 150), Image.LANCZOS).convert("RGB")
    qr_img = ctk.CTkImage(light_image=qr_pil, dark_image=qr_pil, size=(150, 150))
    ctk.CTkLabel(left, image=qr_img, text="").pack(padx=14, pady=(14, 6))
    ctk.CTkLabel(left, text=url, text_color=ACCENT,
                 font=ctk.CTkFont(family="Courier New", size=12, weight="bold"),
                 wraplength=160).pack(padx=12, pady=(0, 14))

    # — Columna derecha: ronda + timer + descarga —
        # — Columna derecha: ronda + información en 2 columnas —
    right = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=12)
    right.grid(row=0, column=1, sticky="nsew")

    # Dos columnas con el mismo ancho
    right.columnconfigure(0, weight=1)
    right.columnconfigure(1, weight=1)

    # ── RONDA ──────────────────────────────────────────────────
    ctk.CTkLabel(
        right,
        text="RONDA",
        text_color=MUTED,
        font=ctk.CTkFont(size=14, weight="bold")
    ).grid(
        row=0,
        column=0,
        sticky="w",
        padx=18,
        pady=(16, 2)
    )

    round_var = tk.StringVar()
    ctk.CTkLabel(
        right,
        textvariable=round_var,
        text_color=TEXT,
        font=ctk.CTkFont(size=22, weight="bold")
    ).grid(
        row=1,
        column=0,
        sticky="w",
        padx=18
    )

    # ── TIEMPO RESTANTE ────────────────────────────────────────
    ctk.CTkLabel(
        right,
        text="TIEMPO RESTANTE",
        text_color=MUTED,
        font=ctk.CTkFont(size=14, weight="bold")
    ).grid(
        row=2,
        column=0,
        sticky="w",
        padx=18,
        pady=(14, 2)
    )

    # ── ÚLTIMA FRASE ───────────────────────────────────────────
    ctk.CTkLabel(
        right,
        text="ÚLTIMA FRASE",
        text_color=MUTED,
        font=ctk.CTkFont(size=14, weight="bold")
    ).grid(
        row=2,
        column=1,
        sticky="w",
        padx=18,
        pady=(14, 2)
    )

    timer_var = tk.StringVar(value="--")
    ctk.CTkLabel(
        right,
        textvariable=timer_var,
        text_color=WARN,
        font=ctk.CTkFont(size=48, weight="bold")
    ).grid(
        row=3,
        column=0,
        sticky="w",
        padx=18
    )

    last_lyric_var = tk.StringVar(value="—")
    ctk.CTkLabel(
        right,
        textvariable=last_lyric_var,
        text_color=TEXT,
        font=ctk.CTkFont(size=18, weight="bold"),
        wraplength=350,
        justify="left"
    ).grid(
        row=3,
        column=1,
        sticky="nw",
        padx=18
    )

    # ── DESCARGA ────────────────────────────────────────────────
    ctk.CTkLabel(
        right,
        text="DESCARGA",
        text_color=MUTED,
        font=ctk.CTkFont(size=14, weight="bold")
    ).grid(
        row=4,
        column=0,
        sticky="w",
        padx=18,
        pady=(14, 2)
    )

    descarga_label_var = tk.StringVar(value="—")
    ctk.CTkLabel(
        right,
        textvariable=descarga_label_var,
        text_color=TEXT,
        font=ctk.CTkFont(size=16)
    ).grid(
        row=5,
        column=0,
        sticky="w",
        padx=18
    )

    progressbar = ctk.CTkProgressBar(
        right,
        progress_color=ACCENT,
        fg_color="#2a2a2a",
        height=8,
        corner_radius=4
    )
    progressbar.set(0)
    progressbar.grid(
        row=6,
        column=0,
        sticky="ew",
        padx=18,
        pady=(4, 18)
    )

    # ── MODO DE JUEGO ──────────────────────────────────────────
    ctk.CTkLabel(
        right,
        text="MODO DE JUEGO",
        text_color=MUTED,
        font=ctk.CTkFont(size=14, weight="bold")
    ).grid(
        row=4,
        column=1,
        sticky="w",
        padx=18,
        pady=(14, 2)
    )

    mode_labels = {
        "🎵 Adivina la canción": "guess_song",
        "📝 Continúa la letra": "continue_lyrics",
    }

    selected_mode = tk.StringVar(value="🎵 Adivina la canción")

    def cambiar_modo(label):
        if not run.action_cambiar_modo(mode_labels[label]):
            selected_mode.set(
                "🎵 Adivina la canción"
                if run.game_mode == "guess_song"
                else "📝 Continúa la letra"
            )

    ctk.CTkOptionMenu(
        right,
        values=list(mode_labels),
        variable=selected_mode,
        command=cambiar_modo,
        fg_color="#2a2a2a",
        button_color=ACCENT,
        button_hover_color="#168a3f"
    ).grid(
        row=5,
        column=1,
        sticky="ew",
        padx=18
    )

    # ── LISTA DE CANCIONES ─────────────────────────────────────

    ctk.CTkLabel(
        right,
        text="LISTA DE CANCIONES",
        text_color=MUTED,
        font=ctk.CTkFont(size=14, weight="bold")
    ).grid(
        row=0,
        column=1,
        sticky="w",
        padx=18,
        pady=(16, 2)
    )

    listas_disponibles = run.obtener_listas()

    lista_labels = {
        lista.stem: lista.name
        for lista in listas_disponibles
    }

    lista_nombres = list(lista_labels.keys())

    lista_actual = tk.StringVar(
        value=run.LISTA.stem
        if run.LISTA.stem in lista_nombres
        else (lista_nombres[0] if lista_nombres else "Sin listas")
    )


    def cambiar_lista(nombre):
        if nombre == "Sin listas":
            return

        nombre_archivo = lista_labels[nombre]

        if not run.action_cambiar_lista(nombre_archivo):
            lista_actual.set(run.LISTA.stem)


    lista_menu = ctk.CTkOptionMenu(
        right,
        values=lista_nombres or ["Sin listas"],
        variable=lista_actual,
        command=cambiar_lista,
        fg_color="#2a2a2a",
        button_color=ACCENT,
        button_hover_color="#168a3f"
    )

    lista_menu.grid(
        row=1,
        column=1,
        sticky="ew",
        padx=18
    )

    # ── JUGADORES ────────────────────────────────────────────────
    ctk.CTkLabel(root, text="JUGADORES", text_color=MUTED,
                 font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=20, pady=(18, 6))

    scores_box = ctk.CTkTextbox(root, fg_color=SURFACE, text_color=TEXT,
                                font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
                                corner_radius=12)
    scores_box.pack(fill="both", expand=True, padx=20)
    scores_box.tag_config("palabra_correcta", foreground="#4ade80")
    scores_box.tag_config("palabra_incorrecta", foreground="#f87171")
    scores_box.tag_config("palabra_omitida", foreground="#f59e0b")
    scores_box.tag_config("palabra_typo", foreground="#d97706")

    # ── BOTONES ──────────────────────────────────────────────────
    btn_frame = ctk.CTkFrame(root, fg_color="transparent")
    btn_frame.pack(pady=18)
    ctk.CTkButton(btn_frame, text="▶  Nueva Ronda", width=180, height=40,
                  command=lambda: run.socketio.start_background_task(run.action_nueva_ronda),
                  fg_color=SURFACE, hover_color="#2a2a2a", text_color=TEXT,
                  border_width=1, border_color="#333",
                  font=ctk.CTkFont(size=15), corner_radius=8).pack(side="left", padx=6)
    ctk.CTkButton(btn_frame, text="✕  Terminar", width=180, height=40,
                  command=lambda: run.socketio.start_background_task(run.action_terminar_partida),
                  fg_color=SURFACE, hover_color="#2a2a2a", text_color="#ff5555",
                  border_width=1, border_color="#333",
                  font=ctk.CTkFont(size=15), corner_radius=8).pack(side="left", padx=6)

    # ── Loop de actualización (500 ms) ───────────────────────────

    def actualizar():
        try:
            round_var.set(f"Canción {run.cancion_actual}/{run.ROUNDS} · Ronda {run.ronda_actual}")
            timer_var.set(str(run.tiempo_restante) if run.temporizador_activo else "--")

            # Última frase reproducida en el modo "Continúa la letra"
            if run.game_mode == "continue_lyrics":
                last_lyric_var.set(
                    getattr(
                        run.continue_lyrics_game,
                        "last_played_line",
                        ""
                    ) or "—"
                )
            else:
                last_lyric_var.set("—")

            # Barra de descarga
            if run.audio_player.download_active:
                if run.audio_player.download_phase == "downloading":
                    descarga_label_var.set(f"⬇  Descargando... {int(run.audio_player.download_progress * 100)}%")
                    progressbar.set(run.audio_player.download_progress)
                elif run.audio_player.download_phase == "processing":
                    descarga_label_var.set("⚙  Procesando audio...")
                    progressbar.set(1.0)
            else:
                descarga_label_var.set("—")
                progressbar.set(0)

            # Snapshot thread-safe del dict antes de iterar
            puntuaciones = list(run.puntuaciones.items())
            respuestas   = run.respuestas
            reveal       = run.panel_reveal

            lines = []

            if run.temporizador_activo:
                jugadores = sorted(
                    [(n, p, "✓" if n in respuestas else "·")
                     for n, p in puntuaciones if n != "host"],
                    key=lambda x: x[1], reverse=True
                )
                for nombre, pts, mark in jugadores:
                    lines.append(f"  {mark}  {nombre}  —  {pts} pts")

            elif reveal:
                scores_box.delete("1.0", "end")
                scores_box.insert("end", f"  {reveal['correcta']}\n\n")
                pts_totales = dict(run.panel_ranking_data)
                for i, respuesta in enumerate(reveal["respuestas"]):
                    nombre = respuesta["nombre"]
                    total = pts_totales.get(nombre, 0)
                    puntos_ronda = respuesta["puntos"]
                    signo = f"+{puntos_ronda}" if puntos_ronda else "+0"
                    scores_box.insert(
                        "end", f"  {i+1}. {nombre} - {total} pts ({signo})\n"
                    )
                    feedback = respuesta["feedback"]
                    if feedback is None:
                        scores_box.insert("end", f"      {respuesta['texto']}\n\n")
                        continue

                    scores_box.insert("end", "      ")
                    for palabra in feedback:
                        if palabra["correct"]:
                            tag = "palabra_correcta"
                        elif palabra["omitted"]:
                            tag = "palabra_omitida"
                        elif palabra["typo"]:
                            tag = "palabra_typo"
                        else:
                            tag = "palabra_incorrecta"
                       
                        scores_box.insert("end", f"{palabra['word']} ", tag)
                    scores_box.insert("end", "\n\n")

                root.after(500, actualizar)
                return
            elif run.panel_ranking_data:
                for i, (nombre, pts) in enumerate(run.panel_ranking_data):
                    lines.append(f"  {i+1}.  {nombre}  —  {pts} pts")

            else:
                jugadores = sorted(
                    [(n, p) for n, p in puntuaciones if n != "host"],
                    key=lambda x: x[1], reverse=True
                )
                for nombre, pts in jugadores:
                    lines.append(f"  {nombre}  —  {pts} pts")

            scores_box.delete("1.0", "end")
            scores_box.insert("1.0", "\n".join(lines).rstrip() or "—  Sin jugadores")
        except Exception as e:
            print(f"⚠️ Error en actualizar GUI: {e}")
            traceback.print_exc()
        root.after(500, actualizar)

    root.after(500, actualizar)
    root.mainloop()
