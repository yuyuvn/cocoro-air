import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from . import DOMAIN, CocoroAir

_LOGGER = logging.getLogger(__name__)

class CocoroAirConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cocoro Air."""
    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.email = None
        self.password = None
        self.discovered_devices = []

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            self.email = user_input[CONF_EMAIL]
            self.password = user_input[CONF_PASSWORD]

            client = CocoroAir(self.email, self.password)
            try:
                await self.hass.async_add_executor_job(client.login)
                self.discovered_devices = await self.hass.async_add_executor_job(client.query_devices)

                if not self.discovered_devices:
                    errors["base"] = "no_devices_found"
                else:
                    return await self.async_step_device()

            except Exception:
                _LOGGER.exception("Unexpected exception during login or device query")
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_EMAIL): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors
        )

    async def async_step_device(self, user_input=None):
        """Handle the device selection step."""
        if user_input is not None:
            selected_devices = user_input["devices"]
            
            await self.async_set_unique_id(self.email)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=self.email,
                data={
                    CONF_EMAIL: self.email,
                    CONF_PASSWORD: self.password,
                    "devices": selected_devices,
                }
            )

        device_options = {d['device_id']: d['label'] for d in self.discovered_devices}

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({
                vol.Required("devices", default=list(device_options.keys())): cv.multi_select(device_options)
            })
        )
