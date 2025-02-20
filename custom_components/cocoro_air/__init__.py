"""The Cocoro Air integration."""
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import Throttle

DOMAIN = "cocoro_air"

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.HUMIDIFIER]
MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=1)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cocoro Air from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    _LOGGER.debug("Setting up entry: %s", entry.as_dict())
    
    try:
        client = get_async_client(hass)
        cocoro_air_api = CocoroAir(
            client,
            entry.data["email"],
            entry.data["password"],
            entry.data["device_id"],
            entry.data["model_name"],
        )
        
        # Test the connection
        await cocoro_air_api.login()
        
        hass.data[DOMAIN][entry.entry_id] = {
            "cocoro_air_api": cocoro_air_api,
        }

        # Load platforms one at a time to avoid blocking imports
        for platform in PLATFORMS:
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(entry, platform)
            )
        return True
        
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

    def __init__(self, client, email, password, device_id, model_name):
        """Initialize the API client."""
        self.client = client
        self.email = email
        self.password = password
        self.device_id = device_id
        self.model_name = model_name
        self.cache = {}

        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"Cocoro Air {model_name}",
            manufacturer="Sharp",
            model=model_name,
        )

    async def login(self):
        """Login to Cocoro Air."""
        async with self.client as client:
            res = await client.get('https://cocoroplusapp.jp.sharp/v1/cocoro-air/login')
            redirect_url = res.json()['redirectUrl']

            res = await client.get(redirect_url, follow_redirects=True)
            assert str(res.url).endswith('/sic-front/sso/ExLoginViewAction.do') or str(res.url).startswith('https://cocoroplusapp.jp.sharp/air')

            if str(res.url).endswith('/sic-front/sso/ExLoginViewAction.do'):
                res = await client.post(
                    'https://cocoromembers.jp.sharp/sic-front/sso/A050101ExLoginAction.do',
                    data={
                    'memberId': self.email,
                    'password': self.password,
                    'captchaText': '1',
                    'autoLogin': 'on',
                    'exsiteId': '50130',
                },
                follow_redirects=True
                )
                assert res.status_code == 200
                assert b'login=success' in str(res.url).encode()

            _LOGGER.info('Login success')
    
    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def update(self, opc, retried=False):
        """Call the API."""
        async with self.client as client:
            res = await client.get(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner',
                params={
                    'device_id': self.device_id,
                    'event_key': 'echonet_property',
                    'opc': 'k1+k2+k3',
                }
            )

            if res.status_code == 401 and not retried:
                _LOGGER.info('Login again')
                await self.login()
                return await self.call_get_api(opc, True)
            elif res.status_code == 401:
                _LOGGER.error('Login failed')
                return None

            _LOGGER.debug(f'cocoro-air response: {res.text}')

            try:
                data = res.json()['objects_aircleaner_020']['body']['data']
                for item in data:
                    if 'k1' in item:
                        self.cache['k1'] = item['k1']
                    if 'k2' in item:
                        self.cache['k2'] = item['k2']
                    if 'k3' in item:
                        self.cache['k3'] = item['k3']
            except (KeyError, IndexError) as e:
                _LOGGER.error(f'Failed to get data, response: {res.text}')
                return None

    def get_sensor_data(self, retried=False):
        """Get sensor data from Cocoro Air."""
        
        temperature = int(self.cache['k1']['s1'], 16) if self.cache.get('k1', {}).get('s1') else None
        humidity = int(self.cache['k1']['s2'], 16) if self.cache.get('k1', {}).get('s2') else None
        water_tank = self.cache.get('k2', {}).get('s6') == 'ff' if self.cache.get('k2', {}).get('s6') else None
        humidity_mode = self.cache.get('k3', {}).get('s7') == 'ff' if self.cache.get('k3', {}).get('s7') else None

        return {
            'temperature': temperature,
            'humidity': humidity,
            'water_tank': water_tank,
            'humidity_mode': humidity_mode,
        }

    async def set_humidity_mode(self, mode, retried=False):
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
                }
            )

            if res.status_code == 401 and not retried:
                _LOGGER.info('Login again')
                await self.login()
                return await self.set_humidity_mode(mode, True)

            if res.status_code != 200:
                _LOGGER.error(f'Failed to set humidity mode, status code: {res.status_code}, response: {res.text}')
                return False

            _LOGGER.debug(f'Set humidity mode response: {res.text}')
            self._humidity_mode = mode
            return True
