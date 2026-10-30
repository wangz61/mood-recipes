# Mood Recipes

Pick how you feel and get a recipe to match. Recipes come from [TheMealDB](https://www.themealdb.com/).

This version extends the course starter (`mood-recipes-example`) with:

- **Accounts**: register, log in, log out, "remember me", and forgot / reset password by email. Passwords are hashed with bcrypt.
- **Favorites**: save any suggested recipe to your account. A recipe saved under several moods keeps every mood as a tag.
- **Favorites page** (`favorites.html`): your saved recipes and their moods, with a mood filter, a recipe detail view, and remove.
- **Custom moods**: name a mood, add an emoji, and choose TheMealDB categories and cuisines. Your moods appear next to the built-in ones and drive the suggestions the same way. Only you can see them.

The product spec, with priorities and acceptance criteria, is in [PRD.md](PRD.md).

## Run

Requires Python 3.10 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

uvicorn app:app --reload
```

Open http://127.0.0.1:8000. The SQLite database `mood_recipes.db` is created on first start.

### Password-reset email

Without SMTP settings, the reset link is printed in the terminal running `uvicorn`, so the flow works locally with no mail account. To send real email, copy `.env.example` to `.env` and fill in `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `SMTP_FROM`. For Gmail, use an app password.

## Test

```bash
pip install -r requirements-dev.txt
pytest
```

The smoke tests cover every page and API flow:
- Accounts, sessions, and password reset.
- Favorites, including that one user can't see or delete another user's favorites.
- Custom moods and their suggestions.

They run against an in-memory stand-in for TheMealDB, so they don't need the internet.

## What changed from the starter

The starter didn't run as shipped:
- Its files were swapped: `requirements.txt` held the recipe code, `app.py` held the front-end script, and `recipe_service.py` held the FastAPI app.
- The **Sweet** button asked for a mood the server didn't know.
- The fallback path called `_random_meal_any` with one argument too many.

All three are fixed. Moods now live in the database, built-in ones included, and the page loads them from `/api/moods`, so the front end and back end can't drift apart again.

## How it works

| Piece | Choice |
| --- | --- |
| Server | FastAPI + Uvicorn |
| Database | SQLite through SQLAlchemy 2.0 (async, aiosqlite) |
| Passwords | bcrypt, run off the event loop |
| Sessions | Random token in an `HttpOnly`, `SameSite=Lax` cookie. Only its SHA-256 hash is stored, so logging out really ends the session. Reset tokens are stored the same way and expire after 30 minutes |
| Pages | Static HTML + Tailwind (CDN) + plain JavaScript |
| Recipes | TheMealDB, with category, cuisine and filter lookups cached for an hour |

### Database

```
users            email (unique), password_hash
sessions         user → token_hash, expires_at
password_resets  user → token_hash, expires_at, used_at
moods            owner (empty for built-in), slug, label, emoji, categories[], areas[]
favorites        user → meal_id (unique per user), name, image, category, area
favorite_moods   favorite ↔ mood
```

Deleting a custom mood removes its tag from your favorites but keeps the favorites themselves.

### API

| Method | Path | |
| --- | --- | --- |
| POST | `/api/auth/register` · `/login` · `/logout` | Accounts |
| GET | `/api/auth/me` | Current user (401 when logged out) |
| POST | `/api/auth/forgot-password` · `/reset-password` | Reset by email link |
| GET / POST | `/api/moods` | Built-in moods plus yours / create one |
| DELETE | `/api/moods/{id}` | Delete one of your moods |
| GET | `/api/meal-filters` | TheMealDB categories and cuisines |
| GET | `/api/recipe?mood=&exclude=` | A recipe for a mood |
| GET | `/api/recipes/{meal_id}` | Full recipe |
| GET / POST | `/api/favorites` | Your favorites / save one `{meal_id, mood}` |
| DELETE | `/api/favorites/{id}` | Remove a favorite |

Interactive API docs are at http://127.0.0.1:8000/docs while the server runs.

## Layout

```
app.py             app factory, startup (tables + built-in moods), error format
config.py          settings from environment / .env
database.py        async engine and session dependency
models.py          tables
schemas.py         request / response bodies and validation
security.py        bcrypt, session cookies, current-user dependencies, login throttle
mailer.py          SMTP or console email
recipe_service.py  TheMealDB client and mood-based selection
routers/           auth, moods (+ recipes), favorites
static/            index, login, reset-password and favorites pages
tests/             pytest smoke tests with a fake TheMealDB
```
