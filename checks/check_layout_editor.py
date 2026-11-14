import base64
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageOps

from control import PanelState, start_server
from dashboard import fit_panel, pack, render_layout_preview
from device_settings import DeviceSettings
from layout_editor import clock_has_seconds, content_key, format_clock, format_date, render_custom, resize_layer


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

    def import_photo(data, code=None):
        headers = {'X-Setup-Code': settings.code if code is None else code,
                   'Content-Type': 'application/octet-stream', 'Origin': base}
        try:
            with urlopen(Request(base + '/api/photo-import', data=data, headers=headers), timeout=5) as reply:
                return reply.status, json.load(reply)
        except HTTPError as error:
            return error.code, json.load(error)

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
        assert schema['panel'] == {'rotation': 180, 'width': 250, 'height': 122, 'bounds': [0, 0, 250, 122]}
        assert json.loads(request('/api/state', code='')[1])['activeLayout'] == {
            'screen': 'dashboard', 'kind': 'default', 'name': None}
        assert json.loads(request('/api/state', code='')[1])['selectedLayouts'] == {
            page: {'screen': page, 'kind': 'default', 'name': None} for page in ('dashboard', 'playback')}
        source = Image.new('RGB', (16, 8), 'black')
        ImageDraw.Draw(source).rectangle((8, 0, 15, 7), fill='white')
        for format in ('JPEG', 'PNG', 'GIF', 'BMP', 'TIFF'):
            with io.BytesIO() as image:
                source.save(image, format=format)
                status, photo = import_photo(image.getvalue())
                assert status == 200 and (photo['w'], photo['h']) == (16, 8)
        assert import_photo(b'not an image')[0] == 400
        assert import_photo(b'not an image', code='wrong')[0] == 403
        photo_option = next(item for item in schema['widgets']['dashboard'] if item['type'] == 'photo')
        tones = Image.new('L', (120, 80))
        ImageDraw.Draw(tones).rectangle((0, 0, 59, 79), fill=140)
        ImageDraw.Draw(tones).rectangle((60, 0, 119, 79), fill=200)
        with io.BytesIO() as image:
            tones.save(image, format='PNG')
            status, gray_photo = import_photo(image.getvalue())
        assert status == 200 and base64.b64decode(gray_photo.get('gray', '')) == tones.tobytes()
        gray_widget = {**photo_option['template'], 'x': 4, 'y': 8, 'w': 60, 'h': 40,
                       'photo': gray_photo, 'crop': [0, 0, 60, 80],
                       'placement': {'x': 5, 'y': 6, 'scaleX': 2, 'scaleY': 1.5}}
        payload = {'screen': 'dashboard', 'layout': [gray_widget]}
        assert request('/api/layouts', payload)[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [gray_widget]
        status, png = request('/api/layout-preview', payload)
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            expected = Image.new('L', preview.size, 255)
            expected.paste(140, (5, 6, 65, 66))
            assert preview.tobytes() == expected.convert('1', dither=Image.Dither.FLOYDSTEINBERG).tobytes()
        status, png = request('/api/layout-preview', {**payload, 'layers': True})
        assert status == 200
        with Image.open(io.BytesIO(png)) as atlas:
            assert atlas.getpixel((15, 1)) == (140, 140, 140, 255)
        png = render_layout_preview('dashboard', [gray_widget], 'light', 'en', 'celsius',
                                    size=(250, 244), rotation=0)
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.size == (250, 122)
            expected = Image.new('L', preview.size, 255)
            expected.paste(140, (64, 3, 94, 33))
            assert preview.tobytes() == expected.convert('1', dither=Image.Dither.FLOYDSTEINBERG).tobytes()
        malformed = {**gray_widget, 'photo': {**gray_photo, 'gray': gray_photo['gray'][:-4]}}
        assert request('/api/layout-preview', {**payload, 'layout': [malformed]})[0] == 400
        # A photo saved by an older version still uses a packed one-bit bitmap.
        photo = {'w': 16, 'h': 8, 'bitmap': base64.b64encode(source.convert('1').tobytes()).decode()}
        photo_widget = {**photo_option['template'], 'x': 4, 'y': 8, 'w': 8, 'h': 8,
                        'photo': photo, 'crop': [0, 0, 8, 8]}
        status, png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': [photo_widget]})
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.getpixel((7, 11)) == 0 and preview.getpixel((3, 11)) == 255
        flipped = {**photo_widget, 'crop': [8, 0, 8, 8]}
        status, png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': [flipped]})
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.getpixel((7, 11)) == 255
        portrait = {**photo_widget, 'crop': [0, 0, 4, 8],
                    'placement': {'x': 242, 'y': 0, 'scaleX': 2, 'scaleY': 1.5}}
        payload = {'screen': 'dashboard', 'layout': [portrait]}
        status, png = request('/api/layout-preview', payload)
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert ImageOps.invert(preview.convert('L')).getbbox() == (242, 0, 250, 12)
        assert request('/api/layouts', payload)[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [portrait]
        assert request('/api/layout-preview', {'screen': 'dashboard',
                       'layout': [{**photo_widget, 'crop': [9, 0, 8, 8]}]})[0] == 400
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [photo_widget]})[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [photo_widget]
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': None})[0] == 200
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
                    if option['type'] == 'photo':
                        widget['photo'] = photo
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
        placed_text = {**text, 'text': 'Hi', 'placement': {'x': 7, 'y': 0, 'scaleX': 2, 'scaleY': 1}}
        text_bounds = []
        for value in ('Hi', 'Hello there'):
            status, png = request('/api/layout-preview', {'screen': 'dashboard',
                                  'layout': [{**placed_text, 'text': value}]})
            assert status == 200
            with Image.open(io.BytesIO(png)) as preview:
                text_bounds.append(ImageOps.invert(preview.convert('L')).getbbox())
        assert text_bounds[0][:2] == text_bounds[1][:2] == (7, 0)
        assert text_bounds[0][2] < text_bounds[1][2]
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
        for path, preview_layout in ((entry, draft['layout']), (listing + '&name=', schema['defaults']['dashboard'])):
            status, thumbnail_png = request(path + '&thumbnail=1')
            logical_status, logical_png = request('/api/layout-preview', {'screen': 'dashboard', 'layout': preview_layout})
            assert status == logical_status == 200
            assert thumbnail_png == logical_png
        assert (root / '.layout-library.json').stat().st_mode & 0o777 == 0o600
        assert settings.layouts == {'dashboard': None, 'playback': []}
        apply = library + '/apply'
        selection = {'screen': 'dashboard', 'name': 'Moje plocha'}
        assert request(apply, selection, code='wrong')[0] == 403
        assert request(apply, {**selection, 'screen': 'playback'})[0] == 404
        assert request(apply, {'screen': 'other', 'name': None})[0] == 400
        assert request(apply, {'screen': 'dashboard'})[0] == 400
        assert state.mode == 'auto' and settings.layouts['dashboard'] is None
        status, applied = request(apply, selection)
        assert status == 200 and json.loads(applied)['mode'] == 'auto'
        assert json.loads(applied)['activeLayout'] == {
            'screen': 'dashboard', 'kind': 'saved', 'name': 'Moje plocha'}
        assert DeviceSettings(root).active_layout('dashboard')['name'] == 'Moje plocha'
        layout_file = json.loads(settings.layouts_path.read_text())
        del layout_file['names']
        settings.layouts_path.write_text(json.dumps(layout_file))
        assert DeviceSettings(root).active_layout('dashboard')['name'] == 'Moje plocha'
        assert request(library, {**draft, 'name': 'Stejné rozvržení'})[0] == 200
        assert request(apply, {**selection, 'name': 'Stejné rozvržení'})[0] == 200
        assert DeviceSettings(root).active_layout('dashboard')['name'] == 'Stejné rozvržení'
        assert request(library, {**draft, 'name': 'Stejné rozvržení', 'delete': True})[0] == 200
        assert DeviceSettings(root).active_layout('dashboard')['kind'] == 'custom'
        assert request(apply, selection)[0] == 200
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': custom})[0] == 200
        assert json.loads(request('/api/state', code='')[1])['activeLayout'] == {
            'screen': 'dashboard', 'kind': 'custom', 'name': None}
        assert request(apply, selection)[0] == 200
        assert DeviceSettings(root).layouts == {'dashboard': draft['layout'], 'playback': []}
        assert PanelState(root / 'theme.txt').mode == 'auto'
        assert json.loads(request(entry)[1])['layout'] == draft['layout']
        assert request(apply, {'screen': 'dashboard', 'name': None})[0] == 200
        assert settings.layouts['dashboard'] is None
        assert request('/api/layouts', {**draft, 'libraryName': 'Moje plocha'})[0] == 200
        assert DeviceSettings(root).active_layout('dashboard')['name'] == 'Moje plocha'
        assert request(apply, {'screen': 'dashboard', 'name': None})[0] == 200
        playback = {'screen': 'playback', 'name': 'Hudba', 'layout': custom}
        assert request(library, playback)[0] == 200
        status, applied = request(apply, {'screen': 'playback', 'name': 'Hudba'})
        assert status == 200 and json.loads(applied)['mode'] == 'auto'
        assert json.loads(applied)['activeLayout'] == {'screen': 'dashboard', 'kind': 'default', 'name': None}
        assert settings.layouts == {'dashboard': None, 'playback': custom}
        assert request('/api/display-mode', {'mode': 'playback'})[0] == 200
        status, applied = request(apply, selection)
        assert status == 200 and json.loads(applied)['mode'] == 'playback'
        assert json.loads(applied)['activeLayout'] == {'screen': 'playback', 'kind': 'saved', 'name': 'Hudba'}
        assert PanelState(root / 'theme.txt').mode == 'playback'
        assert json.loads(applied)['selectedLayouts'] == {
            'dashboard': {'screen': 'dashboard', 'kind': 'saved', 'name': 'Moje plocha'},
            'playback': {'screen': 'playback', 'kind': 'saved', 'name': 'Hudba'},
        }
        assert request(apply, {'screen': 'dashboard', 'name': None})[0] == 200
        delete = {'screen': 'dashboard', 'name': 'Moje plocha', 'delete': True}
        assert request(library, delete)[0] == 200
        assert request(entry)[0] == 404
        assert request(listing) == (200, b'{"names": []}')
        settings.library_path.write_text(json.dumps({'dashboard': {'Starší': custom}, 'playback': {}}))
        assert json.loads(request(listing + '&details=1')[1])['entries'] == [
            {'name': 'Starší', 'savedAt': None, 'layers': 1}]
        assert settings.get_layout_library('dashboard', 'Starší')['layout'] == custom

        now = datetime(2026, 11, 10, 14, 8, 7)
        temperature = next(option['template'] for option in schema['widgets']['dashboard']
                           if option['type'] == 'weather')
        temperature = {**temperature, 'variant': 'temperature-only', 'font': 'bold', 'align': 'center',
                       'placement': {'x': 194, 'y': 93, 'scaleX': 46 / 66, 'scaleY': .75}}

        def temperature_bounds(widget, degrees, units='celsius'):
            pixels = render_custom([widget], now, 'dark', 'en', weather=(degrees, 2, True), units=units)
            return Image.frombytes('L', (250, 122), bytes(bit * 255 for bit in pixels)).getbbox()

        preview_bounds = temperature_bounds(temperature, 16)
        live_bounds = temperature_bounds(temperature, 5)
        assert preview_bounds[0] == 194 and live_bounds[0] > preview_bounds[0]
        assert abs(live_bounds[0] + live_bounds[2] - preview_bounds[0] - preview_bounds[2]) <= 1
        placement = {**temperature['placement'], 'referenceWidth': preview_bounds[2] - preview_bounds[0]}
        centered = {**temperature, 'placement': placement}
        assert temperature_bounds(centered, 5) == live_bounds
        right = {**centered, 'align': 'right'}
        assert temperature_bounds(right, 5)[2] == temperature_bounds(right, 16)[2]
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [centered]})[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [centered]
        assert format_clock(now, 'HH.MM.SS / h:mm a [čas]') == '14.08.07 / 2:08 pm čas'
        assert format_clock(now.replace(hour=0), 'H / hh:mm A') == '0 / 12:08 AM'
        custom_clock = {**clock, 'variant': 'custom', 'format': 'HH.mm.ss'}
        assert clock_has_seconds(custom_clock)
        assert not clock_has_seconds({**custom_clock, 'format': 'HH:mm [ss]'})
        assert content_key([custom_clock], now, None, None, None, 0) == ('14.08.07',)
        stacked_clock = {**custom_clock, 'clockStyle': 'stacked'}
        assert clock_has_seconds(stacked_clock)
        assert content_key([stacked_clock], now, None, None, None, 0) == (('14', '08', '07'),)
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [stacked_clock]})[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [stacked_clock]
        legacy_clock = {**clock, 'variant': 'stacked'}
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [legacy_clock]})[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [{**clock, 'clockStyle': 'stacked'}]
        analog_clock = {**stacked_clock, 'clockStyle': 'analog'}
        assert not clock_has_seconds(analog_clock)
        assert content_key([analog_clock], now, None, None, None, 0) == ((2, 8),)
        date = schema['defaults']['dashboard'][1]
        day = now.replace(day=9)
        for variant, expected in {
            'dotted': '09.11.2026', 'dotted-short-year': '09.11.26',
            'day-first': '09/11/2026', 'month-first': '11/09/2026',
            'month-name': '9 lis 2026', 'day-month': '9. 11.',
        }.items():
            assert content_key([{**date, 'variant': variant}], day, None, None, None, 0,
                               language='cs') == (expected,)
        pattern = '[Dnes] dddd d. MMMM yyyy'
        assert format_date(day, pattern, 'cs') == 'Dnes pondělí 9. listopadu 2026'
        assert format_date(day, 'ddd, MMM DD YY', 'en') == 'Mon, Nov 09 26'
        custom_date = {**date, 'variant': 'custom', 'format': pattern}
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': [custom_date]})[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == [custom_date]
        assert request('/api/layout-preview', {'screen': 'dashboard',
                       'layout': [{**custom_date, 'format': ' '}]})[0] == 400
        layout = [custom_clock, dot]
        assert request('/api/layouts', {'screen': 'dashboard', 'layout': layout})[0] == 200
        assert request('/api/layout-preview', {'screen': 'dashboard',
                       'layout': [{**custom_clock, 'format': ' '}]})[0] == 400

        original = settings.values
        enlarged = {**original, 'display_width': 375, 'display_height': 183}
        assert request('/api/settings', {**enlarged, 'display_height': 401})[0] == 400
        assert request('/api/settings', enlarged)[0] == 200
        schema = json.loads(request('/api/layouts')[1])
        assert (schema['width'], schema['height']) == (375, 183)
        resized = schema['layouts']['dashboard']
        assert resized == DeviceSettings(root).layouts['dashboard']
        assert resized[0]['w'] == round(clock['w'] * 1.5)
        assert resized[0]['format'] == custom_clock['format']
        assert (resized[1]['x'], resized[1]['y']) == (18, 36)
        assert settings.get_layout_library('dashboard', 'Starší')['layout'][0]['x'] == round(text['x'] * 1.5)
        assert request(listing + '&width=250&height=122')[0] == 400
        payload = {'screen': 'dashboard', 'layout': resized, 'displaySize': [375, 183]}
        assert request('/api/layouts', {**payload, 'displaySize': [250, 122]})[0] == 400
        status, png = request('/api/layout-preview', payload)
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.size == (375, 183) and preview.getextrema() == (0, 255)
        status, png = request('/api/layout-preview', {**payload, 'layers': True})
        assert status == 200
        with Image.open(io.BytesIO(png)) as atlas:
            assert atlas.size == (375, 1 + 183 * len(resized))
        assert request('/api/settings', original)[0] == 200
        assert settings.layouts['dashboard'] == layout
        assert settings.get_layout_library('dashboard', 'Starší')['layout'] == custom
        assert DeviceSettings(root, rotation=90).layout_state[0] == (122, 250)
        settings.path.write_text(json.dumps({**original, 'rotation': 90}))
        upgraded = DeviceSettings(root)
        assert upgraded.layout_state[0] == (122, 250)
        assert upgraded.layouts['dashboard'][1]['y'] == 107
        thumbnails = {}
        for rotation in (0, 90, 180, 270):
            assert request('/api/settings', {**original, 'rotation': rotation})[0] == 200
            portrait = rotation in (90, 270)
            width, height = (122, 250) if portrait else (250, 122)
            schema = json.loads(request('/api/layouts')[1])
            assert (schema['width'], schema['height']) == (width, height)
            assert schema['panel'] == {
                'rotation': rotation, 'width': width, 'height': height, 'bounds': [0, 0, width, height]}
            status, png = request(listing + '&name=Star%C5%A1%C3%AD&thumbnail=1')
            assert status == 200
            with Image.open(io.BytesIO(png)) as thumbnail:
                assert thumbnail.size == (width, height) and thumbnail.getextrema() == (0, 255)
            thumbnails[rotation] = png
        assert thumbnails[0] == thumbnails[180] and thumbnails[90] == thumbnails[270]
        portrait_edges = {'screen': 'dashboard', 'displaySize': [122, 250],
                          'layout': [{**dot, 'x': 0, 'y': 0}, {**dot, 'x': 121, 'y': 249}]}
        assert request('/api/layouts', portrait_edges)[0] == 200
        status, png = request('/api/layout-preview', portrait_edges)
        assert status == 200
        with Image.open(io.BytesIO(png)) as preview:
            assert preview.getpixel((0, 0)) == preview.getpixel((121, 249)) == 0
        assert request('/api/settings', {**enlarged, 'rotation': 270})[0] == 200
        assert settings.layout_state[0] == (183, 375)
        assert request(apply, {'screen': 'dashboard', 'name': 'Starší'})[0] == 200
        assert settings.layouts['dashboard'] == settings.get_layout_library('dashboard', 'Starší')['layout']
        assert request('/api/settings', original)[0] == 200
        assert DeviceSettings(root).layouts['dashboard'] == custom
        old_selection = json.loads(settings.layouts_path.read_text())
        old_selection['sizes']['dashboard'] = [122, 250]
        old_selection['dashboard'] = [resize_layer(widget, (250, 122), (122, 250)) for widget in custom]
        settings.layouts_path.write_text(json.dumps(old_selection))
        upgraded = DeviceSettings(root)
        assert upgraded.active_layout('dashboard')['name'] == 'Starší'
        assert upgraded.layouts['dashboard'] == custom

        square = bytearray(100 * 100)
        fitted = fit_panel(square, (100, 100), 'light')
        assert len(fitted) == 250 * 122
        assert fitted[:64] == bytes([1] * 64)
        assert fitted[64:186] == bytes(122)
        assert len(pack(fitted, 180)) == 250 * 16
    finally:
        server.shutdown()
        server.server_close()

print('Layout preview, custom time, display dimensions, saved layouts and panel fit passed.')
