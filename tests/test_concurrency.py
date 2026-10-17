"""
tests/test_concurrency.py — Concurrent booking race tests.

Uses real PostgreSQL. Tests must NOT use mocked DB sessions.
"""
from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from sqlalchemy.orm import Session

from tests.conftest import TestSessionLocal
from app.models import Booking, BookingStatus, Seat, SeatStatus, User


def _make_user_in_db(email: str) -> User:
    db = TestSessionLocal()
    try:
        user = User(name="Concurrent User", email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def _reserve(user_id: str, event_id: str, seat_id: str) -> int:
    """Make a reservation request in its own DB session. Returns HTTP status code."""
    from app.services.booking_service import reserve_seat
    from fastapi import HTTPException
    db = TestSessionLocal()
    try:
        reserve_seat(db, user_id=user_id, event_id=event_id, seat_id=seat_id)
        return 201
    except HTTPException as e:
        return e.status_code
    except Exception:
        return 500
    finally:
        db.close()


class TestHotSeatRace:
    """50 concurrent users all trying to book the same seat."""

    N_THREADS = 50

    def test_exactly_one_hold_created(self, event_obj, db: Session):
        seat = db.query(Seat).filter_by(event_id=event_obj.id, status=SeatStatus.AVAILABLE).first()
        assert seat is not None

        users = [
            _make_user_in_db(f"race-{uuid.uuid4().hex[:8]}@test.local")
            for _ in range(self.N_THREADS)
        ]

        barrier = threading.Barrier(self.N_THREADS)
        results: list[int] = []
        results_lock = threading.Lock()

        def attempt(user: User) -> int:
            barrier.wait()  # All threads start at the same moment
            code = _reserve(user.id, event_obj.id, seat.id)
            with results_lock:
                results.append(code)
            return code

        with ThreadPoolExecutor(max_workers=self.N_THREADS) as pool:
            futures = [pool.submit(attempt, u) for u in users]
            for f in as_completed(futures):
                f.result()  # surface exceptions

        # Exactly one 201
        n_created = results.count(201)
        assert n_created == 1, f"Expected 1 hold, got {n_created}. Codes: {sorted(results)}"

        # All others must be 409 or 500 (never two successes)
        for code in results:
            assert code in (201, 409, 500), f"Unexpected code: {code}"

        # Database invariant: at most one active booking for this seat
        db2 = TestSessionLocal()
        try:
            active = (
                db2.query(Booking)
                .filter(Booking.seat_id == seat.id)
                .filter(Booking.status.in_(["HELD", "PAYMENT_PENDING", "CONFIRMED"]))
                .count()
            )
            assert active == 1, f"Expected 1 active booking, got {active}"
        finally:
            db2.close()


class TestDifferentSeatsRace:
    """Concurrent reservations on different seats should all succeed."""

    N_THREADS = 20

    def test_different_seats_all_succeed(self, event_obj, db: Session):
        seats = (
            db.query(Seat)
            .filter_by(event_id=event_obj.id, status=SeatStatus.AVAILABLE)
            .limit(self.N_THREADS)
            .all()
        )
        assert len(seats) == self.N_THREADS

        users = [
            _make_user_in_db(f"diff-seat-{uuid.uuid4().hex[:8]}@test.local")
            for _ in range(self.N_THREADS)
        ]

        barrier = threading.Barrier(self.N_THREADS)

        def attempt(user: User, seat: Seat) -> int:
            barrier.wait()
            return _reserve(user.id, event_obj.id, seat.id)

        with ThreadPoolExecutor(max_workers=self.N_THREADS) as pool:
            futures = [pool.submit(attempt, u, s) for u, s in zip(users, seats)]
            codes = [f.result() for f in as_completed(futures)]

        n_created = codes.count(201)
        assert n_created == self.N_THREADS, f"Expected all {self.N_THREADS} to succeed, got {n_created}. Codes: {sorted(codes)}"
