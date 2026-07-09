"""Config flow for the Infolada integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD

from .api import (
    InfoladaApiClient,
    InfoladaApiError,
    InfoladaAuthError,
    InfoladaConnectionError,
    InfoladaError,
)
from .const import CONF_LOGIN, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS, DOMAIN
from .helpers import build_scan_interval_schema
from .options_flow import InfoladaOptionsFlow

_LOGGER = logging.getLogger(__name__)


def _build_entry_title(login: str) -> str:
    """Build the config entry title."""
    return f"ИнфоЛада: {login}"


def _user_schema(login: str | None = None) -> vol.Schema:
    """Build the login/password schema."""
    return vol.Schema(
        {
            vol.Required(CONF_LOGIN, default=login or ""): str,
            vol.Required(CONF_PASSWORD): str,
        }
    )


class InfoladaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Infolada."""

    VERSION = 1

    def __init__(self) -> None:
        self._login: str | None = None
        self._password: str | None = None
        self._title: str | None = None
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._login = user_input[CONF_LOGIN].strip()
            self._password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(self._login.lower())
            self._abort_if_unique_id_configured()

            errors = await self._async_validate_credentials(self._login, self._password)
            if not errors:
                self._title = _build_entry_title(self._login)
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(self._login),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication when credentials stop working."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._login = entry_data.get(CONF_LOGIN)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication with a new password."""
        errors: dict[str, str] = {}
        login = self._login or ""

        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            errors = await self._async_validate_credentials(login, password)
            if not errors and self._reauth_entry is not None:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={CONF_LOGIN: login, CONF_PASSWORD: password},
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            description_placeholders={"login": login},
            errors=errors,
        )

    async def async_step_settings(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the integration settings step."""
        if self._login is None or self._password is None:
            return self.async_abort(reason="unknown")

        if user_input is not None:
            return self.async_create_entry(
                title=self._title or _build_entry_title(self._login),
                data={CONF_LOGIN: self._login, CONF_PASSWORD: self._password},
                options={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])},
            )

        return self.async_show_form(
            step_id="settings",
            data_schema=build_scan_interval_schema(DEFAULT_SCAN_INTERVAL_HOURS),
        )

    async def _async_validate_credentials(self, login: str, password: str) -> dict[str, str]:
        """Validate credentials and return form errors."""
        client = InfoladaApiClient(hass=self.hass, login=login, password=password)
        try:
            await client.async_validate_credentials()
        except InfoladaAuthError as err:
            _LOGGER.warning("Infolada authentication failed for %s: %s", login, err)
            return {"base": "invalid_auth"}
        except InfoladaConnectionError as err:
            _LOGGER.error("Infolada connection failed: %s", err)
            return {"base": "cannot_connect"}
        except InfoladaApiError as err:
            _LOGGER.error("Infolada API error during setup: %s", err)
            return {"base": "api_error"}
        except InfoladaError as err:
            _LOGGER.error("Infolada setup failed: %s", err)
            return {"base": "unknown"}
        except Exception:
            _LOGGER.exception("Unexpected error during Infolada setup")
            return {"base": "unknown"}
        finally:
            await client.async_close()
        return {}

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> InfoladaOptionsFlow:
        """Return the options flow for this config entry."""
        return InfoladaOptionsFlow(config_entry)
