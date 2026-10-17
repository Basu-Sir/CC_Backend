from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Booking, BookingEvent, BookingStatus, User
from app.schemas import BookingCreate, BookingOut, BookingListOut, BookingEventOut
from app.services import booking_service
from app import errors

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def _enrich(booking: Booking) -> dict:
    """Compute seconds_remaining for HELD bookings."""
    now = datetime.now(timezone.utc)
    remaining = None
    if booking.status in (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING):
        delta = (booking.hold_expires_at - now).total_seconds()
        remaining = max(0, int(delta))
    data = {c.key: getattr(booking, c.key) for c in Booking.__table__.columns}
    data["seconds_remaining"] = remaining
    return data


@router.post("", response_model=BookingOut, status_code=201)
def reserve_seat(
    body: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = booking_service.reserve_seat(
        db=db,
        user_id=current_user.id,
        event_id=body.event_id,
        seat_id=body.seat_id,
    )
    return _enrich(booking)


@router.get("/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise errors.not_found("Booking")
    if booking.user_id != current_user.id:
        raise errors.forbidden()
    return _enrich(booking)


@router.get("/{booking_id}/timeline", response_model=list[BookingEventOut])
def get_timeline(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise errors.not_found("Booking")
    if booking.user_id != current_user.id:
        raise errors.forbidden()
    return booking.events_log


@router.post("/{booking_id}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = booking_service.cancel_booking(
        db=db, booking_id=booking_id, user_id=current_user.id
    )
    return _enrich(booking)
