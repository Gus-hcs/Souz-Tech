from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from auth_handler import BlingAuth


class BlingClient:
    """HTTP client for Bling API v3 with pagination and rate limiting."""

    def __init__(self) -> None:
        self.auth = BlingAuth()
        self.base_url = "https://www.bling.com.br/Api/v3"

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        token = self.auth.get_valid_token()
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.base_url}{endpoint}"

        response = requests.get(url, headers=headers, params=params, timeout=30)
        if response.status_code == 429:
            response.raise_for_status()
        response.raise_for_status()
        return response.json()

    def get_all_data(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Fetch all pages from a Bling API v3 endpoint."""
        all_items: List[Dict[str, Any]] = []
        page = 1
        params = params.copy() if params else {}

        while True:
            params.update({"pagina": page})
            data = self._get(endpoint, params)

            items = data.get("data", []) if isinstance(data, dict) else []
            if not items:
                break

            all_items.extend(items)
            page += 1
            time.sleep(0.4)

        return all_items
