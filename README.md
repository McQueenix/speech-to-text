# Speech to Text — Real-time Multilingual Transcription

Speak into your browser in **Hindi, English or a mix of both** ("Kal meeting hai, please send the report") and watch the words appear as you talk. Every recording is saved to a **PostgreSQL** database and shown in a **history dashboard** with full CRUD (create, read, update, delete), search and text-to-speech playback.

Built for the Procucev AI Tech Hiring Assignment (Assignment 1: Real-time Transcription).

## Features

- **Real-time transcription.** Mic audio streams to the server over a WebSocket and on to the **Gemini Live API** (`gemini-3.5-transcribe-live`). Interim words show in grey while you speak, and finalised text in black.
- **Multilingual and code-switching.** Automatic language detection handles Hindi-English mixing. You can also give a language hint (Hindi, English, Hindi + English, Tamil).
- **Saved history.** Each recording is stored with its title, text, language, duration and timestamps.
- **Dashboard CRUD.** List with pagination, search, create a manual entry, edit, delete, copy.
- **Text to speech.** "▶ Play" reads any saved transcription aloud using the browser's built-in speech synthesis (Hindi voice for Devanagari text, Indian English otherwise). Needs no API key.
- **Swappable speech engine.** The engine sits behind a small `Transcriber` interface in `app/live.py`, so a self-hosted model such as faster-whisper can be plugged in without touching the rest of the app.
- **Tested.** 11 pytest tests cover the CRUD API and the live WebSocket flow, using a fake speech engine.

## Architecture

```
Browser (mic)                           FastAPI server                      Gemini Live API
─────────────                           ──────────────                      ───────────────
AudioWorklet → 16 kHz PCM  ──WS──▶  /ws/transcribe  ──send_realtime_input──▶  transcribe-live
live text  ◀── interim/final JSON ──                ◀── interim/final text ──
                                           │ on Stop
                                           ▼
                                     PostgreSQL (transcriptions)
Dashboard  ◀──── REST /api/transcriptions (GET, POST, PUT, DELETE) ────▶
```

| Layer | Tech |
|---|---|
| Backend | Python 3.12, FastAPI, WebSockets |
| Database | PostgreSQL (SQLAlchemy 2 + psycopg 3); falls back to SQLite for local dev |
| Speech to text | Gemini Live API, `gemini-3.5-transcribe-live` (google-genai SDK) |
| Text to speech | Web Speech API (browser built-in) |
| Frontend | Plain HTML/CSS/JS with an AudioWorklet for PCM capture |

## Project structure

```
app/
  main.py                 FastAPI app, static files, health check
  config.py               Settings from environment variables
  database.py             SQLAlchemy engine and session
  models.py               Transcription table
  schemas.py              Pydantic request/response models
  crud.py                 Database operations
  live.py                 WebSocket ↔ Gemini Live streaming
  routers/transcriptions.py   REST CRUD endpoints
static/
  index.html, style.css, app.js   Dashboard UI
  pcm-worklet.js          Mic → 16 kHz 16-bit PCM downsampler
tests/                    pytest suite
render.yaml               One-click Render deployment (web + Postgres)
```

## Run locally

```bash
git clone https://github.com/McQueenix/speech-to-text.git
cd speech-to-text
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then paste your key into GEMINI_API_KEY
uvicorn app.main:app --reload
```

Open http://localhost:8000, press **Start speaking**, allow the microphone, talk, then press **Stop & save**.

- Get a free Gemini key at https://aistudio.google.com/apikey.
- With no `DATABASE_URL`, data goes to a local SQLite file. For PostgreSQL, set `DATABASE_URL=postgresql://user:pass@localhost:5432/dbname`. Tables are created automatically on startup.
- Interactive API docs are at http://localhost:8000/docs.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Deploy (Render, free)

1. Push this repo to GitHub.
2. On [Render](https://render.com), choose **New → Blueprint** and select the repo. `render.yaml` creates a free PostgreSQL database and the web service.
3. Paste your `GEMINI_API_KEY` when prompted.
4. Open the `https://…onrender.com` URL. The site needs HTTPS for microphone access, which Render provides.

## API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/transcriptions?skip=0&limit=20&q=` | List and search, newest first |
| `POST` | `/api/transcriptions` | Create `{title, text, language}` |
| `GET` | `/api/transcriptions/{id}` | Read one |
| `PUT` | `/api/transcriptions/{id}` | Update any of `title`, `text`, `language` |
| `DELETE` | `/api/transcriptions/{id}` | Delete |
| `WS` | `/ws/transcribe?lang=auto` | Stream 16 kHz PCM frames, then send `{"type":"stop"}` |
| `GET` | `/api/health` | Status and configured engine |

**WebSocket messages from the server:** `ready`, `interim {text}`, `final {text}`, `saved {transcription}`, `empty`, `error {message}`.

## Notes and limitations

- A single Gemini Live session supports up to about 10 minutes of continuous audio.
- Text-to-speech uses the browser's voices, so quality depends on the operating system. An open-source engine such as Piper could replace it on the server side.
