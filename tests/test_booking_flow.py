"""tests/test_booking_flow.py — Happy path and ownership tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_happy_path_reserve_pay_confirm(client: TestClient, make_user, event_obj, seat_for_event):
    user, headers = make_user()
    seat = seat_for_event

    # Reserve
    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    booking = resp.json()
    assert booking["status"] == "HELD"
    assert booking["seconds_remaining"] is not None
    booking_id = booking["id"]

    # Pay success
    resp = client.post(
        f"/api/v1/bookings/{booking_id}/pay",
        json={"simulate": "success"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    payment = resp.json()
    assert payment["status"] == "SUCCEEDED"

    # Booking should now be CONFIRMED
    resp = client.get(f"/api/v1/bookings/{booking_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"

    # Seat should be BOOKED
    from tests.conftest import TestSessionLocal
    from app.models import Seat, SeatStatus
    db2 = TestSessionLocal()
    try:
        s = db2.get(Seat, seat.id)
        assert s.status == SeatStatus.BOOKED
    finally:
        db2.close()


def test_ownership_protection(client: TestClient, make_user, event_obj, seat_for_event):
    """User B cannot view/cancel User A's booking."""
    user_a, headers_a = make_user(email="a-own@test.local")
    user_b, headers_b = make_user(email="b-own@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers_a,
    )
    assert resp.status_code == 201
    booking_id = resp.json()["id"]

    # B cannot view
    resp = client.get(f"/api/v1/bookings/{booking_id}", headers=headers_b)
    assert resp.status_code == 403

    # B cannot cancel
    resp = client.post(f"/api/v1/bookings/{booking_id}/cancel", headers=headers_b)
    assert resp.status_code == 403


def test_list_seats_available(client: TestClient, event_obj):
    resp = client.get(f"/api/v1/events/{event_obj.id}/seats?status=AVAILABLE&page_size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert all(s["status"] == "AVAILABLE" for s in data["items"])


def test_my_bookings(client: TestClient, make_user, event_obj, seat_for_event):
    user, headers = make_user(email="mybookings@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp.status_code == 201

    resp = client.get("/api/v1/users/me/bookings", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
