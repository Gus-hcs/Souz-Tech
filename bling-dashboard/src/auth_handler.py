from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict

import requests
from dotenv import load_dotenv


@dataclass
class TokenData:
    access_token: str
    refresh_token: str
    expires_in: int
    expiry_timestamp: int


class BlingAuth:
    """Handle OAuth2 token lifecycle for Bling API v3."""

    def __init__(self, token_path: str = "tokens.json") -> None:
        load_dotenv()
        self.client_id = os.getenv("BLING_CLIENT_ID")
        self.client_secret = os.getenv("BLING_CLIENT_SECRET")
        self.redirect_uri = os.getenv("BLING_REDIRECT_URI")
        self.token_path = token_path

        if not self.client_id or not self.client_secret:
            raise RuntimeError(
                "Missing BLING_CLIENT_ID or BLING_CLIENT_SECRET in .env"
            )

    def _read_tokens(self) -> TokenData:
        if not os.path.exists(self.token_path):
            raise FileNotFoundError(
                "tokens.json not found. Provide initial OAuth2 token first."
            )

        with open(self.token_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        return TokenData(
            access_token=raw.get("access_token", ""),
            refresh_token=raw.get("refresh_token", ""),
            expires_in=int(raw.get("expires_in", 0)),
            expiry_timestamp=int(raw.get("expiry_timestamp", 0)),
        )

    def _write_tokens(self, data: TokenData) -> None:
        payload = {
            "access_token": data.access_token,
            "refresh_token": data.refresh_token,
            "expires_in": data.expires_in,
            "expiry_timestamp": data.expiry_timestamp,
        }
        with open(self.token_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _refresh_token(self, refresh_token: str) -> TokenData:
        url = "https://www.bling.com.br/Api/v3/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        response = requests.post(
            url,
            data=payload,
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        response.raise_for_status()
        body: Dict[str, Any] = response.json()

        expires_in = int(body.get("expires_in", 0))
        expiry_timestamp = int(time.time()) + expires_in - 60

        return TokenData(
            access_token=body.get("access_token", ""),
            refresh_token=body.get("refresh_token", refresh_token),
            expires_in=expires_in,
            expiry_timestamp=expiry_timestamp,
        )

    def get_valid_token(self) -> str:
        tokens = self._read_tokens()

        if not tokens.access_token or not tokens.refresh_token:
            raise RuntimeError(
                "tokens.json is missing access_token or refresh_token."
            )

        now = int(time.time())
        if tokens.expiry_timestamp <= now:
            refreshed = self._refresh_token(tokens.refresh_token)
            self._write_tokens(refreshed)
            return refreshed.access_token

        return tokens.access_token
