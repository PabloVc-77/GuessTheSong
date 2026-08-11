# GuessTheSong

Multiplayer party game where players identify songs from short audio clips or test their knowledge of song lyrics. The host runs the game from a desktop control panel, while players join from their phones on the same local network.

The project currently includes **two game modes**:

* **Adivina la canción** — identify the song and artist from an audio clip.
* **Continúa la letra** — listen to a fragment and type the continuation of the lyrics.

---

## 🎵 Game modes

### ❓ Guess the song

The original game mode. Players hear a short fragment of a randomly selected song and try to identify it.

1. Start the game on the host PC.
2. Players scan the QR code displayed by the host and enter their name.
3. The host starts a round and a random song is selected.
4. A short audio fragment is played through the host's speakers.
5. Players submit the **song title** and **artist** from their phones.
6. When everyone has answered, or the timer expires, the answers and scores are shown.
7. The next song starts automatically.

#### Scoring

| Match                  | Points |
| ---------------------- | -----: |
| Correct title          |     +2 |
| Correct artist         |     +1 |
| Correct title + artist |     +4 |

Guesses are compared without considering case or accents.

---

### 🎤 Continue the lyrics

A second game mode where players have to **continue the lyrics of a song** instead of identifying it.

The game uses synchronised lyrics to select a point in the song. Players hear the part immediately before that point and must write what comes next.

#### How it works

1. A song is selected from the configured song list.
2. The song's synchronised lyrics are retrieved.
3. A valid point in the lyrics is selected.
4. The audio immediately before that point is played.
5. Players type the continuation of the lyrics.
6. The answer is compared **word by word** with the expected lyrics.
7. The host interface displays the result using different colours.
8. The score is calculated from the player's answer.

#### Answer correction

The correction system allows players to make small mistakes without immediately invalidating their entire answer.

| Colour    | Meaning                               |
| --------- | ------------------------------------- |
| 🟢 Green  | Correct word                          |
| 🟡 Yellow | Word from the lyrics that was omitted |
| 🔴 Red    | Incorrect word                        |

The comparison keeps track of **consecutive errors**:

* A correct word resets the consecutive-error counter.
* Up to **2 consecutive omissions/errors** can be tolerated.
* When the player reaches the **3rd consecutive omission/error**, the answer is considered finished.
* Everything written after that point is marked **red** without continuing to compare it with the lyrics.

This prevents the correction system from continuing through a completely incorrect answer while still allowing small mistakes.

#### Perfect answer

A completely correct continuation receives a **+5 point bonus**.

The bonus is only awarded when the answer contains no omissions or incorrect words.

---

## ⏱️ +30 seconds

The game includes a **+30 seconds** mechanic that players can request during a song.

Once the extension has been accepted:

* The extra 30 seconds are applied to the current song.
* The **+30 button is disabled** so it cannot be applied multiple times during the same song.
* The button is enabled again when the next song starts.

This prevents players from repeatedly extending the same song.

---

## 💾 Audio cache

Songs downloaded by the game are stored locally so they do not have to be downloaded again every time they are selected.

The cache is organised by song:

```text
Cache/
└── Songs/
    └── Artist - Song/
        ├── Artist - Song.mp3
        └── fragment.wav
```

### MP3

The `.mp3` file is the persistent part of the cache.

When a song is selected:

1. The game checks whether its MP3 already exists.
2. If it exists, it is reused.
3. If it does not exist, the song is downloaded and stored in the cache.
4. Future rounds can use the cached file without downloading it again.

### WAV fragment

`fragment.wav` contains the audio fragment that is currently being played.

It is deliberately overwritten whenever a new fragment is generated.

The cache can therefore be safely cleared by deleting:

```text
Cache/Songs/
```

---

## 📝 Lyrics cache

Synchronised lyrics are also cached locally.

This prevents the game from repeatedly requesting the lyrics for songs that have already been processed.

The lyrics cache is separate from the audio cache.

---

## 🌐 Multiplayer

The game uses a local web server and Socket.IO for communication between the host and players.

The host runs the game from the computer while players connect from their phones.

All devices should be connected to the **same local network**.

Players do not need to install anything.

---

## 🖥️ Host interface

The host interface provides:

* Player list.
* Current round and song.
* Countdown timer.
* Scores.
* QR code for joining.
* Game controls.
* Audio/download progress.
* Results.
* Lyrics correction for **Continúa la letra**.
* +30 seconds control.

When a song is already cached, the host still displays a short loading phase so that the transition between songs remains visually consistent.

---

## ⚙️ Requirements

* **Python 3.10+**
* **FFmpeg** available in `PATH`
* Internet connection for downloading songs and retrieving lyrics the first time.
* All devices connected to the same local network.

---

## 🚀 Installation

Clone the repository:

```bash
git clone https://github.com/PabloVc-77/GuessTheSong.git
cd GuessTheSong
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Or on macOS/Linux:

```bash
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

Make sure FFmpeg is installed and available from the command line:

```bash
ffmpeg -version
```

---

## ▶️ Running the game

Start the application with:

```bash
python run.py
```

The application starts the local web server and the host interface.

The host interface displays the address/QR code that players can use to join the game.

---

## ⚙️ Configuration

The main game configuration is defined in `run.py`.

Some of the main parameters are:

| Variable     | Description                  |
| ------------ | ---------------------------- |
| `LISTA`      | Song list used by the game   |
| `T_FRAGMENT` | Length of the audio fragment |
| `T_RESP`     | Time available to answer     |
| `ROUNDS`     | Number of songs in a round   |

The **Continúa la letra** mode has additional parameters related to lyric selection and answer evaluation.

---

## 🎶 Song lists

Songs are stored in plain text files, with one song per line.

Example:

```text
Song Title - Artist Name
```

The repository contains song lists that can be selected from the game configuration.

---

## 📁 Project structure

```text
GuessTheSong/
│
├── run.py
├── gui.py
├── audio.py
├── lyrics.py
│
├── games/
│   ├── guess_song.py
│   └── continue_lyrics.py
│
├── templates/
│   ├── guess_song.html
│   └── continue_lyrics.html
│
├── static/
│   ├── guess_song.js
│   ├── continue_lyrics.js
│   └── ...
│
├── Cache/
│   ├── Lyrics/
│   └── Songs/
│
├── Olaf.txt
├── Misito.txt
├── requirements.txt
└── README.md
```

### Main components

#### `run.py`

Main application entry point.

Handles:

* Web server.
* Socket.IO communication.
* Players.
* Rounds.
* Timers.
* Game flow.
* Communication with the game modes.

#### `gui.py`

Desktop interface used by the host.

#### `audio.py`

Common audio management layer.

Responsible for:

* Downloading songs.
* Persistent MP3 cache.
* Extracting audio fragments.
* Playing fragments.
* Reporting download/loading progress.

#### `lyrics.py`

Responsible for retrieving, parsing and caching synchronised lyrics.

#### `games/guess_song.py`

Implementation of the original song identification mode.

#### `games/continue_lyrics.py`

Implementation of the lyrics continuation mode.

It handles:

* Selecting lyric fragments.
* Selecting the corresponding audio section.
* Evaluating player answers.
* Detecting omissions and errors.
* Calculating the score.
* Perfect-answer bonuses.

---

## 🏗️ Architecture

The project separates the common game infrastructure from the individual game modes.

The main application handles the multiplayer infrastructure, while each game mode implements its own rules.

```text
                    ┌──────────────┐
                    │    run.py    │
                    │ Game server  │
                    └──────┬───────┘
                           │
              ┌────────────┴────────────┐
              │                         │
       ┌──────▼──────┐          ┌──────▼──────────┐
       │ Guess Song  │          │ Continue Lyrics │
       └──────┬──────┘          └──────┬──────────┘
              │                        │
              └────────────┬───────────┘
                           │
                    ┌──────▼──────┐
                    │   audio.py  │
                    └──────┬──────┘
                           │
                 ┌─────────▼─────────┐
                 │   Cache/Songs     │
                 └───────────────────┘
```

This structure makes it easier to add additional game modes in the future without putting all game-specific logic into `run.py`.

---

## 🔧 Troubleshooting

### Players cannot connect

Make sure:

* The host and players are connected to the same network.
* Windows Firewall allows Python to communicate through private networks.
* Port `7777` is accessible from the local network.

### A song takes a long time to start

The first time a song is selected, it needs to be downloaded.

Once downloaded, the MP3 is stored in:

```text
Cache/Songs/
```

Future uses of the same song should be significantly faster.

### The lyrics cannot be found

The lyrics mode depends on synchronised lyrics being available for the selected song.

If synchronised lyrics cannot be obtained, the game may need to select another song/lyric section.

---

## 📌 Future possibilities

The architecture allows additional game modes to be added in the future, using the same:

* Multiplayer infrastructure.
* Host interface.
* Audio system.
* Song cache.
* Player connection system.

Possible future modes could reuse the same songs and audio cache without downloading them again.
