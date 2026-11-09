from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from PIL import Image

import music_screen


with TemporaryDirectory() as temporary:
    root = Path(temporary)
    source = root / 'album.jpg'
    Image.new('RGB', (96, 96), 'red').save(source)
    generated = Image.new('1', (96, 96), 1)
    generated.putpixel((12, 12), 0)

    with patch.object(music_screen, 'CACHE_ROOT', root / 'cache'):
        with patch.object(music_screen, 'dither_cover', return_value=(generated, 'DETAIL')) as build:
            first, method = music_screen.local_cover(source, source.stat().st_mtime_ns)
            assert first.tobytes() == generated.tobytes()
            assert method == 'DETAIL'
            assert build.call_count == 1

        music_screen._cached_cover.cache_clear()
        with patch.object(music_screen, 'dither_cover', side_effect=AssertionError('Unexpected regeneration')):
            reused, method = music_screen.local_cover(source, source.stat().st_mtime_ns)
            assert reused.tobytes() == first.tobytes()
            assert method == 'DETAIL'

        with patch.object(music_screen, 'download_cover', return_value=(generated, 'DETAIL')) as download:
            url = 'https://i.scdn.co/image/original'
            music_screen.remote_cover(url)
            assert download.call_count == 1

        music_screen._cached_cover.cache_clear()
        with patch.object(music_screen, 'download_cover', side_effect=AssertionError('Unexpected download')):
            music_screen.remote_cover(url, 'album-id')
            reused = music_screen.remote_cover('https://i.scdn.co/image/another-size', 'album-id')
            assert reused.tobytes() == generated.tobytes()

print('The prepared cover is reused from disk after clearing the process cache.')
