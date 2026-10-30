"""Settings from environment variables (a local .env file is loaded if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'mood_recipes.db'}")
    )
    # Used to build password-reset links. Empty: taken from the incoming request.
    app_base_url: str = field(default_factory=lambda: os.getenv("APP_BASE_URL", "").rstrip("/"))
    bcrypt_rounds: int = field(default_factory=lambda: _int("BCRYPT_ROUNDS", 12))

    session_cookie: str = "mr_session"
    session_days_remember: int = 30
    session_days_default: int = 1
    reset_token_minutes: int = 30

    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: _int("SMTP_PORT", 587))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_from: str = field(default_factory=lambda: os.getenv("SMTP_FROM", ""))
    smtp_ssl: bool = field(default_factory=lambda: os.getenv("SMTP_SSL", "").lower() in ("1", "true", "yes"))
    # "smtp" when SMTP_HOST is set, otherwise "console". Tests use "memory".
    mail_backend: str = field(default_factory=lambda: os.getenv("MAIL_BACKEND", ""))

    def __post_init__(self) -> None:
        if not self.mail_backend:
            self.mail_backend = "smtp" if self.smtp_host else "console"
