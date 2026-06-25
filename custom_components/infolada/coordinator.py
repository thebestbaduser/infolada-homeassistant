"""Coordinator for the Infolada integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api import InfoladaApiClient, InfoladaAuthError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class InfoladaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate Infolada account updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: InfoladaApiClient,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.entry = entry
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(
                hours=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_HOURS)
            ),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest account data."""
        try:
            data = await self.client.async_fetch_data()
        except InfoladaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        data["updated_at"] = dt_util.now().isoformat()
        return data
