"""Config flow for Cocoro Air integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.httpx_client import create_async_httpx_client

from . import DOMAIN, CocoroAirLoginError, CocoroAirSession

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Log in with the given credentials and return the account's devices.

    Uses a throwaway client so the flow never touches the cookies of the
    session that the running entries share.
    """
    session = CocoroAirSession(create_async_httpx_client(hass, auto_cleanup=False))
    try:
        try:
            await session.async_login(data["email"], data["password"])
        except CocoroAirLoginError as err:
            raise InvalidAuth from err
        return await session.async_query_devices(data["email"], data["password"])
    finally:
        await session.async_close()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Cocoro Air."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._email: str | None = None
        self._password: str | None = None
        self._devices: list[dict[str, Any]] = []

    async def _async_login_and_discover(
        self,
        user_input: dict[str, Any],
        errors: dict[str, str],
        exclude_entry_id: str | None = None,
    ) -> bool:
        """Log in and populate self._devices. Returns True on success.

        Every entry shares one account session, so the email must match the
        entries that already exist (except the one being reconfigured).
        """
        if any(
            entry.data.get("email") != user_input["email"]
            for entry in self._async_current_entries()
            if entry.entry_id != exclude_entry_id
        ):
            errors["base"] = "single_account"
            return False

        try:
            self._devices = await validate_input(self.hass, user_input)
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            if not self._devices:
                errors["base"] = "no_devices_found"
            else:
                self._email = user_input["email"]
                self._password = user_input["password"]
                return True

        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step: collect credentials and discover devices."""
        errors: dict[str, str] = {}

        if user_input is not None and await self._async_login_and_discover(
            user_input, errors
        ):
            return await self.async_step_device()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device selection."""
        if user_input is not None:
            device_id = user_input["device_id"]
            model_name = next(
                d["model_name"] for d in self._devices if d["device_id"] == device_id
            )

            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            data = {
                "email": self._email,
                "password": self._password,
                "device_id": device_id,
                "model_name": model_name,
            }
            return self.async_create_entry(
                title=f"Cocoro Air {model_name} ({device_id})", data=data
            )

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required("device_id"): vol.In(self._device_options())}
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration: collect credentials and discover devices."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None and await self._async_login_and_discover(
            user_input, errors, exclude_entry_id=reconfigure_entry.entry_id
        ):
            return await self.async_step_reconfigure_device()

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, reconfigure_entry.data
            ),
            errors=errors,
        )

    async def async_step_reconfigure_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device selection during reconfiguration."""
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            device_id = user_input["device_id"]
            model_name = next(
                d["model_name"] for d in self._devices if d["device_id"] == device_id
            )

            data = {
                "email": self._email,
                "password": self._password,
                "device_id": device_id,
                "model_name": model_name,
            }
            return self.async_update_reload_and_abort(
                reconfigure_entry,
                unique_id=device_id,
                title=f"Cocoro Air {model_name} ({device_id})",
                data=data,
            )

        device_options = self._device_options()
        current_device_id = reconfigure_entry.data.get("device_id")

        device_id_key: vol.Marker
        if current_device_id in device_options:
            device_id_key = vol.Required("device_id", default=current_device_id)
        else:
            device_id_key = vol.Required("device_id")

        return self.async_show_form(
            step_id="reconfigure_device",
            data_schema=vol.Schema({device_id_key: vol.In(device_options)}),
        )

    def _device_options(self) -> dict[str, str]:
        """Return a mapping of device_id -> label for the discovered devices."""
        return {d["device_id"]: d["label"] for d in self._devices}


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
