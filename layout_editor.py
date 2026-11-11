"""Validate screen layouts and composite their layers at the configured resolution."""
import re
from base64 import b64decode, b64encode
from copy import deepcopy
from functools import lru_cache
from math import cos, floor, pi, sin, tau

from PIL import Image, ImageChops, ImageDraw, ImageOps

from music_screen import fit_lines, font
from photo_import import PHOTO_SIZE, PHOTO_UPLOAD_LIMIT

WIDTH, HEIGHT = 250, 122
PANEL_SIZE = WIDTH, HEIGHT
MIN_DIMENSION, MAX_DIMENSION = 32, 400
MAX_WIDGETS = 18
MAX_DRAWINGS = 96
BOX_KEYS = ('x', 'y', 'w', 'h')
FONTS = ('regular', 'bold', 'mono', 'mono-bold')
ALIGNMENTS = ('left', 'center', 'right')
WRAPPING = (('wrapped', 'Wrapped'), ('single', 'Single line'))
PIXEL_BITS = bytes([0] + [1] * 255)
TIME_TOKENS = re.compile(r'\[([^\[\]]*)\]|HH|hh|mm|MM|ss|SS|H|h|m|s|A|a')
SECONDS_TOKENS = ('s', 'ss', 'SS')
CLOCK_PATTERNS = {'24h': 'HH:mm', '12h': 'h:mm A', 'seconds': 'HH:mm:ss'}
CLOCK_STYLES = (('digital', 'Side by side'), ('stacked', 'Stacked'), ('analog', 'Analog'))
DATE_TOKENS = re.compile(r'\[([^\[\]]*)\]|YYYY|yyyy|YY|yy|MMMM|MMM|MM|M|dddd|ddd|dd|DD|d|D')
CUSTOM_FORMATS = {'clock': 'HH:mm', 'date': 'DD.MM.YYYY'}
DATE_FORMATS = {
    'dotted': ('Dotted (09.11.2026)', 'DD.MM.YYYY'),
    'dotted-short-year': ('Short year (09.11.26)', 'DD.MM.YY'),
    'day-first': ('Day first (09/11/2026)', 'DD/MM/YYYY'),
    'month-first': ('Month first (11/09/2026)', 'MM/DD/YYYY'),
    'month-name': ('Abbreviated month', 'D MMM YYYY'),
    'day-month': ('Day and month (9. 11.)', 'D. M.'),
}
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
MONTHS_SHORT_CS = ('led', 'úno', 'bře', 'dub', 'kvě', 'čer', 'čvc', 'srp', 'zář', 'říj', 'lis', 'pro')


def panel_view_size(rotation):
    return PANEL_SIZE[::-1] if rotation in (90, 270) else PANEL_SIZE


def panel_bounds(size, view_size):
    """Return the fitted layout's rectangle in upright preview coordinates."""
    width, height = size
    view_width, view_height = view_size
    if width * view_height > height * view_width:
        width, height = view_width, round(height / width * view_width)
    else:
        width, height = round(width / height * view_height), view_height
    return (view_width - width) // 2, (view_height - height) // 2, width, height


def _definition(kind, label, variants, box, *, size=16, face='regular', align='left',
                text='', text_style=True):
    x, y, w, h = box
    definition = {
        'type': kind,
        'label': label,
        'variants': [{'value': value, 'label': name} for value, name in variants],
        'template': {'type': kind, 'variant': variants[0][0], 'x': x, 'y': y, 'w': w, 'h': h,
                     'size': size, 'font': face, 'align': align, 'text': text},
        'textStyle': text_style,
    }
    if kind in CUSTOM_FORMATS:
        definition['customFormat'] = CUSTOM_FORMATS[kind]
    if kind == 'clock':
        definition['clockStyles'] = [{'value': value, 'label': name} for value, name in CLOCK_STYLES]
        definition['template']['clockStyle'] = 'digital'
    return definition


COMMON = (
    _definition('clock', 'Clock', (('24h', '24-hour'), ('12h', '12-hour'),
                                   ('seconds', 'With seconds'), ('custom', 'Custom format')),
                (10, 25, 146, 54), size=47, face='mono'),
    _definition('date', 'Date', (('short', 'Short'), ('long', 'Long'), ('iso', 'ISO'),
                                 *((variant, label) for variant, (label, _) in DATE_FORMATS.items()),
                                 ('custom', 'Custom format')),
                (12, 77, 146, 24), size=14),
    _definition('weather', 'Weather', (('icon-left', 'Icon left'), ('icon-right', 'Icon right'),
                                       ('icon-above', 'Icon above'), ('icon-below', 'Icon below'),
                                       ('icon-only', 'Icon only'),
                                       ('temperature-only', 'Temperature only')),
                (169, 17, 74, 78), size=27, face='bold', align='center'),
    _definition('text', 'Custom text', WRAPPING, (12, 10, 134, 35), text='Your text'),
    _definition('photo', 'Photo', (('fit', 'Fit'), ('fill', 'Fill')),
                (12, 13, 112, 96), text_style=False),
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


def editor_schema(size=PANEL_SIZE):
    dashboard = WIDGETS['dashboard']
    playback = WIDGETS['playback']
    schema = deepcopy({
        'width': size[0],
        'height': size[1],
        'maxWidgets': MAX_WIDGETS,
        'maxDrawings': MAX_DRAWINGS,
        'photoMaxBytes': PHOTO_UPLOAD_LIMIT,
        'defaults': {
            'dashboard': [dashboard['clock']['template'].copy(), dashboard['date']['template'].copy(),
                          {**dashboard['divider']['template'], 'variant': 'vertical',
                           'x': 161, 'y': 30, 'w': 1, 'h': 65},
                          {**dashboard['weather']['template'], 'variant': 'icon-above'}],
            'playback': [playback[kind]['template'].copy() for kind in ('cover', 'title', 'artist', 'progress')],
        },
        'widgets': {screen: list(definitions.values()) for screen, definitions in WIDGETS.items()},
    })
    if size != PANEL_SIZE:
        for screen, defaults in schema['defaults'].items():
            schema['defaults'][screen] = resize_layout(defaults, PANEL_SIZE, size)
            for widget in schema['widgets'][screen]:
                widget['template'] = resize_layer(widget['template'], PANEL_SIZE, size)
    return schema


def validate_display_size(size):
    if (not isinstance(size, (tuple, list)) or len(size) != 2
            or any(type(value) is not int or not MIN_DIMENSION <= value <= MAX_DIMENSION
                   for value in size)):
        raise ValueError('Enter a display width and height from 32 to 400 pixels.')
    return tuple(size)


def _validate_box(x, y, w, h, size):
    width, height = size
    if (any(type(value) is not int for value in (x, y, w, h))
            or not (0 <= x and 0 <= y and 1 <= w <= width - x and 1 <= h <= height - y)):
        raise ValueError('Keep each widget inside the display.')


def _validate_drawing(supplied, size):
    box = {}
    w, h = size
    if any(key in supplied for key in BOX_KEYS):
        box = {key: supplied.get(key) for key in BOX_KEYS}
        _validate_box(**box, size=size)
        w, h = box['w'], box['h']
    return {'type': 'drawing', **box, 'bitmap': _validate_bitmap(supplied.get('bitmap'), w, h)}


def _validate_placement(placement, size):
    if not isinstance(placement, dict):
        raise ValueError('Keep each widget inside the display.')
    x, y = placement.get('x'), placement.get('y')
    _validate_box(x, y, 1, 1, size)
    scales = {axis: placement.get(axis) for axis in ('scaleX', 'scaleY')}
    if any(type(scale) not in (int, float) or not 1 / MAX_DIMENSION <= scale <= MAX_DIMENSION
           for scale in scales.values()):
        raise ValueError('Keep each widget inside the display.')
    normalized = {'x': x, 'y': y, **scales}
    if 'referenceWidth' in placement:
        width = placement['referenceWidth']
        if type(width) is not int or not 1 <= width <= size[0] - x:
            raise ValueError('Keep each widget inside the display.')
        normalized['referenceWidth'] = width
    return normalized


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


def validate_layout(screen, layout, size=PANEL_SIZE):
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
            normalized.append(_validate_drawing(supplied, size))
            continue
        definition = widgets.get(supplied['type'])
        if definition is None:
            raise ValueError('This widget is unavailable on this screen.')
        template = definition['template']
        if size != PANEL_SIZE and not all(key in supplied for key in BOX_KEYS):
            template = resize_layer(template, PANEL_SIZE, size)
        widget = {key: supplied.get(key, value) for key, value in template.items()}
        _validate_box(*(widget[key] for key in BOX_KEYS), size=size)
        if 'placement' in supplied:
            widget['placement'] = _validate_placement(supplied['placement'], size)
        if widget['type'] == 'clock':
            if widget['variant'] in ('stacked', 'analog'):
                widget['clockStyle'], widget['variant'] = widget['variant'], '24h'
            if widget['clockStyle'] not in tuple(style for style, _ in CLOCK_STYLES):
                raise ValueError('Choose an available widget style.')
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
            if type(thickness) is not int or not 1 <= thickness <= MAX_DIMENSION:
                raise ValueError('Choose a valid divider thickness.')
            widget['thickness'] = thickness
        custom_format = definition.get('customFormat')
        if custom_format and (widget['variant'] == 'custom' or 'format' in supplied):
            pattern = supplied.get('format', custom_format)
            if (not isinstance(pattern, str) or not 1 <= len(pattern) <= 64
                    or not pattern.isprintable() or not pattern.strip()):
                message = ('Enter a date format with 1–64 characters.' if widget['type'] == 'date'
                           else 'Enter a time format with 1–64 characters.')
                raise ValueError(message)
            widget['format'] = pattern
        if 'mask' in supplied:
            mask = supplied['mask']
            if not isinstance(mask, dict):
                raise ValueError('The drawing is invalid.')
            w, h = mask.get('w'), mask.get('h')
            _validate_box(0, 0, w, h, (MAX_DIMENSION, MAX_DIMENSION))
            widget['mask'] = {'w': w, 'h': h, 'bitmap': _validate_bitmap(mask.get('bitmap'), w, h)}
        if widget['type'] == 'photo':
            photo = supplied.get('photo')
            if not isinstance(photo, dict):
                raise ValueError('Import a photo first.')
            w, h = photo.get('w'), photo.get('h')
            _validate_box(0, 0, w, h, (PHOTO_SIZE, PHOTO_SIZE))
            widget['photo'] = {'w': w, 'h': h, 'bitmap': _validate_bitmap(photo.get('bitmap'), w, h)}
            crop = supplied.get('crop', [0, 0, w, h])
            if not isinstance(crop, (list, tuple)) or len(crop) != 4:
                raise ValueError('Choose a valid crop inside the photo.')
            try:
                _validate_box(*crop, size=(w, h))
            except ValueError as error:
                raise ValueError('Choose a valid crop inside the photo.') from error
            widget['crop'] = list(crop)
        normalized.append(widget)
    if len(normalized) - drawings > MAX_WIDGETS:
        raise ValueError(f'Use up to {MAX_WIDGETS} widgets per layout.')
    return normalized


def resize_layer(layer, source_size, target_size):
    source_w, source_h = source_size
    target_w, target_h = target_size
    scale_x, scale_y = target_w / source_w, target_h / source_h
    x, y = layer.get('x', 0), layer.get('y', 0)
    w, h = layer.get('w', source_w), layer.get('h', source_h)
    left = min(target_w - 1, round(x * scale_x))
    top = min(target_h - 1, round(y * scale_y))
    width = max(1, round((x + w) * scale_x) - left)
    height = max(1, round((y + h) * scale_y) - top)
    resized = {**layer, 'x': left, 'y': top, 'w': width, 'h': height}
    if layer['type'] == 'drawing':
        pixels = _drawing_mask(layer['bitmap'], w, h).resize((width, height), Image.Resampling.NEAREST)
        resized['bitmap'] = b64encode(pixels.tobytes()).decode()
    else:
        resized['size'] = min(60, max(8, round(layer['size'] * min(scale_x, scale_y))))
        if 'placement' in layer:
            placement = layer['placement']
            resized['placement'] = {**placement,
                                    'x': min(target_w - 1, round(placement['x'] * scale_x)),
                                    'y': min(target_h - 1, round(placement['y'] * scale_y))}
            if 'referenceWidth' in placement:
                available = target_w - resized['placement']['x']
                resized['placement']['referenceWidth'] = min(available, max(1, round(placement['referenceWidth'] * scale_x)))
        if layer['type'] == 'divider':
            scale, limit = (scale_x, width) if layer['variant'] == 'vertical' else (scale_y, height)
            thickness = min(limit, max(1, round(layer.get('thickness', 1) * scale)))
            if thickness != 1 or 'thickness' in layer:
                resized['thickness'] = thickness
    return resized


def resize_layout(layout, source_size, target_size):
    if layout is None or source_size == target_size:
        return layout
    return [resize_layer(layer, source_size, target_size) for layer in layout]


def format_date(now, pattern, language):
    from dashboard import MONTHS, WEEKDAYS, WEEKDAYS_CS

    weekday, month = now.weekday(), now.month - 1
    short_days, short_months = (WEEKDAYS_CS, MONTHS_SHORT_CS) if language == 'cs' else (WEEKDAYS, MONTHS)
    values = {
        'YYYY': f'{now.year:04}', 'YY': f'{now.year % 100:02}',
        'MMMM': MONTHS_LONG[language][month], 'MMM': short_months[month],
        'MM': f'{now.month:02}', 'M': str(now.month),
        'dddd': WEEKDAYS_LONG[language][weekday], 'ddd': short_days[weekday],
        'DD': f'{now.day:02}', 'D': str(now.day),
    }
    values.update(yyyy=values['YYYY'], yy=values['YY'], dd=values['DD'], d=values['D'])
    return DATE_TOKENS.sub(lambda match: match[1] if match[1] is not None else values[match[0]], pattern)


def _date(now, widget, language):
    variant = widget['variant']
    if variant == 'custom':
        return format_date(now, widget.get('format', CUSTOM_FORMATS['date']), language)
    if variant in DATE_FORMATS:
        return format_date(now, DATE_FORMATS[variant][1], language)
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


def format_clock(now, pattern):
    hour = now.hour % 12 or 12
    suffix = 'AM' if now.hour < 12 else 'PM'
    values = {'HH': f'{now.hour:02}', 'H': str(now.hour), 'hh': f'{hour:02}', 'h': str(hour),
              'mm': f'{now.minute:02}', 'm': str(now.minute), 'ss': f'{now.second:02}',
              's': str(now.second), 'A': suffix, 'a': suffix.lower()}
    values.update(MM=values['mm'], SS=values['ss'])
    return TIME_TOKENS.sub(lambda match: match[1] if match[1] is not None else values[match[0]], pattern)


def clock_has_seconds(widget):
    if widget['type'] != 'clock' or _clock_style(widget) == 'analog':
        return False
    return any(token[0] in SECONDS_TOKENS for token in TIME_TOKENS.finditer(_clock_pattern(widget)))


def _clock_style(widget):
    legacy = widget['variant']
    return legacy if legacy in ('stacked', 'analog') else widget.get('clockStyle', 'digital')


def _clock_pattern(widget):
    variant = widget['variant']
    if variant == 'custom':
        return widget.get('format', CUSTOM_FORMATS['clock'])
    return CLOCK_PATTERNS.get(variant, CLOCK_PATTERNS['24h'])


def _stack_clock_pattern(pattern):
    start = 0
    previous = None
    for token in TIME_TOKENS.finditer(pattern):
        if previous and previous[0][0] in 'HhMmSs' and token[0][0] in 'HhMmSs':
            separator = pattern[previous.end():token.start()]
            if separator and not separator.strip(' :./-'):
                yield pattern[start:previous.end()]
                start = token.start()
        previous = token
    yield pattern[start:]


def _clock(now, widget):
    style = _clock_style(widget)
    if style == 'analog':
        return (now.hour % 12, now.minute)
    pattern = _clock_pattern(widget)
    if style == 'stacked':
        return tuple(format_clock(now, line) for line in _stack_clock_pattern(pattern))
    return format_clock(now, pattern)


def preview_weather(units):
    return (61 if units == 'fahrenheit' else 16, 2, True)


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


def _widget_content(widget, now, weather, track, cover, progress, duration_ms, units, language, weather_enabled):
    kind = widget['type']
    if kind == 'drawing':
        return None
    variant = widget['variant']
    if kind == 'clock':
        return _clock(now, widget)
    if kind == 'date':
        return _date(now, widget, language)
    if kind == 'weather':
        return _temperature_and_icon(now, variant, weather, units, language) if weather_enabled else None
    if kind == 'text':
        return widget['text']
    if kind == 'title':
        return track.title if track is not None else ('Nic se nepřehrává' if language == 'cs' else 'Nothing playing')
    if kind == 'artist':
        return getattr(track, kind, '')
    if kind == 'cover':
        return id(cover)
    if kind == 'progress':
        return round(progress * _progress_steps(widget))
    if kind == 'playback-time':
        return _playback_time(progress, duration_ms, variant) if duration_ms else '—'
    return None


def content_key(layout, now, weather, track, cover, progress, *, duration_ms=0,
                units='celsius', language='en', weather_enabled=True):
    """Return the dynamic values that can change the rendered pixels."""
    progress = min(1.0, max(0.0, progress))
    return tuple(_widget_content(widget, now, weather, track, cover, progress, duration_ms,
                                 units, language, weather_enabled) for widget in layout)


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
    if _clock_style(widget) != 'analog':
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


def _contain(image, w, h, resample=Image.Resampling.NEAREST):
    scale = min(w / image.width, h / image.height)
    size = max(1, round(image.width * scale)), max(1, round(image.height * scale))
    return image.resize(size, resample)


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


def _widget_layers(layout, now, language, weather, units, track, cover, progress, duration_ms, size,
                   weather_enabled):
    """Yield a widget's offset, pixel data and whether it is opaque art."""
    values = content_key(layout, now, weather, track, cover, progress, duration_ms=duration_ms,
                         units=units, language=language, weather_enabled=weather_enabled)
    for widget, value in zip(layout, values):
        kind = widget['type']
        if kind == 'weather' and value is None:
            yield (0, 0), None, False
            continue
        if kind == 'drawing':
            yield (0, 0), _drawing_mask(widget['bitmap'], widget.get('w', size[0]), widget.get('h', size[1])), False
            continue
        w, h = widget['w'], widget['h']
        if kind in ('cover', 'photo'):
            source = cover
            resample = Image.Resampling.NEAREST
            if kind == 'photo':
                photo = widget['photo']
                x, y, crop_w, crop_h = widget['crop']
                source = _drawing_mask(photo['bitmap'], photo['w'], photo['h'])
                source = source.crop((x, y, x + crop_w, y + crop_h)).convert('L')
                resample = Image.Resampling.LANCZOS
            art = None
            if source is not None:
                art = (ImageOps.fit(source, (w, h), resample)
                       if widget['variant'] == 'fill' else _contain(source, w, h, resample))
                if kind == 'photo':
                    art = art.convert('1')
            offset = ((w - art.width) // 2, (h - art.height) // 2) if art is not None else (0, 0)
            yield offset, art, True
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
        yield (0, 0), mask, False


def _source_bounds(layer, offset, opaque):
    if layer is None:
        return None
    if opaque:
        bounds = layer.getchannel('A').getbbox() if layer.mode == 'RGBA' else (0, 0, *layer.size)
    else:
        bounds = layer.getbbox()
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    return offset[0] + left, offset[1] + top, right - left, bottom - top


@lru_cache(maxsize=32)
def _weather_sample_width(w, h, variant, font, size, align, value):
    mask = Image.new('1', (w, h))
    _draw_weather(mask, {'variant': variant, 'font': font, 'size': size, 'align': align}, value)
    bounds = mask.getbbox()
    return bounds[2] - bounds[0] if bounds else w


def _scaled_extent(length, scale, limit):
    return min(limit, max(1, floor(length * scale + .5)))


def _placement_left(widget, width, limit, now, units, language):
    placement = widget['placement']
    x = placement['x']
    align = widget['align']
    if align == 'left':
        return min(x, limit - width)
    reference = placement.get('referenceWidth')
    if reference is None and widget['type'] == 'weather':
        # Older placements stored the left edge measured with the editor's sample weather.
        sample = _temperature_and_icon(now, widget['variant'], preview_weather(units), units, language)
        sample_width = _weather_sample_width(widget['w'], widget['h'], widget['variant'], widget['font'],
                                             widget['size'], align, sample)
        reference = _scaled_extent(sample_width, placement['scaleX'], limit)
    if reference is not None:
        x += floor((reference - width) / (2 if align == 'center' else 1) + .5)
    return max(0, min(x, limit - width))


def render_custom(layout, now, theme, language, *, weather=None, units='celsius', track=None,
                  cover=None, progress=0.0, duration_ms=0, size=PANEL_SIZE, weather_enabled=True):
    """Draw widgets back to front, using their boxes to clip every layer."""
    foreground = int(theme == 'dark')
    image = Image.new('1', size, 1 - foreground)
    layers = _widget_layers(layout, now, language, weather, units, track, cover, progress, duration_ms, size,
                            weather_enabled)
    for widget, (offset, layer, opaque) in zip(layout, layers):
        if layer is None:
            continue
        dx, dy = offset
        position = (widget.get('x', 0) + dx, widget.get('y', 0) + dy)
        placement = widget.get('placement')
        bounds = _source_bounds(layer, offset, opaque) if placement is not None else None
        layer = _apply_erasure(widget, layer, offset, art=opaque)
        if placement is not None:
            if bounds is None:
                continue
            left, top, w, h = bounds
            left, top = left - dx, top - dy
            width = _scaled_extent(w, placement['scaleX'], size[0])
            height = _scaled_extent(h, placement['scaleY'], size[1])
            position = (_placement_left(widget, width, size[0], now, units, language),
                        min(placement['y'], size[1] - height))
            layer = layer.crop((left, top, left + w, top + h)).resize((width, height), Image.Resampling.NEAREST)
        if opaque:
            alpha = layer.getchannel('A') if layer.mode == 'RGBA' else None
            image.paste(layer, position, alpha)
        else:
            image.paste(foreground, position, layer)
    return bytearray(image.convert('L').tobytes().translate(PIXEL_BITS))


def render_layer_atlas(layout, now, theme, language, *, weather=None, units='celsius', track=None,
                       cover=None, progress=0.0, duration_ms=0, size=PANEL_SIZE, weather_enabled=True,
                       geometry=None):
    """Put untransformed widget sources in slots below one background pixel."""
    foreground = 255 if theme == 'dark' else 0
    background = 255 - foreground
    width, height = size
    atlas = Image.new('RGBA', (width, 1 + height * len(layout)))
    atlas.putpixel((0, 0), (background, background, background, 255))
    layers = _widget_layers(layout, now, language, weather, units, track, cover, progress, duration_ms, size,
                            weather_enabled)
    for index, (widget, ((x, y), layer, opaque)) in enumerate(zip(layout, layers)):
        if geometry is not None:
            geometry.append(_source_bounds(layer, (x, y), opaque))
        if layer is None:
            continue
        layer = _apply_erasure(widget, layer, (x, y), art=opaque)
        position = (x, y + 1 + height * index)
        if opaque:
            atlas.paste(layer.convert('RGBA'), position)
        else:
            atlas.paste((foreground, foreground, foreground, 255), position, layer)
    return atlas
