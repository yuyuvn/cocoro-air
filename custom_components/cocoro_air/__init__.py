"""The Cocoro Air integration."""
import asyncio
import logging
import re
from datetime import timedelta

import httpx

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.httpx_client import create_async_httpx_client
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import Throttle

DOMAIN = "cocoro_air"
# The account session shared by every config entry. It lives outside
# hass.data[DOMAIN], which maps entry ids to their device objects.
SESSION_KEY = f"{DOMAIN}_session"
PLATFORMS = [Platform.SENSOR, Platform.HUMIDIFIER]
MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=20)
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')

_LOGGER = logging.getLogger(__name__)


class CocoroAirLoginError(Exception):
    """The login flow did not end on the expected page."""


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Cocoro Air from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug("Setting up entry: %s", entry.as_dict())

    session = hass.data.get(SESSION_KEY)
    if session is None:
        session = CocoroAirSession(create_async_httpx_client(hass))
        hass.data[SESSION_KEY] = session

    email = entry.data["email"]
    if session.email is not None and session.email != email:
        raise ConfigEntryError(
            "Only one Cocoro Air account can be used per Home Assistant instance; "
            f"the session is logged in as {session.email}"
        )

    try:
        await session.async_login(email, entry.data["password"])

        hass.data[DOMAIN][entry.entry_id] = {
            "cocoro_air_api": CocoroAir(
                session,
                email,
                entry.data["password"],
                entry.data["device_id"],
                entry.data["model_name"],
            ),
        }

        # Load platforms one at a time to avoid blocking imports
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except (httpx.TimeoutException, httpx.NetworkError, CocoroAirLoginError) as ex:
        # Transient connection problems (e.g. ConnectTimeout during startup)
        # and login flows that end on an unexpected page. Raising
        # ConfigEntryNotReady lets Home Assistant retry automatically with
        # backoff instead of leaving the entry in a failed state. Other
        # TransportError subclasses (protocol/proxy/unsupported-scheme)
        # indicate bugs or misconfiguration, so let them propagate as real
        # errors.
        raise ConfigEntryNotReady(f"Could not connect to Cocoro Air: {ex}") from ex
    except Exception as ex:
        _LOGGER.error("Error setting up entry: %s", ex)
        raise


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN] and (session := hass.data.pop(SESSION_KEY, None)):
            await session.async_close()

    return unload_ok


class CocoroAirSession:
    """One logged-in Cocoro Air account.

    Owns the httpx client and therefore the cookies that carry the login.
    The Auth0 flow binds its state to session cookies, so two logins running
    at the same time in one cookie jar break each other; every login goes
    through the lock and later callers find the jar already logged in.
    """

    def __init__(self, client: httpx.AsyncClient):
        """Initialize the session."""
        self.client = client
        self.email: str | None = None
        self._lock = asyncio.Lock()
        self._logged_in = False

    async def async_close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def async_login(self, email: str, password: str, *, force: bool = False) -> None:
        """Log in unless the session is already logged in.

        Pass force=True after a 401 to log in again.
        """
        async with self._lock:
            if self._logged_in and not force:
                return
            self._logged_in = False
            await self._async_run_login_flow(email, password)
            self._logged_in = True
            self.email = email

    async def _async_run_login_flow(self, email: str, password: str) -> None:
        client = self.client
        res = await client.get('https://cocoroplusapp.jp.sharp/v1/cocoro-air/login')
        redirect_url = res.json()['redirectUrl']

        res = await client.get(redirect_url, follow_redirects=True, headers={'User-Agent': USER_AGENT})
        if str(res.url).startswith('https://cocoroplusapp.jp.sharp/air'):
            # The cookies already carry a login; Auth0 sent us straight back.
            _LOGGER.info('Login success')
            return
        if '/u/login/identifier' not in str(res.url):
            raise CocoroAirLoginError(f'Unexpected login page: {res.status_code} {res.url}')

        state = self._extract_state(res)
        res = await client.post(
            f'https://auth.cocoromembers.jp.sharp/u/login/identifier?state={state}',
            data={
                'state': state,
                'username': email,
                'captcha': '',
                'js-available': 'true',
                'webauthn-available': 'false',
                'is-brave': 'false',
                'webauthn-platform-available': 'false',
                'action': 'default',
            },
            headers={'User-Agent': USER_AGENT},
            follow_redirects=True
        )
        if '/u/login/password' not in str(res.url):
            raise CocoroAirLoginError(f'Unexpected page after identifier step: {res.status_code} {res.url}')

        state = self._extract_state(res)
        res = await client.post(
            f'https://auth.cocoromembers.jp.sharp/u/login/password?state={state}',
            data={
                'state': state,
                'username': email,
                'password': password,
                'action': 'default',
            },
            headers={'User-Agent': USER_AGENT},
            follow_redirects=True
        )
        if res.status_code != 200 or 'login=success' not in str(res.url):
            raise CocoroAirLoginError(f'Unexpected page after password step: {res.status_code} {res.url}')

        _LOGGER.info('Login success')

    @staticmethod
    def _extract_state(res: httpx.Response) -> str:
        match = re.search(r'name="state" value="([^"]+)"', res.text)
        if match is None:
            raise CocoroAirLoginError(f'No state field on {res.url}')
        return match.group(1)

    async def async_query_devices(self, email: str, password: str, retried: bool = False):
        """Query the devices registered to this account."""
        res = await self.client.get('https://cocoroplusapp.jp.sharp/v1/cocoro-air/deviceinfos')

        if res.status_code == 401 and not retried:
            _LOGGER.info('Login again')
            await self.async_login(email, password, force=True)
            return await self.async_query_devices(email, password, True)
        elif res.status_code == 401:
            _LOGGER.error('Login failed')
            return []

        res.raise_for_status()
        data = res.json()

        devices = []
        # Structure: {"device_infos_...": {"body": {"devices": [...]}}}
        for val in data.values():
            if not (isinstance(val, dict) and 'devices' in val.get('body', {})):
                continue

            for item in val['body']['devices']:
                name = item.get('device_name', item.get('device_id', 'Unknown'))
                model = item.get('model_name', '')
                place = item.get('place', '')

                label = name
                if model:
                    label += f' ({model})'
                if place:
                    label += f' - {place}'

                devices.append({
                    'device_id': item['device_id'],
                    'model_name': model,
                    'label': label,
                })

        _LOGGER.debug(f'Discovered devices: {devices}')
        return devices


class CocoroAir:
    """One Cocoro Air device, talking through the shared account session."""

    def __init__(self, session: CocoroAirSession, email, password, device_id, model_name):
        """Initialize the device client."""
        self.session = session
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
        """Log the shared session in again."""
        await self.session.async_login(self.email, self.password, force=True)

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def update(self, retried=False):
        """Call the API."""
        client = self.session.client
        res = await client.get(
            # 'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner',
            'https://cocoroplusapp.jp.sharp/v1/cocoro-air/sensors-conceal/air-cleaner',
            params={
                'device_id': self.device_id,
                'event_key': 'echonet_property',
                'opc': 'k1+k2+k3',
                'epc': '0x80+0x86',
            }
        )
        if res.status_code == 401 and not retried:
            _LOGGER.info('Login again')
            await self.login()
            return await self.update(True)
        elif res.status_code == 401:
            _LOGGER.error('Login failed')
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

    async def set_humidity_mode(self, mode, retried=False):
        """Set the humidity mode of the air purifier."""
        if mode not in ['on', 'off']:
            raise ValueError("Mode must be either 'on' or 'off'")

        mode_value = 'FF' if mode == 'on' else '00'

        client = self.session.client
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
        elif res.status_code == 401:
            _LOGGER.error('Login failed')
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
