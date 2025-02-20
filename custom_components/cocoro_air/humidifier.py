"""Humidifier platform for Cocoro Air."""
import logging
from datetime import timedelta

from homeassistant.components.humidifier import HumidifierEntity, HumidifierDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import Throttle
from homeassistant.config_entries import ConfigEntry

from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=5)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cocoro Air Humidifier platform."""
    cocoro_air_api = hass.data[DOMAIN][config_entry.entry_id]["cocoro_air_api"]
    
    async_add_entities([
        CocoroAirHumidifier(cocoro_air_api),
    ])


class CocoroAirHumidifier(HumidifierEntity):
    """Representation of a Cocoro Air Humidifier."""

    _attr_has_entity_name = True
    _attr_name = "Humidity Mode"
    _attr_icon = "mdi:air-humidifier"
    _attr_device_class = HumidifierDeviceClass.HUMIDIFIER
    
    def __init__(self, api):
        """Initialize the humidifier."""
        self._api = api
        self._attr_unique_id = f"{api.device_id}_humidity_mode"
        self._attr_device_info = api.device_info
        self._attr_is_on = False

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:air-humidifier-off" if not self._attr_is_on else "mdi:air-humidifier"

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            await self._api.update()
        except Exception as e:
            _LOGGER.warning("Failed to update sensor data: %s", e)
        try:
            data = self._api.get_sensor_data()
            self._attr_is_on = data['humidity_mode']
        except KeyError:
            self._attr_is_on = None
