# cocoro-air

https://cocoroplusapp.jp.sharp/air

## Supported features

- [ ] Air Cleaner
    - [x] Temperature Sensor
    - [x] Humidity Sensor
    - [x] Humidifier Mode
    - [ ] Filter Remaining Sensor
    - [ ] ~Power~
    - [ ] ~Fan Speed~
    - [ ] ~Air Quality Sensor~

Note: You can use [echonetlite](https://github.com/scottyphillips/echonetlite_homeassistant) for Power, Air quality and Fan speed control. Thus this plugin won't support it unless someone contribute to the project.

## Installation

### Install via HACS Custom repositories

https://hacs.xyz/docs/faq/custom_repositories

## Configuration

Sharp's login page now requires solving a CAPTCHA, so this integration can no longer log in with just an email and password — instead it authenticates with a session cookie captured from your browser.

1. Ensure you have an account at [Cocoro Air](https://cocoroplusapp.jp.sharp/air).
2. Log in fully (including any CAPTCHA/2FA prompts) at https://cocoroplusapp.jp.sharp/air in your browser.
3. Open devtools → Network tab, find any request to `cocoroplusapp.jp.sharp`, and copy the value of its `Cookie` request header.
4. Get `device_id` and model name from browser devtools (e.g. from the Cocoro Air app).
5. Go to **Settings** → **Devices & Services** in Home Assistant, click **Add Integration**, and search for **Cocoro Air**.
6. Paste the cookie header, device_id and model name.

The session cookie will eventually expire. When it does, sensors stop updating and Home Assistant will prompt you to reauthenticate — repeat steps 2-3 and paste the new cookie into that prompt (or use **Reconfigure** on the integration).

## Model supported

Model that has been tested:
- KILS50
