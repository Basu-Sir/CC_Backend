"""
tests/conftest.py — Pytest fixtures for a real PostgreSQL test database.

Set TEST_DATABASE_URL in environment before running:
  TEST_DATABASE_URL=postgresql+psycopg://booking:booking@localhost:5432/booking_test pytest

The fixture creates all tables before the session and truncates between tests.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session

# Override DATABASE_URL before importing app modules
TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://booking:booking@localhost:5432/booking_test",
)
os.environ["DATABASE_URL"] = TEST_DB_URL

from app.main import app
from app.db import get_db
from app.models import Base, Event, Seat, SeatStatus, User
from app.config import get_settings

settings = get_settings()

# Test engine
test_engine = create_engine(TEST_DB_URL, pool_pre_ping=True)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    """Create all tables once per test session."""
    Base.metadata.create_all(test_engine)
    # Ensure partial unique index exists
    with test_engine.connect() as conn:
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_active_booking_per_seat
            ON bookings (seat_id)
            WHERE status IN ('HELD', 'PAYMENT_PENDING', 'CONFIRMED')
        """))
        conn.commit()
    yield
    Base.metadata.drop_all(test_engine)


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all booking-related tables between tests (keep users/events/seats)."""
    yield
    with test_engine.connect() as conn:
        conn.execute(text("TRUNCATE booking_events, payments, bookings RESTART IDENTITY CASCADE"))
        conn.execute(text("UPDATE seats SET status='AVAILABLE', current_booking_id=NULL"))
        conn.commit()


@pytest.fixture
def db() -> Session:
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db: Session):
    """TestClient wired to the test database session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Shared test data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def shared_db():
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def event_obj(shared_db: Session) -> Event:
    ev = shared_db.query(Event).filter_by(name="Test Concert").first()
    if ev is None:
        ev = Event(
            name="Test Concert",
            venue="Test Venue",
            starts_at=datetime.now(timezone.utc) + timedelta(days=30),
            sales_open_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            total_seats=500,
        )
        shared_db.add(ev)
        shared_db.commit()
        shared_db.refresh(ev)

        # Create 500 seats
        seats = []
        for row in "ABCDEFGHIJKLMNOPQRST":
            for col in range(1, 26):
                seats.append(Seat(event_id=ev.id, label=f"{row}-{col:02d}", status=SeatStatus.AVAILABLE))
        shared_db.bulk_save_objects(seats)
        shared_db.commit()
    return ev


@pytest.fixture
def make_user(db: Session):
    """Factory: creates a user and returns (user, header_dict)."""
    def _make(name: str = "Test User", email: str | None = None) -> tuple[User, dict]:
        email = email or f"test-{uuid.uuid4().hex[:8]}@test.local"
        user = User(name=name, email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, {"X-User-Id": user.id}
    return _make


@pytest.fixture
def seat_for_event(db: Session, event_obj: Event) -> Seat:
    """Return the first available seat for the test event."""
    seat = db.query(Seat).filter_by(event_id=event_obj.id, status=SeatStatus.AVAILABLE).first()
    assert seat is not None, "No available seats"
    return seat
