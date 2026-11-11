import io
import json
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import sleep
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener, urlopen
from unittest.mock import patch

from control import SESSION_AGE, PanelState, start_server, valid_session
from dashboard import Weather, render, screen_content
from datetime import datetime
from device_settings import DEFAULTS, DeviceSettings, REDIRECT_URI, SPOTIFY_SCOPE
from updates import UpdateStore, Updater


with TemporaryDirectory() as folder:
    root = Path(folder)
    settings = DeviceSettings(root)
    calls = []
    update_store = UpdateStore(root)
    update_restart = Event()
    current_revision, new_revision = 'a' * 40, 'b' * 40
    updater = Updater(update_store, current_revision, update_restart.set)
    server = start_server('127.0.0.1', 0, PanelState(root / 'theme.txt'),
                          settings, lambda: calls.append('reload'), updater=updater)
    base = f'http://127.0.0.1:{server.server_port}'

    def get(path, body=None, code=None, origin=base, host=None):
        headers = {'X-Setup-Code': code if code is not None else settings.code}
        if host is not None:
            headers['Host'] = host
        if body is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': origin})
        request = Request(base + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error) if error.headers.get_content_type() == 'application/json' else None

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    cookie_jar = CookieJar()
    browser = build_opener(HTTPCookieProcessor(cookie_jar))
    password_headers = {'Content-Type': 'application/json', 'Origin': base}

    def post_from_browser(path, data, headers=password_headers):
        return browser.open(Request(base + path, data=json.dumps(data).encode(), headers=headers), timeout=5)

    try:
        with urlopen(base) as response:
            html = response.read().decode()
        assert 'data-theme="light"' in html and 'href="/settings"' in html and '<dialog' not in html
        assert 'id="device-form"' not in html
        assert get('/api/state', code='')[1]['mode'] == 'auto'
        for mode in ('dashboard', 'playback', 'auto'):
            assert f'data-mode="{mode}"' in html
            assert get('/api/display-mode', {'mode': mode}, code='')[1]['mode'] == mode
            assert PanelState(root / 'theme.txt').status()['mode'] == mode
        assert get('/api/display-mode', {'mode': 'unknown'}, code='')[0] == 400
        assert get('/api/display-mode', {'mode': 'playback'}, code='', origin='http://other.example')[0] == 403
        sign_in_pages = []
        for destination in ('settings', 'editor'):
            try:
                build_opener(NoRedirect()).open(base + '/' + destination)
            except HTTPError as error:
                assert error.code == 302 and error.headers['Location'] == '/unlock?next=' + destination
            else:
                raise AssertionError('Protected page opened without authentication')
            with browser.open(base + '/' + destination) as response:
                sign_in_pages.append(response.read())
        assert sign_in_pages[0] == sign_in_pages[1] and b'id="unlock-code"' in sign_in_pages[0]
        assert get('/api/unlock', {'code': 'wrong'}, code='')[0] == 403
        assert get('/api/unlock', {'code': settings.code}, code='', origin='http://other.example')[0] == 403
        with post_from_browser('/api/unlock', {'code': settings.code}) as response:
            assert response.status == 200
            cookie = response.headers['Set-Cookie']
            assert all(attr in cookie for attr in ('HttpOnly', 'SameSite=Strict', 'Path=/'))
        session_header = cookie.split(';', 1)[0]
        restarted = DeviceSettings(root)
        assert (root / '.web-session-key').stat().st_mode & 0o777 == 0o600
        assert valid_session(session_header, restarted.session_key, restarted.code)
        with patch('control.time.time', return_value=int(session_header.split('=')[1].split('.')[0]) + SESSION_AGE):
            assert not valid_session(session_header, restarted.session_key, restarted.code)
        with browser.open(base + '/settings') as response:
            page = response.read().decode()
            assert 'id="device-form"' in page and 'href="/"' in page
            assert 'name="weather_interval"' in page and 'name="playing_interval"' in page
        with browser.open(base + '/editor') as response:
            assert b'id="layout-editor"' in response.read()
        with browser.open(base + '/api/layouts') as response:
            assert response.status == 200
        alias = f'eink.local:{server.server_port}'
        alias_origin = f'http://{alias}'
        assert get('/api/state', host=alias)[0] == 200
        assert get('/api/theme', {'theme': 'dark'}, host=alias, origin=alias_origin)[0] == 200
        assert get('/api/theme', {'theme': 'light'}, host=alias, origin=base)[0] == 403
        assert get('/api/local-name', {'enabled': False}, code='wrong')[0] == 403
        assert get('/api/local-name', {'enabled': False}, host=alias, origin=alias_origin) == (
            200, {'enabled': False, 'hostname': 'eink.local', 'ipUrl': base})
        assert DeviceSettings(root).values['local_name'] is False
        assert get('/api/state', host=alias)[0] == 400
        assert get('/api/state')[0] == 200
        assert get('/api/local-name', {'enabled': True})[0] == 200
        assert get('/api/state', host=alias)[0] == 200
        assert get('/api/local-name', {'enabled': True, 'hostname': 'not.example.com'})[0] == 400
        status, result = get('/api/local-name', {'enabled': True, 'hostname': ' Desk-Eink '})
        assert status == 200 and result['hostname'] == 'desk-eink.local'
        renamed = f'desk-eink.local:{server.server_port}'
        assert get('/api/state', host=alias)[0] == 400
        assert get('/api/state', host=renamed)[0] == 200
        assert DeviceSettings(root).values['local_hostname'] == 'desk-eink.local'
        assert get('/api/local-name', {'enabled': True, 'hostname': 'eink.local'},
                   host=renamed, origin=f'http://{renamed}')[0] == 200
        assert get('/api/settings', code='wrong')[0] == 403
        assert get('/api/update', code='')[0] == 403
        assert get('/api/update', {}, code='')[0] == 403
        assert get('/api/update', {}, origin='http://other.example')[0] == 403
        assert get('/api/update', {'retry': 'yes'})[0] == 400
        assert get('/api/update/install', {'version': 'b' * 40}, code='')[0] == 403
        assert get('/api/update/install', {'version': 'b' * 40}, origin='http://other.example')[0] == 403
        assert get('/api/update/install', {})[0] == 400
        with patch('updates.latest_version', return_value=new_revision), patch('updates.is_ahead', return_value=True), \
                patch('updates.prepare_release') as prepare:
            assert get('/api/update', {'retry': True})[0] == 200
            for _ in range(30):
                _, status = get('/api/update')
                if status['state'] == 'available':
                    break
                sleep(.05)
            assert status == {'state': 'available', 'version': current_revision, 'availableVersion': new_revision}
            assert not prepare.called and not update_store.pending.exists() and not update_restart.is_set()
            assert get('/api/update/install', {'version': 'c' * 40})[0] == 400
            assert get('/api/update/install', {'version': new_revision})[0] == 200
            assert update_restart.wait(5) and prepare.call_count == 1
        assert get('/api/settings', DEFAULTS, origin='http://other.example')[0] == 403
        status, data = get('/api/settings')
        assert status == 200 and data['settings'] == DEFAULTS and not data['spotifyConnected']
        assert get('/api/spotify/check', {})[0] == 409
        assert get('/api/spotify/check', {}, code='wrong')[0] == 403
        selected = {**DEFAULTS, 'location': 'London', 'latitude': 51.5,
                    'longitude': -0.12, 'timezone': 'Europe/London', 'rotation': 0,
                    'units': 'fahrenheit'}
        assert get('/api/settings', {**selected, 'timezone': 'fake'})[0] == 400
        assert get('/api/settings', {**selected, 'latitude': 91})[0] == 400
        assert get('/api/settings', {**selected, 'weather_interval': 0})[0] == 400
        assert get('/api/settings', {**selected, 'queue_prefetch': 1})[0] == 400
        tuned = {**selected, 'weather_interval': 4, 'full_refresh_after': 20, 'playing_interval': 2,
                 'idle_interval': 12, 'hotspot_delay': 45, 'queue_prefetch': False,
                 'weather_enabled': False, 'playback_enabled': False}
        assert get('/api/settings', tuned)[0] == 200
        assert DeviceSettings(root).values == tuned and Weather(tuned).interval == 240
        assert render(datetime(2026, 11, 9), (10, 0, True), weather_enabled=False) == render(
            datetime(2026, 11, 9), (-10, 60, False), weather_enabled=False)
        assert get('/api/settings', selected)[0] == 200
        assert DeviceSettings(root).values == selected
        assert get('/api/language', {'language': 'invalid'}, code='')[0] == 400
        assert get('/api/language', {'language': 'cs'}, code='')[1]['language'] == 'cs'
        assert get('/api/state', code='')[1]['language'] == 'cs'
        legacy_settings = {key: value for key, value in selected.items() if key != 'language'}
        assert get('/api/settings', legacy_settings)[0] == 200
        assert DeviceSettings(root).values == {**selected, 'language': 'cs'}
        assert screen_content(datetime(2026, 11, 10), None, language='cs')[1] == 'Út 10. 11. 2026'
        assert screen_content(datetime(2026, 11, 10), None, language='en')[1] == 'Tue 10 Nov 2026'
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
        with patch('control.SpotifyPlayback') as playback:
            playback.return_value.read.return_value = None
            assert get('/api/spotify/check', {}) == (200, {'verified': True})
            playback.return_value.read.side_effect = HTTPError('https://api.spotify.com', 403, '', {}, None)
            assert get('/api/spotify/check', {})[0] == 502
        assert get('/api/spotify/finish', {'callback': callback})[0] == 400
        assert get('/api/spotify/disconnect', {})[1]['spotifyConnected'] is False
        assert not settings.credentials.exists()
        assert len(calls) == 5
        original_code = settings.code
        assert get('/api/setup-code', {'newCode': 'short'})[0] == 400
        assert get('/api/setup-code', {'newCode': 'new-setup-code'}, code='wrong')[0] == 403
        with post_from_browser('/api/setup-code', {'newCode': 'new-setup-code'}) as response:
            assert response.status == 200 and response.headers['Set-Cookie'] != cookie
        with browser.open(base + '/api/settings') as response:
            assert response.status == 200
        try:
            urlopen(Request(base + '/api/settings', headers={'Cookie': session_header}))
        except HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError('Old session survived a setup code change')
        assert get('/api/settings', code=original_code)[0] == 403
        assert get('/api/settings', code='new-setup-code')[0] == 200
        assert DeviceSettings(root).code == 'new-setup-code'
        assert settings.code_path.stat().st_mode & 0o777 == 0o600
        assert get('/api/password-protection', {'required': False}, code='')[0] == 403
        assert get('/api/password-protection', {'required': 0})[0] == 400
        assert get('/api/password-protection', {'required': False}) == (200, {'required': False})
        assert DeviceSettings(root).values['password_required'] is False
        assert get('/api/settings', code='')[0] == 200
        assert get('/api/layouts', code='')[0] == 200
        for path in ('/settings', '/editor', '/unlock?next=editor'):
            with urlopen(base + path) as response:
                assert response.geturl().endswith('/editor' if path.startswith('/unlock') else path)
        assert get('/api/settings', selected, code='')[1]['settings']['password_required'] is False
        assert get('/api/password-protection', {'required': True}, code='', origin='http://other.example')[0] == 403
        with post_from_browser('/api/password-protection', {'required': True}) as response:
            assert json.load(response) == {'required': True} and response.headers.get('Set-Cookie')
        assert DeviceSettings(root).values['password_required'] is True
        assert get('/api/settings', code='')[0] == 403
        with browser.open(base + '/api/settings') as response:
            assert response.status == 200
        assert DeviceSettings(root).code == 'new-setup-code'
    finally:
        server.shutdown()
        server.server_close()

print('LAN settings, location, rotation, access control and Spotify PKCE passed.')


def bind_test_port(address, handler):
    server = ThreadingHTTPServer((address[0], 0), handler)
    server.server_port = 80
    return server


with TemporaryDirectory() as folder, patch('control.ThreadingHTTPServer', bind_test_port):
    root = Path(folder)
    settings = DeviceSettings(root)
    server = start_server('127.0.0.1', 80, PanelState(root / 'theme.txt'),
                          settings, lambda: None)
    try:
        base = f'http://127.0.0.1:{server.server_address[1]}'
        for host in ('127.0.0.1', '127.0.0.1:80'):
            with urlopen(Request(base, headers={'Host': host})) as response:
                assert response.status == 200
        request = Request(base + '/api/settings', data=json.dumps(DEFAULTS).encode(),
                          headers={'Host': '127.0.0.1', 'Origin': 'http://127.0.0.1',
                                   'Content-Type': 'application/json',
                                   'X-Setup-Code': settings.code})
        with urlopen(request) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()

print('Default HTTP port accepts browser requests without a port suffix.')
