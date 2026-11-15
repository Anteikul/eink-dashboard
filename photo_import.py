"""Convert an uploaded photo to a bounded grayscale source for the editor."""
import shutil
import subprocess
from base64 import b64encode
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageOps

PHOTO_SIZE = 600
PHOTO_UPLOAD_LIMIT = 16 * 1024 * 1024
PHOTO_PIXEL_LIMIT = 55_000_000
PHOTO_FORMATS = ('JPEG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF')
HEIF_BRANDS = (b'heic', b'heix', b'heim', b'heis', b'hevc', b'hevx', b'hevm', b'hevs', b'mif1', b'msf1')
BAD_PHOTO = 'Could not open the photo. Choose a supported image file.'


def _heif_png(data):
    decoder = shutil.which('heif-thumbnailer')
    sips = shutil.which('sips')
    if not decoder and not sips:
        raise ValueError('HEIC support is missing. Run the dashboard installer to add it.')
    with TemporaryDirectory(prefix='eink-photo-') as folder:
        source = Path(folder) / 'source.heic'
        png = Path(folder) / 'photo.png'
        source.write_bytes(data)
        if decoder:
            command = [decoder, '-p', '-s', str(PHOTO_SIZE), str(source), str(png)]
        else:
            properties = subprocess.run([sips, '-g', 'pixelWidth', '-g', 'pixelHeight', str(source)],
                                        check=True, timeout=5, capture_output=True, text=True)
            dimensions = [int(line.split(':', 1)[1]) for line in properties.stdout.splitlines()
                          if line.strip().startswith(('pixelWidth:', 'pixelHeight:'))]
            resize = ['-Z', str(PHOTO_SIZE)] if max(dimensions, default=PHOTO_SIZE) > PHOTO_SIZE else []
            command = [sips, *resize, '-s', 'format', 'png', str(source), '--out', str(png)]
        subprocess.run(command, check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return png.read_bytes()


def prepare_photo(data):
    if not 0 < len(data) <= PHOTO_UPLOAD_LIMIT:
        raise ValueError('Choose an image file up to 16 MB.')
    try:
        if data[4:8] == b'ftyp' and data[8:12] in HEIF_BRANDS:
            data = _heif_png(data)
        with Image.open(BytesIO(data), formats=PHOTO_FORMATS) as original:
            if original.width * original.height > PHOTO_PIXEL_LIMIT:
                raise ValueError('Choose a photo under 55 megapixels.')
            original.thumbnail((PHOTO_SIZE, PHOTO_SIZE), Image.Resampling.LANCZOS, reducing_gap=2)
            with ImageOps.exif_transpose(original) as photo:
                if 'A' in photo.getbands() or 'transparency' in photo.info:
                    rgba = photo.convert('RGBA')
                    photo = Image.alpha_composite(Image.new('RGBA', rgba.size, 'white'), rgba)
                # Preserve the tones until the crop reaches the panel resolution.
                gray = photo.convert('L')
                return {'w': gray.width, 'h': gray.height, 'gray': b64encode(gray.tobytes()).decode()}
    except (OSError, SyntaxError, Image.DecompressionBombError, subprocess.SubprocessError) as error:
        raise ValueError(BAD_PHOTO) from error
