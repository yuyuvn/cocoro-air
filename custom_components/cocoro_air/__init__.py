"""The Cocoro Air integration."""
import logging

import httpx
import async_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

DOMAIN = "cocoro_air"

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cocoro Air from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    _LOGGER.debug("Setting up entry: %s", entry.as_dict())
    
    try:
        session = async_get_clientsession(hass)
        cocoro_air_api = CocoroAir(
            session,
            entry.data["email"],
            entry.data["password"],
            entry.data["device_id"],
        )
        
        # Test the connection
        await cocoro_air_api.login()
        
        hass.data[DOMAIN][entry.entry_id] = {
            "cocoro_air_api": cocoro_air_api,
        }

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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

    def __init__(self, session, email, password, device_id):
        """Initialize the API client."""
        self.session = session
        self.email = email
        self.password = password
        self.device_id = device_id

    async def login(self):
        """Login to Cocoro Air."""
        async with async_timeout.timeout(10):
            async with self.session.get('https://cocoroplusapp.jp.sharp/v1/cocoro-air/login') as res:
                data = await res.json()
                redirect_url = data['redirectUrl']

            async with self.session.get(redirect_url) as res:
                assert str(res.url).endswith('/sic-front/sso/ExLoginViewAction.do')

            async with self.session.post(
                'https://cocoromembers.jp.sharp/sic-front/sso/A050101ExLoginAction.do',
                data={
                    'memberId': self.email,
                    'password': self.password,
                    'captchaText': '1',
                    'autoLogin': 'on',
                    'exsiteId': '50130',
                },
                allow_redirects=True
            ) as res:
                assert res.status == 200
                assert b'login=success' in str(res.url).encode()

        _LOGGER.info('Login success')

    async def get_sensor_data(self):
        """Get sensor data from Cocoro Air."""
        async with async_timeout.timeout(10):
            async with self.session.get(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner',
                params={
                    'device_id': self.device_id,
                    'event_key': 'echonet_property',
                    'opc': 'k1',
                }
            ) as res:
                if res.status == 401:
                    _LOGGER.info('Login again')
                    await self.login()
                    return await self.get_sensor_data()

                _LOGGER.debug(f'cocoro-air response: {await res.text()}')

                try:
                    data = await res.json()
                    k1_data = data['objects_aircleaner_020']['body']['data'][0]['k1']
                except KeyError:
                    _LOGGER.error(f'Failed to get sensor data, cocoro-air response: {await res.text()}')
                    return None

                temperature = int(k1_data['s1'], 16)
                humidity = int(k1_data['s2'], 16)

                return {
                    'temperature': temperature,
                    'humidity': humidity,
                }

    async def set_humidity_mode(self, mode):
        """Set the humidity mode of the air purifier."""
        if mode not in ['on', 'off']:
            raise ValueError("Mode must be either 'on' or 'off'")

        mode_value = 'FF' if mode == 'on' else '00'
        
        async with async_timeout.timeout(10):
            async with self.session.post(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/sync/air-cleaner',
                json={
                    'deviceToken': self.device_id,
                    'event_key': 'echonet_control',
                    'opc': 'b0',
                    'data': [
                        {'opc': "k3", 'odt': {'s5': "00", 's7': mode_value}}
                    ]
                }
            ) as res:
                if res.status == 401:
                    _LOGGER.info('Login again')
                    await self.login()
                    return await self.set_humidity_mode(mode)

                if res.status != 200:
                    _LOGGER.error(f'Failed to set humidity mode, status code: {res.status}, response: {await res.text()}')
                    return False

                _LOGGER.debug(f'Set humidity mode response: {await res.text()}')
                return True

    async def get_humidity_mode(self):
        """Get the current humidity mode status."""
        async with async_timeout.timeout(10):
            async with self.session.get(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner',
                params={
                    'device_id': self.device_id,
                    'event_key': 'echonet_property',
                    'opc': 'k3',
                }
            ) as res:
                if res.status == 401:
                    _LOGGER.info('Login again')
                    await self.login()
                    return await self.get_humidity_mode()

                _LOGGER.debug(f'Get humidity mode response: {await res.text()}')

                try:
                    data = await res.json()
                    data = data['objects_aircleaner_020']['body']['data']
                    k3_data = None
                    for item in data:
                        if 'k3' in item:
                            k3_data = item['k3']
                            break
                    if k3_data is None:
                        raise KeyError("Could not find k3 field in response data")
                    mode_value = k3_data['s7']
                    return mode_value == 'FF'
                except (KeyError, IndexError) as e:
                    _LOGGER.error(f'Failed to get humidity mode status: {e}, response: {await res.text()}')
                    return None
