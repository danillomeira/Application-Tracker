"""Login Google restrito a um e-mail (RF-PLA-01) + login de desenvolvimento."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from tracker.api.deps import SessionDep
from tracker.core import audit
from tracker.core.config import get_settings
from tracker.core.security import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    CurrentUser,
    read_session,
    read_state,
    sign_session,
    sign_state,
)
from tracker.integrations.google import oauth

router = APIRouter(prefix="/auth", tags=["auth"])


class Me(BaseModel):
    email: str
    dev_login_enabled: bool


def _set_session(resp: RedirectResponse, email: str) -> None:
    s = get_settings()
    resp.set_cookie(
        SESSION_COOKIE,
        sign_session(email),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=s.app_env == "prod",
        path="/",
    )


@router.get("/google/login")
async def google_login() -> RedirectResponse:
    state = sign_state({"purpose": "login", "nonce": secrets.token_urlsafe(16)})
    try:
        return RedirectResponse(oauth.build_auth_url("login", state))
    except oauth.OAuthError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.get("/google/callback")
async def google_callback(code: str, state: str, session: SessionDep) -> RedirectResponse:
    data = read_state(state)
    if not data or data.get("purpose") != "login":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "state inválido")
    tokens = await oauth.exchange_code(code, "login")
    info = await oauth.userinfo(tokens["access_token"])
    allowed = get_settings().auth_allowed_email
    if not info.get("email_verified") or info.get("email") != allowed:
        await audit.record(session, actor="system", action="auth.denied", after={"email": info.get("email")})
        await session.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "conta não autorizada")
    await audit.record(session, actor="user", action="auth.login")
    await session.commit()
    resp = RedirectResponse(get_settings().app_base_url + "/hoje")
    _set_session(resp, allowed)
    return resp


@router.post("/dev-login")
async def dev_login(request: Request, session: SessionDep) -> RedirectResponse:
    s = get_settings()
    if not s.auth_dev_login or s.app_env == "prod":
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    # Só da própria máquina: quem chega pela rede (ou com Host estranho) não entra sem senha.
    client = request.client.host if request.client else ""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
    if client not in ("127.0.0.1", "::1", "localhost") or host not in ("localhost", "127.0.0.1", "::1", "test"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "login de desenvolvimento só funciona em localhost")
    await audit.record(session, actor="user", action="auth.dev_login")
    await session.commit()
    resp = RedirectResponse(s.app_base_url + "/hoje", status_code=303)
    _set_session(resp, s.auth_allowed_email)
    return resp


@router.post("/logout")
async def logout(_user: CurrentUser) -> RedirectResponse:
    resp = RedirectResponse(get_settings().app_base_url + "/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@router.get("/me", response_model=Me)
async def me(request: Request) -> Me:
    email = read_session(request.cookies.get(SESSION_COOKIE))
    if email is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")
    s = get_settings()
    return Me(email=email, dev_login_enabled=s.auth_dev_login and s.app_env != "prod")


@router.get("/config")
async def auth_config() -> dict[str, bool]:
    s = get_settings()
    return {
        "google": bool(s.google_client_id),
        "dev_login": s.auth_dev_login and s.app_env != "prod",
    }
