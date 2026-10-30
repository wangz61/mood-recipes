"""Mood Recipes: static UI, accounts, favorites and moods on top of TheMealDB.

Run:  uvicorn app:app --reload
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import Settings
from database import Base, make_engine
from models import Mood
from recipe_service import BUILTIN_MOODS, MealDB
from routers import auth, favorites, moods
from security import LoginThrottle

STATIC_DIR = Path(__file__).resolve().parent / "static"


async def seed_builtin_moods(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    """Insert or refresh the built-in moods so their filters always match the code."""
    async with sessionmaker() as db:
        existing = {m.slug: m for m in await db.scalars(select(Mood).where(Mood.user_id.is_(None)))}
        for position, (slug, (label, emoji, categories, areas)) in enumerate(BUILTIN_MOODS.items()):
            mood = existing.get(slug) or Mood(user_id=None, slug=slug)
            mood.label, mood.emoji, mood.categories, mood.areas, mood.position = label, emoji, categories, areas, position
            db.add(mood)
        await db.commit()


def _first_error(exc: RequestValidationError) -> str:
    """One readable sentence for the UI instead of pydantic's error list."""
    for err in exc.errors():
        msg = str(err.get("msg", "Invalid input."))
        msg = msg.removeprefix("Value error, ")
        field = err.get("loc", [])[-1] if err.get("loc") else ""
        if field == "email":
            return "Enter a valid email address."
        if err.get("type") == "value_error" or field in ("", "body"):
            return msg
        return f"{str(field).replace('_', ' ').capitalize()}: {msg[0].lower()}{msg[1:]}"
    return "Invalid input."


def create_app(settings: Settings | None = None, mealdb: MealDB | None = None) -> FastAPI:
    settings = settings or Settings()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = make_engine(settings.database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        app.state.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        app.state.mealdb = mealdb or MealDB()
        await seed_builtin_moods(app.state.sessionmaker)
        yield
        if mealdb is None:
            await app.state.mealdb.aclose()
        await engine.dispose()

    app = FastAPI(title="Mood Recipes", lifespan=lifespan)
    app.state.settings = settings
    app.state.outbox = []  # emails, when MAIL_BACKEND=memory
    app.state.login_throttle = LoginThrottle()

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _first_error(exc)})

    app.include_router(auth.router)
    app.include_router(moods.router)
    app.include_router(favorites.router)
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
    return app


app = create_app()
