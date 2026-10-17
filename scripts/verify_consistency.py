"""
scripts/verify_consistency.py — Consistency verifier.

Exits with code 0 (PASS) or 1 (FAIL) after checking database invariants.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from app.db import SessionLocal


CHECKS: list[tuple[str, str]] = [
    # 1. No seat has more than one active booking
    (
        "No seat has more than one active booking",
        """
        SELECT count(*) FROM (
            SELECT seat_id
            FROM bookings
            WHERE status IN ('HELD', 'PAYMENT_PENDING', 'CONFIRMED')
            GROUP BY seat_id
            HAVING count(*) > 1
        ) x
        """,
    ),
    # 2. BOOKED seats == CONFIRMED bookings per event
    (
        "BOOKED seat count equals CONFIRMED booking count per event",
        """
        SELECT count(*) FROM (
            SELECT e.id
            FROM events e
            LEFT JOIN (
                SELECT event_id, count(*) AS booked_seats
                FROM seats WHERE status = 'BOOKED' GROUP BY event_id
            ) s ON s.event_id = e.id
            LEFT JOIN (
                SELECT event_id, count(*) AS confirmed
                FROM bookings WHERE status = 'CONFIRMED' GROUP BY event_id
            ) b ON b.event_id = e.id
            WHERE coalesce(s.booked_seats, 0) != coalesce(b.confirmed, 0)
        ) x
        """,
    ),
    # 3. AVAILABLE seats have NULL current_booking_id
    (
        "All AVAILABLE seats have NULL current_booking_id",
        """
        SELECT count(*) FROM seats
        WHERE status = 'AVAILABLE' AND current_booking_id IS NOT NULL
        """,
    ),
    # 4. HELD seats point to HELD or PAYMENT_PENDING booking
    (
        "HELD seats point to HELD or PAYMENT_PENDING booking",
        """
        SELECT count(*) FROM seats s
        JOIN bookings b ON b.id = s.current_booking_id
        WHERE s.status = 'HELD' AND b.status NOT IN ('HELD', 'PAYMENT_PENDING')
        """,
    ),
    # 5. BOOKED seats point to CONFIRMED booking
    (
        "BOOKED seats point to CONFIRMED booking",
        """
        SELECT count(*) FROM seats s
        JOIN bookings b ON b.id = s.current_booking_id
        WHERE s.status = 'BOOKED' AND b.status != 'CONFIRMED'
        """,
    ),
    # 6. Every CONFIRMED booking has exactly one SUCCEEDED payment
    (
        "Every CONFIRMED booking has exactly one SUCCEEDED payment",
        """
        SELECT count(*) FROM bookings b
        WHERE b.status = 'CONFIRMED'
        AND (
            SELECT count(*) FROM payments p
            WHERE p.booking_id = b.id AND p.status = 'SUCCEEDED'
        ) != 1
        """,
    ),
    # 7. No EXPIRED or CANCELLED booking retains seat ownership
    (
        "No EXPIRED/CANCELLED booking retains seat ownership",
        """
        SELECT count(*) FROM seats
        WHERE current_booking_id IN (
            SELECT id FROM bookings WHERE status IN ('EXPIRED', 'CANCELLED')
        )
        """,
    ),
    # 8. Confirmed bookings never exceed total_seats per event
    (
        "Confirmed bookings never exceed total_seats per event",
        """
        SELECT count(*) FROM (
            SELECT e.id, e.total_seats, count(b.id) AS confirmed
            FROM events e
            LEFT JOIN bookings b ON b.event_id = e.id AND b.status = 'CONFIRMED'
            GROUP BY e.id, e.total_seats
            HAVING count(b.id) > e.total_seats
        ) x
        """,
    ),
]


def main() -> None:
    db = SessionLocal()
    failures = []
    try:
        for description, query in CHECKS:
            result = db.execute(text(query)).scalar()
            status = "PASS" if result == 0 else "FAIL"
            if result != 0:
                failures.append(description)
            print(f"[{status}] {description} (violations: {result})")
    finally:
        db.close()

    print()
    if failures:
        print(f"CONSISTENCY CHECK FAILED — {len(failures)} violation(s):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("CONSISTENCY CHECK PASSED — all invariants hold.")
        sys.exit(0)


if __name__ == "__main__":
    main()
