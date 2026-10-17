"""
scripts/seed.py — Idempotent seed for one 500-seat event and demo users.

Rows A-T, columns 01-25 = 20×25 = 500 seats.
Re-running this script does NOT duplicate data.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure app package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Base, Event, Seat, SeatStatus, User

settings = get_settings()

EVENT_NAME = "CC-VIT Annual Concert 2026"
VENUE = "VIT Vellore Open Air Auditorium"
ROWS = list("ABCDEFGHIJKLMNOPQRST")  # 20 rows
COLS = range(1, 26)  # 25 columns → 500 seats

DEMO_USERS = [
    {"name": "Alice Demo", "email": "alice@demo.local"},
    {"name": "Bob Demo", "email": "bob@demo.local"},
    {"name": "Charlie Demo", "email": "charlie@demo.local"},
]


def seed(db: Session) -> None:
    now = datetime.now(timezone.utc)

    # --- Event ---
    event = db.query(Event).filter_by(name=EVENT_NAME).first()
    if event is None:
        event = Event(
            name=EVENT_NAME,
            venue=VENUE,
            starts_at=now + timedelta(days=30),
            sales_open_at=now - timedelta(minutes=1),  # already open
            total_seats=500,
        )
        db.add(event)
        db.flush()
        print(f"Created event: {event.id}")
    else:
        print(f"Event already exists: {event.id}")

    # --- Seats ---
    existing_labels = {s.label for s in db.query(Seat).filter_by(event_id=event.id).all()}
    new_seats = []
    for row in ROWS:
        for col in COLS:
            label = f"{row}-{col:02d}"
            if label not in existing_labels:
                new_seats.append(
                    Seat(
                        event_id=event.id,
                        label=label,
                        status=SeatStatus.AVAILABLE,
                    )
                )
    if new_seats:
        db.bulk_save_objects(new_seats)
        print(f"Created {len(new_seats)} seats.")
    else:
        print("Seats already seeded.")

    # --- Demo Users ---
    for u in DEMO_USERS:
        existing = db.query(User).filter_by(email=u["email"]).first()
        if existing is None:
            db.add(User(name=u["name"], email=u["email"]))
            print(f"Created user: {u['email']}")
        else:
            print(f"User already exists: {u['email']}")

    db.commit()
    print("Seed complete.")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
