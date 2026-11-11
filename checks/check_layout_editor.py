import base64
import io
import json
from datetime import datetime, timezone
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

        clock = schema['defaults']['dashboard'][0]
        regular_clock = request('/api/layout-preview', {'screen': 'dashboard', 'layout': [clock]})
        bold_clock = request('/api/layout-preview', {'screen': 'dashboard',
                             'layout': [{**clock, 'font': 'mono-bold'}]})
        assert regular_clock[0] == bold_clock[0] == 200 and regular_clock[1] != bold_clock[1]

        divider = next(item['template'] for item in schema['widgets']['dashboard'] if item['type'] == 'divider')
        divider = {**divider, 'x': 10, 'y': 30, 'w': 8, 'h': 1,
                   'mask': {'w': 8, 'h': 1, 'bitmap': 'IA=='}}
        status, png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': [divider]})
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.getpixel((11, 30)) == preview.getpixel((13, 30)) == 0
            assert preview.getpixel((12, 30)) == 255
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [divider]})[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [divider]
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': None})[0] == 200
        for variant, w, h in (('horizontal', 20, 3), ('vertical', 3, 20)):
            resized = {key: value for key, value in divider.items() if key != 'mask'}
            resized.update(variant=variant, w=w, h=h, thickness=3)
            status, png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': [resized]})
            assert status == 200
            with Image.open(io.BytesIO(png)) as preview:
                assert preview.getpixel((10, 30)) == preview.getpixel((9 + w, 29 + h)) == 0
                assert preview.getpixel((10 + w, 30)) == preview.getpixel((10, 30 + h)) == 255

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
        dot = {'type': 'drawing', 'x': 12, 'y': 24, 'w': 1, 'h': 1, 'bitmap': 'gA=='}
        second_dot = {**dot, 'x': 19, 'y': 40}
        strokes = [dot, second_dot]
        status, png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': strokes})
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.getpixel((12, 24)) == preview.getpixel((19, 40)) == 0
            assert preview.getpixel((12, 25)) == 255
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': strokes})[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == strokes
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [{**dot, 'x': 250}]})[0] == 400
        max_drawings = schema['maxDrawings']
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [dot] * (max_drawings + 1)})[0] == 400
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [{**drawing, 'bitmap': 'AA=='}]})[0] == 400
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [drawing] * max_drawings})[0] == 200
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
        erased_cover = {**cover, 'mask': {'w': 1, 'h': 1, 'bitmap': 'gA=='}}
        status, png = request('/api/layout-preview', {'screen': 'playback', 'layout': [corner, erased_cover]})
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.getpixel((0, 0)) == 255
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

        library = '/api/layout-library'
        listing = library + '?screen=dashboard'
        entry = listing + '&name=Moje%20plocha'
        draft = {'screen': 'dashboard', 'name': 'Moje plocha', 'layout': [*custom, drawing]}
        assert request(listing, code='wrong')[0] == 403
        assert request(library, draft, code='wrong')[0] == 403
        assert request(listing) == (200, b'{"names": []}')
        assert request(library, {**draft, 'name': ' '})[0] == 400
        assert request(library, {**draft, 'layout': [{**text, 'x': 250}]})[0] == 400
        status, payload = request(library, draft)
        assert status == 200
        metadata = json.loads(payload)['entries'][0]
        assert metadata['name'] == 'Moje plocha' and metadata['layers'] == 2
        assert 0 <= (datetime.now(timezone.utc) - datetime.fromisoformat(metadata['savedAt'])).total_seconds() < 10
        assert request(library, {**draft, 'layout': []})[0] == 400
        assert json.loads(request(entry)[1])['layout'] == draft['layout']
        assert json.loads(request(listing)[1])['names'] == ['Moje plocha']
        assert json.loads(request(library + '?screen=playback')[1])['names'] == []
        assert DeviceSettings(root).get_layout_library('dashboard', 'Moje plocha')['layout'] == draft['layout']
        assert json.loads(request(listing + '&details=1')[1])['entries'] == [metadata]
        assert request(entry + '&thumbnail=1', code='wrong')[0] == 403
        assert request(entry + '&thumbnail=1') == request(
            '/api/layout-preview', {'screen': 'dashboard', 'layout': draft['layout']})
        assert request(listing + '&name=&thumbnail=1') == request(
            '/api/layout-preview', {'screen': 'dashboard', 'layout': schema['defaults']['dashboard']})
        assert (root / '.layout-library.json').stat().st_mode & 0o777 == 0o600
        assert settings.layouts == {'dashboard': None, 'playback': []}
        delete = {'screen': 'dashboard', 'name': 'Moje plocha', 'delete': True}
        assert request(library, delete)[0] == 200
        assert request(entry)[0] == 404
        assert request(listing) == (200, b'{"names": []}')
        settings.library_path.write_text(json.dumps({'dashboard': {'Starší': custom}, 'playback': {}}))
        assert json.loads(request(listing + '&details=1')[1])['entries'] == [
            {'name': 'Starší', 'savedAt': None, 'layers': 1}]
        assert settings.get_layout_library('dashboard', 'Starší')['layout'] == custom
    finally:
        server.shutdown()
        server.server_close()

print('Layout preview, validation, protected editing, independent pages and reset passed.')
