import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from unittest.mock import patch

from control import PanelState, start_server
from dashboard import Weather, render
from datetime import datetime
from device_settings import DEFAULTS, DeviceSettings, REDIRECT_URI, SPOTIFY_SCOPE


with TemporaryDirectory() as folder:
    root = Path(folder)
    settings = DeviceSettings(root)
    calls = []
    server = start_server('127.0.0.1', 0, PanelState(root / 'theme.txt'),
                          settings, lambda: calls.append('reload'))
    base = f'http://127.0.0.1:{server.server_port}'

    def get(path, body=None, code=None, origin=base):
        headers = {'X-Setup-Code': code if code is not None else settings.code}
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': origin})
        request = Request(base + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    try:
        assert get('/api/settings', code='wrong')[0] == 403
        assert get('/api/settings', DEFAULTS, origin='http://other.example')[0] == 403
        status, data = get('/api/settings')
        assert status == 200 and data['settings'] == DEFAULTS and not data['spotifyConnected']
        selected = {**DEFAULTS, 'location': 'London', 'latitude': 51.5,
                    'longitude': -0.12, 'timezone': 'Europe/London', 'rotation': 0,
                    'units': 'fahrenheit'}
        assert get('/api/settings', {**selected, 'timezone': 'fake'})[0] == 400
        assert get('/api/settings', {**selected, 'latitude': 91})[0] == 400
        assert get('/api/settings', selected)[0] == 200
        assert DeviceSettings(root).values == selected
        assert 'temperature_unit=fahrenheit' in Weather(selected).url
        assert len(render(datetime(2026, 11, 9), (45, 0, False), units='fahrenheit')) == 250 * 122

        places = [{'location': 'London', 'latitude': 51.5, 'longitude': -0.12,
                   'timezone': 'Europe/London', 'label': 'London, United Kingdom'}]
        with patch('control.find_places', return_value=places):
            assert get('/api/places', {'name': 'London'}) == (200, {'places': places})

        status, data = get('/api/spotify/start', {'clientId': 'a' * 32})
        assert status == 200
        auth = parse_qs(urlsplit(data['url']).query)
        assert auth['redirect_uri'] == [REDIRECT_URI]
        assert auth['code_challenge_method'] == ['S256']
        assert auth['scope'] == [SPOTIFY_SCOPE]
        assert get('/api/spotify/finish', {'callback': REDIRECT_URI + '?code=x&state=wrong'})[0] == 400
        callback = REDIRECT_URI + '?' + urlencode({'code': 'fake-code', 'state': auth['state'][0]})
        token = json.dumps({'scope': SPOTIFY_SCOPE, 'refresh_token': 'fake-token'}).encode()
        with patch('device_settings.urlopen', return_value=io.BytesIO(token)) as exchange:
            status, data = get('/api/spotify/finish', {'callback': callback})
        assert status == 200 and data['spotifyConnected'] and 'fake-token' not in json.dumps(data)
        assert b'code_verifier=' in exchange.call_args.args[0].data
        assert settings.credentials.stat().st_mode & 0o777 == 0o600
        assert get('/api/spotify/finish', {'callback': callback})[0] == 400
        assert get('/api/spotify/disconnect', {})[1]['spotifyConnected'] is False
        assert not settings.credentials.exists()
        assert len(calls) == 3
    finally:
        server.shutdown()
        server.server_close()

print('LAN settings, location, rotation, access control and Spotify PKCE passed.')
