from __future__ import annotations

"""
idempotency.py — P1 idempotency key support.

Stores request hash + response in same transaction as the state change.
"""

import hashlib
import json

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import IdempotencyKey


def make_request_hash(method: str, path: str, body: dict | None) -> str:
    raw = json.dumps({"method": method, "path": path, "body": body or {}}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_saved_response(
    db: Session, key: str, user_id: str, endpoint: str
) -> IdempotencyKey | None:
    return db.get(IdempotencyKey, (key, user_id, endpoint))


def save_response(
    db: Session,
    key: str,
    user_id: str,
    endpoint: str,
    request_hash: str,
    status_code: int,
    body: dict,
) -> None:
    idem = IdempotencyKey(
        key=key,
        user_id=user_id,
        endpoint=endpoint,
        request_hash=request_hash,
        response_status=status_code,
        response_body=body,
    )
    db.add(idem)
    # Caller commits in the same transaction as the state change.
