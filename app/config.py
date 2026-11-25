"""Application settings, read from environment variables (or a .env file)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # PostgreSQL in production, e.g. postgresql://user:pass@host:5432/dbname
    # Falls back to a local SQLite file so the app runs with zero setup.
    database_url: str = "sqlite:///./transcriptions.db"

    # Gemini Live API (free key from https://aistudio.google.com/apikey)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-transcribe-live"

    # Seconds to wait for the final transcript after the user presses Stop
    final_wait_seconds: float = 3.0

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        # Render / Heroku hand out "postgres://", SQLAlchemy needs "postgresql://"
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        # Use the psycopg (v3) driver explicitly
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
