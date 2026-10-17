"""tests/test_idempotency.py — Idempotency and duplicate-reservation tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_same_user_repeat_reservation_returns_existing(
    client: TestClient, make_user, event_obj, seat_for_event
):
    """Same user + same seat while hold is active → returns existing booking (200)."""
    user, headers = make_user(email="idem-repeat@test.local")
    seat = seat_for_event

    resp1 = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    assert resp1.status_code == 201
    booking_id_1 = resp1.json()["id"]

    # Same request again while hold is still valid
    resp2 = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers,
    )
    # Should return the same booking
    assert resp2.status_code in (200, 201)
    booking_id_2 = resp2.json()["id"]
    assert booking_id_1 == booking_id_2, "Duplicate booking created!"


def test_different_user_rejected_on_held_seat(
    client: TestClient, make_user, event_obj, seat_for_event
):
    """Different user on a HELD seat gets 409."""
    user_a, headers_a = make_user(email="idem-a@test.local")
    user_b, headers_b = make_user(email="idem-b@test.local")
    seat = seat_for_event

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers_a,
    )
    assert resp.status_code == 201

    resp = client.post(
        "/api/v1/bookings",
        json={"event_id": event_obj.id, "seat_id": seat.id},
        headers=headers_b,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] in ("SEAT_UNAVAILABLE", "SEAT_BUSY")
