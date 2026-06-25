"""Shared helpers for the Infolada integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_HOURS,
    DOMAIN,
    MAX_SCAN_INTERVAL_HOURS,
    MIN_SCAN_INTERVAL_HOURS,
)


def build_device_info(login: str, login_slug: str, service: str = "internet") -> DeviceInfo:
    """Build device metadata for a service type."""
    service_names = {
        "internet": ("Personal Account", "login"),
        "ktv": ("Cable TV", "ktv"),
        "telephone": ("Telephony", "telephone"),
    }
    model, suffix = service_names.get(service, service_names["internet"])
    return DeviceInfo(
        identifiers={(DOMAIN, f"{suffix}_{login_slug}")},
        manufacturer="Infolada",
        model=model,
        name=f"Infolada: {login}" if service == "internet" else f"Infolada {model}: {login}",
    )


def build_scan_interval_schema(default_value: int = DEFAULT_SCAN_INTERVAL_HOURS) -> vol.Schema:
    """Build a Voluptuous schema for scan interval configuration."""
    return vol.Schema(
        {
            vol.Required(CONF_SCAN_INTERVAL, default=default_value): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL_HOURS,
                    max=MAX_SCAN_INTERVAL_HOURS,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="h",
                )
            )
        }
    )
