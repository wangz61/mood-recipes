"""Register, log in/out, current user, forgot/reset password."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from database import utcnow
from mailer import send_email
from models import PasswordReset, Session, User
from schemas import ForgotBody, LoginBody, RegisterBody, ResetBody, UserOut
from security import DB, CurrentUser, hash_password, hash_token, new_token, end_session, settings_of, start_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

BAD_LOGIN = "Email or password is incorrect."
FORGOT_REPLY = "If an account exists for that email, we've sent a link to reset the password."


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterBody, request: Request, response: Response, db: DB) -> User:
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists. Try logging in.")
    user = User(email=email, password_hash=await hash_password(body.password, settings_of(request).bcrypt_rounds))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:  # two sign-ups racing for the same email
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists. Try logging in.")
    await start_session(db, response, request, user, body.remember)
    return user


@router.post("/login", response_model=UserOut)
async def login(body: LoginBody, request: Request, response: Response, db: DB) -> User:
    email = body.email.lower()
    throttle = request.app.state.login_throttle
    if throttle.blocked(email):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Wait 15 minutes or reset your password.")
    user = await db.scalar(select(User).where(User.email == email))
    if not user or not await verify_password(body.password, user.password_hash):
        throttle.fail(email)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, BAD_LOGIN)
    throttle.reset(email)
    await start_session(db, response, request, user, body.remember)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DB) -> Response:
    await end_session(db, response, request)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user


@router.post("/forgot-password")
async def forgot_password(body: ForgotBody, request: Request, db: DB) -> dict:
    settings = settings_of(request)
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user:
        # Only the newest link works.
        await db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)))
        token, token_hash = new_token()
        db.add(PasswordReset(user_id=user.id, token_hash=token_hash, expires_at=utcnow() + timedelta(minutes=settings.reset_token_minutes)))
        await db.commit()
        base = settings.app_base_url or str(request.base_url).rstrip("/")
        link = f"{base}/reset-password.html?token={token}"
        await send_email(
            settings,
            request.app.state.outbox,
            user.email,
            "Reset your Mood Recipes password",
            f"Someone asked to reset the password for {user.email}.\n\n"
            f"Open this link within {settings.reset_token_minutes} minutes to choose a new one:\n{link}\n\n"
            "If it wasn't you, ignore this email; your password stays the same.",
        )
    return {"message": FORGOT_REPLY}


@router.post("/reset-password")
async def reset_password(body: ResetBody, request: Request, db: DB) -> dict:
    reset = await db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hash_token(body.token)))
    if not reset or reset.used_at is not None or reset.expires_at <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired. Ask for a new one.")
    password_hash = await hash_password(body.password, settings_of(request).bcrypt_rounds)
    await db.execute(update(User).where(User.id == reset.user_id).values(password_hash=password_hash))
    reset.used_at = utcnow()
    # A new password signs out every existing session.
    await db.execute(delete(Session).where(Session.user_id == reset.user_id))
    await db.commit()
    request.app.state.login_throttle.reset(
        (await db.scalar(select(User.email).where(User.id == reset.user_id))) or ""
    )
    return {"message": "Password updated. You can log in with your new password."}
