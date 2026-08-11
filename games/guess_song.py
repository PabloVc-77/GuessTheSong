import unicodedata


def normalizar(texto):
    texto = texto.lower()

    texto = unicodedata.normalize(
        "NFD",
        texto
    )

    texto = texto.encode(
        "ascii",
        "ignore"
    ).decode("utf-8")

    return texto


def evaluar_respuesta(
    respuesta,
    titulo,
    artista
):
    respuesta_normalizada = normalizar(respuesta)

    titulo_normalizado = normalizar(titulo)
    artista_normalizado = normalizar(artista)

    puntos = 0
    aciertos = []

    if titulo_normalizado in respuesta_normalizada:
        puntos += 2
        aciertos.append("🎵 título")

    if artista_normalizado in respuesta_normalizada:
        puntos += 1
        aciertos.append("👤 artista")

    if puntos == 3:
        puntos = 4

    return {
        "puntos": puntos,
        "aciertos": aciertos
    }


def respuesta_correcta(titulo, artista):
    return f"{titulo} - {artista}"