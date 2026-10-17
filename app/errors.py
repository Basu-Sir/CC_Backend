from __future__ import annotations

from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, details: dict | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        },
    )


# Convenience shorthands
def not_found(resource: str) -> HTTPException:
    return api_error(404, "NOT_FOUND", f"{resource} not found.")


def forbidden(msg: str = "Forbidden") -> HTTPException:
    return api_error(403, "FORBIDDEN", msg)


def seat_unavailable(label: str = "") -> HTTPException:
    return api_error(409, "SEAT_UNAVAILABLE", f"Seat {label} is not available.")


def seat_busy() -> HTTPException:
    return api_error(409, "SEAT_BUSY", "Seat is locked by another request. Please retry.")


def invalid_state(msg: str) -> HTTPException:
    return api_error(409, "INVALID_STATE", msg)


def hold_expired() -> HTTPException:
    return api_error(409, "HOLD_EXPIRED", "The hold has expired.")


def payment_failed(reason: str) -> HTTPException:
    return api_error(402, "PAYMENT_FAILED", reason)
