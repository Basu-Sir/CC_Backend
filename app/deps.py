from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User


def get_current_user(
    x_user_id: str = Header(..., description="Demo user UUID. Replace with real auth in production."),
    db: Session = Depends(get_db),
) -> User:
    """
    Identify the caller via the X-User-Id header.
    Production must replace this with real authentication (SSO/JWT/OAuth).
    """
    user = db.get(User, x_user_id)
    if user is None:
        raise HTTPException(status_code=401, detail={
            "error": {
                "code": "UNAUTHENTICATED",
                "message": "User not found. Create a user via POST /api/v1/users first.",
                "details": {}
            }
        })
    return user
