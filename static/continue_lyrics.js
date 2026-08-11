let socket = io({
    transports: ['polling']
});

let jugador = "";


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


socket.on("connect", () => {
    if (jugador) {
        socket.emit("registrar", jugador);
    }
});


function registrarse() {
    jugador = document
        .getElementById("nombre")
        .value
        .trim()
        .toLowerCase();

    if (!jugador) {
        alert("Introduce un nombre válido");
        return;
    }

    socket.emit("registrar", jugador);
}


function enviarRespuesta() {
    const texto = document
        .getElementById("respuesta")
        .value
        .trim();

    if (!texto) {
        alert("Escribe una respuesta");
        return;
    }

    socket.emit("respuesta", {
        nombre: jugador,
        respuesta: texto
    });

    document.getElementById("resultado")
        .innerText = "Respuesta enviada.";

    document.getElementById("respuesta").disabled = true;
}


socket.on("registrado", msg => {

    document.getElementById("registro")
        .style.display = "none";

    document.getElementById("juego")
        .style.display = "block";

    document.getElementById("bienvenida")
        .innerText = msg;
});


socket.on("estado", msg => {
    document.getElementById("estado")
        .innerText = msg;
});


socket.on("resultado", msg => {
    const result = document.getElementById("resultado");

    if (typeof msg === "object" && msg !== null) {
        result.innerText = `✅ ${msg.correct_words} palabras correctas · +${msg.points} puntos`;
        mostrarFeedback(msg.word_feedback || []);
        return;
    }

    result.innerText = msg;
});


socket.on("temporizador", seg => {
    document.getElementById("temporizador")
        .innerText = seg;
});


socket.on("nueva_ronda_letra", () => {
    document.getElementById("respuesta").value = "";
    document.getElementById("respuesta").disabled = false;
    document.getElementById("resultado").innerText = "";
    document.getElementById("feedback-palabras").replaceChildren();
});


function mostrarFeedback(words) {
    const container = document.getElementById("feedback-palabras");
    container.replaceChildren();

    for (const item of words) {
        const word = document.createElement("span");
        word.className = item.correct ? "palabra-correcta" : item.omitted ? "palabra-omitida" : "palabra-incorrecta";
        word.textContent = item.word;
        container.appendChild(word);
    }
}

socket.on("plus_30s_solicitado", () => {
    marcar30sSolicitado();
});


socket.on("nueva_ronda_jugador", () => {
    reiniciar30s();
});
