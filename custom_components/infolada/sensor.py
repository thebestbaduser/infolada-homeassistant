"""Sensor platform for the Infolada integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import CONF_LOGIN, DEFAULT_CURRENCY, DOMAIN, PAYMENT_URL
from .coordinator import InfoladaDataUpdateCoordinator
from .helpers import build_device_info


@dataclass(frozen=True, slots=True)
class InfoladaSensorDescription:
    """Description of a text sensor."""

    key: str
    translation_key: str
    value_key: str
    icon: str
    entity_category: EntityCategory | None = None
    enabled_by_default: bool = True


SENSOR_DESCRIPTIONS: tuple[InfoladaSensorDescription, ...] = (
    InfoladaSensorDescription(
        "contract_number",
        "contract_number",
        "contract_number",
        "mdi:card-account-details-outline",
        EntityCategory.DIAGNOSTIC,
    ),
    InfoladaSensorDescription(
        "contract_owner",
        "contract_owner",
        "contract_owner",
        "mdi:account-circle-outline",
        EntityCategory.DIAGNOSTIC,
    ),
    InfoladaSensorDescription(
        "internet_login",
        "internet_login",
        "internet_login",
        "mdi:account-key-outline",
        EntityCategory.DIAGNOSTIC,
        False,
    ),
    InfoladaSensorDescription(
        "current_tariff",
        "current_tariff",
        "current_tariff",
        "mdi:speedometer",
    ),
    InfoladaSensorDescription(
        "internet_status",
        "internet_status",
        "internet_status",
        "mdi:web",
        EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Infolada sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SensorEntity] = [
        InfoladaTextSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]
    entities.extend(
        [
            InfoladaBalanceSensor(coordinator, entry),
            InfoladaNeedPaySensor(coordinator, entry),
            InfoladaBonusSensor(coordinator, entry),
            InfoladaTrafficSensor(coordinator, entry),
            InfoladaTimestampSensor(
                coordinator,
                entry,
                "tariff_date_on",
                "tariff_date_on",
                "mdi:calendar-start",
            ),
            InfoladaTimestampSensor(
                coordinator,
                entry,
                "tariff_date_off",
                "tariff_date_off",
                "mdi:calendar-end",
            ),
            InfoladaTariffDaysLeftSensor(coordinator, entry),
            InfoladaLastUpdateSensor(coordinator, entry),
        ]
    )

    if coordinator.data.get("ktv_available"):
        entities.extend(_build_service_sensors(coordinator, entry, "ktv"))
    if coordinator.data.get("telephone_available"):
        entities.extend(_build_service_sensors(coordinator, entry, "telephone"))

    async_add_entities(entities)


def _build_service_sensors(
    coordinator: InfoladaDataUpdateCoordinator,
    entry: ConfigEntry,
    service: str,
) -> list[SensorEntity]:
    """Build balance and plan sensors for optional services."""
    plan_icon = "mdi:television-classic" if service == "ktv" else "mdi:phone"
    descriptions = (
        InfoladaSensorDescription(
            f"{service}_account",
            f"{service}_account",
            f"{service}_account",
            "mdi:card-account-details-outline",
            EntityCategory.DIAGNOSTIC,
        ),
        InfoladaSensorDescription(
            f"{service}_plan",
            f"{service}_plan",
            f"{service}_plan",
            plan_icon,
        ),
    )
    sensors: list[SensorEntity] = [
        InfoladaServiceTextSensor(coordinator, entry, description, service)
        for description in descriptions
    ]
    sensors.extend(
        [
            InfoladaServiceBalanceSensor(coordinator, entry, service),
            InfoladaServiceDebtSensor(coordinator, entry, service),
            InfoladaServicePlanPriceSensor(coordinator, entry, service),
        ]
    )
    return sensors


class InfoladaBaseSensor(
    CoordinatorEntity[InfoladaDataUpdateCoordinator],
    RestoreEntity,
    SensorEntity,
):
    """Base class for Infolada sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize a base sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._restored_state: str | None = None
        self._restored_attrs: dict[str, Any] = {}
        login = entry.data[CONF_LOGIN]
        self._login = login
        self._login_slug = slugify(str(login))
        self._attr_device_info = build_device_info(login, self._login_slug)

    async def async_added_to_hass(self) -> None:
        """Restore the last known state before the first successful update."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        self._restored_state = last_state.state
        self._restored_attrs = dict(last_state.attributes)

    @property
    def available(self) -> bool:
        """Keep entities available while live or restored data exists."""
        return self._has_live_data or self._restored_state is not None

    @property
    def _has_live_data(self) -> bool:
        """Return whether the coordinator currently has live data."""
        return bool(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return common attributes."""
        attrs: dict[str, Any] = {}
        login = self.coordinator.data.get("login") or self._entry.data.get(CONF_LOGIN)
        if login:
            attrs["login"] = login
        return attrs


class InfoladaTextSensor(InfoladaBaseSensor):
    """Text sensor backed by one normalized field."""

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
        description: InfoladaSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry)
        self._description = description
        self._attr_translation_key = description.translation_key
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_by_default
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_{description.key}"
        self.entity_id = f"sensor.infolada_{self._login_slug}_{description.key}"

    @property
    def native_value(self) -> str | None:
        """Return the normalized value."""
        value = self.coordinator.data.get(self._description.value_key)
        if value is not None:
            return str(value)
        return self._restored_state


class InfoladaBalanceSensor(InfoladaBaseSensor):
    """Current balance sensor."""

    _attr_translation_key = "current_balance"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:wallet-outline"
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the balance sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_current_balance"
        self.entity_id = f"sensor.infolada_{self._login_slug}_current_balance"

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the balance currency."""
        return str(self.coordinator.data.get("balance_currency") or DEFAULT_CURRENCY)

    @property
    def native_value(self) -> float | None:
        """Return the current balance."""
        value = self.coordinator.data.get("current_balance")
        if isinstance(value, (int, float)):
            return float(value)
        if self._restored_state is None:
            return None
        try:
            return float(self._restored_state)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return balance metadata."""
        attrs = super().extra_state_attributes
        attrs["currency"] = self.native_unit_of_measurement
        attrs["payment_url"] = PAYMENT_URL
        if self.coordinator.data.get("can_pay") is not None:
            attrs["can_pay"] = self.coordinator.data["can_pay"]
        return attrs


class InfoladaNeedPaySensor(InfoladaBaseSensor):
    """Recommended top-up amount sensor."""

    _attr_translation_key = "need_pay"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash-plus"
    _attr_suggested_display_precision = 2
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the need pay sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_need_pay"
        self.entity_id = f"sensor.infolada_{self._login_slug}_need_pay"

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the currency."""
        return str(self.coordinator.data.get("balance_currency") or DEFAULT_CURRENCY)

    @property
    def native_value(self) -> float | None:
        """Return the recommended payment amount."""
        value = self.coordinator.data.get("need_pay")
        if isinstance(value, (int, float)):
            return float(value)
        if self._restored_state is None:
            return None
        try:
            return float(self._restored_state)
        except (TypeError, ValueError):
            return None


class InfoladaBonusSensor(InfoladaBaseSensor):
    """Bonus balance sensor."""

    _attr_translation_key = "bonus"
    _attr_icon = "mdi:gift-outline"
    _attr_suggested_display_precision = 2
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the bonus sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_bonus"
        self.entity_id = f"sensor.infolada_{self._login_slug}_bonus"

    @property
    def native_value(self) -> float | None:
        """Return the bonus balance."""
        value = self.coordinator.data.get("bonus")
        if isinstance(value, (int, float)):
            return float(value)
        if self._restored_state is None:
            return None
        try:
            return float(self._restored_state)
        except (TypeError, ValueError):
            return None


class InfoladaTrafficSensor(InfoladaBaseSensor):
    """Included traffic balance sensor."""

    _attr_translation_key = "traffic_mb"
    _attr_icon = "mdi:cloud-download-outline"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_suggested_display_precision = 0
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the traffic sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_traffic_mb"
        self.entity_id = f"sensor.infolada_{self._login_slug}_traffic_mb"

    @property
    def native_value(self) -> float | None:
        """Return the traffic balance."""
        value = self.coordinator.data.get("traffic_mb")
        if isinstance(value, (int, float)):
            return float(value)
        if self._restored_state is None:
            return None
        try:
            return float(self._restored_state)
        except (TypeError, ValueError):
            return None


class InfoladaTimestampSensor(InfoladaBaseSensor):
    """Timestamp sensor backed by one normalized ISO field."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
        value_key: str,
        translation_key: str,
        icon: str,
        *,
        entity_category: EntityCategory | None = None,
        enabled_by_default: bool = True,
    ) -> None:
        """Initialize the timestamp sensor."""
        super().__init__(coordinator, entry)
        self._value_key = value_key
        self._attr_translation_key = translation_key
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        self._attr_entity_registry_enabled_default = enabled_by_default
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_{value_key}"
        self.entity_id = f"sensor.infolada_{self._login_slug}_{value_key}"

    @property
    def native_value(self):
        """Return the parsed timestamp."""
        value = self.coordinator.data.get(self._value_key)
        if value is None:
            value = self._restored_state
        if value is None:
            return None
        parsed = dt_util.parse_datetime(str(value))
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            return dt_util.as_local(parsed)
        return parsed


class InfoladaTariffDaysLeftSensor(InfoladaBaseSensor):
    """Days remaining until the current tariff ends."""

    _attr_translation_key = "tariff_days_left"
    _attr_icon = "mdi:calendar-alert"
    _attr_native_unit_of_measurement = UnitOfTime.DAYS
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the days-left sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_tariff_days_left"
        self.entity_id = f"sensor.infolada_{self._login_slug}_tariff_days_left"

    @property
    def native_value(self) -> int | None:
        """Return the number of days left on the tariff."""
        value = self.coordinator.data.get("tariff_days_left")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if self._restored_state is None:
            return None
        try:
            return int(float(self._restored_state))
        except (TypeError, ValueError):
            return None


class InfoladaLastUpdateSensor(InfoladaBaseSensor):
    """Last successful update timestamp sensor."""

    _attr_translation_key = "last_update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the last update sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_last_update"
        self.entity_id = f"sensor.infolada_{self._login_slug}_last_update"

    @property
    def native_value(self):
        """Return the last successful update time."""
        value = self.coordinator.data.get("updated_at")
        if value is None:
            value = self._restored_state
        if value is None:
            return None
        return dt_util.parse_datetime(str(value))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return update metadata."""
        attrs = super().extra_state_attributes
        users = self.coordinator.data.get("internet_users")
        if users:
            attrs["internet_users"] = users
        count = self.coordinator.data.get("internet_users_count")
        if count is not None:
            attrs["internet_users_count"] = count
        return attrs


class InfoladaServiceSensor(InfoladaBaseSensor):
    """Base class for optional KTV and telephony sensors."""

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
        service: str,
    ) -> None:
        """Initialize a service sensor."""
        super().__init__(coordinator, entry)
        self._service = service
        self._attr_device_info = build_device_info(self._login, self._login_slug, service)


class InfoladaServiceTextSensor(InfoladaServiceSensor):
    """Text sensor for an optional service."""

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
        description: InfoladaSensorDescription,
        service: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, service)
        self._description = description
        self._attr_translation_key = description.translation_key
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_by_default
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_{description.key}"
        self.entity_id = f"sensor.infolada_{self._login_slug}_{description.key}"

    @property
    def native_value(self) -> str | None:
        """Return the normalized value."""
        value = self.coordinator.data.get(self._description.value_key)
        if value is not None:
            return str(value)
        return self._restored_state


class InfoladaServiceBalanceSensor(InfoladaServiceSensor):
    """Balance sensor for KTV or telephony."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:wallet-outline"
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
        service: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, service)
        self._value_key = f"{service}_balance"
        self._attr_translation_key = f"{service}_balance"
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_{self._value_key}"
        self.entity_id = f"sensor.infolada_{self._login_slug}_{self._value_key}"

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the balance currency."""
        return str(self.coordinator.data.get("balance_currency") or DEFAULT_CURRENCY)

    @property
    def native_value(self) -> float | None:
        """Return the service balance."""
        value = self.coordinator.data.get(self._value_key)
        if isinstance(value, (int, float)):
            return float(value)
        if self._restored_state is None:
            return None
        try:
            return float(self._restored_state)
        except (TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return service balance metadata."""
        attrs = super().extra_state_attributes
        can_pay = self.coordinator.data.get(f"{self._service}_can_pay")
        if can_pay is not None:
            attrs["can_pay"] = can_pay
        return attrs


class InfoladaServiceDebtSensor(InfoladaServiceSensor):
    """Debt sensor for KTV or telephony."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash-minus"
    _attr_suggested_display_precision = 2
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
        service: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, service)
        self._value_key = f"{service}_debt"
        self._attr_translation_key = f"{service}_debt"
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_{self._value_key}"
        self.entity_id = f"sensor.infolada_{self._login_slug}_{self._value_key}"

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the currency."""
        return str(self.coordinator.data.get("balance_currency") or DEFAULT_CURRENCY)

    @property
    def native_value(self) -> float | None:
        """Return the service debt."""
        value = self.coordinator.data.get(self._value_key)
        if isinstance(value, (int, float)):
            return float(value)
        if self._restored_state is None:
            return None
        try:
            return float(self._restored_state)
        except (TypeError, ValueError):
            return None


class InfoladaServicePlanPriceSensor(InfoladaServiceSensor):
    """Plan price sensor for KTV or telephony."""

    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:cash"
    _attr_suggested_display_precision = 2
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: InfoladaDataUpdateCoordinator,
        entry: ConfigEntry,
        service: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, service)
        self._value_key = f"{service}_plan_price"
        self._attr_translation_key = f"{service}_plan_price"
        self._attr_unique_id = f"{entry.entry_id}_{self._login_slug}_{self._value_key}"
        self.entity_id = f"sensor.infolada_{self._login_slug}_{self._value_key}"

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the currency."""
        return str(self.coordinator.data.get("balance_currency") or DEFAULT_CURRENCY)

    @property
    def native_value(self) -> float | None:
        """Return the plan price."""
        value = self.coordinator.data.get(self._value_key)
        if isinstance(value, (int, float)):
            return float(value)
        if self._restored_state is None:
            return None
        try:
            return float(self._restored_state)
        except (TypeError, ValueError):
            return None
