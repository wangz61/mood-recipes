"""TheMealDB-backed recipe selection by mood."""

from __future__ import annotations

import random
import time
from typing import Any

import httpx

BASE = "https://www.themealdb.com/api/json/v1/1"
CACHE_TTL_S = 60 * 60

# Built-in moods: slug -> (label, emoji, categories, areas). Seeded into the moods table on startup,
# so built-in and custom moods go through the same selection code.
BUILTIN_MOODS: dict[str, tuple[str, str, list[str], list[str]]] = {
    "happy": ("Happy", "😊", ["Dessert", "Pasta", "Starter", "Side", "Miscellaneous"], []),
    "comfort": ("Comfort", "🍲", ["Beef", "Chicken", "Lamb", "Pork", "Goat"], []),
    "energized": ("Energized", "⚡", ["Breakfast", "Seafood", "Vegetarian", "Vegan"], []),
    "cozy": ("Cozy", "🧣", [], ["British", "Irish", "American", "Italian", "Canadian", "French"]),
    "adventurous": (
        "Adventurous",
        "🌶️",
        [],
        ["Thai", "Indian", "Mexican", "Japanese", "Chinese", "Moroccan", "Spanish", "Vietnamese", "Greek", "Turkish", "Tunisian", "Malaysian"],
    ),
    # The starter's front end offered "Sweet" but the back end didn't know it.
    "sweet": ("Sweet", "🍰", ["Dessert"], []),
}


def meal_to_payload(meal: dict[str, Any]) -> dict[str, Any]:
    ingredients: list[dict[str, str]] = []
    for i in range(1, 21):
        ing = (meal.get(f"strIngredient{i}") or "").strip()
        meas = (meal.get(f"strMeasure{i}") or "").strip()
        if ing:
            ingredients.append({"ingredient": ing, "measure": meas})

    return {
        "id": str(meal.get("idMeal")),
        "name": meal.get("strMeal"),
        "category": meal.get("strCategory"),
        "area": meal.get("strArea"),
        "image": meal.get("strMealThumb"),
        "instructions": meal.get("strInstructions"),
        "youtube": meal.get("strYoutube"),
        "source": meal.get("strSource"),
        "ingredients": ingredients,
    }


class MealDB:
    """Small TheMealDB client. List and filter lookups are cached because every mood fans out to many of them."""

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client or httpx.AsyncClient(base_url=BASE, timeout=20.0)
        self._cache: dict[tuple, tuple[float, Any]] = {}

    async def aclose(self) -> None:
        await self.client.aclose()

    async def _get(self, path: str, params: dict[str, str], cache: bool) -> dict[str, Any]:
        key = (path, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        if cache and hit and time.monotonic() - hit[0] < CACHE_TTL_S:
            return hit[1]
        data = await self._fetch(path, params)
        if cache:
            self._cache[key] = (time.monotonic(), data)
        return data

    async def _fetch(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        r = await self.client.get(path, params=params)
        r.raise_for_status()
        return r.json() or {}

    async def filter_ids(self, param: str, value: str) -> list[str]:
        data = await self._get("/filter.php", {param: value}, cache=True)
        return [str(m["idMeal"]) for m in data.get("meals") or [] if m.get("idMeal")]

    async def lookup(self, meal_id: str) -> dict[str, Any] | None:
        data = await self._get("/lookup.php", {"i": meal_id}, cache=False)
        meals = data.get("meals") or []
        return meal_to_payload(meals[0]) if meals else None

    async def random_meal(self) -> dict[str, Any]:
        data = await self._get("/random.php", {}, cache=False)
        meals = data.get("meals") or []
        if not meals:
            raise ValueError("random.php returned no meal")
        return meal_to_payload(meals[0])

    async def categories(self) -> list[str]:
        data = await self._get("/list.php", {"c": "list"}, cache=True)
        return sorted(m["strCategory"] for m in data.get("meals") or [] if m.get("strCategory"))

    async def areas(self) -> list[str]:
        data = await self._get("/list.php", {"a": "list"}, cache=True)
        return sorted(m["strArea"] for m in data.get("meals") or [] if m.get("strArea"))

    async def pool(self, categories: list[str], areas: list[str]) -> list[str]:
        """All meal ids matching any of the categories or areas, first-seen order, no duplicates."""
        seen: set[str] = set()
        ordered: list[str] = []
        for param, values in (("c", categories), ("a", areas)):
            for value in values:
                for mid in await self.filter_ids(param, value):
                    if mid not in seen:
                        seen.add(mid)
                        ordered.append(mid)
        return ordered

    async def recipe_for(self, categories: list[str], areas: list[str], exclude_ids: set[str]) -> dict[str, Any]:
        pool = await self.pool(categories, areas)
        candidates = [mid for mid in pool if mid not in exclude_ids] or pool
        if candidates:
            meal = await self.lookup(random.choice(candidates))
            if meal:
                return meal
        # Nothing matched (empty filters or the API had nothing): any meal is better than an error.
        return await self.random_meal()
