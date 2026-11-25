"""WebSocket flow tests using a fake speech engine (no Gemini key needed)."""
import asyncio
import json
from contextlib import asynccontextmanager

from app import live
from app.main import app


class FakeEngine:
    """Emits an interim + final result for every audio chunk it receives."""

    def __init__(self, phrases):
        self.phrases = list(phrases)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.ended = False

    async def send_audio(self, pcm16k: bytes) -> None:
        if self.phrases:
            phrase = self.phrases.pop(0)
            await self.queue.put(("interim", phrase[: len(phrase) // 2]))
            await self.queue.put(("final", phrase))

    async def end_audio(self) -> None:
        self.ended = True

    async def events(self):
        while True:
            yield await self.queue.get()


def _use_fake(phrases, captured=None):
    @asynccontextmanager
    async def factory(language_codes):
        if captured is not None:
            captured["language_codes"] = language_codes
        yield FakeEngine(phrases)

    app.dependency_overrides[live.gemini_factory] = lambda: factory


def test_live_transcription_saves_to_history(client):
    captured = {}
    _use_fake(["Namaste, aaj ka plan", "is to finish the assignment."], captured)

    with client.websocket_connect("/ws/transcribe?lang=hi-IN,en-IN") as ws:
        assert ws.receive_json() == {"type": "ready"}
        silence = b"\x00\x00" * 1600

        ws.send_bytes(silence)
        assert ws.receive_json()["type"] == "interim"
        assert ws.receive_json() == {"type": "final", "text": "Namaste, aaj ka plan"}

        ws.send_bytes(silence)
        ws.receive_json()
        ws.receive_json()

        ws.send_text(json.dumps({"type": "stop"}))
        saved = ws.receive_json()

    assert captured["language_codes"] == ["hi-IN", "en-IN"]
    assert saved["type"] == "saved"
    t = saved["transcription"]
    assert t["text"] == "Namaste, aaj ka plan is to finish the assignment."
    assert t["source"] == "live" and t["language"] == "hi-IN,en-IN"

    listed = client.get("/api/transcriptions").json()
    assert listed["total"] == 1


def test_stop_without_speech_saves_nothing(client):
    _use_fake([])
    with client.websocket_connect("/ws/transcribe") as ws:
        assert ws.receive_json()["type"] == "ready"
        ws.send_text(json.dumps({"type": "stop"}))
        assert ws.receive_json()["type"] == "empty"
    assert client.get("/api/transcriptions").json()["total"] == 0


def test_missing_api_key_reports_error(client):
    with client.websocket_connect("/ws/transcribe") as ws:
        msg = ws.receive_json()
    assert msg["type"] == "error" and "GEMINI_API_KEY" in msg["message"]


def test_language_parsing_and_titles():
    assert live.parse_language("auto") == []
    assert live.parse_language(" hi-IN , en-IN ") == ["hi-IN", "en-IN"]
    assert live.make_title("one two three") == "one two three"
    assert live.make_title("a b c d e f g h i j").endswith("…")
