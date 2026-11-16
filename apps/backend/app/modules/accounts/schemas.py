import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.naming import RESERVED_NAMES

# Reserved names are shared with business slugs (app/core/naming.py).
RESERVED_USERNAMES = RESERVED_NAMES
_USERNAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_.]{1,28}[a-z0-9])$")
_COMMON_PASSWORDS = frozenset(
    {
        "password123",
        "1234567890",
        "qwertyuiop",
        "iloveyou12",
        "password1234",
        "admin12345",
        "welcome123",
        "redstarvibe",
        "abcdefghij",
        "0987654321",
        "qwerty1234",
        "1q2w3e4r5t",
    }
)


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=80)
    is_18_or_older: bool = Field(description="ADR 0015: platform is 18+ until a parental-consent flow exists")

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        v = v.strip().lower()
        if not _USERNAME_RE.fullmatch(v) or ".." in v:
            raise ValueError("Use 3-30 letters, numbers, '_' or '.', starting and ending with a letter or number.")
        if v in RESERVED_USERNAMES:
            raise ValueError("This username is reserved.")
        return v

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Display name is required.")
        return v

    @model_validator(mode="after")
    def _checks(self) -> "SignupRequest":
        if not self.is_18_or_older:
            raise ValueError("You must be 18 or older to use RedStarVibe.")
        low = self.password.lower()
        if low in _COMMON_PASSWORDS or self.username in low:
            raise ValueError("Choose a less common password that does not contain your username.")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


Role = Literal["user", "business", "staff", "admin", "superadmin"]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str
    role: Role
    created_at: datetime


class MeOut(UserOut):
    email: str


class SessionOut(BaseModel):
    family_id: uuid.UUID
    created_at: datetime
    user_agent: str | None
    ip: str | None
    current: bool


class CsrfOut(BaseModel):
    csrf_token: str


class OkOut(BaseModel):
    ok: bool = True
