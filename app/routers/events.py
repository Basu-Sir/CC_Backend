from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.db import get_db
from app.models import Event, Seat, SeatStatus
from app.schemas import EventOut, EventDetailOut, SeatOut, SeatListOut
from app import errors

router = APIRouter(prefix="/events", tags=["Events"])


@router.get("", response_model=list[EventOut])
def list_events(db: Session = Depends(get_db)):
    events = db.query(Event).order_by(Event.starts_at).all()
    return events


@router.get("/{event_id}", response_model=EventDetailOut)
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise errors.not_found("Event")

    counts = (
        db.query(Seat.status, func.count(Seat.id))
        .filter(Seat.event_id == event_id)
        .group_by(Seat.status)
        .all()
    )
    status_map = {s.value: 0 for s in SeatStatus}
    for status, cnt in counts:
        status_map[status.value] = cnt

    return EventDetailOut(
        **{c.key: getattr(event, c.key) for c in Event.__table__.columns},
        available=status_map["AVAILABLE"],
        held=status_map["HELD"],
        booked=status_map["BOOKED"],
    )


@router.get("/{event_id}/seats", response_model=SeatListOut)
def list_seats(
    event_id: str,
    status: str | None = None,
    page: int = 1,
    page_size: int = 100,
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        raise errors.not_found("Event")

    q = db.query(Seat).filter(Seat.event_id == event_id)
    if status:
        try:
            q = q.filter(Seat.status == SeatStatus(status.upper()))
        except ValueError:
            raise errors.api_error(422, "VALIDATION_ERROR", f"Invalid seat status: {status}")

    total = q.count()
    items = q.order_by(Seat.label).offset((page - 1) * page_size).limit(page_size).all()

    return SeatListOut(items=items, total=total, page=page, page_size=page_size)
