"""Prepare album images and render the music screen."""
import hashlib
import tempfile
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps, PngImagePlugin

ROOT = Path(__file__).resolve().parent
FONTS = ROOT / '.spotify-runtime/usr/share/fonts/truetype/dejavu'
CACHE_ROOT = ROOT / '.cover-cache'
COVER_VERSION = hashlib.sha256((ROOT / 'album_algorithm.py').read_bytes()).hexdigest()
COVER_LOCKS = tuple(Lock() for _ in range(16))
COVER_TEXT_X = 118
TEXT_X = 13
BAR_RIGHT = 237


@lru_cache(maxsize=64)
def font(size, bold=False, *, mono=False):
    if mono:
        name = 'DejaVuSansMono.ttf'
        fallback = Path('/System/Library/Fonts/Menlo.ttc')
    else:
        name = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
        fallback = Path('/System/Library/Fonts/Supplemental') / ('Arial Bold.ttf' if bold else 'Arial.ttf')
    for path in (FONTS / name, Path('/usr/share/fonts/truetype/dejavu') / name,
                 fallback):
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def fit_lines(value, face, width, count):
    remaining = ' '.join(value.split())
    lines = []
    for row in range(count):
        if not remaining:
            break
        if face.getlength(remaining) <= width:
            lines.append(remaining)
            break
        suffix = '…' if row == count - 1 else ''
        end = 1
        while end < len(remaining) and face.getlength(remaining[:end + 1] + suffix) <= width:
            end += 1
        if not suffix and ' ' in remaining[:end]:
            end = remaining.rfind(' ', 0, end)
        lines.append(remaining[:end].rstrip() + suffix)
        remaining = remaining[end:].lstrip()
    return lines


def dither_cover(original):
    import album_algorithm as algorithm

    size = (algorithm.COVER_SIZE, algorithm.COVER_SIZE)
    square = ImageOps.pad(original.convert('RGB'), size, Image.Resampling.LANCZOS, color='white')
    base = algorithm.prepare_base_cover(square)
    variants = {name: algorithm.process_cover(base, name) for name in algorithm.MODES}
    scores = {name: algorithm.score_variant(base, image) for name, image in variants.items()}
    mode, *_ = algorithm.choose_best_mode(scores)
    return variants[mode], mode


def download_cover(url):
    limit = 2 * 1024 * 1024
    with urlopen(url, timeout=5) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Album image too large')
    with Image.open(BytesIO(data)) as original:
        if max(original.size) > 2048:
            raise ValueError('Album image dimensions too large')
        return dither_cover(original)


def cover_cache_path(source, modified):
    key = repr((1, COVER_VERSION, str(source), modified)).encode()
    return CACHE_ROOT / (hashlib.sha256(key).hexdigest() + '.png')


@lru_cache(maxsize=32)
def _cached_cover(source, modified, album_id=''):
    original_path = cover_cache_path(source, modified)
    path = cover_cache_path(album_id, 'spotify-album') if album_id else original_path
    for stored in dict.fromkeys((path, original_path)):
        try:
            with Image.open(stored) as cached:
                if cached.mode != '1' or cached.size != (96, 96):
                    continue
                image, mode = cached.copy(), cached.info.get('algorithm', 'cached')
        except (OSError, ValueError):
            continue
        if stored != path:
            try:
                path.hardlink_to(stored)
            except OSError:
                pass
        return image, mode

    if isinstance(source, Path):
        with Image.open(source) as original:
            image, mode = dither_cover(original)
    else:
        image, mode = download_cover(source)

    try:
        CACHE_ROOT.mkdir(mode=0o700, exist_ok=True)
        info = PngImagePlugin.PngInfo()
        info.add_text('algorithm', mode)
        with tempfile.NamedTemporaryFile(dir=CACHE_ROOT, delete=False) as staged:
            temporary = Path(staged.name)
            try:
                image.save(staged, format='PNG', pnginfo=info)
                staged.flush()
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
    except OSError:
        print('Album cover could not be saved to disk', flush=True)
    return image, mode


def local_cover(path, modified):
    lock = COVER_LOCKS[hash((path, modified)) % len(COVER_LOCKS)]
    with lock:
        return _cached_cover(path, modified)


def remote_cover(url, album_id=''):
    lock = COVER_LOCKS[hash(album_id or url) % len(COVER_LOCKS)]
    with lock:
        return _cached_cover(url, None, album_id)[0]


def prepare_cover(track):
    try:
        if track.album_id:
            path = ROOT / 'covers' / f'{track.album_id}.jpg'
            if path.is_file():
                return local_cover(path, path.stat().st_mtime_ns)[0]
        if track.artwork:
            return remote_cover(track.artwork, track.album_id)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        print(f'Album cover unavailable ({type(error).__name__})', flush=True)
    return None


def progress_pixels(progress, cover):
    x = COVER_TEXT_X if cover is not None else TEXT_X
    return round((BAR_RIGHT - x - 1) * progress)


def render_music(track, theme, cover, filled):
    foreground, background = (1, 0) if theme == 'dark' else (0, 1)
    image = Image.new('1', (250, 122), background)
    draw = ImageDraw.Draw(image)
    if cover is not None:
        image.paste(cover, (10, 13))
    x = COVER_TEXT_X if cover is not None else TEXT_X
    width = BAR_RIGHT + 1 - x
    title_font = font(17 if cover is not None else 23, True)
    artist_font = font(12 if cover is not None else 15)
    y = 20
    for line in fit_lines(track.title, title_font, width, 3 if cover is not None else 2):
        draw.text((x, y), line, fill=foreground, font=title_font, anchor='lt')
        y += 19 if cover is not None else 26
    for line in fit_lines(track.artist, artist_font, width, 1 if y > 68 else 2):
        draw.text((x, y + 5), line, fill=foreground, font=artist_font, anchor='lt')
        y += 15
    draw.rectangle((x, 104, BAR_RIGHT, 107), outline=foreground)
    if filled:
        draw.rectangle((x + 1, 105, x + filled, 106), fill=foreground)
    return bytearray(1 if pixel else 0 for pixel in image.getdata())
