"""Options flow for the Infolada integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS
from .helpers import build_scan_interval_schema


class InfoladaOptionsFlow(OptionsFlow):
    """Handle options for Infolada."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        # Keep the entry for Home Assistant versions that do not inject it yet.
        self._config_entry = config_entry

    @property
    def entry(self) -> ConfigEntry:
        """Return the config entry being configured."""
        return getattr(self, "config_entry", None) or self._config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=build_scan_interval_schema(
                self.entry.options.get(
                    CONF_SCAN_INTERVAL,
                    DEFAULT_SCAN_INTERVAL_HOURS,
                )
            ),
        )
