let socket = io({ transports: ['polling'] });
let jugador = "";
let respuestaEnviada = false;

// Re-registrar automáticamente si el socket reconecta
socket.on("connect", () => {
  if (jugador) socket.emit("registrar", jugador);
});

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

// Modal
function mostrarModal(msg) {
  document.getElementById("final-scores").innerText = msg || "";
  document.getElementById("modal").style.display = "flex";
  lanzarConfeti();
}

document.getElementById("close-modal").addEventListener("click", () => {
  document.getElementById("modal").style.display = "none";
});

// Registro
function registrarse() {
  jugador = document.getElementById("nombre").value.trim().toLowerCase();
  if (!jugador) return alert("Introduce un nombre válido");
  socket.emit("registrar", jugador);
}

// Respuesta
function enviarRespuesta() {
  const texto = document.getElementById("respuesta").value.trim();
  if (!texto) return alert("Escribe una respuesta");
  enviarRespuestaAlServidor(texto, false);
}

// Envía la respuesta al servidor una única vez por ronda.
// automatica=true cuando se envía porque se acabó el tiempo.
function enviarRespuestaAlServidor(texto, automatica) {
  if (respuestaEnviada) return;
  respuestaEnviada = true;

  socket.emit("respuesta", { nombre: jugador, respuesta: texto });

  document.getElementById("resultado").innerText = automatica
    ? "⏰ Tiempo agotado. Se envió tu respuesta automáticamente."
    : "Respuesta enviada.";
  document.getElementById("respuesta").disabled = true;
}

// +30s
function solicitarTiempo() {
  const boton = document.getElementById("solicitar-30s");

  if (boton.disabled) return;

  socket.emit("pedir_30s", jugador);
}

function marcar30sSolicitado() {
  const boton = document.getElementById("solicitar-30s");

  boton.disabled = true;
  boton.innerText = "🕒 +30s solicitado";
  document.getElementById("resultado").innerText =
    "🕒 Has solicitado +30 segundos.";
}

function reiniciar30s() {
  const boton = document.getElementById("solicitar-30s");

  boton.disabled = false;
  boton.innerText = "🕒 Solicitar +30s";
}

// Eventos del servidor
socket.on("registrado", msg => {
  document.getElementById("registro").style.display = "none";
  document.getElementById("juego").style.display = "block";
  document.getElementById("bienvenida").innerText = msg;
});

socket.on("estado",      msg     => document.getElementById("estado").innerText = msg);
socket.on("resultado",   msg     => document.getElementById("resultado").innerText = msg);
socket.on("temporizador", seg    => document.getElementById("temporizador").innerText = seg);
socket.on("mostrar_popup_ronda", msg => {
  mostrarModal(msg);
});

socket.on("tiempo_agotado", () => {
  const texto = document.getElementById("respuesta").value.trim();
  enviarRespuestaAlServidor(texto, true);
});

socket.on("nueva_ronda_jugador", () => {
  respuestaEnviada = false;
  document.getElementById("respuesta").value = "";
  document.getElementById("respuesta").disabled = false;
  document.getElementById("resultado").innerText = "";
  reiniciar30s();
});

socket.on("plus_30s_solicitado", () => {
  marcar30sSolicitado();
});