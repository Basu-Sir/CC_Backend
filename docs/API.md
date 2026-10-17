# API.md — REST API Reference

Base URL: `http://localhost:8000/api/v1`  
Interactive docs: `http://localhost:8000/docs`

## Authentication

All endpoints except `POST /users`, `GET /health`, `GET /ready` require:

```
X-User-Id: <uuid>
```

This is a demo header. **In production, replace with real authentication (college SSO/JWT/OAuth).**

---

## Health

### GET /health
No auth required.
```json
{"status": "ok"}
```

### GET /ready
Checks DB connection.
```json
{"status": "ok", "db": "connected"}
```

---

## Users

### POST /api/v1/users
Create a demo user. Idempotent by email.

**Request:**
```json
{"name": "Alice", "email": "alice@example.com"}
```
**Response 201:**
```json
{"id": "uuid", "name": "Alice", "email": "alice@example.com", "created_at": "..."}
```

### GET /api/v1/users/me/bookings
Requires `X-User-Id`. Returns booking history.

---

## Events

### GET /api/v1/events
List all events.

### GET /api/v1/events/{event_id}
Event details including seat counts.
```json
{"id": "...", "name": "...", "available": 498, "held": 1, "booked": 1, ...}
```

### GET /api/v1/events/{event_id}/seats
Seat map. Query params: `status=AVAILABLE|HELD|BOOKED`, `page=1`, `page_size=100`.

---

## Bookings

### POST /api/v1/bookings
Reserve a seat.

**Request:**
```json
{"event_id": "uuid", "seat_id": "uuid"}
```
**Response 201:**
```json
{"id": "uuid", "status": "HELD", "hold_expires_at": "...", "seconds_remaining": 120, ...}
```
**Errors:** `409 SEAT_UNAVAILABLE`, `409 SEAT_BUSY`, `403 SALES_NOT_OPEN`

### GET /api/v1/bookings/{booking_id}
Reservation status with `seconds_remaining`.

### GET /api/v1/bookings/{booking_id}/timeline
Audit trail of all events on this booking.

### POST /api/v1/bookings/{booking_id}/pay
Simulate a payment.

**Request:**
```json
{"method": "card", "simulate": "success"}
```
`simulate` values: `success`, `fail`, `delay`, `random`.

**Response 200 (success):**
```json
{"id": "...", "status": "SUCCEEDED", ...}
```
**Response 200 (delay):**
```json
{"id": "...", "status": "PENDING", "settle_at": "...", ...}
```
**Response 402 (fail):**
```json
{"error": {"code": "PAYMENT_FAILED", "message": "...", "details": {}}}
```

### POST /api/v1/bookings/{booking_id}/cancel
Cancel a booking. Idempotent on already-cancelled.

---

## Payments

### GET /api/v1/payments/{payment_id}
Payment status. Owner only.

---

## Admin

### GET /api/v1/admin/events/{event_id}/stats
Seat and booking counts for verification.
```json
{
  "event_id": "...",
  "total_seats": 500,
  "available": 498,
  "held": 1,
  "booked": 1,
  "confirmed_bookings": 1,
  "expired_bookings": 0,
  "cancelled_bookings": 0
}
```

---

## Error shape

All errors return:
```json
{
  "error": {
    "code": "SEAT_UNAVAILABLE",
    "message": "Seat A-01 is not available",
    "details": {}
  }
}
```

## HTTP status codes

| Code | Meaning |
|---|---|
| 200 | Successful read/update |
| 201 | New hold created |
| 202 | Delayed payment accepted |
| 401 | Missing/invalid user |
| 402 | Simulated payment failure |
| 403 | Sales not open or forbidden |
| 404 | Resource not found |
| 409 | Seat conflict, lock contention, expired hold, invalid state |
| 422 | Validation error |
