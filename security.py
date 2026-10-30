"""Password hashing, opaque session/reset tokens and the current-user dependencies."""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta
from typing import Annotated

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database import get_db, utcnow
from models import Session, User

# bcrypt only looks at the first 72 bytes; longer passwords are refused rather than silently cut.
MAX_PASSWORD_BYTES = 72


def settings_of(request: Request) -> Settings:
    return request.app.state.settings


async def hash_password(password: str, rounds: int) -> str:
    # bcrypt is deliberately slow; keep it off the event loop.
    salt = bcrypt.gensalt(rounds)
    hashed = await run_in_threadpool(bcrypt.hashpw, password.encode(), salt)
    return hashed.decode()


async def verify_password(password: str, password_hash: str) -> bool:
    try:
        return await run_in_threadpool(bcrypt.checkpw, password.encode(), password_hash.encode())
    except ValueError:
        return False


def new_token() -> tuple[str, str]:
    """Returns (token for the client, hash to store)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def start_session(db: AsyncSession, response: Response, request: Request, user: User, remember: bool) -> None:
    settings = settings_of(request)
    days = settings.session_days_remember if remember else settings.session_days_default
    token, token_hash = new_token()
    db.add(Session(user_id=user.id, token_hash=token_hash, expires_at=utcnow() + timedelta(days=days)))
    await db.commit()
    response.set_cookie(
        settings.session_cookie,
        token,
        # Without "remember me" the cookie lasts until the browser closes (the server copy expires in a day).
        max_age=days * 86400 if remember else None,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


async def end_session(db: AsyncSession, response: Response, request: Request) -> None:
    settings = settings_of(request)
    token = request.cookies.get(settings.session_cookie)
    if token:
        await db.execute(delete(Session).where(Session.token_hash == hash_token(token)))
        await db.commit()
    response.delete_cookie(settings.session_cookie, path="/")


async def optional_user(request: Request, db: Annotated[AsyncSession, Depends(get_db)]) -> User | None:
    token = request.cookies.get(settings_of(request).session_cookie)
    if not token:
        return None
    session = await db.scalar(select(Session).where(Session.token_hash == hash_token(token)))
    if not session:
        return None
    if session.expires_at <= utcnow():
        await db.delete(session)
        await db.commit()
        return None
    return session.user


async def require_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in first.")
    return user


OptionalUser = Annotated[User | None, Depends(optional_user)]
CurrentUser = Annotated[User, Depends(require_user)]
DB = Annotated[AsyncSession, Depends(get_db)]


class LoginThrottle:
    """Refuses further attempts for an email after too many recent failures (in memory, per process)."""

    def __init__(self, limit: int = 10, window_s: int = 15 * 60):
        self.limit = limit
        self.window_s = window_s
        self.failures: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str, now: float) -> deque[float]:
        q = self.failures[key]
        while q and now - q[0] > self.window_s:
            q.popleft()
        return q

    def blocked(self, key: str, now: float | None = None) -> bool:
        return len(self._recent(key, now or time.time())) >= self.limit

    def fail(self, key: str, now: float | None = None) -> None:
        now = now or time.time()
        self._recent(key, now).append(now)

    def reset(self, key: str) -> None:
        self.failures.pop(key, None)
