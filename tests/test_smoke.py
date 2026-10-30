"""Smoke tests: every page and API flow works end to end against a fake TheMealDB."""

from __future__ import annotations

import re
import sqlite3

import pytest

from conftest import register


def reset_link(app) -> str:
    body = app.state.outbox[-1].get_content()
    return re.search(r"token=(\S+)", body).group(1)


@pytest.mark.parametrize("path", ["/", "/login.html", "/favorites.html", "/reset-password.html", "/script.js"])
def test_pages_are_served(client, path):
    assert client.get(path).status_code == 200


def test_builtin_moods_include_sweet(client):
    moods = client.get("/api/moods").json()
    assert [m["slug"] for m in moods] == ["happy", "comfort", "energized", "cozy", "adventurous", "sweet"]
    assert all(m["builtin"] for m in moods)


@pytest.mark.parametrize("mood", ["happy", "comfort", "energized", "cozy", "adventurous", "sweet"])
def test_every_builtin_mood_returns_a_recipe(client, mood):
    r = client.get("/api/recipe", params={"mood": mood})
    assert r.status_code == 200
    assert r.json()["name"]


def test_recipe_excludes_and_unknown_mood(client):
    assert client.get("/api/recipe", params={"mood": "sweet", "exclude": "9999"}).json()["id"] == "1002"
    r = client.get("/api/recipe", params={"mood": "grumpy"})
    assert r.status_code == 400 and "Unknown mood" in r.json()["detail"]


# --- Accounts --------------------------------------------------------------------

def test_register_login_logout_me(client, app, tmp_path):
    r = register(client, "Ada@Example.com")
    assert r.status_code == 201 and r.json()["email"] == "ada@example.com"
    assert client.get("/api/auth/me").json()["email"] == "ada@example.com"

    # Only a bcrypt hash is stored.
    db = sqlite3.connect(tmp_path / "test.db")
    (stored,) = db.execute("select password_hash from users").fetchone()
    assert stored.startswith("$2b$") and "correct horse" not in stored
    (session_hash,) = db.execute("select token_hash from sessions").fetchone()
    assert session_hash != client.cookies.get("mr_session")

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_register_validation(client):
    assert register(client, password="short").json()["detail"] == "Password must be at least 8 characters."
    assert register(client, email="not-an-email").json()["detail"] == "Enter a valid email address."
    register(client)
    r = register(client, "ADA@example.com")
    assert r.status_code == 409


def test_login_errors_do_not_reveal_accounts(client):
    register(client)
    client.post("/api/auth/logout")
    wrong_pw = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "nope nope"})
    no_user = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "nope nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json()


def test_login_is_throttled_after_repeated_failures(client):
    register(client)
    client.post("/api/auth/logout")
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong pass"})
    r = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse"})
    assert r.status_code == 429


def test_remember_me_sets_a_persistent_cookie(client):
    r = register(client, remember=True)
    assert "Max-Age=2592000" in r.headers["set-cookie"]
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse"})
    assert "Max-Age" not in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"] and "SameSite=lax" in r.headers["set-cookie"]


def test_forgot_and_reset_password(client, other_client, app):
    register(client)
    # Unknown emails get the same answer and no email.
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert unknown.status_code == 200 and not app.state.outbox

    known = client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
    assert known.json() == unknown.json()
    assert len(app.state.outbox) == 1 and app.state.outbox[0]["To"] == "ada@example.com"
    token = reset_link(app)

    r = other_client.post("/api/auth/reset-password", json={"token": token, "password": "brand new pass"})
    assert r.status_code == 200
    # Old sessions are signed out, the old password stops working, the link can't be reused.
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "correct horse"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "brand new pass"}).status_code == 200
    again = other_client.post("/api/auth/reset-password", json={"token": token, "password": "another pass"})
    assert again.status_code == 400


def test_only_the_newest_reset_link_works(client, app):
    register(client)
    client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
    first = reset_link(app)
    client.post("/api/auth/forgot-password", json={"email": "ada@example.com"})
    assert client.post("/api/auth/reset-password", json={"token": first, "password": "brand new pass"}).status_code == 400
    assert client.post("/api/auth/reset-password", json={"token": reset_link(app), "password": "brand new pass"}).status_code == 200


# --- Favorites -------------------------------------------------------------------

def test_favorites_need_login(client):
    assert client.get("/api/favorites").status_code == 401
    assert client.post("/api/favorites", json={"meal_id": "1002", "mood": "sweet"}).status_code == 401


def test_save_list_and_remove_favorites(client):
    register(client)
    r = client.post("/api/favorites", json={"meal_id": "1002", "mood": "sweet"})
    assert r.status_code == 201
    fav = r.json()
    assert fav["name"] == "Chocolate Cake" and fav["image"] == "https://img.test/1002.jpg"
    assert [m["slug"] for m in fav["moods"]] == ["sweet"]

    # Same dish under another mood: one favorite, two mood tags.
    r = client.post("/api/favorites", json={"meal_id": "1002", "mood": "happy"})
    assert r.status_code == 200
    assert [m["slug"] for m in r.json()["moods"]] == ["happy", "sweet"]
    assert len(client.get("/api/favorites").json()) == 1

    assert client.post("/api/favorites", json={"meal_id": "424242", "mood": "happy"}).status_code == 404
    assert client.delete(f"/api/favorites/{fav['id']}").status_code == 204
    assert client.get("/api/favorites").json() == []


def test_favorites_are_private(client, other_client):
    register(client, "ada@example.com")
    fav = client.post("/api/favorites", json={"meal_id": "1001", "mood": "energized"}).json()
    register(other_client, "bob@example.com")
    assert other_client.get("/api/favorites").json() == []
    assert other_client.delete(f"/api/favorites/{fav['id']}").status_code == 404
    assert len(client.get("/api/favorites").json()) == 1


# --- Custom moods ------------------------------------------------------------------

def test_custom_mood_flow(client, other_client):
    assert client.post("/api/moods", json={"label": "Rainy Day", "areas": ["Irish"]}).status_code == 401
    register(client)
    filters = client.get("/api/meal-filters").json()
    assert "Seafood" in filters["categories"] and "Irish" in filters["areas"]

    r = client.post("/api/moods", json={"label": "Rainy  Day", "emoji": "🌧️", "categories": ["Seafood"], "areas": ["Irish"]})
    assert r.status_code == 201
    mood = r.json()
    assert (mood["slug"], mood["label"], mood["builtin"]) == ("rainy-day", "Rainy Day", False)
    assert mood["slug"] in [m["slug"] for m in client.get("/api/moods").json()]

    # The new mood drives recipe selection: only Seafood or Irish dishes.
    picks = {client.get("/api/recipe", params={"mood": "rainy-day"}).json()["name"] for _ in range(12)}
    assert picks <= {"Fish Pie", "Irish Stew"} and picks

    # Others can't see or use it.
    register(other_client, "bob@example.com")
    assert "rainy-day" not in [m["slug"] for m in other_client.get("/api/moods").json()]
    assert other_client.get("/api/recipe", params={"mood": "rainy-day"}).status_code == 400

    # Favorites can be tagged with it; deleting the mood keeps the favorite.
    fav = client.post("/api/favorites", json={"meal_id": "1004", "mood": "rainy-day"}).json()
    client.post("/api/favorites", json={"meal_id": "1004", "mood": "energized"})
    assert other_client.delete(f"/api/moods/{mood['id']}").status_code == 404
    assert client.delete(f"/api/moods/{mood['id']}").status_code == 204
    favs = client.get("/api/favorites").json()
    assert [f["id"] for f in favs] == [fav["id"]] and [m["slug"] for m in favs[0]["moods"]] == ["energized"]


def test_custom_mood_validation(client):
    register(client)
    no_filters = client.post("/api/moods", json={"label": "Empty"})
    assert no_filters.status_code == 422 and no_filters.json()["detail"] == "Pick at least one category or cuisine."
    unknown = client.post("/api/moods", json={"label": "Space", "categories": ["Moon Rocks"]})
    assert unknown.status_code == 422 and "Moon Rocks" in unknown.json()["detail"]
    clash = client.post("/api/moods", json={"label": "happy", "categories": ["Dessert"]})
    assert clash.status_code == 409
    assert client.post("/api/moods", json={"label": "x" * 25, "categories": ["Dessert"]}).status_code == 422


def test_mood_names_without_latin_letters_get_a_slug(client):
    register(client)
    r = client.post("/api/moods", json={"label": "下雨天", "categories": ["Seafood"]})
    assert r.status_code == 201 and r.json()["slug"].startswith("mood-")
    assert client.get("/api/recipe", params={"mood": r.json()["slug"]}).status_code == 200


def test_filter_lookups_are_cached(client, mealdb):
    client.get("/api/recipe", params={"mood": "comfort"})
    client.get("/api/recipe", params={"mood": "comfort"})
    filters = [p for p, _ in mealdb.requests if p == "/filter.php"]
    assert len(filters) == 5  # five categories, fetched once
