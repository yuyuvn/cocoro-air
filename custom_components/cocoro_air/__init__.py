"""The Cocoro Air integration."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import Throttle

DOMAIN = "cocoro_air"
PLATFORMS = [Platform.SENSOR, Platform.HUMIDIFIER]
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=20)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cocoro Air from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug("Setting up entry: %s", entry.as_dict())

    try:
        client = get_async_client(hass)
        cocoro_air_api = CocoroAir(
            client,
            entry.data["cookie"],
            entry.data["device_id"],
            entry.data["model_name"],
        )

        # Verify the stored session cookie is still valid
        try:
            await cocoro_air_api.login()
        except InvalidSession as err:
            raise ConfigEntryAuthFailed(
                "Session cookie is invalid or expired, please reauthenticate"
            ) from err

        hass.data[DOMAIN][entry.entry_id] = {
            "cocoro_air_api": cocoro_air_api,
        }

        # Load platforms one at a time to avoid blocking imports
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except ConfigEntryAuthFailed:
        raise
    except Exception as ex:
        _LOGGER.error("Error setting up entry: %s", ex)
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class CocoroAir:
    """Cocoro Air API Client."""

    _cache = None

    def __init__(self, client, cookie, device_id, model_name):
        """Initialize the API client.

        `cookie` is the raw `Cookie` request header captured from a browser
        that has completed a full login (including CAPTCHA/2FA) at
        https://cocoroplusapp.jp.sharp/air. Sharp's Auth0 login page gates
        automated credential submission behind a CAPTCHA, so this integration
        can no longer log in with just an email/password.
        """
        self.client = client
        self.device_id = device_id
        self.model_name = model_name
        self.headers = {"Cookie": cookie}
        self.cache = {}

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"Cocoro Air {model_name}",
            manufacturer="Sharp",
            model=model_name,
        )

    async def login(self):
        """Verify the stored session cookie is still valid."""
        async with self.client as client:
            res = await client.get(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/sensors-conceal/air-cleaner',
                params={
                    'device_id': self.device_id,
                    'event_key': 'echonet_property',
                    'opc': 'k1+k2+k3',
                    'epc': '0x80+0x86',
                },
                headers=self.headers,
            )
            if res.status_code != 200:
                raise InvalidSession(
                    f"Unexpected status {res.status_code} from session check: {res.text[:500]!r}"
                )

            _LOGGER.info('Session cookie is valid')

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def update(self):
        """Call the API."""
        async with self.client as client:
            res = await client.get(
                # 'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner',
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/sensors-conceal/air-cleaner',
                params={
                    'device_id': self.device_id,
                    'event_key': 'echonet_property',
                    'opc': 'k1+k2+k3',
                    'epc': '0x80+0x86',
                },
                headers=self.headers,
            )
            if res.status_code == 401:
                _LOGGER.error('Session cookie has expired, reauthenticate to restore updates')
                return None

            _LOGGER.debug(f'cocoro-air response: {res.text}')

            response_data = self.cache
            try:
                # data = res.json()['objects_aircleaner_020']['body']['data']
                data = res.json()['sensors_aircleaner_021']['body']['data']
                for item in data:
                    if 'k1' in item:
                        response_data['k1'] = item['k1']
                    if 'k2' in item:
                        response_data['k2'] = item['k2']
                    if 'k3' in item:
                        response_data['k3'] = item['k3']
            except (KeyError, IndexError) as e:
                _LOGGER.error(f'Failed to get data, response: {res.text}')
                return None

            self.cache = response_data
            return response_data

    def get_sensor_data(self, data=None, retried=False):
        """Get sensor data from Cocoro Air."""
        if data is None:
            data = self.cache

        temperature = int(data['k1']['s1'], 16) if data.get('k1', {}).get('s1') else None
        humidity = int(data['k1']['s2'], 16) if data.get('k1', {}).get('s2') else None
        cleaned_air_volume = int(data.get('k1', {}).get('s6'), 16) if data.get('k1', {}).get('s6') else None
        pm25 = int(data.get('k1', {}).get('s7'), 16) if data.get('k1', {}).get('s7') else None
        odor_level = int(data.get('k2', {}).get('s1'), 16) if data.get('k2', {}).get('s1') else None
        dust_level = int(data.get('k2', {}).get('s2'), 16) if data.get('k2', {}).get('s2') else None
        cleanliness_level = int(data.get('k2', {}).get('s4'), 16) if data.get('k2', {}).get('s4') else None
        water_tank = data.get('k2', {}).get('s6') == 'ff' if data.get('k2', {}).get('s6') else None
        humidity_mode = data.get('k3', {}).get('s7') == 'ff' if data.get('k3', {}).get('s7') else None

        parsed = {
            'temperature': temperature,
            'humidity': humidity,
            'cleaned_air_volume': cleaned_air_volume,
            'pm25': pm25,
            'odor_level': odor_level,
            'dust_level': dust_level,
            'cleanliness_level': cleanliness_level,
            'water_tank': water_tank,
            'humidity_mode': humidity_mode,
        }
        _LOGGER.debug(f'Parsed sensor data: {parsed}')
        return parsed

    async def set_humidity_mode(self, mode):
        """Set the humidity mode of the air purifier."""
        if mode not in ['on', 'off']:
            raise ValueError("Mode must be either 'on' or 'off'")

        mode_value = 'FF' if mode == 'on' else '00'

        async with self.client as client:
            res = await client.post(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/sync/air-cleaner',
                json={
                    'additional_request': False,
                    'deviceToken': self.device_id,
                    'event_key': 'echonet_control',
                    'data': [
                        {'opc': "k3", 'odt': {'s5': "00", 's7': mode_value}}
                    ],
                    'model_name': self.model_name,
                },
                headers=self.headers,
            )

            if res.status_code == 401:
                _LOGGER.error('Session cookie has expired, reauthenticate to restore control')
                return False

            if res.status_code != 200:
                _LOGGER.error(f'Failed to set humidity mode, status code: {res.status_code}, response: {res.text}')
                return False

            _LOGGER.debug(f'Set humidity mode response: {res.text}')

            if not self.cache:
                self.cache = {}
            if 'k3' not in self.cache:
                self.cache['k3'] = {}
            self.cache['k3']['s7'] = mode_value
            return True


class InvalidSession(Exception):
    """Raised when the stored session cookie is invalid or expired."""
