from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SeatStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    BOOKED = "BOOKED"


class BookingStatus(str, enum.Enum):
    HELD = "HELD"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class SimulateMode(str, enum.Enum):
    success = "success"
    fail = "fail"
    delay = "delay"
    random = "random"


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="user")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="user")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    venue: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sales_open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_seats: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    seats: Mapped[list["Seat"]] = relationship("Seat", back_populates="event")
    bookings: Mapped[list["Booking"]] = relationship("Booking", back_populates="event")


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (
        UniqueConstraint("event_id", "label", name="uq_seat_event_label"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[SeatStatus] = mapped_column(
        Enum(SeatStatus, name="seat_status"), nullable=False, default=SeatStatus.AVAILABLE
    )
    current_booking_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    event: Mapped["Event"] = relationship("Event", back_populates="seats")
    current_booking: Mapped["Booking | None"] = relationship(
        "Booking", foreign_keys=[current_booking_id]
    )


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seat_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("seats.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"), nullable=False, default=BookingStatus.HELD
    )
    hold_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="DIRECT")

    user: Mapped["User"] = relationship("User", back_populates="bookings")
    event: Mapped["Event"] = relationship("Event", back_populates="bookings")
    seat: Mapped["Seat"] = relationship("Seat", foreign_keys=[seat_id], back_populates=None)
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="booking", foreign_keys="Payment.booking_id"
    )
    events_log: Mapped[list["BookingEvent"]] = relationship(
        "BookingEvent", back_populates="booking", order_by="BookingEvent.created_at"
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    booking_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status"), nullable=False, default=PaymentStatus.PENDING
    )
    simulate_mode: Mapped[SimulateMode] = mapped_column(
        Enum(SimulateMode, name="simulate_mode"), nullable=False
    )
    settle_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_outcome: Mapped[str | None] = mapped_column(String(20), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now, onupdate=_now
    )

    booking: Mapped["Booking"] = relationship("Booking", back_populates="payments", foreign_keys=[booking_id])
    user: Mapped["User"] = relationship("User", back_populates="payments")


class BookingEvent(Base):
    __tablename__ = "booking_events"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    booking_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )

    booking: Mapped["Booking"] = relationship("Booking", back_populates="events_log")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("key", "user_id", "endpoint", name="pk_idempotency"),
    )

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
