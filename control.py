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

from device_settings import find_places

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


def start_server(host, port, state, settings, reload_settings, *, wifi=None):
    assets = Path(__file__).with_name('web')
    routes = {
        '/': ('index.html', 'text/html; charset=utf-8'),
        '/app.css': ('app.css', 'text/css; charset=utf-8'),
        '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
        '/setup.js': ('setup.js', 'text/javascript; charset=utf-8'),
    }
    if wifi is not None:
        routes = {
            '/': ('wifi.html', 'text/html; charset=utf-8'),
            '/app.css': ('app.css', 'text/css; charset=utf-8'),
            '/wifi.js': ('wifi.js', 'text/javascript; charset=utf-8'),
        }
    subnet = ipaddress.IPv4Network(f'{host}/24', strict=False) if wifi is not None else None
    site = {url: (kind, (assets / filename).read_bytes())
            for url, (filename, kind) in routes.items()}
    admin_routes = {'/api/settings', '/api/places', '/api/spotify/start',
                    '/api/spotify/finish', '/api/spotify/disconnect'}
    allowed_routes = {'/api/wifi'} if wifi is not None else admin_routes | {'/api/theme'}

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
                             "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def json(self, status, body):
            self.reply(status, 'application/json', json.dumps(body).encode())

        def setup_access(self):
            if settings.authorized(self.headers.get('X-Setup-Code', '')):
                return True
            self.json(403, {'error': 'Check the setup code printed by the installer.'})
            return False

        def do_GET(self):
            if self.headers.get('Host') not in accepted_hosts:
                self.send_error(400)
                return
            if subnet is not None and ipaddress.IPv4Address(self.client_address[0]) not in subnet:
                self.send_error(403)
                return
            path = self.path.partition('?')[0]
            if path in site:
                self.reply(200, *site[path])
            elif wifi is not None:
                if path == '/api/wifi':
                    self.json(200, {'status': wifi.status})
                else:
                    self.send_error(404)
            elif path == '/api/state':
                self.json(200, state.status())
            elif path == '/api/settings':
                if self.setup_access():
                    self.json(200, settings.status())
            elif path == '/screen.png' and (frame := state.frame) is not None:
                self.reply(200, 'image/png', frame)
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path not in allowed_routes:
                self.send_error(404)
                return
            if (self.headers.get('Host') not in accepted_hosts
                    or self.headers.get('Origin') != f'http://{authority}'
                    or (subnet is not None and ipaddress.IPv4Address(self.client_address[0]) not in subnet)):
                self.json(403, {'error': 'Open the dashboard directly on the Pi.'})
                return
            if self.path in admin_routes and not self.setup_access():
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192 or self.headers.get_content_type() != 'application/json':
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
                    self.json(200, state.status())
                    return
                if self.path == '/api/places':
                    self.json(200, {'places': find_places(payload['name'])})
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
    accepted_hosts = {authority, explicit_authority}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f'Control page: http://{authority}', flush=True)
    return server
