# LOAD_TEST_RESULTS.md — Load Test Results

## Status

> **Not yet run.** Load tests require Docker + PostgreSQL to be running.

To run the load test:

```bash
# 1. Start the stack
cp .env.example .env
docker compose up --build -d

# 2. Run Locust headless (50 users, 5/s spawn rate, 60s)
locust -f loadtest/locustfile.py \
  --host http://localhost:8000 \
  --users 50 \
  --spawn-rate 5 \
  --run-time 60s \
  --headless \
  --csv loadtest/results

# 3. Verify consistency
python scripts/verify_consistency.py
```

## Results template (fill in after running)

| Metric | Value |
|---|---|
| Machine | _(CPU, RAM)_ |
| Docker workers | 2 API, 1 worker |
| Locust users | _(N)_ |
| Spawn rate | _(N/s)_ |
| Duration | _(s)_ |
| Total requests | _(N)_ |
| Throughput | _(req/s)_ |
| p50 latency | _(ms)_ |
| p95 latency | _(ms)_ |
| p99 latency | _(ms)_ |
| HTTP 201 (seats reserved) | _(N)_ |
| HTTP 409 (contention — expected) | _(N)_ |
| HTTP 500 (unexpected errors) | _(N)_ |
| Final confirmed bookings | _(N)_ |
| Consistency verifier | _(PASS/FAIL)_ |

## Notes

- `409 SEAT_UNAVAILABLE` and `409 SEAT_BUSY` are **expected** under contention and are not treated as failures.
- Do not fabricate numbers. Start small (20–50 users) and scale up based on hardware.
- A documented lower maximum is better than invented results.
