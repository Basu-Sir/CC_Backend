"""tests/test_cancellation.py — Cancellation tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models import BookingStatus, SeatStatus
from tests.conftest import TestSessionLocal


def test_cancel_held_booking_releases_seat(client: TestClient, make_user, event_obj, seat_for_event):
    user, headers = make_user(email="canheld@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    resp = client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    db2 = TestSessionLocal()
    try:
        from app.models import Seat
        s = db2.get(Seat, seat.id)
        assert s.status == SeatStatus.AVAILABLE
        assert s.current_booking_id is None
    finally:
        db2.close()


def test_cancel_confirmed_booking_refunds_and_releases(client: TestClient, make_user, event_obj, seat_for_event):
    user, headers = make_user(email="canconf@test.local")
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
        json={"simulate": "success"},
        headers=headers,
    )
    assert resp.status_code == 200

    resp = client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    db2 = TestSessionLocal()
    try:
        from app.models import Seat, Payment, PaymentStatus
        s = db2.get(Seat, seat.id)
        assert s.status == SeatStatus.AVAILABLE

        from app.models import Booking
        b = db2.get(Booking, booking_id)
        payment = b.payments[0]
        assert payment.status == PaymentStatus.REFUNDED
    finally:
        db2.close()


def test_double_cancel_is_idempotent(client: TestClient, make_user, event_obj, seat_for_event):
    user, headers = make_user(email="dblcancel@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    resp1 = client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=headers)
    resp2 = client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200  # idempotent
