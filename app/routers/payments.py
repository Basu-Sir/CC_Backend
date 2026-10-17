from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Booking, BookingStatus, Payment, User
from app.schemas import PaymentCreate, PaymentOut
from app.services import payment_service
from app import errors

router = APIRouter(prefix="", tags=["Payments"])


@router.post("/bookings/{booking_id}/pay", response_model=PaymentOut, status_code=200)
def pay_booking(
    booking_id: str,
    body: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payment = payment_service.initiate_payment(
            db=db,
            booking_id=booking_id,
            user_id=current_user.id,
            simulate=body.simulate,
            method=body.method,
        )
    except errors.HTTPException:
        raise
    return payment


@router.get("/payments/{payment_id}", response_model=PaymentOut)
def get_payment(
    payment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise errors.not_found("Payment")
    if payment.user_id != current_user.id:
        raise errors.forbidden()
    return payment
