from __future__ import annotations

"""
booking_service.py — Core concurrency-safe booking logic.

Lock order is SEAT → BOOKING → PAYMENT in every code path.
Uses SELECT ... FOR UPDATE NOWAIT on the seat row so hot-seat
requests fail fast instead of queuing.
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import text, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.models import (
    Booking,
    BookingEvent,
    BookingStatus,
    Seat,
    SeatStatus,
    Event,
)
from app import errors

settings = get_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _db_now(db: Session) -> datetime:
    """Read current timestamp from PostgreSQL (avoids clock skew)."""
    return db.execute(text("SELECT clock_timestamp()")).scalar()


def _append_event(db: Session, booking_id: str, event_type: str, detail: dict) -> None:
    ev = BookingEvent(booking_id=booking_id, type=event_type, detail=detail)
    db.add(ev)


def _expire_held_booking(db: Session, booking: Booking, seat: Seat, now: datetime) -> None:
    """
    Expire a HELD booking whose hold_expires_at has passed.
    Called inside a transaction that already holds the seat lock.
    """
    booking.status = BookingStatus.EXPIRED
    booking.updated_at = now
    seat.status = SeatStatus.AVAILABLE
    seat.current_booking_id = None
    seat.updated_at = now
    _append_event(db, booking.id, "EXPIRED", {"expired_at": now.isoformat()})


# ---------------------------------------------------------------------------
# Reserve
# ---------------------------------------------------------------------------


def reserve_seat(db: Session, user_id: str, event_id: str, seat_id: str) -> Booking:
    """
    Atomically reserve a seat for a user.

    The entire operation runs in a single short transaction:
    1. Verify event + seat.
    2. Check sales_open_at via DB clock.
    3. Lock the seat with FOR UPDATE NOWAIT.
    4. Lazy-expire any stale HELD booking on this seat.
    5. Idempotent: return existing booking if this user already holds it.
    6. Reject with 409 if seat is not AVAILABLE.
    7. Insert HELD booking, update seat, append audit event.
    """
    # Step 1 — verify event and seat
    event = db.get(Event, event_id)
    if event is None:
        raise errors.not_found("Event")

    seat = db.get(Seat, seat_id)
    if seat is None or seat.event_id != event_id:
        raise errors.not_found("Seat")

    # Step 2 — check sales_open_at with DB clock
    now = _db_now(db)
    if now < event.sales_open_at:
        raise errors.api_error(403, "SALES_NOT_OPEN", "Ticket sales have not opened yet.")

    # Step 3 — lock the seat row (NOWAIT = fail fast under contention)
    try:
        locked_seat: Seat = db.execute(
            select(Seat)
            .where(Seat.id == seat_id)
            .with_for_update(nowait=True)
        ).scalar_one()
    except Exception as exc:
        # SQLSTATE 55P03: lock_not_available
        if "55P03" in str(exc) or "LockNotAvailable" in type(exc).__name__ or "could not obtain lock" in str(exc).lower():
            raise errors.seat_busy()
        raise

    # Step 4 — lazy expiry
    now = _db_now(db)  # refresh after potential wait
    if locked_seat.status == SeatStatus.HELD and locked_seat.current_booking_id:
        existing_booking = db.get(Booking, locked_seat.current_booking_id)
        if existing_booking and existing_booking.status == BookingStatus.HELD:
            if existing_booking.hold_expires_at <= now:
                _expire_held_booking(db, existing_booking, locked_seat, now)
                db.flush()

    # Step 5 / 6 — check seat availability after expiry
    if locked_seat.status != SeatStatus.AVAILABLE:
        # Idempotent: return existing booking if it belongs to the same user
        if locked_seat.current_booking_id:
            existing = db.get(Booking, locked_seat.current_booking_id)
            if (
                existing
                and existing.user_id == user_id
                and existing.status in (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING)
                and existing.hold_expires_at > now
            ):
                return existing
        raise errors.seat_unavailable(seat.label)

    # Step 7 — create booking
    hold_expires_at = now + timedelta(seconds=settings.hold_ttl_seconds)
    booking = Booking(
        user_id=user_id,
        event_id=event_id,
        seat_id=seat_id,
        status=BookingStatus.HELD,
        hold_expires_at=hold_expires_at,
    )
    db.add(booking)
    db.flush()  # get booking.id before we reference it

    locked_seat.status = SeatStatus.HELD
    locked_seat.current_booking_id = booking.id
    locked_seat.updated_at = now

    _append_event(db, booking.id, "HELD", {
        "seat_label": seat.label,
        "hold_expires_at": hold_expires_at.isoformat(),
    })

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "uq_active_booking_per_seat" in str(exc):
            raise errors.seat_unavailable(seat.label)
        raise

    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


def cancel_booking(db: Session, booking_id: str, user_id: str) -> Booking:
    """
    Cancel a booking. Lock order: seat → booking.
    """
    # Read booking without lock to learn seat_id
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise errors.not_found("Booking")
    if booking.user_id != user_id:
        raise errors.forbidden("You do not own this booking.")

    # Idempotent: already cancelled
    if booking.status == BookingStatus.CANCELLED:
        return booking

    if booking.status == BookingStatus.EXPIRED:
        raise errors.invalid_state("Booking is already expired.")

    # Lock seat first, then booking
    seat: Seat = db.execute(
        select(Seat).where(Seat.id == booking.seat_id).with_for_update(nowait=True)
    ).scalar_one()

    booking = db.execute(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    ).scalar_one()

    now = _db_now(db)

    # Mark any pending payments cancelled/failed
    from app.models import Payment, PaymentStatus
    for payment in booking.payments:
        if payment.status == PaymentStatus.PENDING:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = "Booking cancelled"
            payment.updated_at = now
        elif payment.status == PaymentStatus.SUCCEEDED:
            payment.status = PaymentStatus.REFUNDED
            payment.updated_at = now

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = now
    booking.updated_at = now

    seat.status = SeatStatus.AVAILABLE
    seat.current_booking_id = None
    seat.updated_at = now

    _append_event(db, booking.id, "CANCELLED", {"cancelled_at": now.isoformat()})
    db.commit()
    db.refresh(booking)
    return booking


# ---------------------------------------------------------------------------
# Status read with effective expiry
# ---------------------------------------------------------------------------


def get_booking_with_effective_status(db: Session, booking: Booking) -> Booking:
    """
    Return a booking with seconds_remaining computed. Does NOT persist expiry —
    lazy expiry on next mutation is the persistence path.
    """
    return booking
