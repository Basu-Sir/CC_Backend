from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=3, max_length=255)


class UserOut(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class EventOut(BaseModel):
    id: str
    name: str
    venue: str
    starts_at: datetime
    sales_open_at: datetime
    total_seats: int
    created_at: datetime

    model_config = {"from_attributes": True}


class EventDetailOut(EventOut):
    available: int
    held: int
    booked: int


# ---------------------------------------------------------------------------
# Seat
# ---------------------------------------------------------------------------


class SeatOut(BaseModel):
    id: str
    event_id: str
    label: str
    status: str
    current_booking_id: Optional[str] = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SeatListOut(BaseModel):
    items: list[SeatOut]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


class BookingCreate(BaseModel):
    event_id: str
    seat_id: str


class BookingOut(BaseModel):
    id: str
    user_id: str
    event_id: str
    seat_id: str
    status: str
    hold_expires_at: datetime
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    payment_attempts: int
    source: str
    seconds_remaining: Optional[int] = None

    model_config = {"from_attributes": True}


class BookingListOut(BaseModel):
    items: list[BookingOut]
    total: int


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


class PaymentCreate(BaseModel):
    method: str = Field(default="card")
    simulate: str = Field(default="success", pattern="^(success|fail|delay|random)$")


class PaymentOut(BaseModel):
    id: str
    booking_id: str
    user_id: str
    amount: int
    status: str
    simulate_mode: str
    settle_at: Optional[datetime] = None
    final_outcome: Optional[str] = None
    failure_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Booking timeline
# ---------------------------------------------------------------------------


class BookingEventOut(BaseModel):
    id: str
    booking_id: str
    type: str
    detail: dict
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Admin stats
# ---------------------------------------------------------------------------


class EventStatsOut(BaseModel):
    event_id: str
    total_seats: int
    available: int
    held: int
    booked: int
    confirmed_bookings: int
    expired_bookings: int
    cancelled_bookings: int
