"""Local browser controls and a preview of the last completed panel update."""
import ipaddress
import json
import os
import struct
import tempfile
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs

from device_settings import find_places
from layout_editor import editor_schema, validate_layout
from local_name import HOSTNAME

THEMES = ('light', 'dark')


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
        self.lock = threading.Lock()
        try:
            theme = path.read_text(encoding='utf-8').strip()
        except FileNotFoundError:
            theme = 'light'
        self.theme = theme if theme in THEMES else 'light'
        self.applied_theme = None
        self.frame = None
        self.revision = None
        self.track_url = None

    def set_theme(self, theme):
        if theme not in THEMES:
            raise ValueError('Invalid theme')
        with self.lock:
            if theme != self.theme:
                with tempfile.NamedTemporaryFile(
                    mode='w', encoding='utf-8', dir=self.path.parent, delete=False
                ) as staged:
                    temporary = Path(staged.name)
                    try:
                        staged.write(theme + '\n')
                        staged.flush()
                        os.replace(temporary, self.path)
                    finally:
                        temporary.unlink(missing_ok=True)
                self.theme = theme

    def publish(self, theme, frame, track_url=None):
        with self.lock:
            self.applied_theme = theme
            self.frame = frame
            self.revision = str(time.time_ns())
            self.track_url = track_url

    def status(self):
        with self.lock:
            return {'theme': self.theme, 'appliedTheme': self.applied_theme,
                    'revision': self.revision, 'trackUrl': self.track_url}


def start_server(host, port, state, settings, reload_settings, *, wifi=None, layout_preview=None):
    assets = Path(__file__).with_name('web')
    routes = {
        '/': ('index.html', 'text/html; charset=utf-8'),
        '/editor': ('editor.html', 'text/html; charset=utf-8'),
        '/app.css': ('app.css', 'text/css; charset=utf-8'),
        '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
        '/setup.js': ('setup.js', 'text/javascript; charset=utf-8'),
        '/locale.js': ('locale.js', 'text/javascript; charset=utf-8'),
        '/editor.js': ('editor.js', 'text/javascript; charset=utf-8'),
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
    admin_routes = {'/api/settings', '/api/setup-code', '/api/local-name', '/api/places', '/api/spotify/start',
                    '/api/spotify/finish', '/api/spotify/disconnect', '/api/layouts', '/api/layout-preview',
                    '/api/layout-library'}
    allowed_routes = {'/api/wifi'} if wifi is not None else admin_routes | {'/api/theme', '/api/language'}

    def panel_status():
        return {**state.status(), 'language': settings.values['language']}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, format, *args):
            pass

        def reply(self, status, kind, body):
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, body):
            self.reply(status, 'application/json', json.dumps(body).encode())

        def setup_access(self):
            if settings.authorized(self.headers.get('X-Setup-Code', '')):
                return True
            self.json(403, {'error': 'Check the device setup code.'})
            return False

        def request_authority(self):
            request_host = self.headers.get('Host', '').lower()
            if request_host in ip_hosts:
                return authority
            if wifi is None and settings.values['local_name'] and request_host in local_hosts:
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
                    self.json(200, {**editor_schema(), 'layouts': settings.layouts})
            elif path == '/api/layout-library':
                if self.setup_access():
                    params = parse_qs(query, keep_blank_values=True)
                    screen = params.get('screen', [''])[0]
                    name = params.get('name', [None])[0]
                    try:
                        self.json(200, settings.get_layout_library(screen, name))
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
            if self.path in admin_routes and not self.setup_access():
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                limit = 576 * 1024 if self.path in ('/api/layouts', '/api/layout-preview', '/api/layout-library') else 8192
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
                if self.path == '/api/theme':
                    if payload.get('theme') not in THEMES:
                        raise ValueError('Invalid theme.')
                    state.set_theme(payload['theme'])
                    self.json(200, panel_status())
                    return
                if self.path == '/api/language':
                    settings.set_language(payload['language'])
                    self.json(200, panel_status())
                    return
                if self.path == '/api/local-name':
                    settings.set_local_name(payload['enabled'])
                    self.json(200, {'enabled': settings.values['local_name'], 'ipUrl': f'http://{authority}'})
                    return
                if self.path == '/api/setup-code':
                    if settings.change_code(self.headers.get('X-Setup-Code', ''), payload['newCode']):
                        self.json(200, {})
                    else:
                        self.json(403, {'error': 'Check the device setup code.'})
                    return
                if self.path == '/api/layouts':
                    screen = payload['screen']
                    layout = settings.save_layout(screen, payload['layout'])
                    self.json(200, {'screen': screen, 'layout': layout})
                    return
                if self.path == '/api/layout-library':
                    screen, name = payload['screen'], payload['name']
                    delete = payload.get('delete', False)
                    if type(delete) is not bool:
                        raise ValueError('Invalid request.')
                    layout = None if delete else payload['layout']
                    try:
                        self.json(200, settings.edit_layout_library(screen, name, layout, delete=delete))
                    except KeyError:
                        self.json(404, {'error': 'That saved layout no longer exists.'})
                    return
                if self.path == '/api/layout-preview':
                    screen = payload['screen']
                    layout = validate_layout(screen, payload['layout'])
                    layers = payload.get('layers', False)
                    if type(layers) is not bool or (layers and layout is None):
                        raise ValueError('Invalid preview.')
                    if layout_preview is None:
                        from dashboard import render_layout_preview
                    else:
                        render_layout_preview = layout_preview
                    preferences = settings.values
                    options = {'layers': True} if layers else {}
                    png = render_layout_preview(screen, layout, state.theme, preferences['language'],
                                                preferences['units'], **options)
                    self.reply(200, 'image/png', png)
                    return
                if self.path == '/api/places':
                    self.json(200, {'places': find_places(payload['name'], settings.values['language'])})
                    return
                if self.path == '/api/spotify/start':
                    self.json(200, {'url': settings.authorize(payload['clientId'])})
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
    explicit_local = f'{HOSTNAME}:{server.server_port}'
    local_authority = HOSTNAME if server.server_port == 80 else explicit_local
    local_hosts = {local_authority, explicit_local}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'Control page: http://{authority}', flush=True)
    return server
