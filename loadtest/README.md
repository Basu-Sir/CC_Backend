# Load Test Instructions

## Quick start

```bash
locust -f loadtest/locustfile.py --host http://localhost:8000 -u 50 -r 5 --headless --run-time 60s
```

Open the Locust web UI (interactive):

```bash
locust -f loadtest/locustfile.py --host http://localhost:8000
# Then visit http://localhost:8089
```

## Recommended test progression

1. Start small: `-u 20 -r 2` — verify no errors.
2. Medium: `-u 50 -r 5` — measure p95 latency.
3. High: `-u 100 -r 10` — stress test.

## What to record

See `docs/LOAD_TEST_RESULTS.md` for the results template.

Treat `409 SEAT_UNAVAILABLE` as expected contention, NOT a failure.

## Notes

- Run `python scripts/verify_consistency.py` after each load test.
- Record actual hardware specs when reporting numbers.
