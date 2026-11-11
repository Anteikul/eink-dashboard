"""Validate screen layouts and composite their layers at the panel's resolution."""
from base64 import b64decode, b64encode
from copy import deepcopy
from functools import lru_cache
from math import cos, pi, sin, tau

from PIL import Image, ImageChops, ImageDraw, ImageOps

from music_screen import fit_lines, font

WIDTH, HEIGHT = 250, 122
MAX_WIDGETS = 18
MAX_DRAWINGS = 96
BOX_KEYS = ('x', 'y', 'w', 'h')
FONTS = ('regular', 'bold', 'mono', 'mono-bold')
ALIGNMENTS = ('left', 'center', 'right')
WRAPPING = (('wrapped', 'Wrapped'), ('single', 'Single line'))
PIXEL_BITS = bytes([0] + [1] * 255)
WEEKDAYS_LONG = {
    'en': ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'),
    'cs': ('pondělí', 'úterý', 'středa', 'čtvrtek', 'pátek', 'sobota', 'neděle'),
}
MONTHS_LONG = {
    'en': ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
           'September', 'October', 'November', 'December'),
    'cs': ('ledna', 'února', 'března', 'dubna', 'května', 'června', 'července',
           'srpna', 'září', 'října', 'listopadu', 'prosince'),
}


def _definition(kind, label, variants, box, *, size=16, face='regular', align='left',
                text='', text_style=True):
    x, y, w, h = box
    return {
        'type': kind,
        'label': label,
        'variants': [{'value': value, 'label': name} for value, name in variants],
        'template': {'type': kind, 'variant': variants[0][0], 'x': x, 'y': y, 'w': w, 'h': h,
                     'size': size, 'font': face, 'align': align, 'text': text},
        'textStyle': text_style,
    }


COMMON = (
    _definition('clock', 'Clock', (('24h', '24-hour'), ('12h', '12-hour'),
                                   ('seconds', 'With seconds'), ('stacked', 'Stacked'),
                                   ('analog', 'Analog')),
                (10, 25, 146, 54), size=47, face='mono'),
    _definition('date', 'Date', (('short', 'Short'), ('long', 'Long'), ('iso', 'ISO')),
                (12, 77, 146, 24), size=14),
    _definition('weather', 'Weather', (('icon-left', 'Icon left'), ('icon-right', 'Icon right'),
                                       ('icon-above', 'Icon above'), ('icon-below', 'Icon below'),
                                       ('icon-only', 'Icon only'),
                                       ('temperature-only', 'Temperature only')),
                (169, 17, 74, 78), size=27, face='bold', align='center'),
    _definition('text', 'Custom text', WRAPPING, (12, 10, 134, 35), text='Your text'),
    _definition('divider', 'Divider', (('horizontal', 'Horizontal'), ('vertical', 'Vertical')),
                (12, 63, 120, 1), text_style=False),
)
PLAYBACK = (
    _definition('title', 'Track title', WRAPPING, (118, 13, 119, 54), size=17, face='bold'),
    _definition('artist', 'Artist', WRAPPING, (118, 67, 119, 24), size=12),
    _definition('cover', 'Cover art', (('fit', 'Fit'), ('fill', 'Fill')),
                (10, 13, 96, 96), text_style=False),
    _definition('progress', 'Playback progress', (('horizontal', 'Horizontal bar'),
                                                  ('vertical', 'Vertical bar'),
                                                  ('ring', 'Ring'), ('line', 'Line')),
                (118, 104, 120, 4), text_style=False),
    _definition('playback-time', 'Playback time', (('elapsed', 'Elapsed'), ('remaining', 'Remaining'),
                                                   ('both', 'Elapsed and remaining')),
                (118, 88, 119, 16), size=11, face='mono'),
)
WIDGETS = {
    'dashboard': {widget['type']: widget for widget in COMMON},
    'playback': {widget['type']: widget for widget in (*PLAYBACK, *COMMON)},
}


def editor_schema():
    dashboard = WIDGETS['dashboard']
    playback = WIDGETS['playback']
    return deepcopy({
        'width': WIDTH,
        'height': HEIGHT,
        'maxWidgets': MAX_WIDGETS,
        'maxDrawings': MAX_DRAWINGS,
        'defaults': {
            'dashboard': [dashboard['clock']['template'].copy(), dashboard['date']['template'].copy(),
                          {**dashboard['divider']['template'], 'variant': 'vertical',
                           'x': 161, 'y': 30, 'w': 1, 'h': 65},
                          {**dashboard['weather']['template'], 'variant': 'icon-above'}],
            'playback': [playback[kind]['template'].copy() for kind in ('cover', 'title', 'artist', 'progress')],
        },
        'widgets': {screen: list(definitions.values()) for screen, definitions in WIDGETS.items()},
    })


def _validate_box(x, y, w, h):
    if (any(type(value) is not int for value in (x, y, w, h))
            or not (0 <= x and 0 <= y and 1 <= w <= WIDTH - x and 1 <= h <= HEIGHT - y)):
        raise ValueError('Keep each widget inside the display.')


def _validate_drawing(supplied):
    box = {}
    w, h = WIDTH, HEIGHT
    if any(key in supplied for key in BOX_KEYS):
        box = {key: supplied.get(key) for key in BOX_KEYS}
        _validate_box(**box)
        w, h = box['w'], box['h']
    return {'type': 'drawing', **box, 'bitmap': _validate_bitmap(supplied.get('bitmap'), w, h)}


def _validate_bitmap(bitmap, w, h):
    size = ((w + 7) // 8) * h
    if not isinstance(bitmap, str) or len(bitmap) != 4 * ((size + 2) // 3):
        raise ValueError('The drawing is invalid.')
    try:
        pixels = b64decode(bitmap, validate=True)
    except ValueError as error:
        raise ValueError('The drawing is invalid.') from error
    if len(pixels) != size:
        raise ValueError('The drawing is invalid.')
    return b64encode(pixels).decode()


def validate_layout(screen, layout):
    """Return normalized widget dictionaries, or None to select the original screen."""
    if screen not in ('dashboard', 'playback'):
        raise ValueError('Choose Dashboard or Playback.')
    if layout is None:
        return None
    if not isinstance(layout, list) or len(layout) > MAX_WIDGETS + MAX_DRAWINGS:
        raise ValueError('The layout has too many layers.')

    widgets = WIDGETS[screen]
    normalized = []
    drawings = 0
    for supplied in layout:
        if not isinstance(supplied, dict) or not isinstance(supplied.get('type'), str):
            raise ValueError('Choose a widget type.')
        if supplied['type'] == 'drawing':
            drawings += 1
            if drawings > MAX_DRAWINGS:
                raise ValueError(f'Use up to {MAX_DRAWINGS} pen strokes per layout.')
            normalized.append(_validate_drawing(supplied))
            continue
        definition = widgets.get(supplied['type'])
        if definition is None:
            raise ValueError('This widget is unavailable on this screen.')
        widget = {key: supplied.get(key, value) for key, value in definition['template'].items()}
        _validate_box(*(widget[key] for key in BOX_KEYS))
        if widget['variant'] not in tuple(variant['value'] for variant in definition['variants']):
            raise ValueError('Choose an available widget style.')
        if (type(widget['size']) is not int or not 8 <= widget['size'] <= 60
                or widget['font'] not in FONTS or widget['align'] not in ALIGNMENTS):
            raise ValueError('Choose a font, alignment and a size from 8 to 60.')
        if not isinstance(widget['text'], str) or len(widget['text']) > 120:
            raise ValueError('Use up to 120 characters of text.')
        try:
            widget['text'].encode('utf-8')
        except UnicodeEncodeError as error:
            raise ValueError('Use valid Unicode text.') from error
        if widget['type'] == 'divider' and 'thickness' in supplied:
            thickness = supplied['thickness']
            if type(thickness) is not int or not 1 <= thickness <= HEIGHT:
                raise ValueError('Choose a valid divider thickness.')
            widget['thickness'] = thickness
        if 'mask' in supplied:
            mask = supplied['mask']
            if not isinstance(mask, dict):
                raise ValueError('The drawing is invalid.')
            w, h = mask.get('w'), mask.get('h')
            _validate_box(0, 0, w, h)
            widget['mask'] = {'w': w, 'h': h, 'bitmap': _validate_bitmap(mask.get('bitmap'), w, h)}
        normalized.append(widget)
    if len(normalized) - drawings > MAX_WIDGETS:
        raise ValueError(f'Use up to {MAX_WIDGETS} widgets per layout.')
    return normalized


def _date(now, variant, language):
    if variant == 'iso':
        return now.date().isoformat()
    if variant == 'short':
        from dashboard import screen_content

        return screen_content(now, None, language=language)[1]
    weekday = WEEKDAYS_LONG[language][now.weekday()]
    month = MONTHS_LONG[language][now.month - 1]
    if language == 'cs':
        return f'{weekday} {now.day}. {month} {now.year}'
    return f'{weekday}, {now.day} {month} {now.year}'


def _clock(now, variant):
    if variant == 'analog':
        return (now.hour % 12, now.minute)
    if variant == 'stacked':
        return (f'{now.hour:02}', f'{now.minute:02}')
    if variant == 'seconds':
        return now.strftime('%H:%M:%S')
    if variant == '12h':
        suffix = 'AM' if now.hour < 12 else 'PM'
        return f'{now.hour % 12 or 12}:{now.minute:02} {suffix}'
    return now.strftime('%H:%M')


def _temperature_and_icon(now, variant, weather, units, language):
    from dashboard import screen_content

    _, _, temperature, icon = screen_content(now, weather, units, language)
    if variant == 'temperature-only':
        return temperature, None
    if variant == 'icon-only':
        return '', icon
    return temperature, icon


def _progress_steps(widget):
    w, h = widget['w'], widget['h']
    variant = widget['variant']
    if variant == 'ring':
        return max(1, round(pi * min(w, h)))
    inset = int(min(w, h) >= 3 and variant != 'line')
    return (h if variant == 'vertical' else w) - 2 * inset


def _playback_time(progress, duration_ms, variant):
    def format_seconds(milliseconds):
        minutes, seconds = divmod(milliseconds // 1000, 60)
        return f'{minutes}:{seconds:02}'

    position = round(progress * duration_ms)
    elapsed = format_seconds(position)
    remaining = '−' + format_seconds(duration_ms - position)
    if variant == 'elapsed':
        return elapsed
    if variant == 'remaining':
        return remaining
    return f'{elapsed} / {remaining}'


def _widget_content(widget, now, weather, track, cover, progress, duration_ms, units, language):
    kind = widget['type']
    if kind == 'drawing':
        return None
    variant = widget['variant']
    if kind == 'clock':
        return _clock(now, variant)
    if kind == 'date':
        return _date(now, variant, language)
    if kind == 'weather':
        return _temperature_and_icon(now, variant, weather, units, language)
    if kind == 'text':
        return widget['text']
    if kind in ('title', 'artist'):
        return getattr(track, kind, '')
    if kind == 'cover':
        return id(cover)
    if kind == 'progress':
        return round(progress * _progress_steps(widget))
    if kind == 'playback-time':
        return _playback_time(progress, duration_ms, variant) if duration_ms else '—'
    return None


def content_key(layout, now, weather, track, cover, progress, *, duration_ms=0,
                units='celsius', language='en'):
    """Return the dynamic values that can change the rendered pixels."""
    progress = min(1.0, max(0.0, progress))
    return tuple(_widget_content(widget, now, weather, track, cover, progress, duration_ms,
                                 units, language) for widget in layout)


def _face(widget, size):
    face = widget['font']
    return font(size, bold=face in ('bold', 'mono-bold'), mono=face in ('mono', 'mono-bold'))


def _fit_face(widget, size, lines, w, h):
    face = _face(widget, size)
    while size > 8:
        boxes = [face.getbbox(line) for line in lines]
        widest = max(max(right - left for left, _, right, _ in boxes),
                     max(face.getlength(line) for line in lines))
        tallest = max(bottom - top for _, top, _, bottom in boxes)
        scale = min(w / max(1, widest), h / len(lines) / max(1, tallest))
        if scale >= 1:
            break
        size = max(8, min(size - 1, int(size * scale)))
        face = _face(widget, size)
    return face, size


def _draw_text(mask, widget, value, *, wrapped=False, fit=False):
    w, h = mask.size
    size = widget['size']
    if isinstance(value, tuple):
        lines = value
        size = min(size, max(8, h // len(lines) - 2))
    else:
        lines = []
    if fit:
        # Keep the digits and units legible when a variant needs more space.
        samples = (value,) if isinstance(value, str) else value
        face, size = _fit_face(widget, size, samples, w, h)
    else:
        face = _face(widget, size)
    line_height = size + 2
    if isinstance(value, str):
        if wrapped:
            rows = max(1, h // line_height)
            for paragraph in value.splitlines():
                available = rows - len(lines)
                if available == 0:
                    break
                lines.extend(fit_lines(paragraph, face, w, available) or [''])
        else:
            lines = fit_lines(value, face, w, 1)
    draw = ImageDraw.Draw(mask)
    boxes = [draw.textbbox((0, 0), line, font=face) for line in lines]
    if not boxes:
        return
    top = min(index * line_height + box[1] for index, box in enumerate(boxes))
    bottom = max(index * line_height + box[3] for index, box in enumerate(boxes))
    start_y = max(0, (h - (bottom - top)) // 2) - top
    for index, (line, (left, _, right, _)) in enumerate(zip(lines, boxes)):
        width = right - left
        start_x = {'left': 0, 'center': (w - width) // 2, 'right': w - width}[widget['align']]
        draw.text((start_x - left, start_y + index * line_height), line, font=face, fill=1)


def _dial_box(w, h):
    size = min(w, h)
    x, y = (w - size) // 2, (h - size) // 2
    return x, y, x + size - 1, y + size - 1


def _draw_clock(mask, widget, value):
    if widget['variant'] != 'analog':
        _draw_text(mask, widget, value, fit=True)
        return
    draw = ImageDraw.Draw(mask)
    box = _dial_box(*mask.size)
    x0, y0, x1, y1 = box
    radius = (x1 - x0) / 2
    cx, cy = x0 + radius, y0 + radius
    draw.ellipse(box, outline=1)
    hour, minute = value
    for turn, length, width in (((hour + minute / 60) / 12, .58, 2), (minute / 60, .8, 1)):
        angle = turn * tau - pi / 2
        point = (round(cx + cos(angle) * radius * length), round(cy + sin(angle) * radius * length))
        draw.line(((round(cx), round(cy)), point), fill=1, width=width)


@lru_cache(maxsize=9)
def _icon_mask(name):
    from dashboard import ATLAS

    icon = Image.new('1', (36, 34))
    ImageDraw.Draw(icon).point([tuple(point) for point in ATLAS['weather'][name]], fill=1)
    return icon


def _contain(image, w, h):
    scale = min(w / image.width, h / image.height)
    size = max(1, round(image.width * scale)), max(1, round(image.height * scale))
    return image.resize(size, Image.Resampling.NEAREST)


def _draw_icon(mask, name, box, align='center'):
    x, y, w, h = box
    if w < 1 or h < 1:
        return
    icon = _contain(_icon_mask(name), w, h)
    shift = {'left': 0, 'center': (w - icon.width) // 2, 'right': w - icon.width}[align]
    mask.paste(icon, (x + shift, y + (h - icon.height) // 2), icon)


def _draw_weather(mask, widget, value):
    temperature, icon = value
    w, h = mask.size
    variant = widget['variant']
    if variant == 'icon-only':
        if icon:
            _draw_icon(mask, icon, (0, 0, w, h), widget['align'])
        return
    if not icon or w < 2 or h < 2:
        _draw_text(mask, widget, temperature, fit=True)
        return

    face = _face(widget, widget['size'])
    left, top, right, bottom = face.getbbox(temperature)
    if variant in ('icon-left', 'icon-right'):
        gap = min(4, w - 2)
        icon_w = min(h, max((w - gap) // 3, w - gap - (right - left)))
        text_w = max(1, w - gap - icon_w)
        icon_x, text_x = (0, icon_w + gap) if variant == 'icon-left' else (text_w + gap, 0)
        icon_box = (icon_x, 0, icon_w, h)
        text_box = (text_x, 0, text_w, h)
    else:
        gap = min(3, h - 2)
        text_h = min(h - gap - 1, max(1, bottom - top + 4))
        icon_h = h - gap - text_h
        icon_y, text_y = (0, icon_h + gap) if variant == 'icon-above' else (text_h + gap, 0)
        icon_box = (0, icon_y, w, icon_h)
        text_box = (0, text_y, w, text_h)
    _draw_icon(mask, icon, icon_box)
    x, y, text_w, text_h = text_box
    label = Image.new('1', (text_w, text_h))
    _draw_text(label, widget, temperature, fit=True)
    mask.paste(label, (x, y), label)


def _draw_divider(mask, variant, thickness=1):
    w, h = mask.size
    if variant == 'vertical':
        thickness = min(w, thickness)
        left = (w - thickness) // 2
        box = (left, 0, left + thickness - 1, h - 1)
    else:
        thickness = min(h, thickness)
        top = (h - thickness) // 2
        box = (0, top, w - 1, top + thickness - 1)
    ImageDraw.Draw(mask).rectangle(box, fill=1)


def _draw_progress(mask, widget, filled):
    w, h = mask.size
    variant = widget['variant']
    draw = ImageDraw.Draw(mask)
    if variant == 'ring':
        box = _dial_box(w, h)
        if min(w, h) >= 3:
            draw.ellipse(box, outline=1)
        if filled:
            angle = 360 * filled / _progress_steps(widget) - 90
            width = max(2, min(w, h) // 9) if min(w, h) >= 3 else 1
            draw.arc(box, -90, angle, fill=1, width=width)
    elif variant == 'line':
        if h >= 3:
            _draw_divider(mask, 'horizontal')
        if filled:
            draw.rectangle((0, max(0, (h - 1) // 2 - 1), filled - 1, h // 2 + 1), fill=1)
    else:
        inset = int(min(w, h) >= 3)
        if inset:
            draw.rectangle((0, 0, w - 1, h - 1), outline=1)
        if filled and variant == 'vertical':
            draw.rectangle((inset, h - inset - filled, w - 1 - inset, h - 1 - inset), fill=1)
        elif filled:
            draw.rectangle((inset, inset, inset + filled - 1, h - 1 - inset), fill=1)


@lru_cache(maxsize=256)
def _drawing_mask(bitmap, w, h):
    return Image.frombytes('1', (w, h), b64decode(bitmap))


def _apply_erasure(widget, layer, offset=(0, 0), *, art=False):
    mask = widget.get('mask')
    if mask is None or layer is None:
        return layer
    erased = _drawing_mask(mask['bitmap'], mask['w'], mask['h'])
    erased = erased.resize((widget['w'], widget['h']), Image.Resampling.NEAREST)
    x, y = offset
    visible = ImageChops.invert(erased.crop((x, y, x + layer.width, y + layer.height)))
    if art:
        layer = layer.convert('RGBA')
        layer.putalpha(visible.convert('L'))
        return layer
    return ImageChops.logical_and(layer, visible)


def _widget_layers(layout, now, language, weather, units, track, cover, progress, duration_ms):
    """Yield a widget's offset, pixel data and whether it is opaque art."""
    values = content_key(layout, now, weather, track, cover, progress, duration_ms=duration_ms,
                         units=units, language=language)
    for widget, value in zip(layout, values):
        kind = widget['type']
        if kind == 'drawing':
            yield (0, 0), _drawing_mask(widget['bitmap'], widget.get('w', WIDTH), widget.get('h', HEIGHT)), False
            continue
        w, h = widget['w'], widget['h']
        if kind == 'cover':
            art = None
            if cover is not None:
                art = (ImageOps.fit(cover, (w, h), Image.Resampling.NEAREST)
                       if widget['variant'] == 'fill' else _contain(cover, w, h))
            offset = ((w - art.width) // 2, (h - art.height) // 2) if art is not None else (0, 0)
            yield offset, _apply_erasure(widget, art, offset, art=True), True
            continue
        mask = Image.new('1', (w, h))
        if kind == 'clock':
            _draw_clock(mask, widget, value)
        elif kind == 'weather':
            _draw_weather(mask, widget, value)
        elif kind == 'divider':
            _draw_divider(mask, widget['variant'], widget.get('thickness', 1))
        elif kind == 'progress':
            _draw_progress(mask, widget, value)
        else:
            _draw_text(mask, widget, value, wrapped=widget['variant'] == 'wrapped',
                       fit=kind in ('date', 'playback-time'))
        yield (0, 0), _apply_erasure(widget, mask), False


def render_custom(layout, now, theme, language, *, weather=None, units='celsius', track=None,
                  cover=None, progress=0.0, duration_ms=0):
    """Draw widgets back to front, using their boxes to clip every layer."""
    foreground = int(theme == 'dark')
    image = Image.new('1', (WIDTH, HEIGHT), 1 - foreground)
    layers = _widget_layers(layout, now, language, weather, units, track, cover, progress, duration_ms)
    for widget, ((dx, dy), layer, opaque) in zip(layout, layers):
        if layer is None:
            continue
        position = (widget.get('x', 0) + dx, widget.get('y', 0) + dy)
        if opaque:
            alpha = layer.getchannel('A') if layer.mode == 'RGBA' else None
            image.paste(layer, position, alpha)
        else:
            image.paste(foreground, position, layer)
    return bytearray(image.convert('L').tobytes().translate(PIXEL_BITS))


def render_layer_atlas(layout, now, theme, language, *, weather=None, units='celsius', track=None,
                       cover=None, progress=0.0, duration_ms=0):
    """Put independent transparent widgets in fixed slots below one background pixel."""
    foreground = 255 if theme == 'dark' else 0
    background = 255 - foreground
    atlas = Image.new('RGBA', (WIDTH, 1 + HEIGHT * len(layout)))
    atlas.putpixel((0, 0), (background, background, background, 255))
    layers = _widget_layers(layout, now, language, weather, units, track, cover, progress, duration_ms)
    for index, ((x, y), layer, opaque) in enumerate(layers):
        if layer is None:
            continue
        position = (x, y + 1 + HEIGHT * index)
        if opaque:
            atlas.paste(layer.convert('RGBA'), position)
        else:
            atlas.paste((foreground, foreground, foreground, 255), position, layer)
    return atlas
