"""Built-in and custom moods, plus mood-based recipe suggestions."""

from __future__ import annotations

import re
import secrets
import unicodedata

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Mood, User
from recipe_service import MealDB
from schemas import MoodIn, MoodOut
from security import DB, CurrentUser, OptionalUser

router = APIRouter(prefix="/api", tags=["moods"])

CUSTOM_POSITION = 1000  # custom moods list after the built-in ones


def mealdb_of(request: Request) -> MealDB:
    return request.app.state.mealdb


def slugify(label: str) -> str:
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_label.lower()).strip("-")[:32]
    return slug or f"mood-{secrets.token_hex(3)}"


def visible_to(user: User | None):
    """Built-in moods for everyone, plus the user's own."""
    return or_(Mood.user_id.is_(None), Mood.user_id == user.id) if user else Mood.user_id.is_(None)


async def visible_moods(db: AsyncSession, user: User | None) -> list[Mood]:
    rows = await db.scalars(select(Mood).where(visible_to(user)).order_by(Mood.position, Mood.id))
    return list(rows)


async def find_mood(db: AsyncSession, user: User | None, slug: str) -> Mood | None:
    rows = await db.scalars(select(Mood).where(visible_to(user), Mood.slug == slug.strip().lower()).order_by(Mood.position))
    return rows.first()


def upstream_error() -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "The recipe service (TheMealDB) isn't responding. Try again in a moment.")


@router.get("/moods", response_model=list[MoodOut])
async def list_moods(db: DB, user: OptionalUser) -> list[Mood]:
    return await visible_moods(db, user)


@router.post("/moods", response_model=MoodOut, status_code=status.HTTP_201_CREATED)
async def create_mood(body: MoodIn, request: Request, db: DB, user: CurrentUser) -> Mood:
    existing = await visible_moods(db, user)
    if any(m.label.casefold() == body.label.casefold() for m in existing):
        raise HTTPException(status.HTTP_409_CONFLICT, f'You already have a mood called "{body.label}".')

    mealdb = mealdb_of(request)
    try:
        known_categories, known_areas = set(await mealdb.categories()), set(await mealdb.areas())
    except (httpx.HTTPError, ValueError):
        raise upstream_error()
    unknown = [c for c in body.categories if c not in known_categories] + [a for a in body.areas if a not in known_areas]
    if unknown:
        raise HTTPException(422, f"Unknown category or cuisine: {', '.join(unknown)}.")

    taken = {m.slug for m in existing}
    base = slugify(body.label)
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1

    mood = Mood(
        user_id=user.id,
        slug=slug,
        label=body.label,
        emoji=body.emoji,
        categories=body.categories,
        areas=body.areas,
        position=CUSTOM_POSITION,
    )
    db.add(mood)
    await db.commit()
    await db.refresh(mood)
    return mood


@router.delete("/moods/{mood_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mood(mood_id: int, db: DB, user: CurrentUser) -> None:
    mood = await db.scalar(select(Mood).where(Mood.id == mood_id, Mood.user_id == user.id))
    if not mood:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mood not found.")
    # Favorites keep existing; only their tag for this mood goes (ON DELETE CASCADE on the link table).
    await db.delete(mood)
    await db.commit()


@router.get("/meal-filters")
async def meal_filters(request: Request) -> dict[str, list[str]]:
    mealdb = mealdb_of(request)
    try:
        return {"categories": await mealdb.categories(), "areas": await mealdb.areas()}
    except (httpx.HTTPError, ValueError):
        raise upstream_error()


@router.get("/recipe")
async def recipe_for_mood(
    request: Request,
    db: DB,
    user: OptionalUser,
    mood: str = Query(..., description="Mood slug from /api/moods"),
    exclude: str | None = Query(None, description="Comma-separated meal ids to avoid"),
) -> dict:
    found = await find_mood(db, user, mood)
    if not found:
        valid = ", ".join(m.slug for m in await visible_moods(db, user))
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown mood. Valid: {valid}")
    exclude_ids = {x.strip() for x in (exclude or "").split(",") if x.strip()}
    try:
        return await mealdb_of(request).recipe_for(found.categories, found.areas, exclude_ids)
    except (httpx.HTTPError, ValueError):
        raise upstream_error()


@router.get("/recipes/{meal_id}")
async def recipe_details(meal_id: str, request: Request) -> dict:
    if not meal_id.isdigit():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found.")
    try:
        meal = await mealdb_of(request).lookup(meal_id)
    except (httpx.HTTPError, ValueError):
        raise upstream_error()
    if not meal:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found.")
    return meal
