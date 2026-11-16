"""Field-level encryption for sensitive PII such as phone numbers (Blueprint 12.4). The key never lives in the DB."""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().field_encryption_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str | None) -> bytes | None:
    return None if value is None else _fernet().encrypt(value.encode())


def decrypt(token: bytes | None) -> str | None:
    return None if token is None else _fernet().decrypt(bytes(token)).decode()
