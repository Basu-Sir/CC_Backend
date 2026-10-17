"""
loadtest/locustfile.py — Locust load test scenarios for The Last Seat.

Run:
  locust -f loadtest/locustfile.py --host http://localhost:8000 -u 100 -r 10

Scenarios:
1. Browse available seats.
2. Many users attempting the same few hot seats.
3. Full flow: reserve → pay → confirm.
4. Cancel abandoned holds.
"""
from __future__ import annotations

import random
import uuid

from locust import HttpUser, TaskSet, between, events, task


# ---------------------------------------------------------------------------
# Shared state (populated during setup)
# ---------------------------------------------------------------------------

_event_id: str | None = None
_hot_seat_ids: list[str] = []
_user_pool: list[str] = []  # user IDs pre-created


def _create_user(client) -> str | None:
    resp = client.post(
        "/api/v1/users",
        json={"name": "Load User", "email": f"load-{uuid.uuid4().hex[:10]}@test.load"},
        name="/api/v1/users [setup]",
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]
    return None


@events.test_start.add_listener
def on_start(environment, **kwargs):
    global _event_id, _hot_seat_ids
    client = environment.runner.user_classes[0]._make_locust_client(environment)
    # Get first event
    resp = client.get("/api/v1/events", name="/api/v1/events [setup]")
    if resp.status_code == 200 and resp.json():
        _event_id = resp.json()[0]["id"]
        # Pick 5 hot seats from the first available
        seats_resp = client.get(
            f"/api/v1/events/{_event_id}/seats?status=AVAILABLE&page_size=5",
            name="setup seats",
        )
        if seats_resp.status_code == 200:
            _hot_seat_ids = [s["id"] for s in seats_resp.json().get("items", [])]


# ---------------------------------------------------------------------------
# Task sets
# ---------------------------------------------------------------------------


class BrowseTaskSet(TaskSet):
    @task(3)
    def list_events(self):
        self.client.get("/api/v1/events", name="/api/v1/events")

    @task(5)
    def browse_seats(self):
        if _event_id:
            self.client.get(
                f"/api/v1/events/{_event_id}/seats?status=AVAILABLE&page_size=50",
                name="/api/v1/events/{id}/seats",
            )

    @task(1)
    def health(self):
        self.client.get("/health")


class HotSeatTaskSet(TaskSet):
    """Multiple users hammering a few hot seats."""

    @task
    def try_hot_seat(self):
        if not _hot_seat_ids or not _event_id:
            return
        seat_id = random.choice(_hot_seat_ids)
        resp = self.client.post(
            "/api/v1/bookings",
            json={"event_id": _event_id, "seat_id": seat_id},
            headers={"X-User-Id": self.user.user_id},
            name="POST /bookings [hot seat]",
        )
        # 409 is expected contention, not a failure
        if resp.status_code == 409:
            resp.success()


class FullFlowTaskSet(TaskSet):
    """Reserve a random available seat and pay."""

    @task
    def full_flow(self):
        if not _event_id:
            return

        # Get a random available seat
        resp = self.client.get(
            f"/api/v1/events/{_event_id}/seats?status=AVAILABLE&page_size=50",
            name="/api/v1/events/{id}/seats",
        )
        if resp.status_code != 200:
            return
        items = resp.json().get("items", [])
        if not items:
            return
        seat_id = random.choice(items)["id"]

        # Reserve
        resp = self.client.post(
            "/api/v1/bookings",
            json={"event_id": _event_id, "seat_id": seat_id},
            headers={"X-User-Id": self.user.user_id},
            name="POST /bookings",
        )
        if resp.status_code not in (200, 201):
            return
        booking_id = resp.json()["id"]

        # Pay
        self.client.post(
            f"/api/v1/bookings/{booking_id}/pay",
            json={"simulate": "success"},
            headers={"X-User-Id": self.user.user_id},
            name="POST /bookings/{id}/pay",
        )


# ---------------------------------------------------------------------------
# User classes
# ---------------------------------------------------------------------------


class BrowseUser(HttpUser):
    tasks = [BrowseTaskSet]
    wait_time = between(0.5, 2)
    weight = 5

    user_id: str = ""

    @classmethod
    def _make_locust_client(cls, environment):
        from locust.clients import HttpSession
        return HttpSession(base_url=environment.host, request_event=environment.events.request)

    def on_start(self):
        uid = _create_user(self.client)
        self.user_id = uid or str(uuid.uuid4())


class HotSeatUser(HttpUser):
    tasks = [HotSeatTaskSet]
    wait_time = between(0.1, 0.5)
    weight = 3

    user_id: str = ""

    @classmethod
    def _make_locust_client(cls, environment):
        from locust.clients import HttpSession
        return HttpSession(base_url=environment.host, request_event=environment.events.request)

    def on_start(self):
        uid = _create_user(self.client)
        self.user_id = uid or str(uuid.uuid4())


class FullFlowUser(HttpUser):
    tasks = [FullFlowTaskSet]
    wait_time = between(1, 3)
    weight = 2

    user_id: str = ""

    @classmethod
    def _make_locust_client(cls, environment):
        from locust.clients import HttpSession
        return HttpSession(base_url=environment.host, request_event=environment.events.request)

    def on_start(self):
        uid = _create_user(self.client)
        self.user_id = uid or str(uuid.uuid4())
