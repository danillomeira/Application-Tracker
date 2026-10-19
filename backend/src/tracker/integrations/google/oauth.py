"""OAuth 2.0 do Google (login + autorização incremental de Gmail/Calendar). docs/07 §1."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tracker.core.config import get_settings
from tracker.core.crypto import decrypt_json, encrypt_json
from tracker.modules.platform.models import OAuthCredential

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

LOGIN_SCOPES = ["openid", "email", "profile"]
INTEGRATION_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",  # só para marcadores Vagas/* (ADR-015)
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.freebusy",
]


class OAuthError(Exception):
    pass


def redirect_uri(purpose: str) -> str:
    base = get_settings().api_base_url
    if purpose == "login":
        return f"{base}/api/v1/auth/google/callback"
    return f"{base}/api/v1/integrations/google/callback"


def build_auth_url(purpose: str, state: str) -> str:
    s = get_settings()
    if not s.google_client_id:
        raise OAuthError("GOOGLE_CLIENT_ID não configurado")
    params: dict[str, str] = {
        "client_id": s.google_client_id,
        "redirect_uri": redirect_uri(purpose),
        "response_type": "code",
        "state": state,
        "include_granted_scopes": "true",
    }
    if purpose == "login":
        params["scope"] = " ".join(LOGIN_SCOPES)
        params["prompt"] = "select_account"
    else:
        params["scope"] = " ".join(LOGIN_SCOPES + INTEGRATION_SCOPES)
        params["access_type"] = "offline"
        params["prompt"] = "consent"
        if s.gmail_account:
            params["login_hint"] = s.gmail_account
    return f"{AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str, purpose: str) -> dict[str, Any]:
    s = get_settings()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "redirect_uri": redirect_uri(purpose),
                "grant_type": "authorization_code",
            },
        )
    if r.status_code != 200:
        raise OAuthError(f"falha na troca do código: {r.status_code}")
    return r.json()


async def userinfo(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if r.status_code != 200:
        raise OAuthError("falha ao obter dados do usuário")
    return r.json()


async def save_credential(session: AsyncSession, email: str, tokens: dict[str, Any]) -> None:
    row = await session.scalar(
        select(OAuthCredential).where(OAuthCredential.provider == "google", OAuthCredential.account_email == email)
    )
    existing: dict[str, Any] = decrypt_json(row.token_encrypted) if row else {}
    merged = {**existing, **tokens}
    if "refresh_token" not in tokens and "refresh_token" in existing:
        merged["refresh_token"] = existing["refresh_token"]
    expires = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)
    scopes = str(tokens.get("scope", "")).split()
    if row is None:
        row = OAuthCredential(provider="google", account_email=email, token_encrypted=encrypt_json(merged))
        session.add(row)
    row.token_encrypted = encrypt_json(merged)
    row.scopes = scopes or row.scopes
    row.expires_at = expires
    row.status = "active"
    await session.flush()


async def google_credential(session: AsyncSession, email: str | None = None) -> OAuthCredential | None:
    """Credencial Google em uso: a de GMAIL_ACCOUNT, se definida; senão a conta conectada (usuário único)."""
    email = email or get_settings().gmail_account
    q = select(OAuthCredential).where(OAuthCredential.provider == "google")
    if email:
        q = q.where(OAuthCredential.account_email == email)
    return await session.scalar(q.order_by(OAuthCredential.updated_at.desc()).limit(1))


async def connected_email(session: AsyncSession) -> str | None:
    cred = await google_credential(session)
    return cred.account_email if cred else None


async def get_access_token(session: AsyncSession, email: str | None = None) -> str:
    """Token válido para a conta do Gmail; renova com refresh_token se necessário."""
    s = get_settings()
    row = await google_credential(session, email)
    if row is None or row.status != "active":
        raise OAuthError("conta Google não conectada")
    tokens = decrypt_json(row.token_encrypted)
    if row.expires_at and row.expires_at > datetime.now(UTC):
        return tokens["access_token"]
    refresh = tokens.get("refresh_token")
    if not refresh:
        row.status = "expired"
        await session.flush()
        raise OAuthError("sem refresh_token; reconecte a conta Google")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            TOKEN_URL,
            data={
                "client_id": s.google_client_id,
                "client_secret": s.google_client_secret,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        )
    if r.status_code != 200:
        row.status = "expired"
        await session.flush()
        raise OAuthError("falha ao renovar o token; reconecte a conta Google")
    await save_credential(session, row.account_email, r.json())
    return r.json()["access_token"]


async def revoke(session: AsyncSession, email: str) -> None:
    row = await session.scalar(
        select(OAuthCredential).where(OAuthCredential.provider == "google", OAuthCredential.account_email == email)
    )
    if row is None:
        return
    tokens = decrypt_json(row.token_encrypted)
    token = tokens.get("refresh_token") or tokens.get("access_token")
    if token:
        async with httpx.AsyncClient(timeout=20) as client:
            await client.post(REVOKE_URL, params={"token": token})
    await session.delete(row)
    await session.flush()
