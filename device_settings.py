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
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from spotify_playback import TOKEN_URL

DEFAULTS = {
    'location': 'Praha', 'latitude': 50.0755, 'longitude': 14.4378,
    'timezone': 'Europe/Prague', 'units': 'celsius', 'rotation': 180,
}
REDIRECT_URI = 'http://127.0.0.1:8765/callback'
SPOTIFY_SCOPE = 'user-read-currently-playing user-read-playback-state'


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
        raise ValueError('Zadej název místa.')
    result['location'] = result['location'].strip()
    for key, limit in (('latitude', 90), ('longitude', 180)):
        value = float(result[key])
        if not math.isfinite(value) or abs(value) > limit:
            raise ValueError('Zkontroluj zeměpisné souřadnice.')
        result[key] = value
    try:
        ZoneInfo(result['timezone'])
    except (ValueError, ZoneInfoNotFoundError, TypeError) as error:
        raise ValueError('Zadej platnou časovou zónu, třeba Europe/Prague.') from error
    if (result['units'] not in ('celsius', 'fahrenheit')
            or type(result['rotation']) is not int or result['rotation'] not in (0, 180)):
        raise ValueError('Zkontroluj jednotky a otočení.')
    return result


class DeviceSettings:
    def __init__(self, directory):
        self.path = directory / '.settings.json'
        self.code_path = directory / '.setup-code'
        self.credentials = directory / '.spotify.json'
        self.lock = threading.Lock()
        self.pending = None
        self.values = validate_settings({**DEFAULTS, **json.loads(self.path.read_text())}) if self.path.is_file() else DEFAULTS.copy()
        if not self.code_path.exists():
            write_private(self.code_path, secrets.token_urlsafe(18) + '\n')
        self.code = self.code_path.read_text().strip()

    def authorized(self, code):
        return hmac.compare_digest(self.code.encode(), code.encode())

    def status(self):
        return {'settings': self.values, 'spotifyConnected': self.credentials.is_file(),
                'redirectUri': REDIRECT_URI}

    def save(self, payload):
        values = validate_settings(payload)
        with self.lock:
            write_private(self.path, json.dumps(values, ensure_ascii=False) + '\n')
            self.values = values

    def authorize(self, client_id):
        if not re.fullmatch(r'[a-fA-F0-9]{32}', client_id):
            raise ValueError('Zadej Client ID z aplikace Spotify.')
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
            raise ValueError('Vlož adresu, na kterou tě Spotify přesměrovalo.')
        parts = urlsplit(callback.strip())
        if (parts.scheme, parts.netloc, parts.path) != ('http', '127.0.0.1:8765', '/callback'):
            raise ValueError('Vlož celou adresu začínající http://127.0.0.1:8765/callback.')
        query = parse_qs(parts.query)
        with self.lock:
            if not self.pending or time.monotonic() >= self.pending[3]:
                raise ValueError('Přihlášení vypršelo. Začni znovu.')
            state, verifier, client_id, _ = self.pending
            if query.get('state') != [state]:
                raise ValueError('Adresa nepatří k tomuto přihlášení.')
            self.pending = None
            if len(query.get('code', [])) != 1:
                raise ValueError('Spotify přístup neudělilo. Začni znovu.')
            form = urlencode({
                'grant_type': 'authorization_code', 'code': query['code'][0],
                'redirect_uri': REDIRECT_URI, 'client_id': client_id, 'code_verifier': verifier,
            })
            request = Request(TOKEN_URL, data=form.encode(),
                              headers={'Content-Type': 'application/x-www-form-urlencoded'})
            with urlopen(request, timeout=8) as response:
                token = json.load(response)
            if not set(SPOTIFY_SCOPE.split()) <= set(token.get('scope', '').split()):
                raise ValueError('Spotify neudělilo oprávnění ke čtení přehrávání a fronty.')
            write_private(self.credentials, json.dumps({
                'client_id': client_id, 'refresh_token': token['refresh_token'],
            }))

    def disconnect(self):
        with self.lock:
            self.pending = None
            self.credentials.unlink(missing_ok=True)


def find_places(name):
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 80:
        raise ValueError('Zadej alespoň dva znaky názvu místa.')
    query = urlencode({'name': name.strip(), 'count': 8, 'language': 'cs'})
    with urlopen('https://geocoding-api.open-meteo.com/v1/search?' + query, timeout=6) as response:
        matches = json.load(response).get('results', [])
    return [{
        'location': item['name'], 'latitude': item['latitude'], 'longitude': item['longitude'],
        'timezone': item['timezone'],
        'label': ', '.join(dict.fromkeys(filter(None, (item['name'], item.get('admin1'), item.get('country'))))),
    } for item in matches if item.get('timezone')]
