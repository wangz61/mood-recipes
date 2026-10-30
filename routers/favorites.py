"""Saved recipes, each tagged with the moods it was saved under."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from models import Favorite
from routers.moods import find_mood, mealdb_of, upstream_error
from schemas import FavoriteIn, FavoriteOut
from security import DB, CurrentUser

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("", response_model=list[FavoriteOut])
async def list_favorites(db: DB, user: CurrentUser) -> list[Favorite]:
    rows = await db.scalars(
        select(Favorite).where(Favorite.user_id == user.id).order_by(Favorite.created_at.desc(), Favorite.id.desc())
    )
    return list(rows)


@router.post("", response_model=FavoriteOut)
async def add_favorite(body: FavoriteIn, request: Request, response: Response, db: DB, user: CurrentUser) -> Favorite:
    mood = await find_mood(db, user, body.mood)
    if not mood:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown mood.")

    favorite = await db.scalar(select(Favorite).where(Favorite.user_id == user.id, Favorite.meal_id == body.meal_id))
    if favorite:
        # Already saved: just add this mood as another tag.
        if mood not in favorite.moods:
            favorite.moods.append(mood)
            await db.commit()
        response.status_code = status.HTTP_200_OK
    else:
        # Snapshot from TheMealDB rather than trusting names and images sent by the browser.
        try:
            meal = await mealdb_of(request).lookup(body.meal_id)
        except (httpx.HTTPError, ValueError):
            raise upstream_error()
        if not meal:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found.")
        favorite = Favorite(
            user_id=user.id,
            meal_id=body.meal_id,
            name=meal["name"] or "Recipe",
            image=meal["image"] or "",
            category=meal["category"] or "",
            area=meal["area"] or "",
            moods=[mood],
        )
        db.add(favorite)
        await db.commit()
        response.status_code = status.HTTP_201_CREATED

    await db.refresh(favorite, ["moods"])
    return favorite


@router.delete("/{favorite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_favorite(favorite_id: int, db: DB, user: CurrentUser) -> None:
    favorite = await db.scalar(select(Favorite).where(Favorite.id == favorite_id, Favorite.user_id == user.id))
    if not favorite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Favorite not found.")
    await db.delete(favorite)
    await db.commit()
