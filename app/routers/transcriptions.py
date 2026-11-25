"""REST endpoints: full CRUD for saved transcriptions."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/transcriptions", tags=["transcriptions"])


def _get_or_404(db: Session, transcription_id: int):
    row = crud.get(db, transcription_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Transcription not found")
    return row


@router.get("", response_model=schemas.TranscriptionPage)
def list_transcriptions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    q: Optional[str] = Query(None, max_length=200, description="Search in title and text"),
    db: Session = Depends(get_db),
):
    items, total = crud.list_page(db, skip=skip, limit=limit, q=q)
    return schemas.TranscriptionPage(items=items, total=total, skip=skip, limit=limit)


@router.post("", response_model=schemas.TranscriptionOut, status_code=status.HTTP_201_CREATED)
def create_transcription(payload: schemas.TranscriptionCreate, db: Session = Depends(get_db)):
    return crud.create(db, title=payload.title, text=payload.text, language=payload.language, source="manual")


@router.get("/{transcription_id}", response_model=schemas.TranscriptionOut)
def read_transcription(transcription_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, transcription_id)


@router.put("/{transcription_id}", response_model=schemas.TranscriptionOut)
def update_transcription(
    transcription_id: int, payload: schemas.TranscriptionUpdate, db: Session = Depends(get_db)
):
    return crud.update(db, _get_or_404(db, transcription_id), payload)


@router.delete("/{transcription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transcription(transcription_id: int, db: Session = Depends(get_db)):
    crud.delete(db, _get_or_404(db, transcription_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
