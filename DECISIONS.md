# DECISIONS.md

## Questions for the student

### 1. What was the most technically challenging part of the implementation, and how did you approach it?

The most technically challenging part was guaranteeing zero double-bookings under extreme concurrency (simulating thousands of students racing for the same seat at the same millisecond) while managing time-limited holds, lazy expiry, and asynchronous payment states.

I approached this with a defense-in-depth model centered entirely on PostgreSQL as the single source of truth:

1. **Row-Level Locking with `NOWAIT`:** When reserving a seat, the transaction locks the row using `SELECT ... FOR UPDATE NOWAIT`. Contenders immediately receive a fast `409 Conflict (SEAT_BUSY)` rather than queuing up, which prevents connection pool exhaustion and thread starvation under load.
2. **Lazy Hold Expiry Inside the Lock:** Before deciding seat availability, the transaction checks whether an existing hold has expired using the database clock (`clock_timestamp()`). If expired, it releases the stale hold and reallocates the seat to the current caller in a single atomic transaction.
3. **Database-Level Partial Unique Index:** As an ultimate backstop against race conditions, I created a partial unique index:
   ```sql
   CREATE UNIQUE INDEX uq_active_booking_per_seat 
   ON bookings (event_id, seat_id) 
   WHERE status IN ('HELD', 'CONFIRMED', 'PAYMENT_PENDING');
   ```
   Even if application-layer locks failed or experienced edge cases, PostgreSQL itself rejects any duplicate active booking with an `IntegrityError`.
4. **Strict Lock Ordering:** Across all booking, payment, and cancellation flows, locks are always acquired in a fixed order (`Seat` → `Booking` → `Payment`) to mathematically eliminate deadlocks.

---

### 2. Describe one important design decision you made, and why did you choose that approach over alternatives?

I chose **PostgreSQL transactional row locks and constraints as the authoritative lock mechanism**, rather than using in-memory application locks (e.g., Python `threading.Lock`) or a distributed lock manager (e.g., Redis Redlock).

**Why this approach was chosen over alternatives:**
- **Alternative 1 — In-process locks (`threading.Lock` / `asyncio.Lock`):** In-memory locks only synchronize within a single Python process. In real-world deployments running multiple Uvicorn/Gunicorn workers or multiple Docker replicas, separate worker processes cannot see each other's memory, resulting in immediate double-bookings under concurrent traffic.
- **Alternative 2 — Redis Distributed Lock (Redlock):** Adding Redis as the authority for seat reservations introduces dual-system synchronization problems. If Redis grants a lock but the database transaction fails to commit (or vice versa), the system enters an inconsistent split-brain state. Redis distributed locks also suffer from TTL expiration edge cases during process pauses (garbage collection, high CPU) where a lock is prematurely released while the transaction is still writing.
- **The PostgreSQL Solution:** PostgreSQL provides ACID guarantees out of the box. Because the seat status change and booking record creation must be committed to the database anyway, handling the lock inside the database transaction ensures that the lock and the data change are 100% atomic, crash-resilient, and cluster-safe across all replicas.

---

### 3. What is one limitation or failure case the implementation does not handle well?

The primary limitation is the **"Hot-Seat Thundering Herd" problem on database connections**.

While `SELECT ... FOR UPDATE NOWAIT` prevents queries from waiting on each other, every single incoming request still opens a database connection and executes a transaction against PostgreSQL. If 5,000 students hammer the exact same popular seat within a 200-millisecond window:
- 1 request acquires the row lock and succeeds.
- 4,999 requests hit the database, fail the lock check, rollback, and return `409 Conflict`.

Even though correctness is strictly preserved, this thundering herd can saturate the PostgreSQL connection pool, increase connection overhead, and degrade latency for requests touching other non-conflicting seats. 

Furthermore, delayed payment settlement depends on the background worker process; if the worker crashes or falls behind, bookings in `PAYMENT_PENDING` remain locked longer than intended before resolving.

---

### 4. If you had another week, what would you improve first and why?

If I had another week, I would implement two key improvements in order of priority:

1. **Redis Read-Through Caching and Rate Limiting (Priority 1):**
   - **Why:** In ticket drops, 90–95% of incoming traffic consists of repeated read requests (`GET /events/{id}/seats`) from users refreshing seat maps. Serving seat maps directly from PostgreSQL creates unnecessary I/O.
   - **Improvement:** Cache the seat availability map in Redis with a short TTL (e.g., 2–3 seconds) and invalidate the cache asynchronously on booking state mutations. In addition, implement sliding-window rate limiting (via Redis token bucket) per IP/User to deflect automated scripts and bot traffic before they ever touch PostgreSQL.

2. **FIFO Transactional Waitlist (Priority 2):**
   - **Why:** When a sold-out concert has holds that expire or bookings that get cancelled, currently the seat is returned to the public pool, triggering another chaotic race condition among users.
   - **Improvement:** Introduce a `waitlist` table ordered by `joined_at`. When a seat is released, the background worker or release transaction atomically allocates a 2-minute exclusive hold to the next eligible user in the queue and notifies them (e.g., via webhook or email), creating a fair and orderly user experience.
