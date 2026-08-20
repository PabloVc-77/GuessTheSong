"""Panel de control (GUI) para el host de "Adivina la Canción"."""

import sys
import traceback
import tkinter as tk

import customtkinter as ctk
import qrcode
from PIL import Image

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

# ── Paleta de colores ─────────────────────────────────────────────────
BG            = "#0f0f0f"
SURFACE       = "#1a1a1a"
ACCENT        = "#1db954"
ACCENT_HOVER  = "#168a3f"
TEXT          = "#e0e0e0"
MUTED         = "#666666"
WARN          = "#ffaa00"
DANGER        = "#c0392b"
DANGER_HOVER  = "#a93226"
NEUTRAL       = "#2a2a2a"
NEUTRAL_HOVER = "#3a3a3a"

# ── Constantes de juego ───────────────────────────────────────────────
MODE_LABELS = {
    "🎵 Adivina la canción": "guess_song",
    "📝 Continúa la letra": "continue_lyrics",
}
MODE_LABELS_REVERSE = {v: k for k, v in MODE_LABELS.items()}

CACHE_LABEL = "🎧 Canciones en caché"
CACHE_VALUE = "__CACHE__"

UPDATE_INTERVAL_MS = 500


# ── Helpers de construcción de widgets ────────────────────────────────

def _section_header(parent, text, row, column, pady_top=16):
    """Etiqueta pequeña en mayúsculas usada como cabecera de sección."""
    label = ctk.CTkLabel(
        parent,
        text=text,
        text_color=MUTED,
        font=ctk.CTkFont(size=14, weight="bold"),
    )
    label.grid(row=row, column=column, sticky="w", padx=18, pady=(pady_top, 2))
    return label


def _toplevel(parent, title, size):
    """Crea una ventana modal (Toplevel) con el estilo estándar del panel."""
    window = ctk.CTkToplevel(parent)
    window.title(title)
    window.geometry(size)
    window.configure(fg_color=BG)
    window.transient(parent)
    window.grab_set()
    return window


class HostPanel:
    """Ventana de control mostrada en el equipo del host de la partida."""

    def __init__(self, run):
        self.run = run
        self.root = ctk.CTk()

        # Variables de estado compartidas entre las distintas secciones
        self.round_var = tk.StringVar()
        self.timer_var = tk.StringVar(value="--")
        self.last_lyric_var = tk.StringVar(value="—")
        self.descarga_label_var = tk.StringVar(value="—")
        self.selected_mode = tk.StringVar(value=next(iter(MODE_LABELS)))
        self.lista_actual = tk.StringVar()
        self.lista_labels = {}

        # Referencias a widgets que necesitan actualizarse más tarde
        self.lista_menu = None
        self.progressbar = None
        self.scores_box = None

        self._build_window()
        self._build_top_section()
        self._build_scores_section()
        self._build_control_buttons()

        self.root.after(UPDATE_INTERVAL_MS, self._update)

    def run_forever(self):
        self.root.mainloop()

    # ── Ventana principal ──────────────────────────────────────────
    def _build_window(self):
        self.root.title("Panel de Control · Adivina la Canción")
        self.root.configure(fg_color=BG)
        self.root.resizable(True, True)
        self.root.minsize(640, 640)

    # ── Cabecera: QR + estadísticas ────────────────────────────────
    def _build_top_section(self):
        top = ctk.CTkFrame(self.root, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(20, 0))
        top.columnconfigure(0, weight=0)
        top.columnconfigure(1, weight=1)

        self._build_qr_panel(top)

        right = ctk.CTkFrame(top, fg_color=SURFACE, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.columnconfigure(1, weight=1)

        self._build_stats_column(right)
        self._build_playlist_column(right)

    def _build_qr_panel(self, parent):
        url = f"http://{self.run.obtener_ip_local()}:7777"

        left = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=12)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 14))

        qr_pil = qrcode.make(url).resize((150, 150), Image.LANCZOS).convert("RGB")
        qr_img = ctk.CTkImage(light_image=qr_pil, dark_image=qr_pil, size=(150, 150))

        ctk.CTkLabel(left, image=qr_img, text="").pack(padx=14, pady=(14, 6))
        ctk.CTkLabel(
            left,
            text=url,
            text_color=ACCENT,
            font=ctk.CTkFont(family="Courier New", size=12, weight="bold"),
            wraplength=160,
        ).pack(padx=12, pady=(0, 14))

    def _build_stats_column(self, parent):
        """Columna izquierda: ronda, tiempo restante y descarga."""
        _section_header(parent, "RONDA", row=0, column=0)
        ctk.CTkLabel(
            parent, textvariable=self.round_var, text_color=TEXT,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=1, column=0, sticky="w", padx=18)

        _section_header(parent, "TIEMPO RESTANTE", row=2, column=0, pady_top=14)
        ctk.CTkLabel(
            parent, textvariable=self.timer_var, text_color=WARN,
            font=ctk.CTkFont(size=48, weight="bold"),
        ).grid(row=3, column=0, sticky="w", padx=18)

        _section_header(parent, "DESCARGA", row=4, column=0, pady_top=14)
        ctk.CTkLabel(
            parent, textvariable=self.descarga_label_var, text_color=TEXT,
            font=ctk.CTkFont(size=16),
        ).grid(row=5, column=0, sticky="w", padx=18)

        self.progressbar = ctk.CTkProgressBar(
            parent, progress_color=ACCENT, fg_color=NEUTRAL, height=8, corner_radius=4,
        )
        self.progressbar.set(0)
        self.progressbar.grid(row=6, column=0, sticky="ew", padx=18, pady=(4, 18))

    def _build_playlist_column(self, parent):
        """Columna derecha: lista de canciones, última frase y modo de juego."""
        run = self.run

        _section_header(parent, "LISTA DE CANCIONES", row=0, column=1)

        self.lista_labels = {lista.stem: lista.name for lista in run.obtener_listas()}
        self.lista_labels[CACHE_LABEL] = CACHE_VALUE
        nombres = list(self.lista_labels)

        if run.USAR_CACHE:
            valor_inicial = CACHE_LABEL
        elif run.LISTA.stem in nombres:
            valor_inicial = run.LISTA.stem
        else:
            valor_inicial = nombres[0] if nombres else "Sin listas"
        self.lista_actual.set(valor_inicial)

        self.lista_menu = ctk.CTkOptionMenu(
            parent, values=nombres or ["Sin listas"], variable=self.lista_actual,
            command=self._cambiar_lista, fg_color=NEUTRAL, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        )
        self.lista_menu.grid(row=1, column=1, sticky="ew", padx=18)

        self._build_playlist_buttons(parent)

        _section_header(parent, "ÚLTIMA FRASE", row=3, column=1, pady_top=14)
        ctk.CTkLabel(
            parent, textvariable=self.last_lyric_var, text_color=TEXT,
            font=ctk.CTkFont(size=18, weight="bold"), wraplength=350, justify="left",
        ).grid(row=4, column=1, sticky="nw", padx=18)

        _section_header(parent, "MODO DE JUEGO", row=5, column=1, pady_top=14)
        ctk.CTkOptionMenu(
            parent, values=list(MODE_LABELS), variable=self.selected_mode,
            command=self._cambiar_modo, fg_color=NEUTRAL, button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
        ).grid(row=6, column=1, sticky="ew", padx=18)

    def _build_playlist_buttons(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=2, column=1, sticky="ew", padx=18, pady=(10, 0))
        for col in range(3):
            frame.columnconfigure(col, weight=1)

        ctk.CTkButton(
            frame, text="➕ Crear", command=self._abrir_editor_playlist,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))

        ctk.CTkButton(
            frame, text="✏️ Editar", command=self._editar_playlist_actual,
        ).grid(row=0, column=1, sticky="ew", padx=3)

        ctk.CTkButton(
            frame, text="🗑️ Eliminar", fg_color=DANGER, hover_color=DANGER_HOVER,
            command=self._eliminar_playlist,
        ).grid(row=0, column=2, sticky="ew", padx=(3, 0))

    # ── Marcador de jugadores ───────────────────────────────────────
    def _build_scores_section(self):
        ctk.CTkLabel(
            self.root, text="JUGADORES", text_color=MUTED,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(18, 6))

        self.scores_box = ctk.CTkTextbox(
            self.root, fg_color=SURFACE, text_color=TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            corner_radius=12,
        )
        self.scores_box.pack(fill="both", expand=True, padx=20)

        for tag, color in (
            ("palabra_correcta", "#4ade80"),
            ("palabra_incorrecta", "#f87171"),
            ("palabra_omitida", "#f59e0b"),
            ("palabra_typo", "#d97706"),
        ):
            self.scores_box.tag_config(tag, foreground=color)

    # ── Botones de control de partida ──────────────────────────────
    def _build_control_buttons(self):
        run = self.run
        frame = ctk.CTkFrame(self.root, fg_color="transparent")
        frame.pack(pady=18)

        ctk.CTkButton(
            frame, text="▶  Nueva Ronda", width=180, height=40,
            command=lambda: run.socketio.start_background_task(run.action_nueva_ronda),
            fg_color=SURFACE, hover_color=NEUTRAL, text_color=TEXT,
            border_width=1, border_color="#333",
            font=ctk.CTkFont(size=15), corner_radius=8,
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            frame, text="✕  Terminar", width=180, height=40,
            command=lambda: run.socketio.start_background_task(run.action_terminar_partida),
            fg_color=SURFACE, hover_color=NEUTRAL, text_color="#ff5555",
            border_width=1, border_color="#333",
            font=ctk.CTkFont(size=15), corner_radius=8,
        ).pack(side="left", padx=6)

    # ── Cambiar modo / lista de canciones ──────────────────────────
    def _cambiar_modo(self, label):
        run = self.run
        if run.action_cambiar_modo(MODE_LABELS[label]):
            return
        self.selected_mode.set(
            MODE_LABELS_REVERSE.get(run.game_mode, next(iter(MODE_LABELS)))
        )

    def _cambiar_lista(self, nombre):
        if nombre == "Sin listas":
            return

        run = self.run
        nombre_archivo = self.lista_labels[nombre]

        if run.action_cambiar_lista(nombre_archivo):
            return

        self.lista_actual.set(CACHE_LABEL if run.USAR_CACHE else run.LISTA.stem)

    def _refresh_playlists(self):
        """Recarga las playlists disponibles desde disco y actualiza el selector."""
        self.lista_labels = {lista.stem: lista.name for lista in self.run.obtener_listas()}
        self.lista_labels[CACHE_LABEL] = CACHE_VALUE
        self.lista_menu.configure(values=list(self.lista_labels))

    # ── Crear / editar playlist ─────────────────────────────────────
    def _editar_playlist_actual(self):
        nombre = self.lista_actual.get()
        archivo = self.lista_labels.get(nombre)

        if not archivo or archivo == CACHE_VALUE:
            return

        self._abrir_editor_playlist(archivo)

    def _abrir_editor_playlist(self, nombre_archivo=None):
        """Ventana para crear (nombre_archivo=None) o editar una playlist existente."""
        run = self.run
        editando = nombre_archivo is not None

        ventana = _toplevel(
            self.root, "Editar playlist" if editando else "Crear playlist", "700x650"
        )

        nombre_inicial = ""
        contenido_inicial = ""

        if editando:
            ruta = run.DATA_DIR / nombre_archivo
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    contenido_inicial = f.read()
                nombre_inicial = ruta.stem
            except OSError as e:
                ventana.destroy()
                print(f"Error leyendo playlist: {e}")
                return

        ctk.CTkLabel(
            ventana, text="EDITAR PLAYLIST" if editando else "CREAR PLAYLIST",
            text_color=TEXT, font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w", padx=25, pady=(25, 15))

        ctk.CTkLabel(
            ventana, text="Nombre de la playlist", text_color=MUTED,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=25)

        nombre_entry = ctk.CTkEntry(ventana, placeholder_text="Ej. Fiesta verano")
        nombre_entry.pack(fill="x", padx=25, pady=(5, 20))
        if nombre_inicial:
            nombre_entry.insert(0, nombre_inicial)

        ctk.CTkLabel(
            ventana, text="Canciones", text_color=MUTED,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=25)
        ctk.CTkLabel(
            ventana, text="Una canción por línea, en formato: Título - Autor",
            text_color=MUTED, font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=25, pady=(2, 5))

        canciones_text = ctk.CTkTextbox(
            ventana, fg_color=SURFACE, text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        canciones_text.pack(fill="both", expand=True, padx=25, pady=(0, 15))
        if contenido_inicial:
            canciones_text.insert("1.0", contenido_inicial)

        estado_var = tk.StringVar(value="")
        ctk.CTkLabel(
            ventana, textvariable=estado_var, text_color=WARN,
            font=ctk.CTkFont(size=13), wraplength=600,
        ).pack(padx=25, pady=(0, 10))

        def guardar():
            nombre = nombre_entry.get().strip()
            contenido = canciones_text.get("1.0", "end")

            if editando:
                ok, datos = run.action_editar_lista(nombre_archivo, nombre, contenido)
            else:
                ok, datos = run.action_crear_lista(nombre, contenido)

            if not ok:
                estado_var.set(f"⚠️ {datos}")
                return

            self._refresh_playlists()
            self.lista_actual.set(datos["nombre"])
            ventana.destroy()

        botones = ctk.CTkFrame(ventana, fg_color="transparent")
        botones.pack(fill="x", padx=25, pady=(0, 25))

        ctk.CTkButton(
            botones, text="Cancelar", fg_color=NEUTRAL, hover_color=NEUTRAL_HOVER,
            command=ventana.destroy,
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            botones, text="Guardar cambios" if editando else "➕ Crear playlist",
            fg_color=ACCENT, hover_color=ACCENT_HOVER, command=guardar,
        ).pack(side="right")

        nombre_entry.focus()

    # ── Eliminar playlist ────────────────────────────────────────────
    def _eliminar_playlist(self):
        run = self.run
        ventana = _toplevel(self.root, "Eliminar playlist", "500x400")

        ctk.CTkLabel(
            ventana, text="ELIMINAR PLAYLIST", text_color=TEXT,
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w", padx=25, pady=(25, 10))

        ctk.CTkLabel(
            ventana, text="Selecciona la playlist que quieres eliminar:",
            text_color=MUTED, font=ctk.CTkFont(size=13),
        ).pack(anchor="w", padx=25, pady=(0, 15))

        listas_eliminables = [
            lista for lista in run.obtener_listas()
            if lista.resolve() != run.LISTA.resolve()
        ]

        if not listas_eliminables:
            ctk.CTkLabel(
                ventana, text="No hay playlists disponibles para eliminar.",
                text_color=MUTED, font=ctk.CTkFont(size=14),
            ).pack(pady=30)
            ctk.CTkButton(ventana, text="Cerrar", command=ventana.destroy).pack(pady=10)
            return

        nombres = [lista.stem for lista in listas_eliminables]
        seleccion = tk.StringVar(value=nombres[0])

        ctk.CTkOptionMenu(ventana, variable=seleccion, values=nombres).pack(
            fill="x", padx=25, pady=(0, 20)
        )

        estado_var = tk.StringVar(value="")
        ctk.CTkLabel(
            ventana, textvariable=estado_var, text_color=WARN,
            font=ctk.CTkFont(size=13), wraplength=420,
        ).pack(padx=25, pady=(0, 10))

        botones = ctk.CTkFrame(ventana, fg_color="transparent")
        botones.pack(fill="x", padx=25, pady=20)

        def confirmar_eliminacion(nombre, confirmar_ventana):
            nombre_archivo = self.lista_labels[nombre]
            ok, mensaje = run.action_eliminar_lista(nombre_archivo)

            if not ok:
                estado_var.set(f"⚠️ {mensaje}")
                confirmar_ventana.destroy()
                return

            confirmar_ventana.destroy()
            ventana.destroy()
            self._refresh_playlists()

        def eliminar():
            nombre = seleccion.get()
            confirmar = _toplevel(ventana, "Confirmar eliminación", "400x220")

            ctk.CTkLabel(
                confirmar, text="¿Eliminar playlist?", text_color=TEXT,
                font=ctk.CTkFont(size=20, weight="bold"),
            ).pack(pady=(25, 10))

            ctk.CTkLabel(
                confirmar, text=f"¿Seguro que quieres eliminar\n«{nombre}»?",
                text_color=MUTED, font=ctk.CTkFont(size=14), justify="center",
            ).pack(pady=5)

            botones_confirmar = ctk.CTkFrame(confirmar, fg_color="transparent")
            botones_confirmar.pack(pady=20)

            ctk.CTkButton(
                botones_confirmar, text="Cancelar", fg_color=NEUTRAL,
                hover_color=NEUTRAL_HOVER, command=confirmar.destroy,
            ).pack(side="left", padx=5)

            ctk.CTkButton(
                botones_confirmar, text="Eliminar", fg_color=DANGER,
                hover_color=DANGER_HOVER,
                command=lambda: confirmar_eliminacion(nombre, confirmar),
            ).pack(side="left", padx=5)

        ctk.CTkButton(
            botones, text="Cancelar", fg_color=NEUTRAL, hover_color=NEUTRAL_HOVER,
            command=ventana.destroy,
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            botones, text="🗑️ Eliminar", fg_color=DANGER, hover_color=DANGER_HOVER,
            command=eliminar,
        ).pack(side="right")

    # ── Loop de actualización (cada 500 ms) ──────────────────────────
    def _update(self):
        try:
            self._update_header()
            self._update_download_progress()
            self._update_scores()
        except Exception as exc:
            print(f"⚠️ Error en actualizar GUI: {exc}")
            traceback.print_exc()
        self.root.after(UPDATE_INTERVAL_MS, self._update)

    def _update_header(self):
        run = self.run
        self.round_var.set(f"Canción {run.cancion_actual}/{run.ROUNDS} · Ronda {run.ronda_actual}")
        self.timer_var.set(str(run.tiempo_restante) if run.temporizador_activo else "--")

        if run.game_mode == "continue_lyrics":
            ultima_frase = getattr(run.continue_lyrics_game, "last_played_line", "")
            self.last_lyric_var.set(ultima_frase or "—")
        else:
            self.last_lyric_var.set("—")

    def _update_download_progress(self):
        player = self.run.audio_player

        if not player.download_active:
            self.descarga_label_var.set("—")
            self.progressbar.set(0)
            return

        if player.download_phase == "downloading":
            self.descarga_label_var.set(f"⬇  Descargando... {int(player.download_progress * 100)}%")
            self.progressbar.set(player.download_progress)
        elif player.download_phase == "processing":
            self.descarga_label_var.set("⚙  Procesando audio...")
            self.progressbar.set(1.0)

    def _update_scores(self):
        run = self.run
        # Snapshot thread-safe del dict antes de iterar
        puntuaciones = list(run.puntuaciones.items())

        if run.temporizador_activo:
            self._mostrar_jugadores_en_juego(puntuaciones, run.respuestas)
        elif run.panel_reveal:
            self._mostrar_revelacion(run.panel_reveal)
        elif run.panel_ranking_data:
            self._mostrar_lista_puntos(run.panel_ranking_data)
        else:
            ranking = sorted(
                [(n, p) for n, p in puntuaciones if n != "host"],
                key=lambda x: x[1], reverse=True,
            )
            self._mostrar_lista_puntos(ranking)

    def _mostrar_jugadores_en_juego(self, puntuaciones, respuestas):
        jugadores = sorted(
            [(n, p, "✓" if n in respuestas else "·") for n, p in puntuaciones if n != "host"],
            key=lambda x: x[1], reverse=True,
        )
        lines = [f"  {mark}  {nombre}  —  {pts} pts" for nombre, pts, mark in jugadores]
        self._set_scores_text("\n".join(lines).rstrip() or "—  Sin jugadores")

    def _mostrar_lista_puntos(self, ranking):
        lines = [f"  {i + 1}.  {nombre}  —  {pts} pts" for i, (nombre, pts) in enumerate(ranking)]
        self._set_scores_text("\n".join(lines).rstrip() or "—  Sin jugadores")

    def _mostrar_revelacion(self, reveal):
        box = self.scores_box
        box.delete("1.0", "end")
        box.insert("end", f"  {reveal['correcta']}\n\n")

        puntos_totales = dict(self.run.panel_ranking_data)
        for i, respuesta in enumerate(reveal["respuestas"]):
            nombre = respuesta["nombre"]
            total = puntos_totales.get(nombre, 0)
            puntos_ronda = respuesta["puntos"]
            signo = f"+{puntos_ronda}" if puntos_ronda else "+0"
            box.insert("end", f"  {i + 1}. {nombre} - {total} pts ({signo})\n")

            feedback = respuesta["feedback"]
            if feedback is None:
                box.insert("end", f"      {respuesta['texto']}\n\n")
                continue

            box.insert("end", "      ")
            for palabra in feedback:
                box.insert("end", f"{palabra['word']} ", self._tag_para_palabra(palabra))
            box.insert("end", "\n\n")

    @staticmethod
    def _tag_para_palabra(palabra):
        if palabra["correct"]:
            return "palabra_correcta"
        if palabra["omitted"]:
            return "palabra_omitida"
        if palabra["typo"]:
            return "palabra_typo"
        return "palabra_incorrecta"

    def _set_scores_text(self, text):
        self.scores_box.delete("1.0", "end")
        self.scores_box.insert("1.0", text)


def crear_panel_host():
    """Punto de entrada: crea y lanza el panel de control del host."""
    run = sys.modules["__main__"]
    HostPanel(run).run_forever()