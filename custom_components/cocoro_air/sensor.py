"""Platform for sensor integration."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN, CocoroAir

_LOGGER = logging.getLogger(__name__)


def setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    cocoro_air = hass.data[DOMAIN]["cocoro_air"]

    add_entities([
        CocoroAirTemperatureSensor(cocoro_air),
        CocoroAirHumiditySensor(cocoro_air),
    ])


class CocoroAirSensorBase(SensorEntity):
    """Base class for Cocoro Air sensor."""

    def __init__(self, cocoro_air: CocoroAir, name: str, device_class: SensorDeviceClass, state_class: str,
                 unit_of_measurement: str):
        """Initialize the sensor."""
        self._cocoro_air = cocoro_air
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement

    def update(self) -> None:
        """Fetch new state data for the sensor."""
        sensor_data = self._cocoro_air.get_sensor_data()
        self._attr_native_value = sensor_data[self._attr_name.lower()]


class CocoroAirTemperatureSensor(CocoroAirSensorBase):
    """Cocoro Air temperature sensor."""

    def __init__(self, cocoro_air: CocoroAir):
        """Initialize the sensor."""
        super().__init__(cocoro_air, "Temperature", SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT,
                         UnitOfTemperature.CELSIUS)


class CocoroAirHumiditySensor(CocoroAirSensorBase):
    """Cocoro Air humidity sensor."""

    def __init__(self, cocoro_air: CocoroAir):
        """Initialize the sensor."""
        super().__init__(cocoro_air, "Humidity", SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT, "%")
