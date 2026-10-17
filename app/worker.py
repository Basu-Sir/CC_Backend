"""
app/worker.py — Background process for:
1. Expiring abandoned HELD bookings.
2. Settling delayed payments (PAYMENT_PENDING bookings).

Run as a separate process: python -m app.worker
Lock order: seat → booking → payment (same as booking_service and payment_service).
Uses SKIP LOCKED so multiple workers can run safely.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Booking, BookingStatus, Payment, PaymentStatus, Seat, SeatStatus
from app.services.booking_service import _append_event, _db_now

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(levelname)s %(message)s")
log = logging.getLogger("worker")


def expire_held_bookings(db: Session) -> int:
    """
    Find a batch of HELD bookings past their hold_expires_at,
    then expire each one in its own short transaction.
    """
    now_raw = db.execute(text("SELECT clock_timestamp()")).scalar()

    # Read candidates without locking
    candidates = db.execute(
        select(Booking.id, Booking.seat_id)
        .where(Booking.status == BookingStatus.HELD)
        .where(Booking.hold_expires_at <= now_raw)
        .limit(50)
    ).all()

    expired = 0
    for booking_id, seat_id in candidates:
        try:
            _expire_one(db, booking_id, seat_id)
            expired += 1
        except Exception as exc:
            db.rollback()
            log.debug("Skipping expiry for booking %s: %s", booking_id, exc)

    return expired


def _expire_one(db: Session, booking_id: str, seat_id: str) -> None:
    # Lock seat first (SKIP LOCKED — skip if held by another worker)
    seat = db.execute(
        select(Seat).where(Seat.id == seat_id).with_for_update(skip_locked=True)
    ).scalar_one_or_none()

    if seat is None:
        return  # Another process holds it

    booking = db.execute(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    ).scalar_one_or_none()

    if booking is None:
        return

    now = _db_now(db)

    # Re-check after lock
    if booking.status != BookingStatus.HELD:
        return
    if booking.hold_expires_at > now:
        return

    booking.status = BookingStatus.EXPIRED
    booking.updated_at = now
    seat.status = SeatStatus.AVAILABLE
    seat.current_booking_id = None
    seat.updated_at = now
    _append_event(db, booking.id, "EXPIRED", {"expired_at": now.isoformat(), "by": "worker"})
    db.commit()


def settle_delayed_payments(db: Session) -> int:
    """
    Find PENDING payments whose settle_at has passed and settle them.
    """
    now_raw = db.execute(text("SELECT clock_timestamp()")).scalar()

    candidates = db.execute(
        select(Payment.id)
        .where(Payment.status == PaymentStatus.PENDING)
        .where(Payment.settle_at <= now_raw)
        .limit(50)
    ).scalars().all()

    settled = 0
    for payment_id in candidates:
        try:
            from app.services.payment_service import settle_delayed_payment
            settle_delayed_payment(db, payment_id)
            settled += 1
        except Exception as exc:
            db.rollback()
            log.debug("Failed to settle payment %s: %s", payment_id, exc)

    return settled


def run_sweep() -> None:
    db = SessionLocal()
    try:
        expired = expire_held_bookings(db)
        settled = settle_delayed_payments(db)
        if expired or settled:
            log.info("Sweep: expired=%d settled=%d", expired, settled)
    finally:
        db.close()


def main() -> None:
    log.info(
        "Worker started. interval=%ds", settings.sweep_interval_seconds
    )
    while True:
        try:
            run_sweep()
        except Exception as exc:
            log.error("Sweep error: %s", exc)
        time.sleep(settings.sweep_interval_seconds)


if __name__ == "__main__":
    main()
