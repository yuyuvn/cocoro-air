"""Platform for sensor integration."""

import logging

from datetime import timedelta

from homeassistant.core import callback
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity

from . import DOMAIN, CocoroAir

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
        hass: HomeAssistant,
        _config: ConfigType,
        async_add_entities: AddEntitiesCallback,
        discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    # if discovery_info is None:
    #     return

    _LOGGER.debug("Setting up sensor platform.")

    cocoro_air = hass.data[DOMAIN]["cocoro_air"]
    coordinator = MyCoordinator(hass, cocoro_air)

    async_add_entities([
        CocoroAirTemperatureSensor(coordinator),
        CocoroAirHumiditySensor(coordinator),
    ])


class MyCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, my_api: CocoroAir):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="Cocoro Air update",
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=60),
        )
        self.my_api = my_api

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        return self.my_api.get_sensor_data()


class CocoroAirSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Cocoro Air sensor."""

    def __init__(self, coordinator: DataUpdateCoordinator, name: str,
                 device_class: SensorDeviceClass, state_class: str, unit_of_measurement: str):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        sensor_data = self.coordinator.data
        self._attr_native_value = sensor_data[self._attr_name.lower()]
        self.async_write_ha_state()

    def device_info(self) -> DeviceInfo | None:
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self.coordinator.my_api.device_id)},
            "name": "Cocoro Air",
            "manufacturer": "Sharp",
            "model": "Cocoro Air",
        }


class CocoroAirTemperatureSensor(CocoroAirSensorBase):
    """Cocoro Air temperature sensor."""

    def __init__(self, coordinator: DataUpdateCoordinator):
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            "Temperature",
            SensorDeviceClass.TEMPERATURE,
            SensorStateClass.MEASUREMENT,
            UnitOfTemperature.CELSIUS
        )


class CocoroAirHumiditySensor(CocoroAirSensorBase):
    """Cocoro Air humidity sensor."""

    def __init__(self, coordinator: DataUpdateCoordinator):
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            "Humidity",
            SensorDeviceClass.HUMIDITY,
            SensorStateClass.MEASUREMENT,
            "%"
        )
