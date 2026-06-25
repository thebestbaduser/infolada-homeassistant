"""Client for the Infolada personal account API."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import API_URL, AUTH_URL, BASE_URL, COOKIE_ACCESS_TOKEN
from .models import as_dict, as_user_list, normalize_account_data

_LOGGER = logging.getLogger(__name__)


class InfoladaError(Exception):
    """Base Infolada error."""


class InfoladaConnectionError(InfoladaError):
    """Raised when the Infolada website cannot be reached."""


class InfoladaAuthError(InfoladaError):
    """Raised on invalid credentials."""


class InfoladaApiError(InfoladaError):
    """Raised when the API returns an unexpected response."""


class InfoladaApiClient:
    """Infolada REST API client."""

    def __init__(self, hass: HomeAssistant, login: str, password: str) -> None:
        """Initialize the client."""
        self._session = async_create_clientsession(
            hass,
            cookie_jar=aiohttp.CookieJar(),
        )
        self._login = login
        self._password = password
        self._authenticated = False

    async def async_fetch_data(self) -> dict[str, Any]:
        """Authenticate and return normalized account data."""
        await self._ensure_authenticated(force=True)

        contract = await self._api_get("/internet-contract")
        account = await self._api_get("/internet-account")
        users = await self._api_get("/user/list")

        return normalize_account_data(
            login=self._login,
            contract=as_dict(contract),
            account=as_dict(account),
            users=as_user_list(users),
        )

    async def async_validate_credentials(self) -> dict[str, Any]:
        """Validate credentials and return account data."""
        return await self.async_fetch_data()

    async def _ensure_authenticated(self, *, force: bool = False) -> None:
        """Authenticate when needed."""
        if not force and self._authenticated and self._get_access_token():
            return

        await self._login_request()
        await self._refresh_access_token(force=True)
        token = self._get_access_token()
        if not token:
            raise InfoladaAuthError("No access token received after authentication")

        self._authenticated = True

    async def _login_request(self) -> None:
        """Submit portal credentials."""
        payload = {
            "username": self._login,
            "password": self._password,
            "remember_me": True,
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/lk/",
        }

        try:
            async with self._session.post(
                AUTH_URL,
                json=payload,
                headers=headers,
            ) as response:
                data = await _read_json(response)
        except ClientError as err:
            raise InfoladaConnectionError(str(err)) from err

        if response.status == 401 or _is_auth_failure(data):
            message = _extract_error_message(data) or "Invalid login or password"
            raise InfoladaAuthError(message)

        if response.status >= 400:
            message = _extract_error_message(data) or f"Authentication failed ({response.status})"
            raise InfoladaApiError(message)

        if isinstance(data, dict) and data.get("success") is False:
            message = _extract_error_message(data) or "Authentication failed"
            raise InfoladaAuthError(message)

    async def _refresh_access_token(self, *, force: bool = False) -> None:
        """Exchange the session for a bearer token cookie."""
        url = f"{AUTH_URL}?forceRefresh=1" if force else AUTH_URL
        headers = {
            "Accept": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/lk/",
        }

        try:
            async with self._session.post(url, headers=headers) as response:
                data = await _read_json(response)
        except ClientError as err:
            raise InfoladaConnectionError(str(err)) from err

        if response.status == 401 or _is_auth_failure(data):
            message = _extract_error_message(data) or "Session refresh failed"
            raise InfoladaAuthError(message)

        if response.status >= 400 and not self._get_access_token():
            message = _extract_error_message(data) or f"Session refresh failed ({response.status})"
            raise InfoladaApiError(message)

    async def _api_get(self, path: str) -> Any:
        """Perform an authenticated GET request."""
        await self._ensure_authenticated()

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }

        try:
            async with self._session.get(f"{API_URL}{path}", headers=headers) as response:
                data = await _read_json(response)
        except ClientError as err:
            raise InfoladaConnectionError(str(err)) from err

        if response.status == 401:
            self._authenticated = False
            await self._ensure_authenticated(force=True)
            return await self._api_get(path)

        if response.status >= 400:
            message = _extract_error_message(data) or f"API request failed ({response.status})"
            raise InfoladaApiError(message)

        return data

    def _get_access_token(self) -> str | None:
        """Return the bearer token stored in cookies."""
        for cookie in self._session.cookie_jar:
            if cookie.key != COOKIE_ACCESS_TOKEN:
                continue
            if cookie.value and cookie.value != "deleted":
                return cookie.value
        return None


async def _read_json(response: aiohttp.ClientResponse) -> Any:
    """Read JSON when available, otherwise return text."""
    try:
        return await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        text = await response.text()
        return {"message": text} if text else {}


def _extract_error_message(data: Any) -> str | None:
    """Extract a human-readable error message from an API payload."""
    if not isinstance(data, dict):
        return None
    for key in ("message", "error", "detail"):
        value = data.get(key)
        if value:
            return str(value)
    return None


def _is_auth_failure(data: Any) -> bool:
    """Return whether the payload indicates an auth failure."""
    if not isinstance(data, dict):
        return False
    if data.get("name") == "Unauthorized":
        return True
    status = data.get("status")
    return status in {401, "401"}
