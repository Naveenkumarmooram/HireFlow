"""Database-backed account throttling shared by serverless instances.

Identifiers are keyed hashes; email addresses and IPs are not stored here.
A successful login still consumes one attempt to avoid reset races.
"""

import hashlib
import hmac
import time

from fastapi import HTTPException
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LoginAttempt


def check_login_rate(db: Session, email: str) -> None:
    now = int(time.time())
    window = now // settings.login_window_seconds * settings.login_window_seconds
    key = hmac.new(settings.jwt_secret.encode(), email.lower().encode(), hashlib.sha256).hexdigest()
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(LoginAttempt).values(key=key, window_start=window, attempts=1)
    statement = statement.on_conflict_do_update(
        index_elements=[LoginAttempt.key],
        set_={
            "window_start": window,
            "attempts": case(
                (LoginAttempt.window_start == window, LoginAttempt.attempts + 1),
                else_=1,
            ),
        },
    ).returning(LoginAttempt.attempts)
    attempts = db.scalar(statement)
    db.execute(
        delete(LoginAttempt).where(
            LoginAttempt.window_start < window - settings.login_window_seconds
        )
    )
    db.commit()
    if attempts > settings.login_attempt_limit:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Try again later.",
            headers={"Retry-After": str(window + settings.login_window_seconds - now)},
        )
