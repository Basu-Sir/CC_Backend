# WORKFLOWS.md — System Workflow Diagrams

## 1. Reserve → Pay → Confirm

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant DB as PostgreSQL

    C->>API: POST /bookings {event_id, seat_id}
    API->>DB: BEGIN
    API->>DB: SELECT seat FOR UPDATE NOWAIT
    alt Seat is HELD and expired
        API->>DB: mark booking EXPIRED, seat AVAILABLE
    end
    alt Seat AVAILABLE
        API->>DB: INSERT booking (HELD)
        API->>DB: UPDATE seat (HELD, current_booking_id)
        API->>DB: INSERT booking_event (HELD)
        API->>DB: COMMIT
        API-->>C: 201 {booking_id, hold_expires_at}
    else Seat not available
        API->>DB: ROLLBACK
        API-->>C: 409 SEAT_UNAVAILABLE
    end

    C->>API: POST /bookings/{id}/pay {simulate: success}
    API->>DB: BEGIN
    API->>DB: SELECT seat FOR UPDATE NOWAIT
    API->>DB: SELECT booking FOR UPDATE
    API->>DB: INSERT payment (SUCCEEDED)
    API->>DB: UPDATE booking → CONFIRMED
    API->>DB: UPDATE seat → BOOKED
    API->>DB: COMMIT
    API-->>C: 200 {payment_id, status: SUCCEEDED}
```

## 2. Two Users Racing for One Seat

```mermaid
sequenceDiagram
    participant U1 as User 1
    participant U2 as User 2
    participant DB as PostgreSQL

    U1->>DB: BEGIN; SELECT seat FOR UPDATE NOWAIT → gets lock
    U2->>DB: BEGIN; SELECT seat FOR UPDATE NOWAIT → 55P03 (lock not available)
    U2-->>U2: 409 SEAT_BUSY (fail fast)
    U1->>DB: INSERT booking, UPDATE seat → HELD
    U1->>DB: COMMIT
    Note over DB: Partial unique index ensures only one active booking
```

## 3. Delayed Payment Settlement

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant DB as PostgreSQL
    participant W as Worker

    C->>API: POST /bookings/{id}/pay {simulate: delay}
    API->>DB: INSERT payment (PENDING, settle_at=now+10s)
    API->>DB: UPDATE booking → PAYMENT_PENDING
    API-->>C: 200 {status: PENDING, settle_at}

    Note over W: Every 5s sweep
    W->>DB: SELECT payments WHERE status=PENDING AND settle_at<=now
    W->>DB: SELECT seat FOR UPDATE SKIP LOCKED
    W->>DB: SELECT booking FOR UPDATE
    W->>DB: SELECT payment FOR UPDATE
    alt final_outcome = success
        W->>DB: payment→SUCCEEDED, booking→CONFIRMED, seat→BOOKED
    else final_outcome = fail
        W->>DB: payment→FAILED, booking→HELD (retry window) or CANCELLED
    end
    W->>DB: COMMIT
```

## 4. Booking State Machine

```mermaid
stateDiagram-v2
    [*] --> HELD : reserve (seat AVAILABLE)
    HELD --> EXPIRED : hold_expires_at passed (lazy or worker)
    HELD --> CANCELLED : user cancels / max payment attempts
    HELD --> PAYMENT_PENDING : simulate delay
    HELD --> CONFIRMED : simulate success

    PAYMENT_PENDING --> CONFIRMED : worker settles (success)
    PAYMENT_PENDING --> HELD : worker settles (fail, retry window)
    PAYMENT_PENDING --> CANCELLED : max attempts or user cancels

    CONFIRMED --> CANCELLED : user cancels (seat released, payment refunded)

    EXPIRED --> [*]
    CANCELLED --> [*]
```

## 5. Hold Expiry and Seat Release

```mermaid
flowchart TD
    A[Seat HELD] --> B{Is hold_expires_at <= now?}
    B -- No --> C[Seat stays HELD]
    B -- Yes via lazy --> D[User attempts new reservation]
    D --> E[Lock seat FOR UPDATE]
    E --> F[Read existing booking under lock]
    F --> G{Status HELD and expired?}
    G -- Yes --> H[Mark booking EXPIRED]
    H --> I[Set seat AVAILABLE]
    I --> J[New booking created for requester]
    B -- Yes via worker --> K[Worker sweep]
    K --> L[SELECT seat FOR UPDATE SKIP LOCKED]
    L --> M[Re-check after lock]
    M --> N[Mark EXPIRED, release seat, audit event]
```
