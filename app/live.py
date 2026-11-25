"""Real-time transcription over WebSocket.

Flow:
    Browser mic --(16 kHz PCM, binary frames)--> /ws/transcribe --> Gemini Live API
    Browser     <--(JSON interim/final text)---- /ws/transcribe <-- Gemini Live API

When the user presses Stop, the browser sends {"type": "stop"}. The server ends
the audio stream, waits briefly for the last final transcript, saves the whole
text to the database and replies with {"type": "saved", ...}.

The speech engine sits behind a small interface (`Transcriber`) so it can be
swapped for a self-hosted model (e.g. faster-whisper) or faked in tests.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncContextManager, AsyncIterator, Callable, Optional, Protocol

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app import crud, schemas
from app.config import get_settings
from app.database import SessionLocal

log = logging.getLogger(__name__)
router = APIRouter()


# --------------------------------------------------------------------------- #
# Speech engine interface
# --------------------------------------------------------------------------- #
class Transcriber(Protocol):
    async def send_audio(self, pcm16k: bytes) -> None: ...
    async def end_audio(self) -> None: ...
    def events(self) -> AsyncIterator[tuple[str, str]]: ...  # ("interim"|"final", text)


# Takes language codes, returns an async context manager that yields a Transcriber
TranscriberFactory = Callable[[list[str]], AsyncContextManager[Transcriber]]


class GeminiTranscriber:
    """Thin wrapper around a Gemini Live API transcription session."""

    def __init__(self, session):
        self._session = session

    async def send_audio(self, pcm16k: bytes) -> None:
        from google.genai import types

        await self._session.send_realtime_input(
            audio=types.Blob(data=pcm16k, mime_type="audio/pcm;rate=16000")
        )

    async def end_audio(self) -> None:
        await self._session.send_realtime_input(audio_stream_end=True)

    async def events(self) -> AsyncIterator[tuple[str, str]]:
        # session.receive() ends after each completed turn, so keep re-entering
        # it until the connection stops delivering messages.
        while True:
            got_any = False
            async for response in self._session.receive():
                got_any = True
                sc = response.server_content
                if not sc:
                    continue
                if sc.interim_input_transcription and sc.interim_input_transcription.text:
                    yield "interim", sc.interim_input_transcription.text
                if sc.input_transcription and sc.input_transcription.text:
                    yield "final", sc.input_transcription.text
            if not got_any:
                return


def gemini_factory() -> Optional[TranscriberFactory]:
    """Returns a factory for Gemini sessions, or None if no API key is set."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return None

    @asynccontextmanager
    async def _open(language_codes: list[str]):
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini_api_key)
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            input_audio_transcription=types.AudioTranscriptionConfig(
                # [] = automatic detection, which also handles Hindi-English code-switching
                language_codes=language_codes,
            ),
        )
        async with client.aio.live.connect(model=settings.gemini_model, config=config) as session:
            yield GeminiTranscriber(session)

    return _open


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_language(lang: str) -> list[str]:
    lang = (lang or "auto").strip()
    if lang.lower() == "auto":
        return []
    return [code.strip() for code in lang.split(",") if code.strip()][:5]


def make_title(text: str, max_words: int = 8) -> str:
    words = text.split()
    title = " ".join(words[:max_words])
    if len(words) > max_words:
        title += "…"
    return title[:200] or "Untitled recording"


def join_segments(segments: list[str]) -> str:
    return " ".join(s.strip() for s in segments if s and s.strip())


# --------------------------------------------------------------------------- #
# WebSocket endpoint
# --------------------------------------------------------------------------- #
@router.websocket("/ws/transcribe")
async def transcribe(
    ws: WebSocket,
    lang: str = "auto",
    factory: Optional[TranscriberFactory] = Depends(gemini_factory),
):
    await ws.accept()
    if factory is None:
        await ws.send_json({"type": "error", "message": "GEMINI_API_KEY is not configured on the server."})
        await ws.close()
        return

    settings = get_settings()
    language_codes = parse_language(lang)
    state = {"finals": [], "interim": ""}
    started = time.monotonic()
    stopped = False
    engine_error: Optional[str] = None

    try:
        async with factory(language_codes) as engine:
            await ws.send_json({"type": "ready"})

            async def pump_results():
                async for kind, text in engine.events():
                    if kind == "interim":
                        state["interim"] = text
                    else:
                        state["finals"].append(text)
                        state["interim"] = ""
                    await ws.send_json({"type": kind, "text": text})

            results_task = asyncio.create_task(pump_results())

            try:
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    if msg.get("bytes"):
                        if results_task.done():
                            break  # engine died; fall through to error reporting
                        await engine.send_audio(msg["bytes"])
                    elif msg.get("text"):
                        try:
                            data = json.loads(msg["text"])
                        except json.JSONDecodeError:
                            continue
                        if data.get("type") == "stop":
                            stopped = True
                            break
            except WebSocketDisconnect:
                pass

            if stopped and not results_task.done():
                # Flush: tell the engine no more audio is coming and wait for the
                # final transcript of whatever was still being spoken.
                await engine.end_audio()
                deadline = time.monotonic() + settings.final_wait_seconds
                while time.monotonic() < deadline and state["interim"] and not results_task.done():
                    await asyncio.sleep(0.1)
                await asyncio.sleep(0.3)

            if results_task.done() and not results_task.cancelled() and results_task.exception():
                engine_error = str(results_task.exception())
            results_task.cancel()
    except Exception as exc:  # connection to the speech engine failed
        log.exception("Live transcription failed")
        engine_error = str(exc)

    if engine_error:
        await _safe_send(ws, {"type": "error", "message": f"Speech engine error: {engine_error}"})

    if stopped:
        text = join_segments(state["finals"] + [state["interim"]])
        if text:
            db = SessionLocal()
            try:
                row = crud.create(
                    db,
                    title=make_title(text),
                    text=text,
                    language=lang or "auto",
                    source="live",
                    duration_seconds=time.monotonic() - started,
                )
                out = schemas.TranscriptionOut.model_validate(row).model_dump(mode="json")
            finally:
                db.close()
            await _safe_send(ws, {"type": "saved", "transcription": out})
        else:
            await _safe_send(ws, {"type": "empty", "message": "No speech was detected."})

    try:
        await ws.close()
    except RuntimeError:
        pass


async def _safe_send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_json(payload)
    except (RuntimeError, WebSocketDisconnect):
        pass
