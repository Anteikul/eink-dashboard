import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image

from control import PanelState, start_server
from device_settings import DeviceSettings


with TemporaryDirectory() as folder:
    root = Path(folder)
    settings = DeviceSettings(root)
    state = PanelState(root / 'theme.txt')
    server = start_server('127.0.0.1', 0, state, settings, lambda: None)
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, payload=None, code=None):
        headers = {'X-Setup-Code': settings.code if code is None else code}
        body = None
        if payload is not None:
            headers.update({'Content-Type': 'application/json', 'Origin': base})
            body = json.dumps(payload).encode()
        try:
            with urlopen(Request(base + path, data=body, headers=headers), timeout=5) as reply:
                return reply.status, reply.read()
        except HTTPError as error:
            return error.code, error.read()

    try:
        status, page = request('/editor')
        assert status == 200 and b'<main id="layout-editor">' in page
        status, home = request('/')
        assert status == 200 and b'href="/editor"' in home and b'id="layout-editor"' not in home
        assert request('/api/layouts', code='wrong')[0] == 403
        status, data = request('/api/layouts')
        assert status == 200
        schema = json.loads(data)
        assert schema['layouts'] == {'dashboard': None, 'playback': None}
        assert (schema['width'], schema['height']) == (250, 122)
        for page in schema['layouts']:
            for layout in (None, schema['defaults'][page]):
                status, png = request('/api/layout-preview', {'screen': page, 'layout': layout})
                assert status == 200
                with Image.open(io.BytesIO(png)) as preview:
                    assert preview.mode == '1' and preview.size == (250, 122)
                    assert preview.getextrema() == (0, 255)
            for option in schema['widgets'][page]:
                for variant in option['variants']:
                    widget = {**option['template'], 'variant': variant['value']}
                    status, png = request('/api/layout-preview', {'screen': page, 'layout': [widget]})
                    assert status == 200, (page, option['type'], variant, png)
                    assert png.startswith(b'\x89PNG\r\n\x1a\n')
        assert settings.layouts['dashboard'] is None and state.revision is None

        stride = (schema['width'] + 7) // 8
        bitmap = bytearray(stride * schema['height'])
        bitmap[0] = 0x80
        bitmap[-1] = 0x40
        drawing = {'type': 'drawing', 'bitmap': base64.b64encode(bitmap).decode()}
        status, png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': [drawing]})
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.getpixel((0, 0)) == preview.getpixel((249, 121)) == 0
            assert preview.getpixel((1, 0)) == 255
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [drawing, drawing]})[0] == 400
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [{**drawing, 'bitmap': 'AA=='}]})[0] == 400
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [drawing]})[0] == 200
        assert DeviceSettings(root).layouts == {'dashboard': [drawing], 'playback': None}
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': None})[0] == 200

        # A drawing can sit above or below an opaque cover, including after a reload.
        cover = next(item['template'] for item in schema['widgets']['playback'] if item['type'] == 'cover')
        cover = {**cover, 'x': 0, 'y': 0}
        corner_only = bytearray(stride * schema['height'])
        corner_only[0] = 0x80
        corner = {'type': 'drawing', 'bitmap': base64.b64encode(corner_only).decode()}
        for stack, expected in (([corner, cover], 0), ([cover, corner], 255)):
            status, data = request('/api/layouts', {'screen': 'playback', 'layout': stack})
            assert status == 200 and json.loads(data)['layout'] == stack
            assert DeviceSettings(root).layouts['playback'] == stack
            # The cover corner is black. Use dark mode to make the overlaid stroke white.
            state.set_theme('dark')
            status, png = request('/api/layout-preview', {'screen': 'playback', 'layout': stack})
            assert status == 200
            with Image.open(io.BytesIO(png)) as preview:
                assert preview.getpixel((0, 0)) == expected
        state.set_theme('light')
        assert request('/api/layouts', {'screen': 'playback', 'layout': None})[0] == 200

        layout = schema['defaults']['playback']
        status, png = request('/api/layout-preview', {'screen': 'playback', 'layout': layout, 'layers': True})
        assert status == 200
        with Image.open(io.BytesIO(png)) as atlas:
            assert atlas.mode == 'RGBA' and atlas.size == (250, 1 + 122 * len(layout))
            background = Image.new('RGBA', (250, 122), atlas.getpixel((0, 0)))
            for index, widget in enumerate(layout):
                y = 1 + 122 * index
                layer = atlas.crop((0, y, widget['w'], y + widget['h']))
                background.alpha_composite(layer, (widget['x'], widget['y']))
        status, png = request('/api/layout-preview', {'screen': 'playback', 'layout': layout})
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert background.convert('1').tobytes() == preview.tobytes()

        text = next(option['template'] for option in schema['widgets']['dashboard'] if option['type'] == 'text')
        custom = [{**text, 'text': 'Dobrý den <3'}]
        assert request('/api/layouts', {'screen': 'other', 'layout': custom})[0] == 400
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [{**text, 'x': 250}]})[0] == 400
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': custom * 19})[0] == 400
        full = [{**text, 'text': '🎵' * 120}] * 18
        assert request('/api/layout-preview', {'screen': 'dashboard', 'layout': full})[0] == 200
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': custom}, code='wrong')[0] == 403
        status, png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': custom})
        assert status == 200 and settings.layouts['dashboard'] is None
        status, saved = request('/api/layouts', {'screen': 'dashboard', 'layout': custom})
        assert status == 200 and json.loads(saved)['layout'] == custom
        assert request('/api/layouts', {'screen': 'playback', 'layout': []})[0] == 200
        assert DeviceSettings(root).layouts == {'dashboard': custom, 'playback': []}
        assert (root / '.layouts.json').stat().st_mode & 0o777 == 0o600
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': None})[0] == 200
        assert DeviceSettings(root).layouts == {'dashboard': None, 'playback': []}
    finally:
        server.shutdown()
        server.server_close()

print('Layout preview, validation, protected editing, independent pages and reset passed.')
