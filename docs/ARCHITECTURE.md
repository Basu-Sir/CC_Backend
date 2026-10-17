# ARCHITECTURE.md — System Design

## Why PostgreSQL is the source of truth

PostgreSQL is the single authoritative store for all seat and booking state.
Every state transition—reserve, pay, confirm, expire, cancel—is performed inside
a database transaction. This means:

- Reads and writes are consistent and durable.
- No "split-brain" between a cache and the database.
- Worker restarts and API restarts are safe: the DB holds the correct state.

**We never make a booking decision based on a cache (Redis) or in-memory lock.**

## Row-level locking: SELECT ... FOR UPDATE NOWAIT

When a user tries to reserve a seat, the reservation transaction acquires an
exclusive row lock on the seat row:

```sql
SELECT * FROM seats WHERE id = $1 FOR UPDATE NOWAIT
```

`NOWAIT` means: if another transaction already holds the lock (another user
trying to book the same seat), this transaction immediately raises error
`55P03 lock_not_available`. The API converts this to `409 SEAT_BUSY`.

This keeps the system responsive under hot contention: instead of 10,000
requests queuing behind one lock and exhausting the connection pool, they
fail fast and can retry or pick another seat.

## Partial unique index as a backstop

Even with row locking, concurrent retries and edge cases could theoretically
produce two active bookings for one seat. The database enforces:

```sql
CREATE UNIQUE INDEX uq_active_booking_per_seat
ON bookings (seat_id)
WHERE status IN ('HELD', 'PAYMENT_PENDING', 'CONFIRMED');
```

This index means PostgreSQL itself will raise an `IntegrityError` if any code
path (bug, race, replay) tries to insert a second active booking for the same seat.
The API catches this and returns `409 SEAT_UNAVAILABLE`. **This index is never removed.**

## Lock order: SEAT → BOOKING → PAYMENT

Every state-changing code path acquires locks in the same order:
seat → booking → payment. Mixing lock order across concurrent transactions is
the classic recipe for deadlocks. Consistent order ensures two transactions can
only deadlock if they both want the *same* seat, which PostgreSQL detects and
resolves automatically (one transaction is aborted and retried).

## Atomic state changes in transactions

All related writes in a single operation (reserve/pay/cancel) are committed
atomically. Either all writes succeed or none do. This means:
- A confirmed booking always has exactly one succeeded payment.
- A released seat always has `current_booking_id = NULL`.
- An audit event is always appended in the same transaction.

## Database-clock expiry

Expiry decisions use `clock_timestamp()` (the PostgreSQL server clock), not
each API worker's local Python `datetime.now()`. This avoids clock skew when
multiple API replicas have slightly different system clocks.

Within a transaction that acquires locks, `clock_timestamp()` is used (not
`now()`/`CURRENT_TIMESTAMP`, which is fixed at transaction start and becomes
stale if the transaction waits for a lock).

## Background worker

The worker (`app/worker.py`) runs as a separate process that periodically:

1. Finds HELD bookings past their `hold_expires_at` (plain SELECT, no lock).
2. For each, tries to lock the seat `FOR UPDATE SKIP LOCKED` (skips if busy).
3. Locks the booking, re-checks status and expiry, marks EXPIRED, releases seat.
4. Finds PENDING payments past their `settle_at` and settles them.

`SKIP LOCKED` allows multiple worker replicas to process different rows in
parallel without fighting over the same seat.

**The worker is mandatory for delayed-payment settlement.** If it is down,
PAYMENT_PENDING seats stay unavailable until it restarts. This is a documented
limitation; production would add a settlement timeout.

## Lazy expiry

When a user tries to reserve a seat that is HELD but expired, the reservation
transaction itself expires the old booking and continues. This means seats
eventually become available even without the worker, as long as users are
actively trying to book them.

## Idempotency and retries

- `POST /bookings`: if the same user re-requests the same seat while their hold
  is active, the existing booking is returned (no duplicate created).
- `POST /bookings/{id}/cancel`: cancelling an already-cancelled booking returns
  the current state without error.
- P1: `Idempotency-Key` header stores key+response in the same transaction as
  the state change; duplicate requests return the saved response.

## What happens on restart

- **API restart**: stateless. Reconnects to PostgreSQL. No in-flight work is lost
  because all state is in the DB.
- **Worker restart**: resumes the sweep loop. Any payments that were supposed to
  settle during the downtime are settled on the next sweep.
- **PostgreSQL restart**: PostgreSQL WAL ensures committed transactions survive.

## Why in-memory locks are insufficient

Python `threading.Lock` only works within a single process. With multiple API
workers (Uvicorn `--workers 2+`) or multiple Docker replicas, each process has
its own lock objects. Two processes can both see a seat as AVAILABLE and both
create a booking. Only PostgreSQL row locks and the unique index coordinate
across processes.

## Scaling options

| Concern | Approach |
|---|---|
| More API traffic | Add stateless API replicas (no shared state) |
| DB connection overload | PgBouncer connection pooler in front of PostgreSQL |
| Read-heavy seat maps | Short-TTL Redis cache (invalidated on every booking mutation) |
| Thundering herd on sale open | Admission control / virtual waiting room (rate limiter + queue) |
| Delayed payment settlement | Dedicated queue (Celery/RQ/SQS) instead of simple sweep |
| Observability | Prometheus metrics + Grafana; pg_locks monitoring; distributed tracing |

## Limitations and tradeoffs

- **Simplified authentication**: `X-User-Id` header is for demo only. Production requires SSO/JWT.
- **Simulated payments**: no real payment gateway. A production system integrates with Stripe/Razorpay via webhooks.
- **Worker-down PAYMENT_PENDING**: a pending payment holds the seat until the worker restarts. No settlement timeout.
- **No rate limiting**: implemented with Redis (P2). Without it, a single user can flood requests.
- **No waitlist**: P2 feature; would require additional tables and careful seat-release logic.
- **Single PostgreSQL node**: no read replicas. Under extreme read load, a cache layer is needed.
