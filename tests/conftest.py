from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from config import Settings  # noqa: E402
from recipe_service import MealDB  # noqa: E402

# A tiny stand-in for TheMealDB: meal id -> (name, category, area).
MEALS = {
    "1001": ("Pancakes", "Breakfast", "American"),
    "1002": ("Chocolate Cake", "Dessert", "British"),
    "1003": ("Pad Thai", "Pasta", "Thai"),
    "1004": ("Fish Pie", "Seafood", "British"),
    "1005": ("Irish Stew", "Lamb", "Irish"),
}


class FakeMealDB(MealDB):
    """Same selection code as the real client; only the HTTP calls are replaced."""

    def __init__(self) -> None:
        self._cache = {}
        self.requests: list[tuple[str, dict]] = []

    async def aclose(self) -> None:
        pass

    async def _fetch(self, path: str, params: dict[str, str]) -> dict:
        self.requests.append((path, params))
        meal = lambda i: {  # noqa: E731
            "idMeal": i,
            "strMeal": MEALS[i][0],
            "strCategory": MEALS[i][1],
            "strArea": MEALS[i][2],
            "strMealThumb": f"https://img.test/{i}.jpg",
            "strInstructions": "Cook it.",
            "strIngredient1": "Love",
            "strMeasure1": "1 cup",
        }
        if path == "/filter.php":
            (key, value), = params.items()
            col = 1 if key == "c" else 2
            return {"meals": [{"idMeal": i} for i, m in MEALS.items() if m[col] == value] or None}
        if path == "/lookup.php":
            return {"meals": [meal(params["i"])] if params["i"] in MEALS else None}
        if path == "/random.php":
            return {"meals": [meal("1001")]}
        if path == "/list.php":
            if "c" in params:
                return {"meals": [{"strCategory": c} for c in ["Beef", "Breakfast", "Dessert", "Lamb", "Pasta", "Seafood"]]}
            return {"meals": [{"strArea": a} for a in ["American", "British", "Irish", "Thai"]]}
        raise AssertionError(f"unexpected request {path}")


@pytest.fixture
def mealdb() -> FakeMealDB:
    return FakeMealDB()


@pytest.fixture
def app(tmp_path, mealdb):
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        bcrypt_rounds=4,
        mail_backend="memory",
        app_base_url="http://testserver",
    )
    return create_app(settings, mealdb=mealdb)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def other_client(app):
    """A second browser with its own cookies, sharing the same server."""
    with TestClient(app) as c:
        yield c


def register(c: TestClient, email: str = "ada@example.com", password: str = "correct horse", remember: bool = False):
    return c.post("/api/auth/register", json={"email": email, "password": password, "remember": remember})
