"""Database operations for transcriptions, kept separate from the HTTP layer."""
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas


def create(
    db: Session,
    *,
    title: str,
    text: str,
    language: str = "auto",
    source: str = "manual",
    duration_seconds: float = 0.0,
) -> models.Transcription:
    row = models.Transcription(
        title=title.strip(),
        text=text.strip(),
        language=language,
        source=source,
        duration_seconds=round(duration_seconds, 2),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get(db: Session, transcription_id: int) -> Optional[models.Transcription]:
    return db.get(models.Transcription, transcription_id)


def list_page(db: Session, *, skip: int, limit: int, q: Optional[str] = None):
    stmt = select(models.Transcription)
    count_stmt = select(func.count(models.Transcription.id))
    if q:
        like = f"%{q}%"
        cond = or_(models.Transcription.title.ilike(like), models.Transcription.text.ilike(like))
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(models.Transcription.created_at.desc(), models.Transcription.id.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return items, total


def update(db: Session, row: models.Transcription, data: schemas.TranscriptionUpdate) -> models.Transcription:
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(row, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    db.refresh(row)
    return row


def delete(db: Session, row: models.Transcription) -> None:
    db.delete(row)
    db.commit()
