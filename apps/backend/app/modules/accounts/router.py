from fastapi import APIRouter, Request, Response

from app.api.deps import DB, Client, CurrentPrincipal, CurrentUser
from app.core.cookies import CSRF_COOKIE, clear_auth_cookies, refresh_cookie_name, set_auth_cookies, set_csrf_cookie
from app.core.security import new_csrf_token
from app.modules.accounts import repository as repo
from app.modules.accounts import service
from app.modules.accounts.schemas import CsrfOut, LoginRequest, MeOut, OkOut, SessionOut, SignupRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/csrf", response_model=CsrfOut)
async def csrf(request: Request, response: Response) -> CsrfOut:
    token = request.cookies.get(CSRF_COOKIE) or new_csrf_token()
    set_csrf_cookie(response, token)
    return CsrfOut(csrf_token=token)


@router.post("/signup", response_model=MeOut, status_code=201)
async def signup(body: SignupRequest, response: Response, db: DB, client: Client) -> MeOut:
    tokens = await service.signup(db, body, client)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return MeOut.model_validate(tokens.user)


@router.post("/login", response_model=MeOut)
async def login(body: LoginRequest, response: Response, db: DB, client: Client) -> MeOut:
    tokens = await service.login(db, body, client)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return MeOut.model_validate(tokens.user)


@router.post("/refresh", response_model=MeOut)
async def refresh(request: Request, response: Response, db: DB, client: Client) -> MeOut:
    try:
        tokens = await service.refresh(db, request.cookies.get(refresh_cookie_name()), client)
    except Exception:
        clear_auth_cookies(response)
        raise
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return MeOut.model_validate(tokens.user)


@router.post("/logout", response_model=OkOut)
async def logout(response: Response, principal: CurrentPrincipal, db: DB) -> OkOut:
    await service.logout(db, principal.user.id, principal.claims.session_family)
    clear_auth_cookies(response)
    return OkOut()


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser) -> MeOut:
    return MeOut.model_validate(user)


@router.get("/sessions", response_model=list[SessionOut])
async def sessions(principal: CurrentPrincipal, db: DB) -> list[SessionOut]:
    rows = await repo.list_active_families(db, principal.user.id)
    return [
        SessionOut(
            family_id=r.family_id,
            created_at=r.created_at,
            user_agent=r.user_agent,
            ip=str(r.ip) if r.ip else None,
            current=r.family_id == principal.claims.session_family,
        )
        for r in rows
    ]


@router.post("/sessions/logout-others", response_model=OkOut)
async def logout_others(principal: CurrentPrincipal, db: DB) -> OkOut:
    await service.logout_other_devices(db, principal.user.id, principal.claims.session_family)
    return OkOut()
