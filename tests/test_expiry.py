"""tests/test_expiry.py — Expiry tests."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Booking, BookingStatus, Seat, SeatStatus
from tests.conftest import TestSessionLocal


def test_expired_hold_can_be_reused(client: TestClient, make_user, event_obj, seat_for_event, db: Session):
    """After a hold expires, another user can reserve the seat."""
    user_a, headers_a = make_user(email="exp-a@test.local")
    user_b, headers_b = make_user(email="exp-b@test.local")
    seat = seat_for_event

    # User A reserves
    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers_a,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    # Force expiry by backdating hold_expires_at in DB
    db2 = TestSessionLocal()
    try:
        booking = db2.get(Booking, booking_id)
        booking.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        db2.commit()
    finally:
        db2.close()

    # User B can now reserve the same seat (lazy expiry triggers)
    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers_b,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["user_id"] == user_b.id

    # User A's booking should now be EXPIRED
    db3 = TestSessionLocal()
    try:
        b = db3.get(Booking, booking_id)
        assert b.status == BookingStatus.EXPIRED
    finally:
        db3.close()


def test_pay_expired_booking_rejected(client: TestClient, make_user, event_obj, seat_for_event, db: Session):
    """Paying an expired booking returns 409 HOLD_EXPIRED."""
    user, headers = make_user(email="payexp@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    # Force expiry
    db2 = TestSessionLocal()
    try:
        b = db2.get(Booking, booking_id)
        b.hold_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        db2.commit()
    finally:
        db2.close()

    resp = client.post(
        f"/api/v1/bookings/{booking_id}/pay",
        json={"simulate": "success"},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "HOLD_EXPIRED"
