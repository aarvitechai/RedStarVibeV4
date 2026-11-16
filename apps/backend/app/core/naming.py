"""Public handles (usernames and business slugs) share one namespace rule and one reserved list (Blueprint 8.2)."""

import re

RESERVED_NAMES = frozenset(
    {
        "admin",
        "api",
        "login",
        "logout",
        "signup",
        "media",
        "mcp",
        "ws",
        "business",
        "p",
        "settings",
        "help",
        "www",
        "health",
        "account",
        "auth",
        "explore",
        "feed",
        "search",
        "notifications",
        "messages",
        "shop",
        "events",
        "i",
        "redstarvibe",
        "support",
        "about",
        "terms",
        "privacy",
        "static",
        "_next",
        "dashboard",
        "bookings",
        "nearby",
    }
)
HANDLE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_.-]{1,58}[a-z0-9])$")


def normalize_handle(value: str, *, max_len: int = 30) -> str:
    v = value.strip().lower()
    if len(v) < 3 or len(v) > max_len or not HANDLE_RE.fullmatch(v) or ".." in v or "--" in v:
        raise ValueError(f"Use 3-{max_len} letters, numbers, '_', '.' or '-', starting and ending with a letter or number.")
    if v in RESERVED_NAMES:
        raise ValueError("This name is reserved.")
    return v
