"""Options flow for the Infolada integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry, OptionsFlow

from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS
from .helpers import build_scan_interval_schema


class InfoladaOptionsFlow(OptionsFlow):
    """Handle options for Infolada."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None):
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=build_scan_interval_schema(
                self._config_entry.options.get(
                    CONF_SCAN_INTERVAL,
                    DEFAULT_SCAN_INTERVAL_HOURS,
                )
            ),
        )
