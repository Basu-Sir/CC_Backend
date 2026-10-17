from __future__ import annotations

"""
payment_service.py — Simulated payment processing.

Lock order: seat → booking → payment (consistent with booking_service).
"""

import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Booking,
    BookingEvent,
    BookingStatus,
    Payment,
    PaymentStatus,
    Seat,
    SeatStatus,
    SimulateMode,
)
from app import errors
from app.services.booking_service import _db_now, _append_event

settings = get_settings()


def _lock_seat_booking(db: Session, booking_id: str, user_id: str):
    """
    Lock seat first, then booking. Re-verify booking still points to that seat.
    Returns (seat, booking).
    """
    booking_unl = db.get(Booking, booking_id)
    if booking_unl is None:
        raise errors.not_found("Booking")
    if booking_unl.user_id != user_id:
        raise errors.forbidden("You do not own this booking.")

    try:
        seat: Seat = db.execute(
            select(Seat).where(Seat.id == booking_unl.seat_id).with_for_update(nowait=True)
        ).scalar_one()
    except Exception as exc:
        if "55P03" in str(exc) or "could not obtain lock" in str(exc).lower():
            raise errors.seat_busy()
        raise

    booking: Booking = db.execute(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    ).scalar_one()

    # Re-verify linkage
    if booking.seat_id != seat.id:
        raise errors.invalid_state("Booking seat mismatch after lock.")

    return seat, booking


def initiate_payment(
    db: Session,
    booking_id: str,
    user_id: str,
    simulate: str,
    method: str,
) -> Payment:
    """
    Main payment entry point. Dispatches to simulate mode.
    """
    seat, booking = _lock_seat_booking(db, booking_id, user_id)
    now = _db_now(db)

    # Guard: booking must be HELD and not expired
    if booking.status == BookingStatus.EXPIRED or (
        booking.status == BookingStatus.HELD and booking.hold_expires_at <= now
    ):
        raise errors.hold_expired()

    if booking.status not in (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING):
        raise errors.invalid_state(f"Booking is {booking.status.value}, cannot pay.")

    # Resolve 'random' mode
    actual_mode = simulate
    if simulate == "random":
        actual_mode = random.choice(["success", "fail", "delay"])

    mode = SimulateMode(actual_mode)

    if mode == SimulateMode.success:
        return _pay_success(db, seat, booking, now, mode)
    elif mode == SimulateMode.fail:
        return _pay_fail(db, booking, now, mode)
    elif mode == SimulateMode.delay:
        return _pay_delay(db, booking, now, mode)
    else:
        raise errors.api_error(422, "VALIDATION_ERROR", f"Unknown simulate mode: {simulate}")


def _pay_success(db: Session, seat: Seat, booking: Booking, now: datetime, mode: SimulateMode) -> Payment:
    payment = Payment(
        booking_id=booking.id,
        user_id=booking.user_id,
        amount=settings.seat_price,
        status=PaymentStatus.SUCCEEDED,
        simulate_mode=mode,
        final_outcome="success",
    )
    db.add(payment)
    db.flush()

    booking.status = BookingStatus.CONFIRMED
    booking.confirmed_at = now
    booking.updated_at = now
    booking.payment_attempts += 1

    seat.status = SeatStatus.BOOKED
    seat.updated_at = now

    _append_event(db, booking.id, "PAYMENT_STARTED", {"simulate": mode.value})
    _append_event(db, booking.id, "CONFIRMED", {"payment_id": payment.id, "confirmed_at": now.isoformat()})

    db.commit()
    db.refresh(payment)
    return payment


def _pay_fail(db: Session, booking: Booking, now: datetime, mode: SimulateMode) -> Payment:
    booking.payment_attempts += 1
    payment = Payment(
        booking_id=booking.id,
        user_id=booking.user_id,
        amount=settings.seat_price,
        status=PaymentStatus.FAILED,
        simulate_mode=mode,
        failure_reason="Simulated payment failure",
        final_outcome="fail",
    )
    db.add(payment)

    _append_event(db, booking.id, "PAYMENT_STARTED", {"simulate": mode.value})
    _append_event(db, booking.id, "PAYMENT_FAILED", {"attempt": booking.payment_attempts, "reason": "simulated"})

    if booking.payment_attempts >= settings.max_payment_attempts:
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.updated_at = now
        seat: Seat = db.get(Seat, booking.seat_id)
        seat.status = SeatStatus.AVAILABLE
        seat.current_booking_id = None
        seat.updated_at = now
        _append_event(db, booking.id, "CANCELLED", {"reason": "max_payment_attempts_exceeded"})
    else:
        booking.updated_at = now

    db.commit()
    db.refresh(payment)

    raise errors.payment_failed(f"Payment simulation failed (attempt {booking.payment_attempts}/{settings.max_payment_attempts}).")


def _pay_delay(db: Session, booking: Booking, now: datetime, mode: SimulateMode) -> Payment:
    settle_at = now + timedelta(seconds=settings.payment_delay_seconds)
    # Randomly decide the final outcome for delayed payment
    outcome = random.choice(["success", "fail"])

    payment = Payment(
        booking_id=booking.id,
        user_id=booking.user_id,
        amount=settings.seat_price,
        status=PaymentStatus.PENDING,
        simulate_mode=mode,
        settle_at=settle_at,
        final_outcome=outcome,
    )
    db.add(payment)

    booking.status = BookingStatus.PAYMENT_PENDING
    booking.payment_attempts += 1
    booking.updated_at = now

    _append_event(db, booking.id, "PAYMENT_STARTED", {"simulate": mode.value, "settle_at": settle_at.isoformat(), "outcome": outcome})

    db.commit()
    db.refresh(payment)
    return payment


def settle_delayed_payment(db: Session, payment_id: str) -> None:
    """
    Called by the background worker to settle a delayed payment.
    Lock order: seat → booking → payment.
    """
    payment_unl = db.get(Payment, payment_id)
    if payment_unl is None or payment_unl.status != PaymentStatus.PENDING:
        return

    booking_unl = db.get(Booking, payment_unl.booking_id)
    if booking_unl is None:
        return

    # Lock seat first
    from sqlalchemy.exc import OperationalError
    try:
        seat: Seat = db.execute(
            select(Seat)
            .where(Seat.id == booking_unl.seat_id)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
    except Exception:
        return  # seat locked by another worker, skip

    if seat is None:
        return

    booking: Booking = db.execute(
        select(Booking).where(Booking.id == booking_unl.booking_id).with_for_update()
    ).scalar_one()

    payment: Payment = db.execute(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    ).scalar_one()

    now = _db_now(db)

    # Re-check: still pending and settle_at reached
    if payment.status != PaymentStatus.PENDING:
        return
    if payment.settle_at and payment.settle_at > now:
        return

    # If booking was cancelled/expired in the meantime, mark payment failed/refunded
    if booking.status in (BookingStatus.CANCELLED, BookingStatus.EXPIRED):
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Booking cancelled or expired before settlement"
        payment.updated_at = now
        db.commit()
        return

    outcome = payment.final_outcome or "success"

    if outcome == "success":
        payment.status = PaymentStatus.SUCCEEDED
        payment.updated_at = now
        booking.status = BookingStatus.CONFIRMED
        booking.confirmed_at = now
        booking.updated_at = now
        seat.status = SeatStatus.BOOKED
        seat.updated_at = now
        _append_event(db, booking.id, "CONFIRMED", {"settled_by": "worker", "payment_id": payment.id})
    else:
        # Payment failed: return to HELD with retry window, or cancel
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "Simulated delayed payment failure"
        payment.updated_at = now

        _append_event(db, booking.id, "PAYMENT_FAILED", {"settled_by": "worker", "attempt": booking.payment_attempts})

        if booking.payment_attempts >= settings.max_payment_attempts:
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
            booking.updated_at = now
            seat.status = SeatStatus.AVAILABLE
            seat.current_booking_id = None
            seat.updated_at = now
            _append_event(db, booking.id, "CANCELLED", {"reason": "max_payment_attempts_exceeded"})
        else:
            # Return to HELD with extended window
            booking.status = BookingStatus.HELD
            booking.hold_expires_at = max(
                booking.hold_expires_at,
                now + timedelta(seconds=settings.payment_retry_window_seconds),
            )
            booking.updated_at = now

    db.commit()
