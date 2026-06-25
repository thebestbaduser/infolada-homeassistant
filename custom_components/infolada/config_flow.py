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

_LOGGER = logging.getLogger(__name__)
from .const import CONF_LOGIN, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS, DOMAIN
from .helpers import build_scan_interval_schema
from .options_flow import InfoladaOptionsFlow


def _build_entry_title(login: str) -> str:
    """Build the config entry title."""
    return f"ИнфоЛада: {login}"


class InfoladaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Infolada."""

    VERSION = 1

    def __init__(self) -> None:
        self._login: str | None = None
        self._password: str | None = None
        self._title: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._login = user_input[CONF_LOGIN].strip()
            self._password = user_input[CONF_PASSWORD]

            await self.async_set_unique_id(self._login.lower())
            self._abort_if_unique_id_configured()

            client = InfoladaApiClient(
                hass=self.hass,
                login=self._login,
                password=self._password,
            )
            try:
                await client.async_validate_credentials()
            except InfoladaAuthError as err:
                _LOGGER.warning("Infolada authentication failed for %s: %s", self._login, err)
                errors["base"] = "invalid_auth"
            except InfoladaConnectionError as err:
                _LOGGER.error("Infolada connection failed: %s", err)
                errors["base"] = "cannot_connect"
            except InfoladaApiError as err:
                _LOGGER.error("Infolada API error during setup: %s", err)
                errors["base"] = "api_error"
            except InfoladaError as err:
                _LOGGER.error("Infolada setup failed: %s", err)
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error during Infolada setup")
                errors["base"] = "unknown"
            else:
                self._title = _build_entry_title(self._login)
                return await self.async_step_settings()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LOGIN, default=self._login or ""): str,
                    vol.Required(CONF_PASSWORD, default=self._password or ""): str,
                }
            ),
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

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> InfoladaOptionsFlow:
        """Return the options flow for this config entry."""
        return InfoladaOptionsFlow(config_entry)
