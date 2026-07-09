"""The Infolada integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .api import InfoladaApiClient, InfoladaAuthError
from .const import CONF_LOGIN, DOMAIN
from .coordinator import InfoladaDataUpdateCoordinator

PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class InfoladaRuntimeData:
    """Runtime data for an Infolada config entry."""

    client: InfoladaApiClient
    coordinator: InfoladaDataUpdateCoordinator


type InfoladaConfigEntry = ConfigEntry[InfoladaRuntimeData]


async def async_setup(hass: HomeAssistant, _config: dict) -> bool:
    """Initialize the integration domain storage."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: InfoladaConfigEntry) -> bool:
    """Set up Infolada from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = InfoladaApiClient(
        hass=hass,
        login=entry.data[CONF_LOGIN],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator = InfoladaDataUpdateCoordinator(hass, client, entry)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        await client.async_close()
        raise
    except InfoladaAuthError as err:
        await client.async_close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except Exception as err:
        await client.async_close()
        raise ConfigEntryNotReady(str(err)) from err

    runtime = InfoladaRuntimeData(client=client, coordinator=coordinator)
    entry.runtime_data = runtime
    hass.data[DOMAIN][entry.entry_id] = runtime
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: InfoladaConfigEntry) -> bool:
    """Unload an Infolada config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    runtime = hass.data[DOMAIN].pop(entry.entry_id, None)
    if runtime is None and hasattr(entry, "runtime_data"):
        runtime = entry.runtime_data
    if runtime is not None:
        await runtime.client.async_close()
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
