import tkinter as tk
import customtkinter as ctk
from PIL import Image
import qrcode

import run

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")

BG       = "#0f0f0f"
SURFACE  = "#1a1a1a"
ACCENT   = "#1db954"   # verde Spotify-ish
TEXT     = "#e0e0e0"
MUTED    = "#666666"
WARN     = "#ffaa00"


def crear_panel_host():
    url = f"http://{run.obtener_ip_local()}:7777"

    root = ctk.CTk()
    root.title("Panel de Control · Adivina la Canción")
    root.configure(fg_color=BG)
    root.resizable(True, True)
    root.minsize(300, 520)

    # --- URL ---
    ctk.CTkLabel(root, text="Dirección para jugadores",
                 text_color=MUTED, font=ctk.CTkFont(size=11)).pack(pady=(20, 2))
    ctk.CTkLabel(root, text=url, text_color=ACCENT,
                 font=ctk.CTkFont(family="Courier New", size=13, weight="bold")).pack()

    # --- QR ---
    qr_pil = qrcode.make(url).resize((160, 160), Image.LANCZOS).convert("RGB")
    qr_img = ctk.CTkImage(light_image=qr_pil, dark_image=qr_pil, size=(160, 160))
    ctk.CTkLabel(root, image=qr_img, text="").pack(pady=12)

    # --- Info de ronda ---
    round_var = tk.StringVar()
    ctk.CTkLabel(root, textvariable=round_var,
                 text_color=TEXT, font=ctk.CTkFont(size=13, weight="bold")).pack()

    # --- Temporizador ---
    timer_frame = ctk.CTkFrame(root, fg_color="transparent")
    timer_frame.pack(pady=4)
    ctk.CTkLabel(timer_frame, text="Tiempo: ",
                 text_color=MUTED, font=ctk.CTkFont(size=12)).pack(side="left")
    timer_var = tk.StringVar(value="--")
    ctk.CTkLabel(timer_frame, textvariable=timer_var,
                 text_color=WARN, font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

    # --- Barra de descarga ---
    prog_frame = ctk.CTkFrame(root, fg_color="transparent")
    prog_frame.pack(fill="x", padx=18, pady=(8, 0))
    descarga_label_var = tk.StringVar(value="")
    ctk.CTkLabel(prog_frame, textvariable=descarga_label_var,
                 text_color=MUTED, font=ctk.CTkFont(size=11), anchor="w").pack(fill="x")
    progressbar = ctk.CTkProgressBar(prog_frame, progress_color=ACCENT,
                                     fg_color=SURFACE, height=8, corner_radius=4)
    progressbar.set(0)
    progressbar.pack(fill="x", pady=(3, 0))

    # --- Cuadro de jugadores ---
    ctk.CTkLabel(root, text="JUGADORES",
                 text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).pack(pady=(16, 4))
    scores_box = ctk.CTkTextbox(root, fg_color=SURFACE, text_color=TEXT,
                                font=ctk.CTkFont(family="Courier New", size=12),
                                corner_radius=8, state="disabled")
    scores_box.pack(padx=15, fill="both", expand=True)

    # --- Botones ---
    btn_frame = ctk.CTkFrame(root, fg_color="transparent")
    btn_frame.pack(pady=18)
    ctk.CTkButton(btn_frame, text="▶  Nueva Ronda", width=140,
                  command=lambda: run.socketio.start_background_task(run.action_nueva_ronda),
                  fg_color=SURFACE, hover_color="#2a2a2a", text_color=TEXT,
                  border_width=1, border_color="#333333",
                  font=ctk.CTkFont(size=12), corner_radius=8).pack(side="left", padx=6)
    ctk.CTkButton(btn_frame, text="✕  Terminar", width=140,
                  command=lambda: run.socketio.start_background_task(run.action_terminar_partida),
                  fg_color=SURFACE, hover_color="#2a2a2a", text_color="#ff5555",
                  border_width=1, border_color="#333333",
                  font=ctk.CTkFont(size=12), corner_radius=8).pack(side="left", padx=6)

    # --- Loop de actualización (500 ms) ---
    def actualizar():
        round_var.set(f"Canción {run.cancion_actual}/{run.ROUNDS} · Ronda {run.ronda_actual}")
        timer_var.set(str(run.tiempo_restante) if run.temporizador_activo else "--")

        if run.descarga_activa:
            if run.descarga_fase == "descargando":
                descarga_label_var.set(f"⬇  Descargando... {int(run.descarga_progreso * 100)}%")
                progressbar.set(run.descarga_progreso)
            elif run.descarga_fase == "procesando":
                descarga_label_var.set("⚙  Procesando audio...")
                progressbar.set(1.0)
        else:
            descarga_label_var.set("")
            progressbar.set(0)

        scores_box.configure(state="normal")
        scores_box.delete("1.0", "end")
        if run.temporizador_activo:
            for nombre, pts in run.puntuaciones.items():
                if nombre == "host":
                    continue
                mark = "✓" if nombre in run.respuestas else " "
                scores_box.insert("end", f"[{mark}] {nombre}: {pts} pts\n")
        elif run.panel_ranking_texto:
            scores_box.insert("end", run.panel_ranking_texto)
        else:
            for nombre, pts in run.puntuaciones.items():
                if nombre == "host":
                    continue
                scores_box.insert("end", f"{nombre}: {pts} pts\n")
        scores_box.configure(state="disabled")

        root.after(500, actualizar)

    root.after(500, actualizar)
    root.mainloop()
