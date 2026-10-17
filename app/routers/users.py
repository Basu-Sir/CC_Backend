from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Booking, User
from app.schemas import UserCreate, UserOut, BookingListOut, BookingOut
from app import errors
from datetime import datetime, timezone

router = APIRouter(tags=["Users"])


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        return existing  # idempotent: same email returns existing user
    user = User(name=body.name, email=body.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/me/bookings", response_model=BookingListOut)
def my_bookings(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)

    q = (
        db.query(Booking)
        .filter(Booking.user_id == current_user.id)
        .order_by(Booking.created_at.desc())
    )
    total = q.count()
    bookings = q.offset((page - 1) * page_size).limit(page_size).all()

    def enrich(b: Booking) -> dict:
        from app.models import BookingStatus
        remaining = None
        if b.status in (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING):
            delta = (b.hold_expires_at - now).total_seconds()
            remaining = max(0, int(delta))
        data = {c.key: getattr(b, c.key) for c in Booking.__table__.columns}
        data["seconds_remaining"] = remaining
        return data

    return BookingListOut(items=[enrich(b) for b in bookings], total=total)
