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

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)


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

    _attr_name = "Cocoro Air Humidity Mode"
    _attr_unique_id = "cocoro_air_humidity_mode"
    
    def __init__(self, api):
        """Initialize the switch."""
        self._api = api
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs):
        """Turn the humidity mode on."""
        await self.hass.async_add_executor_job(self._api.set_humidity_mode, 'on')
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the humidity mode off."""
        await self.hass.async_add_executor_job(self._api.set_humidity_mode, 'off')
        self._attr_is_on = False
        self.async_write_ha_state()

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        """Fetch new state data for the sensor."""
        state = await self.hass.async_add_executor_job(self._api.get_humidity_mode)
        if state is not None:
            self._attr_is_on = state ? 'on' : 'off'
