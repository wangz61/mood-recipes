"""Request and response bodies."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from security import MAX_PASSWORD_BYTES

MIN_PASSWORD = 8


def _check_new_password(v: str) -> str:
    if len(v) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    if len(v.encode()) > MAX_PASSWORD_BYTES:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")
    return v


class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    remember: bool = False

    _pw = field_validator("password")(_check_new_password)


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    remember: bool = False


class ForgotBody(BaseModel):
    email: EmailStr


class ResetBody(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str

    _pw = field_validator("password")(_check_new_password)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str


class MoodIn(BaseModel):
    label: str = Field(min_length=1, max_length=24)
    emoji: str = Field(default="", max_length=16)
    categories: list[str] = Field(default_factory=list, max_length=20)
    areas: list[str] = Field(default_factory=list, max_length=40)

    @field_validator("label", "emoji")
    @classmethod
    def _strip(cls, v: str) -> str:
        return " ".join(v.split())

    @field_validator("categories", "areas")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(s.strip() for s in v if s.strip()))

    @model_validator(mode="after")
    def _needs_a_filter(self) -> "MoodIn":
        if not self.label:
            raise ValueError("Give the mood a name.")
        if not self.categories and not self.areas:
            raise ValueError("Pick at least one category or cuisine.")
        return self


class MoodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    label: str
    emoji: str
    categories: list[str]
    areas: list[str]
    builtin: bool


class MoodTag(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    label: str
    emoji: str


class FavoriteIn(BaseModel):
    meal_id: str = Field(pattern=r"^\d{1,10}$")
    mood: str = Field(min_length=1, max_length=40)


class FavoriteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meal_id: str
    name: str
    image: str
    category: str
    area: str
    created_at: datetime
    moods: list[MoodTag]
