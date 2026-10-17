from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Booking, BookingStatus, Event, Seat, SeatStatus
from app.schemas import EventStatsOut
from app import errors

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/events/{event_id}/stats", response_model=EventStatsOut)
def event_stats(event_id: str, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise errors.not_found("Event")

    seat_counts = (
        db.query(Seat.status, func.count(Seat.id))
        .filter(Seat.event_id == event_id)
        .group_by(Seat.status)
        .all()
    )
    seat_map = {s.value: 0 for s in SeatStatus}
    for status, cnt in seat_counts:
        seat_map[status.value] = cnt

    booking_counts = (
        db.query(Booking.status, func.count(Booking.id))
        .filter(Booking.event_id == event_id)
        .group_by(Booking.status)
        .all()
    )
    booking_map = {s.value: 0 for s in BookingStatus}
    for status, cnt in booking_counts:
        booking_map[status.value] = cnt

    return EventStatsOut(
        event_id=event_id,
        total_seats=event.total_seats,
        available=seat_map["AVAILABLE"],
        held=seat_map["HELD"],
        booked=seat_map["BOOKED"],
        confirmed_bookings=booking_map["CONFIRMED"],
        expired_bookings=booking_map["EXPIRED"],
        cancelled_bookings=booking_map["CANCELLED"],
    )
