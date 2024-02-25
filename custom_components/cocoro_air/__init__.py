import logging

import httpx

import voluptuous as vol

from homeassistant.helpers import config_validation, discovery

from homeassistant.const import Platform

DOMAIN = "cocoro_air"

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required("email"): config_validation.string,
        vol.Required("password"): config_validation.string,
        vol.Required("device_id"): config_validation.string,
    })
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    _LOGGER.debug("Setting up Cocoro Air component.")

    email = config[DOMAIN]["email"]
    password = config[DOMAIN]["password"]
    device_id = config[DOMAIN]["device_id"]

    cocoro_air_api = CocoroAir(email, password, device_id)

    hass.data[DOMAIN] = {
        "cocoro_air_api": cocoro_air_api,
    }

    await discovery.async_load_platform(hass, Platform.SENSOR, DOMAIN, {}, config)

    # Return boolean to indicate that initialization was successful.
    return True


class CocoroAir:
    def __init__(self, email, password, device_id):
        self.opener = httpx.Client()
        self.email = email
        self.password = password
        self.device_id = device_id

    def login(self):
        res = self.opener.get('https://cocoroplusapp.jp.sharp/v1/cocoro-air/login')

        redirect_url = res.json()['redirectUrl']

        res = self.opener.get(redirect_url, follow_redirects=True)

        assert res.url.path == '/sic-front/sso/ExLoginViewAction.do'

        res = self.opener.post('https://cocoromembers.jp.sharp/sic-front/sso/A050101ExLoginAction.do', data={
            'memberId': self.email,
            'password': self.password,
            'captchaText': '1',
            'autoLogin': 'on',
            'exsiteId': '50130',
        }, follow_redirects=True)

        assert res.status_code == 200
        assert b'login=success' in res.url.query

        _LOGGER.info('Login success')

    def get_sensor_data(self):
        res = self.opener.get(f'https://cocoroplusapp.jp.sharp/v1/cocoro-air/objects-conceal/air-cleaner', params={
            'device_id': self.device_id,
            'event_key': 'echonet_property',
            'opc': 'k1',
        })

        if res.status_code == 401:
            _LOGGER.info('Login again')
            self.login()
            return self.get_sensor_data()

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
