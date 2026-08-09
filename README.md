# Adivina la Canción

Party game where players hear a short audio sample and guess the **song title** and **artist**. The host runs a desktop control panel; players join from their phones on the same Wi‑Fi.

## How it works

1. Start the game on the host PC — a control panel opens with a QR code.
2. Players scan the QR (or open the URL) and enter a name.
3. The host clicks **Nueva Ronda**. A random song is picked from the list, a short clip is downloaded and played.
4. Players type their guess on their phones before the timer ends.
5. When everyone has answered (or time runs out), scores update and the main screen shows the correct answer plus each player's guess.
6. Repeat for the configured number of songs, then start another round or end the game.

### Scoring

| Match | Points |
|-------|--------|
| Title | +2 |
| Artist | +1 |
| Both | +4 |

Guesses are matched as substrings (case- and accent-insensitive).

Players can request **+30 seconds**; if *everyone* asks, the extra time is added.

## Requirements

- **Python 3.10+**
- **[FFmpeg](https://ffmpeg.org/)** on your `PATH` (used to cut the audio fragment)
- Network access (YouTube audio is fetched with `yt-dlp`)
- Host and players on the same local network

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python run.py
```

This starts:

- A **web server** on port `7777` (`http://<your-local-ip>:7777`) for players
- The **host panel** (CustomTkinter) with QR code, timer, scores, and round controls

## Configuration

Edit the parameters at the top of `run.py`:

| Variable | Default | Meaning |
|----------|---------|---------|
| `LISTA` | `Olaf.txt` | Song list file |
| `T_FRAGMENT` | `5` | Clip length in seconds |
| `T_RESP` | `45` | Guessing time in seconds |
| `ROUNDS` | `10` | Songs per round |

### Song lists

Plain text files, one song per line:

```text
Song Title - Artist Name
```

Included lists: `Olaf.txt`, `Misito.txt`. Switch with `LISTA = 'Misito.txt'` in `run.py`.

## Project layout

```text
run.py              # Game server, scoring, audio download/playback
gui.py              # Host control panel
templates/host.html # Player web UI
static/             # Player JS / CSS
Olaf.txt            # Song list
Misito.txt          # Alternate song list
requirements.txt
```

## Tips

- Keep the host speakers loud enough for everyone; players only guess from their phones — they do not hear the clip through the browser.
- A firewall prompt may appear the first time; allow local network access so phones can reach port `7777`.
- If a clip fails to download, the game retries with another random song.
