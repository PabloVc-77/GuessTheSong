let socket = io();
let jugador = "";
let esHost = false;

// Dark/Light toggle
document.getElementById('mode-toggle').addEventListener('click', () => {
  document.body.classList.toggle('light');
});

// Confetti generator
function lanzarConfeti() {
  const emojis = ["🐐","🐐","🐐","🐐"];
  for (let i=0; i<30; i++) {
    const conf = document.createElement("div");
    conf.className = "confetti";
    conf.textContent = emojis[Math.floor(Math.random()*emojis.length)];
    conf.style.left = Math.random() * 100 + "vw";
    conf.style.animationDuration = (3 + Math.random()*2) + "s";
    document.body.appendChild(conf);
    setTimeout(() => conf.remove(), 5000);
  }
}

// Modal logic
function mostrarFinal() {
  // Show modal
  const modal = document.getElementById("modal");
  const scores = document.getElementById("puntuaciones").innerText;
  document.getElementById("final-scores").innerText = scores;
  modal.style.display = "flex";
  lanzarConfeti();
}

document.getElementById("close-modal").addEventListener("click", () => {
  document.getElementById("modal").style.display = "none";
});

// Socket.io functions
function registrarse() {
  jugador = document.getElementById("nombre").value.trim().toLowerCase();
  if (!jugador) return alert("Introduce un nombre válido");
  socket.emit("registrar", jugador);
}

function enviarRespuesta() {
  const texto = document.getElementById("respuesta").value.trim();
  if (!texto) return alert("Escribe una respuesta");
  socket.emit("respuesta", { nombre: jugador, respuesta: texto });
  document.getElementById("resultado").innerText = "Respuesta enviada.";
}

function nuevaRonda() { socket.emit("nueva_ronda"); }
function solicitarTiempo() {
  socket.emit("pedir_30s", jugador);
  document.getElementById("resultado").innerText = "🕒 Has solicitado +30 segundos.";
}

socket.on("registrado", msg => {
  document.getElementById("registro").style.display = "none";
  document.getElementById("juego").style.display = "block";
  document.getElementById("bienvenida").innerText = msg;
  if (jugador === "host") {
    esHost = true;
    document.getElementById("panel_host").style.display = "block";
    document.getElementById("panel_jugador").style.display = "none";
    document.getElementById("qr-contenedor").style.display = "flex";
    if (esHost) {
        document.getElementById("url").innerText = document.body.dataset.url;
        document.getElementById("qr").src = "data:image/png;base64," + document.body.dataset.qr;
    }

  } 
});

socket.on("round", msg => {document.getElementById("bienvenida").innerText = msg;});

socket.on("estado", msg => document.getElementById("estado").innerText = msg);
socket.on("resultado", msg => document.getElementById("resultado").innerText = msg);
socket.on("temporizador", segundos => document.getElementById("temporizador").innerText = segundos);
socket.on("puntuaciones", texto => document.getElementById("puntuaciones").innerText = texto);
socket.on("mostrar_popup_ronda", msg => {
  mostrarFinal();
});