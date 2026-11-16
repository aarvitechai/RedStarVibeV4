"""Auth cookies (Blueprint 12.1): HttpOnly, Secure, SameSite=Lax, __Host- prefix when served over HTTPS.

Locally (http://localhost) browsers reject Secure/__Host- cookies, so plain names are used there.
"""

from starlette.responses import Response

from app.core.config import get_settings
from app.core.security import ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL

CSRF_COOKIE = "rsv_csrf"
CSRF_HEADER = "x-csrf-token"


def _secure() -> bool:
    return get_settings().is_deployed


def access_cookie_name() -> str:
    return "__Host-rsv_at" if _secure() else "rsv_at"


def refresh_cookie_name() -> str:
    return "__Host-rsv_rt" if _secure() else "rsv_rt"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    common = {"httponly": True, "secure": _secure(), "samesite": "lax", "path": "/"}
    response.set_cookie(access_cookie_name(), access_token, max_age=int(ACCESS_TOKEN_TTL.total_seconds()), **common)  # type: ignore[arg-type]
    response.set_cookie(refresh_cookie_name(), refresh_token, max_age=int(REFRESH_TOKEN_TTL.total_seconds()), **common)  # type: ignore[arg-type]


def clear_auth_cookies(response: Response) -> None:
    for name in (access_cookie_name(), refresh_cookie_name()):
        response.delete_cookie(name, path="/", secure=_secure(), httponly=True, samesite="lax")


def set_csrf_cookie(response: Response, token: str) -> None:
    # Readable by our JS (double-submit pattern); SameSite=Lax blocks cross-site sending on POST.
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        httponly=False,
        secure=_secure(),
        samesite="lax",
        path="/",
    )
