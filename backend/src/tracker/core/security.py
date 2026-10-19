"""Sessão do usuário único (cookie assinado), CSRF e token do agente."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, WebSocket, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from tracker.core.config import get_settings

SESSION_COOKIE = "tracker_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
CSRF_HEADER = "x-tracker-csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="session")


def sign_session(email: str) -> str:
    return _serializer().dumps({"email": email})


def read_session(token: str | None) -> str | None:
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    email = data.get("email") if isinstance(data, dict) else None
    if email != get_settings().auth_allowed_email:
        return None
    return email


def sign_state(data: dict[str, str]) -> str:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="oauth-state").dumps(data)


def read_state(token: str) -> dict[str, str] | None:
    try:
        return URLSafeTimedSerializer(get_settings().secret_key, salt="oauth-state").loads(token, max_age=600)
    except (BadSignature, SignatureExpired):
        return None


async def current_user(request: Request) -> str:
    email = read_session(request.cookies.get(SESSION_COOKIE))
    if email is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "não autenticado")
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "header CSRF ausente")
    return email


CurrentUser = Annotated[str, Depends(current_user)]


def ws_user(websocket: WebSocket) -> str | None:
    return read_session(websocket.cookies.get(SESSION_COOKIE))


def check_agent_token(token: str | None) -> bool:
    if not token:
        return False
    raw = token.removeprefix("Device ").strip()
    return hmac.compare_digest(raw, get_settings().agent_device_token)


async def agent_auth(authorization: Annotated[str | None, Header()] = None) -> None:
    if not check_agent_token(authorization):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token de dispositivo inválido")
