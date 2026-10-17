"""Initial schema: users, events, seats, bookings, payments, booking_events, idempotency_keys

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-17 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enums ---
    seat_status = postgresql.ENUM("AVAILABLE", "HELD", "BOOKED", name="seat_status", create_type=False)
    seat_status.create(op.get_bind(), checkfirst=True)

    booking_status = postgresql.ENUM(
        "HELD", "PAYMENT_PENDING", "CONFIRMED", "EXPIRED", "CANCELLED",
        name="booking_status", create_type=False,
    )
    booking_status.create(op.get_bind(), checkfirst=True)

    payment_status = postgresql.ENUM("PENDING", "SUCCEEDED", "FAILED", "REFUNDED", name="payment_status", create_type=False)
    payment_status.create(op.get_bind(), checkfirst=True)

    simulate_mode = postgresql.ENUM("success", "fail", "delay", "random", name="simulate_mode", create_type=False)
    simulate_mode.create(op.get_bind(), checkfirst=True)

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- events ---
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("venue", sa.String(255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sales_open_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_seats", sa.Integer(), nullable=False, server_default="500"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- bookings (before seats for FK) ---
    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("seat_id", postgresql.UUID(as_uuid=False), nullable=False),  # FK added after seats
        sa.Column("status", sa.Enum("HELD", "PAYMENT_PENDING", "CONFIRMED", "EXPIRED", "CANCELLED", name="booking_status"), nullable=False),
        sa.Column("hold_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False, server_default="DIRECT"),
    )

    # --- seats ---
    op.create_table(
        "seats",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("status", sa.Enum("AVAILABLE", "HELD", "BOOKED", name="seat_status"), nullable=False, server_default="AVAILABLE"),
        sa.Column("current_booking_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("bookings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "label", name="uq_seat_event_label"),
    )

    # Add FK seat_id → seats on bookings
    op.create_foreign_key(
        "fk_bookings_seat_id", "bookings", "seats", ["seat_id"], ["id"], ondelete="RESTRICT"
    )

    # --- payments ---
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("PENDING", "SUCCEEDED", "FAILED", "REFUNDED", name="payment_status"), nullable=False),
        sa.Column("simulate_mode", sa.Enum("success", "fail", "delay", "random", name="simulate_mode"), nullable=False),
        sa.Column("settle_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_outcome", sa.String(20), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- booking_events ---
    op.create_table(
        "booking_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # --- idempotency_keys ---
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("endpoint", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", "user_id", "endpoint", name="pk_idempotency"),
    )

    # === Indexes ===

    # Partial unique index: at most one active booking per seat (the key safety backstop)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_active_booking_per_seat
        ON bookings (seat_id)
        WHERE status IN ('HELD', 'PAYMENT_PENDING', 'CONFIRMED')
        """
    )

    op.create_index("ix_bookings_status_hold_expires", "bookings", ["status", "hold_expires_at"])
    op.create_index("ix_bookings_user_created", "bookings", ["user_id", sa.text("created_at DESC")])
    op.create_index("ix_seats_event_status", "seats", ["event_id", "status"])
    op.create_index("ix_payments_status_settle", "payments", ["status", "settle_at"])
    op.create_index("ix_booking_events_booking", "booking_events", ["booking_id"])


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.drop_table("booking_events")
    op.drop_table("payments")
    op.drop_constraint("fk_bookings_seat_id", "bookings", type_="foreignkey")
    op.drop_table("seats")
    op.drop_table("bookings")
    op.drop_table("events")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS seat_status")
    op.execute("DROP TYPE IF EXISTS booking_status")
    op.execute("DROP TYPE IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS simulate_mode")
