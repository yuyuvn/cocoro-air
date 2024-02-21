import logging

import httpx

DOMAIN = "cocoro_air"

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config):
    _LOGGER.debug("Setting up Cocoro Air component.")
    cocoromembers_cookie_str = config[DOMAIN]["cocoromembers_cookie_str"]
    device_id = config[DOMAIN]["device_id"]

    cocoro_air = CocoroAir(cocoromembers_cookie_str, device_id)

    hass.data[DOMAIN] = {
        "cocoro_air": cocoro_air,
    }

    # Return boolean to indicate that initialization was successful.
    return True


class CocoroAir:
    def __init__(self, cocoromembers_cookie_str, device_id):
        self.opener = httpx.Client()
        self.cocoromembers_cookie_str = cocoromembers_cookie_str
        self.device_id = device_id

    def login(self):
        res = self.opener.get('https://cocoroplusapp.jp.sharp/v1/cocoro-air/login')

        redirect_url = res.json()['redirectUrl']

        res = self.opener.get(redirect_url, headers={
            'Cookie': self.cocoromembers_cookie_str,
        }, follow_redirects=True)

        assert res.status_code == 200

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
        k1_data = res.json()['objects_aircleaner_020']['body']['data'][0]['k1']

        temperature = int(k1_data['s1'], 16)
        humidity = int(k1_data['s2'], 16)

        return {
            'temperature': temperature,
            'humidity': humidity,
        }
