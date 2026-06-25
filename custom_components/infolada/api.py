"""Client for the Infolada personal account API."""

from __future__ import annotations

import logging
import re
from typing import Any

import aiohttp
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    API_URL,
    AUTH_URL,
    BASE_URL,
    COOKIE_ACCESS_TOKEN,
    PORTAL_URL,
)
from .models import as_dict, as_user_list, normalize_account_data

_LOGGER = logging.getLogger(__name__)

_CSRF_RE = re.compile(r'name="_csrfy"\s+value="([^"]+)"')
_PORTAL_WHO_RE = re.compile(r'name="PortalForm\[who\]"\s+value="([^"]+)"')
_PORTAL_SUM_RE = re.compile(r'name="PortalForm\[sum\]"\s+value="([^"]+)"')

SESSION_COOKIES = frozenset({"_ilkr", "_ilkrs", COOKIE_ACCESS_TOKEN})


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
            cookie_jar=aiohttp.CookieJar(unsafe=True, quote_cookie=False),
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

        await self._authenticate()
        token = self._get_access_token()
        if not token:
            raise InfoladaAuthError("No access token received after authentication")

        self._authenticated = True

    async def _authenticate(self) -> None:
        """Perform a full login and token refresh sequence."""
        auth_error: InfoladaAuthError | None = None

        try:
            await self._login_json()
        except InfoladaAuthError as err:
            auth_error = err
            _LOGGER.debug("JSON auth failed, trying portal form: %s", err)

        if not self._has_session_cookies() and not self._get_access_token():
            try:
                await self._login_portal()
                auth_error = None
            except InfoladaAuthError as err:
                auth_error = err

        if not self._has_session_cookies() and not self._get_access_token():
            raise auth_error or InfoladaAuthError("Invalid login or password")

        if not self._get_access_token():
            await self._refresh_access_token(force=False)
        if not self._get_access_token():
            await self._refresh_access_token(force=True)

    async def _login_json(self) -> None:
        """Submit credentials to the LK JSON auth endpoint."""
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

        response, data = await self._request("POST", AUTH_URL, json=payload, headers=headers)
        self._raise_for_auth_response(response, data)

    async def _login_portal(self) -> None:
        """Submit credentials using the start.infolada.ru portal form."""
        response, html = await self._request(
            "GET",
            PORTAL_URL,
            headers={"Accept": "text/html"},
            expect_json=False,
        )
        if response.status >= 400:
            raise InfoladaConnectionError(
                f"Failed to load portal page ({response.status})"
            )

        csrf_match = _CSRF_RE.search(html)
        who_match = _PORTAL_WHO_RE.search(html)
        sum_match = _PORTAL_SUM_RE.search(html)
        if not csrf_match or not who_match or not sum_match:
            raise InfoladaApiError("Unable to parse portal login form")

        form_data = {
            "_csrfy": csrf_match.group(1),
            "PortalForm[login]": self._login,
            "PortalForm[password]": self._password,
            "PortalForm[who]": who_match.group(1),
            "PortalForm[sum]": sum_match.group(1),
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://start.infolada.ru",
            "Referer": PORTAL_URL,
        }

        response, data = await self._request(
            "POST",
            AUTH_URL,
            data=form_data,
            headers=headers,
            allow_redirects=False,
        )
        self._raise_for_auth_response(response, data)

        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location", "")
            if "error" in location.lower():
                raise InfoladaAuthError("Invalid login or password")

    async def _refresh_access_token(self, *, force: bool) -> None:
        """Exchange the session for a bearer token cookie."""
        url = f"{AUTH_URL}?forceRefresh=1" if force else AUTH_URL
        headers = {
            "Accept": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/lk/",
        }

        response, data = await self._request("POST", url, headers=headers)

        if self._get_access_token():
            return

        if _is_refresh_expire(data) and not force:
            return

        if response.status == 401 or _is_auth_failure(data):
            message = _extract_error_message(data) or "Session refresh failed"
            raise InfoladaAuthError(message)

        if response.status >= 400:
            message = _extract_error_message(data) or f"Session refresh failed ({response.status})"
            raise InfoladaApiError(message)

    async def _api_get(self, path: str, *, _retry: bool = True) -> Any:
        """Perform an authenticated GET request."""
        await self._ensure_authenticated()

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
        }

        response, data = await self._request("GET", f"{API_URL}{path}", headers=headers)

        if response.status in {401, 403} or _is_missing_api_auth(response.status, data):
            if not _retry:
                raise InfoladaAuthError("API authentication failed")
            self._authenticated = False
            await self._ensure_authenticated(force=True)
            return await self._api_get(path, _retry=False)

        if response.status >= 400:
            message = _extract_error_message(data) or f"API request failed ({response.status})"
            raise InfoladaApiError(message)

        return data

    async def _request(
        self,
        method: str,
        url: str,
        *,
        expect_json: bool = True,
        allow_redirects: bool = True,
        **kwargs: Any,
    ) -> tuple[aiohttp.ClientResponse, Any]:
        """Perform an HTTP request and parse the response."""
        try:
            async with self._session.request(
                method,
                url,
                allow_redirects=allow_redirects,
                **kwargs,
            ) as response:
                if expect_json:
                    data = await _read_json(response)
                else:
                    data = await response.text()
                return response, data
        except ClientError as err:
            raise InfoladaConnectionError(str(err)) from err

    def _raise_for_auth_response(
        self,
        response: aiohttp.ClientResponse,
        data: Any,
    ) -> None:
        """Validate an authentication response."""
        if response.status == 401 or _is_auth_failure(data):
            message = _extract_error_message(data) or "Invalid login or password"
            raise InfoladaAuthError(message)

        if isinstance(data, dict) and data.get("success") is False:
            message = _extract_error_message(data) or "Authentication failed"
            raise InfoladaAuthError(message)

        if response.status >= 400:
            message = _extract_error_message(data) or f"Authentication failed ({response.status})"
            raise InfoladaApiError(message)

        if isinstance(data, dict) and data.get("success") is True:
            return

        if self._has_session_cookies() or self._get_access_token():
            return

        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location", "")
            if location and "error" not in location.lower():
                return

        if response.status == 200:
            raise InfoladaAuthError("Invalid login or password")

    def _get_access_token(self) -> str | None:
        """Return the bearer token stored in cookies."""
        for cookie in self._session.cookie_jar:
            if cookie.key != COOKIE_ACCESS_TOKEN:
                continue
            if cookie.value and cookie.value != "deleted":
                return cookie.value
        return None

    def _has_session_cookies(self) -> bool:
        """Return whether auth session cookies are present."""
        for cookie in self._session.cookie_jar:
            if cookie.key in SESSION_COOKIES and cookie.value and cookie.value != "deleted":
                return True
        return False


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


def _is_refresh_expire(data: Any) -> bool:
    """Return whether the refresh token endpoint reports an expired session."""
    return isinstance(data, dict) and data.get("name") == "RefreshExpireException"


def _is_missing_api_auth(status: int, data: Any) -> bool:
    """Return whether an API 404 likely means the bearer token is invalid."""
    return status == 404 and isinstance(data, dict) and data.get("statusCode") == 404
