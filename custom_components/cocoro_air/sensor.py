"""Sensor platform for Cocoro Air."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cocoro Air sensor platform."""
    cocoro_air_api = hass.data[DOMAIN][entry.entry_id]["cocoro_air_api"]

    async_add_entities(
        [
            CocoroAirTemperatureSensor(cocoro_air_api),
            CocoroAirHumiditySensor(cocoro_air_api),
        ]
    )


class CocoroAirTemperatureSensor(SensorEntity):
    """Representation of a Cocoro Air Temperature Sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Cocoro Air Temperature"
    _attr_unique_id = "cocoro_air_temperature"
    _attr_icon = "mdi:thermometer"

    def __init__(self, api):
        """Initialize the sensor."""
        self._api = api
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        data = await self._api.get_sensor_data()
        if data:
            self._attr_native_value = data["temperature"]


class CocoroAirHumiditySensor(SensorEntity):
    """Representation of a Cocoro Air Humidity Sensor."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_name = "Cocoro Air Humidity"
    _attr_unique_id = "cocoro_air_humidity"
    _attr_icon = "mdi:water-percent"

    def __init__(self, api):
        """Initialize the sensor."""
        self._api = api
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Fetch new state data for the sensor."""
        data = await self._api.get_sensor_data()
        if data:
            self._attr_native_value = data["humidity"]
