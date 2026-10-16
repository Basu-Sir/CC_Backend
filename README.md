# The Last Seat — Concert Ticket Booking Backend

CC-VIT 2026–27 Recruitment Task

A REST API for a college concert with **500 seats and up to 10,000 concurrent booking attempts**, built to be demonstrably correct under race conditions.

---

## What this system does

- Users can view events and seat availability.
- A seat can be **temporarily held** for one user (120s by default).
- After holding, a **simulated payment** confirms the booking.
- Abandoned holds **expire** automatically (lazy expiry + background worker).
- Bookings can be **cancelled**; confirmed bookings simulate a refund.
- **At most one active booking may exist per seat** — enforced at the database level via row locking and a partial unique index.

---

## Architecture and Technology Stack

| Component | Choice |
|---|---|
| Language | Python 3.12 |
| Web framework | FastAPI + Pydantic v2 |
| Database | PostgreSQL 16 |
| ORM | SQLAlchemy 2.x (sync) |
| DB driver | psycopg v3 |
| Migrations | Alembic |
| Testing | pytest + HTTPX/TestClient |
| Load testing | Locust |
| Containerisation | Docker Compose |

**Source of truth:** PostgreSQL only. No booking decision is made from a cache.

---

## Prerequisites

- Docker and Docker Compose, OR
- Python 3.12 + PostgreSQL 16 (local)

---

## Quick Start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Then verify:
- `http://localhost:8000/health`
- `http://localhost:8000/docs`

---

## Quick Start (Local Python)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment
cp .env.example .env
# Edit .env: set DATABASE_URL to your local PostgreSQL

# 3. Run migrations
alembic upgrade head

# 4. Seed data
python scripts/seed.py

# 5. Start API
uvicorn app.main:app --reload

# 6. Start worker (separate terminal)
python -m app.worker
```

---

## Migrations and Seeding

```bash
# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1

# Seed (idempotent — safe to re-run)
python scripts/seed.py
```

Seed creates:
- 1 event with 500 seats (rows A–T, columns 01–25)
- 3 demo users (`alice@demo.local`, `bob@demo.local`, `charlie@demo.local`)

---

## API Examples

All endpoints require `X-User-Id: <uuid>` (except user creation and health).

### Create a user
```bash
curl -X POST http://localhost:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com"}'
```

### List events
```bash
curl http://localhost:8000/api/v1/events
```

### List available seats
```bash
curl "http://localhost:8000/api/v1/events/{event_id}/seats?status=AVAILABLE&page_size=10"
```

### Reserve a seat
```bash
curl -X POST http://localhost:8000/api/v1/bookings \
  -H "X-User-Id: {user_id}" \
  -H "Content-Type: application/json" \
  -d '{"event_id": "{event_id}", "seat_id": "{seat_id}"}'
```

### Check booking status
```bash
curl http://localhost:8000/api/v1/bookings/{booking_id} \
  -H "X-User-Id: {user_id}"
```

### Pay (success)
```bash
curl -X POST http://localhost:8000/api/v1/bookings/{booking_id}/pay \
  -H "X-User-Id: {user_id}" \
  -H "Content-Type: application/json" \
  -d '{"simulate": "success"}'
```

### Pay (fail)
```bash
curl -X POST http://localhost:8000/api/v1/bookings/{booking_id}/pay \
  -H "X-User-Id: {user_id}" \
  -d '{"simulate": "fail"}'
```

### Pay (delay — settles asynchronously)
```bash
curl -X POST http://localhost:8000/api/v1/bookings/{booking_id}/pay \
  -H "X-User-Id: {user_id}" \
  -d '{"simulate": "delay"}'
```

### Cancel
```bash
curl -X POST http://localhost:8000/api/v1/bookings/{booking_id}/cancel \
  -H "X-User-Id: {user_id}"
```

### Booking history
```bash
curl http://localhost:8000/api/v1/users/me/bookings \
  -H "X-User-Id: {user_id}"
```

---

## Running Tests

```bash
# Set test DB (must be a different DB from production)
export TEST_DATABASE_URL=postgresql+psycopg://booking:booking@localhost:5432/booking_test

pytest tests/ -v
```

Concurrency tests use real PostgreSQL. Mock sessions are not used.

---

## Running Load Tests

```bash
locust -f loadtest/locustfile.py \
  --host http://localhost:8000 \
  --users 50 --spawn-rate 5 --run-time 60s --headless
```

See `loadtest/README.md` and `docs/LOAD_TEST_RESULTS.md` for details.

---

## Consistency Verifier

```bash
python scripts/verify_consistency.py
```

Checks 8 database invariants. Exits 0 on PASS, 1 on FAIL.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` | PostgreSQL connection string |
| `HOLD_TTL_SECONDS` | `120` | How long a seat hold lasts |
| `PAYMENT_DELAY_SECONDS` | `10` | Delay before simulated async payment settles |
| `PAYMENT_RETRY_WINDOW_SECONDS` | `60` | Retry window after a failed delayed payment |
| `MAX_PAYMENT_ATTEMPTS` | `3` | Failures before booking is cancelled |
| `SWEEP_INTERVAL_SECONDS` | `5` | Worker sweep frequency |
| `SEAT_PRICE` | `500` | Seat price in rupees |
| `DB_LOCK_TIMEOUT_MS` | `2000` | PostgreSQL lock wait timeout |

---

## Known Limitations

- **Authentication is simplified**: `X-User-Id` header is for demo only. Production requires real SSO/JWT/OAuth.
- **Payments are simulated**: No real gateway. `simulate=success|fail|delay|random`.
- **Worker-down gap**: If the worker is down, PAYMENT_PENDING seats stay locked until it restarts.
- **No rate limiting**: P2 feature (requires Redis).
- **No waitlist**: P2 feature.
- **Single PostgreSQL node**: No read replicas.

---

## Features Implemented vs Not Implemented

| Feature | Status |
|---|---|
| Reserve seat (row lock, lazy expiry) | ✅ Implemented |
| Confirm payment (success/fail/delay) | ✅ Implemented |
| Hold expiry (lazy + worker) | ✅ Implemented |
| Cancel (HELD and CONFIRMED) | ✅ Implemented |
| Background worker | ✅ Implemented |
| Booking history and audit trail | ✅ Implemented |
| Concurrency tests | ✅ Implemented |
| Consistency verifier | ✅ Implemented |
| Docker Compose | ✅ Implemented |
| API docs (`/docs`) | ✅ Implemented |
| Idempotency keys (P1) | ⚠️ Schema present; header middleware not wired |
| Redis seat cache (P2) | ❌ Not implemented |
| Rate limiting (P2) | ❌ Not implemented |
| Waitlist (P2) | ❌ Not implemented |
| Load test results | ⚠️ Template present; not yet run |
