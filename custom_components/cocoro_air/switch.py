"""Switch platform for Cocoro Air."""
import logging
from datetime import timedelta

from homeassistant.components.switch import SwitchEntity
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
    """Set up the Cocoro Air Switch platform."""
    cocoro_air_api = hass.data[DOMAIN][config_entry.entry_id]["cocoro_air_api"]
    
    async_add_entities([
        CocoroAirHumiditySwitch(cocoro_air_api),
    ])


class CocoroAirHumiditySwitch(SwitchEntity):
    """Representation of a Cocoro Air Humidity Switch."""

    _attr_has_entity_name = True
    _attr_name = "Humidity Mode"
    _attr_icon = "mdi:air-humidifier"
    
    def __init__(self, api):
        """Initialize the switch."""
        self._api = api
        self._attr_unique_id = f"{api.device_id}_humidity_mode"
        self._attr_device_info = api.device_info
        self._attr_is_on = False

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:air-humidifier-off" if not self._attr_is_on else "mdi:air-humidifier"

    async def async_turn_on(self, **kwargs):
        """Turn the humidity mode on."""
        await self._api.set_humidity_mode('on')
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the humidity mode off."""
        await self._api.set_humidity_mode('off')
        self._attr_is_on = False
        self.async_write_ha_state()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Fetch new state data for the sensor."""
        state = await self._api.get_humidity_mode()
        if state is not None:
            self._attr_is_on = state
