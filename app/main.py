"""FastAPI entry point: `uvicorn app.main:app --reload`."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import live, models  # noqa: F401  (models registers the tables)
from app.config import get_settings
from app.database import Base, engine
from app.routers import transcriptions

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Speech to Text",
    description="Real-time multilingual (Hindi + English) transcription with saved history.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(transcriptions.router)
app.include_router(live.router)


@app.get("/api/health", tags=["meta"])
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "speech_engine": settings.gemini_model,
        "speech_engine_configured": bool(settings.gemini_api_key),
        "database": settings.sqlalchemy_url.split(":", 1)[0],
    }


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
