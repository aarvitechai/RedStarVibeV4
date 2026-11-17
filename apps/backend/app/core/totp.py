"""RFC 6238 TOTP (30 s, 6 digits, SHA-1 — what authenticator apps support)."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_S = 30
DIGITS = 6


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((now if now is not None else time.time()) // STEP_S)


def code_at(secret: str, now: float | None = None) -> str:
    return _code(secret, current_step(now))


def verify(secret: str, code: str, last_step: int | None, now: float | None = None) -> int | None:
    """Accept the current step ±1 (clock drift). Returns the matched step, or None. A step at or before
    `last_step` is rejected so a code can never be used twice."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for s in (step - 1, step, step + 1):
        if (last_step is None or s > last_step) and hmac.compare_digest(_code(secret, s), code):
            return s
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "RedStarVibe") -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP_S}"
    )
