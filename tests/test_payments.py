"""tests/test_payments.py — Payment simulation tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models import BookingStatus
from tests.conftest import TestSessionLocal


def test_failed_payment_booking_stays_held(client: TestClient, make_user, event_obj, seat_for_event):
    user, headers = make_user(email="failpay@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    resp = client.post(
        f"/api/v1/bookings/{booking_id}/pay",
        json={"simulate": "fail"},
        headers=headers,
    )
    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "PAYMENT_FAILED"

    # Booking stays HELD
    db2 = TestSessionLocal()
    try:
        from app.models import Booking
        b = db2.get(Booking, booking_id)
        assert b.status == BookingStatus.HELD
        assert b.payment_attempts == 1
    finally:
        db2.close()


def test_max_payment_attempts_cancels_booking(client: TestClient, make_user, event_obj, seat_for_event):
    from app.config import get_settings
    settings = get_settings()
    user, headers = make_user(email="maxattempt@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    # Hit max attempts
    for _ in range(settings.max_payment_attempts):
        resp = client.post(
            f"/api/v1/bookings/{booking_id}/pay",
            json={"simulate": "fail"},
            headers=headers,
        )

    # Booking should be CANCELLED after max attempts
    db2 = TestSessionLocal()
    try:
        from app.models import Booking
        b = db2.get(Booking, booking_id)
        assert b.status == BookingStatus.CANCELLED
    finally:
        db2.close()

    # Seat should be AVAILABLE again
    from app.models import Seat, SeatStatus
    db3 = TestSessionLocal()
    try:
        s = db3.get(Seat, seat.id)
        assert s.status == SeatStatus.AVAILABLE
    finally:
        db3.close()


def test_delayed_payment_sets_pending(client: TestClient, make_user, event_obj, seat_for_event):
    user, headers = make_user(email="delaypay@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    resp = client.post(
        f"/api/v1/bookings/{booking_id}/pay",
        json={"simulate": "delay"},
        headers=headers,
    )
    assert resp.status_code == 200
    payment = resp.json()
    assert payment["status"] == "PENDING"
    assert payment["settle_at"] is not None

    # Booking should be PAYMENT_PENDING
    db2 = TestSessionLocal()
    try:
        from app.models import Booking
        b = db2.get(Booking, booking_id)
        assert b.status == BookingStatus.PAYMENT_PENDING
    finally:
        db2.close()
