"""Pydantic request/response models."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TranscriptionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1)
    language: str = Field("auto", max_length=50)


class TranscriptionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    text: Optional[str] = Field(None, min_length=1)
    language: Optional[str] = Field(None, max_length=50)


class TranscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    text: str
    language: str
    source: str
    duration_seconds: float
    created_at: datetime
    updated_at: datetime


class TranscriptionPage(BaseModel):
    items: list[TranscriptionOut]
    total: int
    skip: int
    limit: int
