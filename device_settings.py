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
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from layout_editor import PANEL_SIZE, resize_layer, resize_layout, validate_display_size, validate_layout
from local_name import HOSTNAME
from spotify_playback import IDLE_INTERVAL, PLAYING_INTERVAL, TOKEN_URL
from wifi_setup import GRACE

DEFAULTS = {
    'location': 'Prague', 'latitude': 50.0755, 'longitude': 14.4378,
    'timezone': 'Europe/Prague', 'units': 'celsius', 'rotation': 180, 'language': 'en',
    'local_name': True, 'password_required': True,
    'display_width': PANEL_SIZE[0], 'display_height': PANEL_SIZE[1],
    'weather_enabled': True, 'weather_interval': 15, 'full_refresh_after': 5,
    'playback_enabled': True, 'playing_interval': PLAYING_INTERVAL, 'idle_interval': IDLE_INTERVAL,
    'queue_prefetch': True, 'local_hostname': HOSTNAME, 'hotspot_delay': GRACE,
}
SETTING_RANGES = {
    'weather_interval': (1, 60), 'full_refresh_after': (1, 60),
    'playing_interval': (1, 120), 'idle_interval': (1, 120), 'hotspot_delay': (5, 300),
}
EXTRA_SETTINGS = (*SETTING_RANGES, 'display_width', 'display_height',
                  'weather_enabled', 'playback_enabled', 'queue_prefetch',
                  'language', 'local_name', 'local_hostname')
LANGUAGES = ('en', 'cs')
ROTATIONS = (0, 90, 180, 270)
REDIRECT_URI = 'http://127.0.0.1:8765/callback'
SPOTIFY_SCOPE = 'user-read-currently-playing user-read-playback-state'
LAYOUT_SCREENS = ('dashboard', 'playback')
MAX_SAVED_LAYOUTS = 30


def layout_name(value):
    name = unicodedata.normalize('NFC', value.strip()) if isinstance(value, str) else ''
    if not 1 <= len(name) <= 64 or not name.isprintable():
        raise ValueError('Enter a layout name with 1–64 characters.')
    return name


def library_entry(value):
    if not isinstance(value, dict):
        return value, None
    saved_at = value.get('savedAt')
    return value['layout'], saved_at if isinstance(saved_at, str) else None


def library_layout(screen, entry):
    layout, _ = library_entry(entry)
    source = validate_display_size(entry.get('size', PANEL_SIZE)) if isinstance(entry, dict) else PANEL_SIZE
    return source, validate_layout(screen, layout, source)


def library_listing(entries, *, details=False):
    names = sorted(entries, key=str.casefold)
    result = {'names': names}
    if details:
        records = []
        for name in names:
            layout, saved_at = library_entry(entries[name])
            records.append({'name': name, 'savedAt': saved_at,
                            'layers': len(layout) if isinstance(layout, list) else None})
        result['entries'] = sorted(records, key=lambda record: record['savedAt'] or '', reverse=True)
    return result


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
            or type(result['rotation']) is not int or result['rotation'] not in ROTATIONS):
        raise ValueError('Check the temperature units and rotation.')
    if result['language'] not in LANGUAGES:
        raise ValueError('Choose English or Czech.')
    if type(result['local_name']) is not bool:
        raise ValueError('Choose whether to use the local address.')
    result['local_hostname'] = validate_local_hostname(result['local_hostname'])
    for key in ('weather_enabled', 'playback_enabled', 'queue_prefetch', 'password_required'):
        if type(result[key]) is not bool:
            raise ValueError('Check the on/off settings.')
    for key, (minimum, maximum) in SETTING_RANGES.items():
        if type(result[key]) is not int or not minimum <= result[key] <= maximum:
            raise ValueError('Check the refresh intervals and Wi-Fi setup delay.')
    result['display_width'], result['display_height'] = display_size(result)
    return result


def display_size(values, rotation=None):
    width, height = validate_display_size((values['display_width'], values['display_height']))
    angle = values['rotation'] if rotation is None else rotation
    portrait = angle in (90, 270)
    return (height, width) if portrait != (width < height) else (width, height)


def validate_local_hostname(hostname):
    if not isinstance(hostname, str):
        raise ValueError('Use a local name such as eink.local.')
    name = hostname.strip().lower().removesuffix('.local')
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', name):
        raise ValueError('Use a local name such as eink.local.')
    return name + '.local'


class DeviceSettings:
    def __init__(self, directory, *, rotation=None):
        self.path = directory / '.settings.json'
        self.layouts_path = directory / '.layouts.json'
        self.library_path = directory / '.layout-library.json'
        self.code_path = directory / '.setup-code'
        self.credentials = directory / '.spotify.json'
        self.lock = threading.Lock()
        self.pending = None
        self.rotation_override = rotation
        self.values = validate_settings({**DEFAULTS, **json.loads(self.path.read_text())}) if self.path.is_file() else DEFAULTS.copy()
        self._stored_layouts = self.load_layouts()
        size = display_size(self.values, self.rotation_override)
        self.layout_state = size, self.layouts_at(size)
        if not self.code_path.exists():
            write_private(self.code_path, secrets.token_urlsafe(18) + '\n')
        self.code = self.code_path.read_text().strip()
        session_key_path = directory / '.web-session-key'
        try:
            self.session_key = bytes.fromhex(session_key_path.read_text().strip())
        except (FileNotFoundError, ValueError):
            self.session_key = b''
        if len(self.session_key) != 32:
            self.session_key = secrets.token_bytes(32)
            write_private(session_key_path, self.session_key.hex() + '\n')

    def load_layouts(self):
        defaults = {screen: (PANEL_SIZE, None, None) for screen in LAYOUT_SCREENS}
        try:
            saved = json.loads(self.layouts_path.read_text())
            sizes = saved.get('sizes', {})
            names = saved.get('names', {})
            if not isinstance(names, dict):
                names = {}
            try:
                library = self.read_library()
            except OSError:
                library = {}
            layouts = {}
            for screen in defaults:
                size = validate_display_size(sizes.get(screen, PANEL_SIZE))
                layout = validate_layout(screen, saved.get(screen), size)
                # Older installations stored the layout alone. Recover its name if the match is unique.
                candidates = library.get(screen, {})
                if screen in names:
                    candidates = {key: entry for key, entry in candidates.items() if key == names[screen]}
                matches = []
                if layout is not None:
                    for name, entry in candidates.items():
                        try:
                            source, saved_layout = library_layout(screen, entry)
                            adapted = resize_layout(saved_layout, source, size)
                            if adapted != layout and source != size and saved_layout is not None:
                                # Earlier versions scaled the two axes independently across orientations.
                                adapted = [resize_layer(layer, source, size) for layer in saved_layout]
                            if adapted == layout:
                                matches.append((source, saved_layout, name))
                        except (KeyError, TypeError, ValueError):
                            continue
                layouts[screen] = matches[0] if len(matches) == 1 else (size, layout, None)
            return layouts
        except FileNotFoundError:
            pass
        except (AttributeError, TypeError, ValueError, OSError):
            print('Could not read the saved layouts. Using the built-in screens.', flush=True)
        return defaults

    @property
    def layouts(self):
        return self.layout_state[1]

    def layouts_at(self, size):
        return {screen: resize_layout(layout, source, size)
                for screen, (source, layout, _) in self._stored_layouts.items()}

    def active_layout(self, screen):
        _, layout, name = self._stored_layouts[screen]
        kind = 'saved' if name is not None else 'default' if layout is None else 'custom'
        return {'screen': screen, 'kind': kind, 'name': name}

    def require_display_size(self, expected):
        size = self.layout_state[0]
        if expected is not None and validate_display_size(expected) != size:
            raise ValueError('Display dimensions changed. Reopen the editor.')
        return size

    def save_layout(self, screen, layout, *, expected_size=None, name=None):
        with self.lock:
            size = self.require_display_size(expected_size)
            layout = validate_layout(screen, layout, size)
            selected = self._stored_layouts[screen][2] if layout == self.layouts[screen] else None
            source, stored_layout = size, layout
            if name is not None:
                name = layout_name(name)
                try:
                    library_size, library_content = library_layout(screen, self.read_library()[screen][name])
                    if layout == resize_layout(library_content, library_size, size):
                        selected = name
                        source, stored_layout = library_size, library_content
                except KeyError:
                    pass
            if layout != self.layouts[screen] or selected != self._stored_layouts[screen][2]:
                self._write_layout(screen, source, stored_layout, selected)
        return layout

    def apply_layout(self, screen, name):
        if screen not in LAYOUT_SCREENS:
            raise ValueError('Choose Dashboard or Playback.')
        with self.lock:
            if name is None:
                if self.layouts[screen] is not None or self._stored_layouts[screen][2] is not None:
                    self._write_layout(screen, self.layout_state[0], None, None)
                return
            name = layout_name(name)
            source, layout = library_layout(screen, self.read_library()[screen][name])
            if (source, layout, name) != self._stored_layouts[screen]:
                self._write_layout(screen, source, layout, name)

    def _write_layout(self, screen, size, layout, name):
        current_size, layouts = self.layout_state
        visible = resize_layout(layout, size, current_size)
        stored = {**self._stored_layouts, screen: (size, layout, name)}
        data = {key: value for key, (_, value, _) in stored.items()}
        data['sizes'] = {key: dimensions for key, (dimensions, _, _) in stored.items()}
        data['names'] = {key: selected for key, (_, _, selected) in stored.items()}
        write_private(self.layouts_path, json.dumps(data, ensure_ascii=False) + '\n')
        self._stored_layouts = stored
        self.layout_state = current_size, {**layouts, screen: visible}

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

    def get_layout_library(self, screen, name=None, *, details=False, size=None):
        if screen not in LAYOUT_SCREENS:
            raise ValueError('Choose Dashboard or Playback.')
        entries = self.read_library()[screen]
        if name is None:
            return library_listing(entries, details=details)
        entry = entries[layout_name(name)]
        size = self.layout_state[0] if size is None else size
        source, layout = library_layout(screen, entry)
        return {'layout': resize_layout(layout, source, size)}

    def edit_layout_library(self, screen, name, layout, *, delete=False, expected_size=None):
        if screen not in LAYOUT_SCREENS:
            raise ValueError('Choose Dashboard or Playback.')
        name = layout_name(name)
        with self.lock:
            size = self.require_display_size(expected_size)
            library = self.read_library()
            entries = library[screen]
            if delete:
                del entries[name]
                source, active, selected = self._stored_layouts[screen]
                if selected == name:
                    self._write_layout(screen, source, active, None)
            else:
                if name in entries:
                    raise ValueError('A saved layout already has that name.')
                if len(entries) >= MAX_SAVED_LAYOUTS:
                    raise ValueError(f'This screen already has {MAX_SAVED_LAYOUTS} saved layouts.')
                entries[name] = {'layout': validate_layout(screen, layout, size), 'size': size,
                                 'savedAt': datetime.now(timezone.utc).isoformat()}
            write_private(self.library_path, json.dumps(library, ensure_ascii=False) + '\n')
            return library_listing(entries, details=True)

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
                'redirectUri': REDIRECT_URI, 'ranges': SETTING_RANGES}

    def set_password_required(self, required):
        if type(required) is not bool:
            raise ValueError('Check the on/off settings.')
        with self.lock:
            if self.values['password_required'] != required:
                self.write_values({**self.values, 'password_required': required})

    def save(self, payload):
        with self.lock:
            values = validate_settings({
                **{key: self.values[key] for key in EXTRA_SETTINGS}, **payload,
                'password_required': self.values['password_required'],
            })
            size = display_size(values, self.rotation_override)
            layout_state = self.layout_state if size == self.layout_state[0] else (size, self.layouts_at(size))
            self.write_values(values)
            self.layout_state = layout_state

    def set_local_name(self, enabled, hostname=None):
        if type(enabled) is not bool:
            raise ValueError('Choose whether to use the local address.')
        with self.lock:
            name = self.values['local_hostname'] if hostname is None else validate_local_hostname(hostname)
            values = {**self.values, 'local_name': enabled, 'local_hostname': name}
            if values != self.values:
                self.write_values(values)
            return enabled, name

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
