from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Optional

import pytz
import requests
from sqlalchemy.orm import Session

from models import Client, now_sp

SP_TZ = pytz.timezone("America/Sao_Paulo")


class BlingAuthError(Exception):
    pass


def _api_base() -> str:
    return os.getenv("BLING_API_BASE", "https://www.bling.com.br/Api/v3")


def _redirect_uri() -> str:
    return os.getenv("BLING_REDIRECT_URI", "http://localhost:8502")


def _token_expires_at_from_seconds(expires_in: int) -> datetime:
    return datetime.now(SP_TZ) + timedelta(seconds=expires_in)


def refresh_token(client_id: str, client_secret: str, refresh_token_value: str) -> tuple[str, str, datetime]:
    if not refresh_token_value:
        raise BlingAuthError("Refresh token não informado.")

    time.sleep(0.5)
    url = f"{_api_base()}/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
    }
    resp = requests.post(url, data=payload, auth=(client_id, client_secret), timeout=30)
    if resp.status_code >= 400:
        raise BlingAuthError(f"Falha ao renovar token: {resp.text}")

    data = resp.json()
    access_token = data.get("access_token")
    new_refresh = data.get("refresh_token") or refresh_token_value
    expires_in = int(data.get("expires_in", 3600))
    expires_at = _token_expires_at_from_seconds(expires_in)

    if not access_token:
        raise BlingAuthError("Resposta inválida do Bling (access_token ausente).")

    return access_token, new_refresh, expires_at


def get_authorization_url(client_id: str, state: str = "") -> str:
    base = f"{_api_base()}/oauth/authorize"
    redirect_uri = _redirect_uri()
    state_param = f"&state={state}" if state else ""
    return f"{base}?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}{state_param}"


def exchange_code_for_token(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str | None = None,
) -> tuple[str, str, datetime]:
    if not code:
        raise BlingAuthError("Código de autorização não informado.")

    url = f"{_api_base()}/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri or _redirect_uri(),
    }
    resp = requests.post(url, data=payload, auth=(client_id, client_secret), timeout=30)
    if resp.status_code >= 400:
        raise BlingAuthError(f"Falha ao trocar code por token: {resp.text}")

    data = resp.json()
    access_token = data.get("access_token")
    refresh = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600))
    expires_at = _token_expires_at_from_seconds(expires_in)
    if not access_token or not refresh:
        raise BlingAuthError("Resposta inválida do Bling (token ausente).")
    return access_token, refresh, expires_at


def is_token_expiring(expires_at: Optional[datetime], minutes: int = 10) -> bool:
    if not expires_at:
        return True
    exp = expires_at
    if exp.tzinfo is None:
        exp = SP_TZ.localize(exp)
    return exp <= datetime.now(SP_TZ) + timedelta(minutes=minutes)


def token_status(client: Client, minutes: int = 10) -> str:
    if not client.token_expires_at:
        return "expired"
    if is_token_expiring(client.token_expires_at, minutes=minutes):
        return "expiring"
    return "valid"


def ensure_valid_token(client: Client, session: Session, minutes: int = 10) -> None:
    if not is_token_expiring(client.token_expires_at, minutes=minutes):
        return
    access, refresh, expires_at = refresh_token(
        client.bling_client_id,
        client.bling_client_secret,
        client.refresh_token or "",
    )
    client.access_token = access
    client.refresh_token = refresh
    client.token_expires_at = expires_at
    session.add(client)
    session.commit()


def force_refresh_token(client: Client, session: Session) -> None:
    access, refresh, expires_at = refresh_token(
        client.bling_client_id,
        client.bling_client_secret,
        client.refresh_token or "",
    )
    client.access_token = access
    client.refresh_token = refresh
    client.token_expires_at = expires_at
    session.add(client)
    session.commit()


def friendly_token_icon(status: str) -> str:
    return {"valid": "🟢", "expiring": "🟡", "expired": "🔴"}.get(status, "🔴")
