from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import engine
from app.routers import events, bookings, payments, admin, users

app = FastAPI(
    title="The Last Seat — Concert Ticket Booking API",
    description=(
        "CC-VIT 2026–27 recruitment task. "
        "500 seats, up to 10,000 concurrent users. "
        "PostgreSQL is the source of truth."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# Exception handlers — convert raw HTTPExceptions to the defined error shape
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        # Already structured
        if isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "ERROR", "message": str(exc.detail), "details": {}}},
        )
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": str(exc), "details": {}}},
    )


# ---------------------------------------------------------------------------
# Health / Readiness
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Health"])
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "unavailable", "detail": str(exc)})


# ---------------------------------------------------------------------------
# Routers (all under /api/v1 prefix)
# ---------------------------------------------------------------------------

PREFIX = "/api/v1"

app.include_router(users.router, prefix=PREFIX)
app.include_router(events.router, prefix=PREFIX)
app.include_router(bookings.router, prefix=PREFIX)
app.include_router(payments.router, prefix=PREFIX)
app.include_router(admin.router, prefix=PREFIX)
