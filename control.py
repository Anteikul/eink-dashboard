"""Local browser controls and a preview of the last completed panel update."""
import hmac
import ipaddress
import json
import re
import secrets
import struct
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs

from device_settings import find_places, write_private
from layout_editor import MAX_DIMENSION, MAX_DRAWINGS, MAX_WIDGETS, PANEL_SIZE, editor_schema, validate_layout
from photo_import import PHOTO_SIZE, PHOTO_UPLOAD_LIMIT, prepare_photo
from spotify_playback import SpotifyPlayback

THEMES = ('light', 'dark')
DISPLAY_MODES = ('auto', 'dashboard', 'playback')
LAYOUT_ROUTES = ('/api/layouts', '/api/layout-preview', '/api/layout-library')
MAX_BITMAP_BYTES = ((MAX_DIMENSION + 7) // 8) * MAX_DIMENSION
MAX_PHOTO_BITMAP_BYTES = ((PHOTO_SIZE + 7) // 8) * PHOTO_SIZE
MAX_LAYOUT_BYTES = (4 * ((MAX_BITMAP_BYTES + 2) // 3) * (MAX_DRAWINGS + MAX_WIDGETS)
                    + 4 * ((MAX_PHOTO_BITMAP_BYTES + 2) // 3) * MAX_WIDGETS + 128 * 1024)
PROTECTED_PAGES = ('/settings', '/editor')
SESSION_COOKIE = 'eink_session'
SESSION_AGE = 8 * 60 * 60
BAD_CODE = 'Check the device setup code.'
SESSION_TOKEN = re.compile(r'([0-9]{1,12})\.([0-9a-f]{32})\.([0-9a-f]{64})')


def session_signature(key, expires, nonce, code):
    return hmac.digest(key, f'{expires}.{nonce}.{code}'.encode(), 'sha256').hex()


def session_cookie(key, code):
    expires = int(time.time()) + SESSION_AGE
    nonce = secrets.token_hex(16)
    signature = session_signature(key, expires, nonce, code)
    return (f'{SESSION_COOKIE}={expires}.{nonce}.{signature}; '
            f'Path=/; Max-Age={SESSION_AGE}; HttpOnly; SameSite=Strict')


def valid_session(cookies, key, code):
    try:
        session = SimpleCookie(cookies).get(SESSION_COOKIE)
    except CookieError:
        return False
    match = SESSION_TOKEN.fullmatch(session.value) if session else None
    if not match:
        return False
    expires, nonce, signature = match.groups()
    return int(expires) > time.time() and hmac.compare_digest(
        signature, session_signature(key, expires, nonce, code))


def pack_row(row):
    padding = (-len(row)) % 8
    row = bytes(row) + bytes(padding)
    return bytes(
        sum(bit << (7 - index) for index, bit in enumerate(row[start:start+8]))
        for start in range(0, len(row), 8)
    )


def preview_png(pixels, width, height):
    def chunk(kind, content):
        return (struct.pack('>I', len(content)) + kind + content
                + struct.pack('>I', zlib.crc32(kind + content)))

    rows = b''.join(b'\x00' + pack_row(pixels[y:y+width]) for y in range(0, len(pixels), width))
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 1, 0, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(rows))
        + chunk(b'IEND', b'')
    )


class PanelState:
    def __init__(self, path):
        self.path = path
        self.mode_path = path.with_name('display-mode.txt')
        self.lock = threading.Lock()
        self.theme = self.read_choice(self.path, THEMES)
        self.mode = self.read_choice(self.mode_path, DISPLAY_MODES)
        self.applied_theme = None
        self.page = None
        self.frame = None
        self.revision = None
        self.track_url = None

    @staticmethod
    def read_choice(path, choices):
        try:
            value = path.read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            return choices[0]
        return value if value in choices else choices[0]

    def set_theme(self, theme):
        if theme not in THEMES:
            raise ValueError('Invalid theme')
        with self.lock:
            if theme != self.theme:
                write_private(self.path, theme + '\n')
                self.theme = theme

    def set_mode(self, mode):
        if mode not in DISPLAY_MODES:
            raise ValueError('Choose a display mode.')
        with self.lock:
            if mode != self.mode:
                write_private(self.mode_path, mode + '\n')
                self.mode = mode

    def publish(self, theme, frame, track_url=None, *, page='dashboard'):
        with self.lock:
            self.applied_theme = theme
            self.frame = frame
            self.revision = str(time.time_ns())
            self.track_url = track_url
            self.page = page

    def status(self):
        with self.lock:
            return {'theme': self.theme, 'appliedTheme': self.applied_theme,
                    'mode': self.mode, 'page': self.page, 'revision': self.revision, 'trackUrl': self.track_url}


def start_server(host, port, state, settings, reload_settings, *, wifi=None, layout_preview=None, spotify=None):
    assets = Path(__file__).with_name('web')
    routes = {
        '/': ('index.html', 'text/html; charset=utf-8'),
        '/editor': ('editor.html', 'text/html; charset=utf-8'),
        '/settings': ('settings.html', 'text/html; charset=utf-8'),
        '/unlock': ('unlock.html', 'text/html; charset=utf-8'),
        '/app.css': ('app.css', 'text/css; charset=utf-8'),
        '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
        '/setup.js': ('setup.js', 'text/javascript; charset=utf-8'),
        '/locale.js': ('locale.js', 'text/javascript; charset=utf-8'),
        '/editor.js': ('editor.js', 'text/javascript; charset=utf-8'),
        '/photo-crop.js': ('photo-crop.js', 'text/javascript; charset=utf-8'),
        '/unlock.js': ('unlock.js', 'text/javascript; charset=utf-8'),
    }
    if wifi is not None:
        routes = {
            '/': ('wifi.html', 'text/html; charset=utf-8'),
            '/app.css': ('app.css', 'text/css; charset=utf-8'),
            '/wifi.js': ('wifi.js', 'text/javascript; charset=utf-8'),
            '/locale.js': ('locale.js', 'text/javascript; charset=utf-8'),
        }
    subnet = ipaddress.IPv4Network(f'{host}/24', strict=False) if wifi is not None else None
    site = {url: (kind, (assets / filename).read_bytes())
            for url, (filename, kind) in routes.items()}
    admin_routes = {'/api/settings', '/api/setup-code', '/api/password-protection', '/api/local-name', '/api/places', '/api/spotify/start',
                    '/api/spotify/finish', '/api/spotify/disconnect', '/api/layouts', '/api/layout-preview',
                    '/api/layout-library', '/api/photo-import', '/api/spotify/check'}
    allowed_routes = {'/api/wifi'} if wifi is not None else admin_routes | {
        '/api/theme', '/api/display-mode', '/api/language', '/api/unlock',
    }
    photo_lock = threading.Lock()

    def panel_status():
        return {**state.status(), 'language': settings.values['language']}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            pass

        def reply(self, status, kind, body, headers=()):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
            for name, value in headers:
                self.send_header(name, value)
            try:
                self.end_headers()
                self.wfile.write(body)
            except ConnectionError:
                self.close_connection = True

        def json(self, status, body, headers=()):
            self.reply(status, 'application/json', json.dumps(body).encode(), headers)

        def setup_credentials(self):
            code = settings.code
            if not settings.values['password_required']:
                return code
            supplied = self.headers.get('X-Setup-Code', '')
            if supplied and settings.authorized(supplied):
                return supplied
            if valid_session(self.headers.get('Cookie', ''), settings.session_key, code):
                return code
            return None

        def setup_access(self):
            if self.setup_credentials() is not None:
                return True
            self.json(403, {'error': BAD_CODE})
            return False

        def layout_png(self, screen, layout, size, *, geometry=None):
            if layout_preview is None:
                from dashboard import render_layout_preview
            else:
                render_layout_preview = layout_preview
            preferences = settings.values
            options = {'layers': True, 'geometry': geometry} if geometry is not None else {}
            if size != PANEL_SIZE:
                options['size'] = size
            if not preferences['weather_enabled']:
                options['weather_enabled'] = False
            return render_layout_preview(screen, layout, state.theme, preferences['language'],
                                         preferences['units'], **options)

        def request_authority(self):
            request_host = self.headers.get('Host', '').lower()
            if request_host in ip_hosts:
                return authority
            config = settings.values
            if wifi is None and config['local_name']:
                hostname = config['local_hostname']
                explicit = f'{hostname}:{server.server_port}'
                local_authority = hostname if server.server_port == 80 else explicit
                if request_host in (local_authority, explicit):
                    return local_authority
            return None

        def do_GET(self):
            if self.request_authority() is None:
                self.send_error(400)
                return
            if subnet is not None and ipaddress.IPv4Address(self.client_address[0]) not in subnet:
                self.send_error(403)
                return
            path, _, query = self.path.partition('?')
            if path in site:
                if path in PROTECTED_PAGES and self.setup_credentials() is None:
                    self.reply(302, 'text/plain', b'', [('Location', f'/unlock?next={path[1:]}')])
                elif path == '/unlock' and not settings.values['password_required']:
                    next_page = parse_qs(query).get('next') == ['editor']
                    self.reply(302, 'text/plain', b'', [('Location', '/editor' if next_page else '/settings')])
                else:
                    self.reply(200, *site[path])
            elif wifi is not None:
                if path == '/api/wifi':
                    self.json(200, {'status': wifi.status, 'language': settings.values['language']})
                else:
                    self.send_error(404)
            elif path == '/api/state':
                self.json(200, panel_status())
            elif path == '/api/settings':
                if self.setup_access():
                    self.json(200, settings.status())
            elif path == '/api/layouts':
                if self.setup_access():
                    size, layouts = settings.layout_state
                    self.json(200, {**editor_schema(size), 'layouts': layouts})
            elif path == '/api/layout-library':
                if self.setup_access():
                    params = parse_qs(query, keep_blank_values=True)
                    screen = params.get('screen', [''])[0]
                    name = params.get('name', [None])[0]
                    try:
                        expected = [int(params[key][0]) for key in ('width', 'height')] if (
                            'width' in params and 'height' in params) else None
                        size = settings.require_display_size(expected)
                        if params.get('thumbnail') == ['1']:
                            if screen not in ('dashboard', 'playback') or name is None:
                                raise ValueError('Invalid preview.')
                            layout = settings.get_layout_library(screen, name, size=size)['layout'] if name else None
                            if layout is None:
                                layout = editor_schema(size)['defaults'][screen]
                            self.reply(200, 'image/png', self.layout_png(screen, layout, size))
                        else:
                            self.json(200, settings.get_layout_library(
                                screen, name, details=params.get('details') == ['1'], size=size))
                    except KeyError:
                        self.json(404, {'error': 'That saved layout no longer exists.'})
                    except ValueError as error:
                        self.json(400, {'error': str(error)})
                    except OSError:
                        self.json(500, {'error': 'Could not read the layout library.'})
            elif path == '/screen.png' and (frame := state.frame) is not None:
                self.reply(200, 'image/png', frame)
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path not in allowed_routes:
                self.send_error(404)
                return
            request_authority = self.request_authority()
            if (request_authority is None
                    or self.headers.get('Origin') != f'http://{request_authority}'
                    or (subnet is not None and ipaddress.IPv4Address(self.client_address[0]) not in subnet)):
                self.json(403, {'error': 'Open the dashboard directly on the Pi.'})
                return
            code = None
            if self.path in admin_routes:
                code = self.setup_credentials()
                if code is None:
                    self.json(403, {'error': BAD_CODE})
                    return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.path == '/api/photo-import':
                    if not 0 < size <= PHOTO_UPLOAD_LIMIT or self.headers.get_content_type() != 'application/octet-stream':
                        raise ValueError('Choose an image file up to 16 MB.')
                    with photo_lock:
                        photo = prepare_photo(self.rfile.read(size))
                    self.json(200, photo)
                    return
                limit = MAX_LAYOUT_BYTES if self.path in LAYOUT_ROUTES else 8192
                if not 0 < size <= limit or self.headers.get_content_type() != 'application/json':
                    raise ValueError('Invalid request.')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('Invalid request.')
                if wifi is not None:
                    if wifi.submit(payload['ssid'], payload['password']):
                        self.json(202, {'status': 'joining'})
                    else:
                        self.json(409, {'error': 'Wi-Fi setup is busy or the hotspot has already closed.'})
                    return
                if self.path == '/api/unlock':
                    submitted = payload.get('code')
                    if not isinstance(submitted, str) or not settings.authorized(submitted):
                        self.json(403, {'error': BAD_CODE})
                    else:
                        cookie = session_cookie(settings.session_key, submitted)
                        self.json(200, {}, [('Set-Cookie', cookie)])
                    return
                if self.path == '/api/theme':
                    state.set_theme(payload.get('theme'))
                    self.json(200, panel_status())
                    return
                if self.path == '/api/display-mode':
                    state.set_mode(payload.get('mode'))
                    self.json(200, panel_status())
                    return
                if self.path == '/api/language':
                    settings.set_language(payload['language'])
                    self.json(200, panel_status())
                    return
                if self.path == '/api/local-name':
                    enabled, hostname = settings.set_local_name(payload['enabled'], payload.get('hostname'))
                    self.json(200, {'enabled': enabled, 'hostname': hostname, 'ipUrl': f'http://{authority}'})
                    return
                if self.path == '/api/setup-code':
                    if settings.change_code(code, payload['newCode']):
                        cookie = session_cookie(settings.session_key, payload['newCode'])
                        self.json(200, {}, [('Set-Cookie', cookie)])
                    else:
                        self.json(403, {'error': BAD_CODE})
                    return
                if self.path == '/api/password-protection':
                    required = payload.get('required')
                    settings.set_password_required(required)
                    headers = [('Set-Cookie', session_cookie(settings.session_key, settings.code))] if required else ()
                    self.json(200, {'required': required}, headers)
                    return
                if self.path == '/api/layouts':
                    screen = payload['screen']
                    layout = settings.save_layout(screen, payload['layout'], expected_size=payload.get('displaySize'))
                    self.json(200, {'screen': screen, 'layout': layout})
                    return
                if self.path == '/api/layout-library':
                    screen, name = payload['screen'], payload['name']
                    delete = payload.get('delete', False)
                    if type(delete) is not bool:
                        raise ValueError('Invalid request.')
                    layout = None if delete else payload['layout']
                    try:
                        self.json(200, settings.edit_layout_library(screen, name, layout, delete=delete,
                                                                    expected_size=payload.get('displaySize')))
                    except KeyError:
                        self.json(404, {'error': 'That saved layout no longer exists.'})
                    return
                if self.path == '/api/layout-preview':
                    screen = payload['screen']
                    size = settings.require_display_size(payload.get('displaySize'))
                    layout = validate_layout(screen, payload['layout'], size)
                    layers = payload.get('layers', False)
                    if type(layers) is not bool or (layers and layout is None):
                        raise ValueError('Invalid preview.')
                    geometry = [] if layers else None
                    png = self.layout_png(screen, layout, size, geometry=geometry)
                    headers = [('X-Eink-Layer-Bounds', json.dumps(geometry))] if layers else ()
                    self.reply(200, 'image/png', png, headers)
                    return
                if self.path == '/api/places':
                    self.json(200, {'places': find_places(payload['name'], settings.values['language'])})
                    return
                if self.path == '/api/spotify/start':
                    self.json(200, {'url': settings.authorize(payload['clientId'])})
                    return
                if self.path == '/api/spotify/check':
                    if not settings.credentials.is_file():
                        self.json(409, {'error': 'Connect Spotify first.'})
                        return
                    playback = spotify if spotify is not None else SpotifyPlayback(settings.credentials, settings.lock)
                    playback.read()
                    self.json(200, {'verified': True})
                    return
                if self.path == '/api/settings':
                    settings.save(payload)
                elif self.path == '/api/spotify/finish':
                    settings.finish(payload['callback'])
                else:
                    settings.disconnect()
            except HTTPError as error:
                self.json(502, {'error': f'The upstream service returned HTTP {error.code}. Try again.'})
                return
            except (KeyError, TypeError, json.JSONDecodeError):
                self.json(400, {'error': 'Check the values you entered.'})
                return
            except ValueError as error:
                self.json(400, {'error': str(error)})
                return
            except OSError:
                self.json(502, {'error': 'Could not apply the change. Try again.'})
                return
            try:
                self.json(200, settings.status())
            finally:
                reload_settings()

    server = ThreadingHTTPServer((host, port), Handler)
    explicit_authority = f'{host}:{server.server_port}'
    authority = host if server.server_port == 80 else explicit_authority
    ip_hosts = {authority, explicit_authority}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'Control page: http://{authority}', flush=True)
    return server
