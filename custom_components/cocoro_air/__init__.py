"""The Cocoro Air integration."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client

DOMAIN = "cocoro_air"

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]


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

    def __init__(self, client, email, password, device_id, model_name):
        """Initialize the API client."""
        self.client = client
        self.email = email
        self.password = password
        self.device_id = device_id
        self.model_name = model_name

    async def login(self):
        """Login to Cocoro Air."""
        async with self.client as client:
            res = await client.get('https://cocoroplusapp.jp.sharp/v1/cocoro-air/login')
            redirect_url = res.json()['redirectUrl']

            res = await client.get(redirect_url, follow_redirects=True)
            assert str(res.url).endswith('/sic-front/sso/ExLoginViewAction.do')

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

    async def get_sensor_data(self):
        """Get sensor data from Cocoro Air."""
        async with self.client as client:
            res = await client.get(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner',
                params={
                    'device_id': self.device_id,
                    'event_key': 'echonet_property',
                    'opc': 'k1',
                }
            )

            if res.status_code == 401:
                _LOGGER.info('Login again')
                await self.login()
                return await self.get_sensor_data()

            _LOGGER.debug(f'cocoro-air response: {res.text}')

            try:
                k1_data = res.json()['objects_aircleaner_020']['body']['data'][0]['k1']
            except KeyError:
                _LOGGER.error(f'Failed to get sensor data, cocoro-air response: {res.text}')
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

            if res.status_code == 401:
                _LOGGER.info('Login again')
                await self.login()
                return await self.set_humidity_mode(mode)

            if res.status_code != 200:
                _LOGGER.error(f'Failed to set humidity mode, status code: {res.status_code}, response: {res.text}')
                return False

            _LOGGER.debug(f'Set humidity mode response: {res.text}')
            return True

    async def get_humidity_mode(self):
        """Get the current humidity mode status."""
        async with self.client as client:
            res = await client.get(
                'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner',
                params={
                    'device_id': self.device_id,
                    'event_key': 'echonet_property',
                    'epc': '0x80+0x86',
                    'opc': 'k1+k2+k3',
                    'count': '1',
                }
            )

            if res.status_code == 401:
                _LOGGER.info('Login again')
                await self.login()
                return await self.get_humidity_mode()

            _LOGGER.debug(f'Get humidity mode response: {res.text}')

            try:
                data = res.json()['objects_aircleaner_020']['body']['data']
                k3_data = None
                for item in data:
                    if 'k3' in item:
                        k3_data = item['k3']
                        break
                if k3_data is None:
                    raise KeyError("Could not find k3 field in response data")
                mode_value = k3_data['s7']
                return mode_value == 'ff'
            except (KeyError, IndexError) as e:
                _LOGGER.error(f'Failed to get humidity mode status: {e}, response: {res.text}')
                return None
