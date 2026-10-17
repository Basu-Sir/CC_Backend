erDiagram
    users {
        UUID id PK
        string name
        string email UK
        timestamptz created_at
    }

    events {
        UUID id PK
        string name
        string venue
        timestamptz starts_at
        timestamptz sales_open_at
        int total_seats
        timestamptz created_at
    }

    seats {
        UUID id PK
        UUID event_id FK
        string label
        enum status "AVAILABLE|HELD|BOOKED"
        UUID current_booking_id FK "nullable"
        timestamptz updated_at
    }

    bookings {
        UUID id PK
        UUID user_id FK
        UUID event_id FK
        UUID seat_id FK
        enum status "HELD|PAYMENT_PENDING|CONFIRMED|EXPIRED|CANCELLED"
        timestamptz hold_expires_at
        timestamptz created_at
        timestamptz updated_at
        timestamptz confirmed_at "nullable"
        timestamptz cancelled_at "nullable"
        int payment_attempts
        string source "DIRECT|WAITLIST"
    }

    payments {
        UUID id PK
        UUID booking_id FK
        UUID user_id FK
        int amount
        enum status "PENDING|SUCCEEDED|FAILED|REFUNDED"
        enum simulate_mode "success|fail|delay|random"
        timestamptz settle_at "nullable"
        string final_outcome "nullable"
        string idempotency_key "nullable"
        string failure_reason "nullable"
        timestamptz created_at
        timestamptz updated_at
    }

    booking_events {
        UUID id PK
        UUID booking_id FK
        string type
        jsonb detail
        timestamptz created_at
    }

    idempotency_keys {
        string key PK
        UUID user_id PK
        string endpoint PK
        string request_hash
        int response_status
        jsonb response_body
        timestamptz created_at
    }

    users ||--o{ bookings : "makes"
    users ||--o{ payments : "pays"
    events ||--o{ seats : "has"
    events ||--o{ bookings : "contains"
    seats ||--o| bookings : "current_booking (nullable)"
    bookings ||--o{ payments : "has"
    bookings ||--o{ booking_events : "audit trail"
