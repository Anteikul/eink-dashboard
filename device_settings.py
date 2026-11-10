"""Settings, local setup access and Spotify PKCE authorization."""
import base64
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import tempfile
import threading
import time
import unicodedata
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from layout_editor import validate_layout
from spotify_playback import TOKEN_URL

DEFAULTS = {
    'location': 'Prague', 'latitude': 50.0755, 'longitude': 14.4378,
    'timezone': 'Europe/Prague', 'units': 'celsius', 'rotation': 180, 'language': 'en',
    'local_name': True,
}
LANGUAGES = ('en', 'cs')
REDIRECT_URI = 'http://127.0.0.1:8765/callback'
SPOTIFY_SCOPE = 'user-read-currently-playing user-read-playback-state'
LAYOUT_SCREENS = ('dashboard', 'playback')
MAX_SAVED_LAYOUTS = 30


def layout_name(value):
    name = unicodedata.normalize('NFC', value.strip()) if isinstance(value, str) else ''
    if not 1 <= len(name) <= 64 or not name.isprintable():
        raise ValueError('Enter a layout name with 1–64 characters.')
    return name


def write_private(path, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     delete=False) as staged:
        temporary = path.with_name(os.path.basename(staged.name))
        try:
            staged.write(value)
            staged.flush()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def validate_settings(payload):
    result = {key: payload[key] for key in DEFAULTS}
    if not isinstance(result['location'], str) or not 0 < len(result['location'].strip()) <= 120:
        raise ValueError('Enter a location name.')
    result['location'] = result['location'].strip()
    for key, limit in (('latitude', 90), ('longitude', 180)):
        value = float(result[key])
        if not math.isfinite(value) or abs(value) > limit:
            raise ValueError('Check the latitude and longitude.')
        result[key] = value
    try:
        ZoneInfo(result['timezone'])
    except (ValueError, ZoneInfoNotFoundError, TypeError) as error:
        raise ValueError('Enter a valid time zone such as Europe/Prague.') from error
    if (result['units'] not in ('celsius', 'fahrenheit')
            or type(result['rotation']) is not int or result['rotation'] not in (0, 180)):
        raise ValueError('Check the temperature units and rotation.')
    if result['language'] not in LANGUAGES:
        raise ValueError('Choose English or Czech.')
    if type(result['local_name']) is not bool:
        raise ValueError('Choose whether to use the local address.')
    return result


class DeviceSettings:
    def __init__(self, directory):
        self.path = directory / '.settings.json'
        self.layouts_path = directory / '.layouts.json'
        self.library_path = directory / '.layout-library.json'
        self.code_path = directory / '.setup-code'
        self.credentials = directory / '.spotify.json'
        self.lock = threading.Lock()
        self.pending = None
        self.values = validate_settings({**DEFAULTS, **json.loads(self.path.read_text())}) if self.path.is_file() else DEFAULTS.copy()
        self.layouts = self.load_layouts()
        if not self.code_path.exists():
            write_private(self.code_path, secrets.token_urlsafe(18) + '\n')
        self.code = self.code_path.read_text().strip()

    def load_layouts(self):
        defaults = {'dashboard': None, 'playback': None}
        try:
            saved = json.loads(self.layouts_path.read_text())
            return {screen: validate_layout(screen, saved.get(screen)) for screen in defaults}
        except FileNotFoundError:
            pass
        except (AttributeError, TypeError, ValueError, OSError):
            print('Could not read the saved layouts. Using the built-in screens.', flush=True)
        return defaults

    def save_layout(self, screen, layout):
        layout = validate_layout(screen, layout)
        with self.lock:
            layouts = {**self.layouts, screen: layout}
            if layouts != self.layouts:
                write_private(self.layouts_path, json.dumps(layouts, ensure_ascii=False) + '\n')
                self.layouts = layouts
        return layout

    def read_library(self):
        try:
            library = json.loads(self.library_path.read_text(encoding='utf-8'))
            if not isinstance(library, dict) or any(
                not isinstance(library.get(screen), dict) for screen in LAYOUT_SCREENS
            ):
                raise ValueError
            return library
        except FileNotFoundError:
            return {screen: {} for screen in LAYOUT_SCREENS}
        except ValueError as error:
            raise OSError('Could not read the layout library.') from error

    def get_layout_library(self, screen, name=None):
        if screen not in LAYOUT_SCREENS:
            raise ValueError('Choose Dashboard or Playback.')
        entries = self.read_library()[screen]
        if name is None:
            return {'names': sorted(entries, key=str.casefold)}
        return {'layout': validate_layout(screen, entries[layout_name(name)])}

    def edit_layout_library(self, screen, name, layout, *, delete=False):
        if screen not in LAYOUT_SCREENS:
            raise ValueError('Choose Dashboard or Playback.')
        name = layout_name(name)
        if not delete:
            layout = validate_layout(screen, layout)
        with self.lock:
            library = self.read_library()
            entries = library[screen]
            if delete:
                del entries[name]
            else:
                if name in entries:
                    raise ValueError('A saved layout already has that name.')
                if len(entries) >= MAX_SAVED_LAYOUTS:
                    raise ValueError(f'This screen already has {MAX_SAVED_LAYOUTS} saved layouts.')
                entries[name] = layout
            write_private(self.library_path, json.dumps(library, ensure_ascii=False) + '\n')
            return {'names': sorted(entries, key=str.casefold)}

    def authorized(self, code):
        return hmac.compare_digest(self.code.encode(), code.encode())

    def change_code(self, current, new_code):
        if not isinstance(new_code, str) or not re.fullmatch(r'[!-~]{8,64}', new_code):
            raise ValueError('Use 8–64 letters, numbers, or symbols without spaces.')
        with self.lock:
            if not self.authorized(current):
                return False
            write_private(self.code_path, new_code + '\n')
            self.code = new_code
            return True

    def status(self):
        return {'settings': self.values, 'spotifyConnected': self.credentials.is_file(),
                'redirectUri': REDIRECT_URI}

    def save(self, payload):
        with self.lock:
            self.write_values(validate_settings({
                **payload, 'language': self.values['language'], 'local_name': self.values['local_name'],
            }))

    def set_local_name(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Choose whether to use the local address.')
        with self.lock:
            if self.values['local_name'] != enabled:
                self.write_values({**self.values, 'local_name': enabled})

    def set_language(self, language):
        if language not in LANGUAGES:
            raise ValueError('Choose English or Czech.')
        with self.lock:
            if self.values['language'] != language:
                self.write_values({**self.values, 'language': language})

    def write_values(self, values):
        write_private(self.path, json.dumps(values, ensure_ascii=False) + '\n')
        self.values = values

    def authorize(self, client_id):
        if not re.fullmatch(r'[a-fA-F0-9]{32}', client_id):
            raise ValueError('Enter the Client ID from your Spotify app.')
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        with self.lock:
            self.pending = state, verifier, client_id, time.monotonic() + 600
        query = urlencode({
            'client_id': client_id, 'response_type': 'code', 'redirect_uri': REDIRECT_URI,
            'scope': SPOTIFY_SCOPE, 'state': state, 'code_challenge_method': 'S256',
            'code_challenge': challenge,
        })
        return 'https://accounts.spotify.com/authorize?' + query

    def finish(self, callback):
        if not isinstance(callback, str):
            raise ValueError('Paste the address Spotify redirected you to.')
        parts = urlsplit(callback.strip())
        if (parts.scheme, parts.netloc, parts.path) != ('http', '127.0.0.1:8765', '/callback'):
            raise ValueError('Paste the full address starting with http://127.0.0.1:8765/callback.')
        query = parse_qs(parts.query)
        with self.lock:
            if not self.pending or time.monotonic() >= self.pending[3]:
                raise ValueError('The sign-in attempt expired. Start again.')
            state, verifier, client_id, _ = self.pending
            if query.get('state') != [state]:
                raise ValueError('This redirect URL does not match the current sign-in attempt.')
            self.pending = None
            if len(query.get('code', [])) != 1:
                raise ValueError('Spotify did not grant access. Start again.')
            form = urlencode({
                'grant_type': 'authorization_code', 'code': query['code'][0],
                'redirect_uri': REDIRECT_URI, 'client_id': client_id, 'code_verifier': verifier,
            })
            request = Request(TOKEN_URL, data=form.encode(),
                              headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with urlopen(request, timeout=8) as response:
                token = json.load(response)
            if not set(SPOTIFY_SCOPE.split()) <= set(token.get('scope', '').split()):
                raise ValueError('Spotify did not grant access to playback and the queue.')
            write_private(self.credentials, json.dumps({
                'client_id': client_id, 'refresh_token': token['refresh_token'],
            }))

    def disconnect(self):
        with self.lock:
            self.pending = None
            self.credentials.unlink(missing_ok=True)


def find_places(name, language='en'):
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 80:
        raise ValueError('Enter at least two characters of the location name.')
    query = urlencode({'name': name.strip(), 'count': 8, 'language': language})
    with urlopen('https://geocoding-api.open-meteo.com/v1/search?' + query, timeout=6) as response:
        matches = json.load(response).get('results', [])
    return [{
        'location': item['name'], 'latitude': item['latitude'], 'longitude': item['longitude'],
        'timezone': item['timezone'],
        'label': ', '.join(dict.fromkeys(filter(None, (item['name'], item.get('admin1'), item.get('country'))))),
    } for item in matches if item.get('timezone')]
