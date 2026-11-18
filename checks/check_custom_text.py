"""Custom text grows beyond its initial box without losing lines or adding ellipses."""
from base64 import b64encode
from datetime import datetime, timezone

from PIL import Image, ImageChops, ImageDraw, ImageOps

from layout_editor import render_custom, render_layer_atlas, resize_layer, validate_layout
from music_screen import font


NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)
SIZE = (250, 122)
FACE = font(16, mono=True)


def expected_lines(lines):
    image = Image.new('1', SIZE)
    draw = ImageDraw.Draw(image)
    for index, line in enumerate(lines):
        draw.text((-FACE.getbbox(line)[0], index * 18), line, font=FACE, fill=1)
    return image.crop(image.getbbox()).convert('L')


def check_text(value, lines, *, variant='wrapped', placed=False):
    widget = {'type': 'text', 'text': value, 'variant': variant,
              'x': 7, 'y': 9, 'w': 52, 'h': 18, 'size': 16, 'font': 'mono'}
    if placed:
        widget['placement'] = {'x': 7, 'y': 9, 'scaleX': 1, 'scaleY': 1}
    layout = validate_layout('dashboard', [widget])
    pixels = render_custom(layout, NOW, 'light', 'en')
    actual = ImageOps.invert(Image.frombytes('L', SIZE, bytes(pixels)).point([0, 255] + [255] * 254))
    bounds = actual.getbbox()
    expected = expected_lines(lines)
    assert bounds and actual.crop(bounds).size == expected.size, (value, bounds, expected.size)
    assert ImageChops.difference(actual.crop(bounds), expected).getbbox() is None, value

    # The editor consumes an atlas, while the device consumes render_custom.
    geometry = []
    atlas = render_layer_atlas(layout, NOW, 'light', 'en', geometry=geometry)
    x, y, w, h = geometry[0]
    tile = atlas.crop((x, 1 + y, x + w, 1 + y + h)).getchannel('A')
    assert tile.size == expected.size and ImageChops.difference(tile, expected).getbbox() is None
    return layout, bounds


for placed in (False, True):
    check_text('AAAA BBBB CCCC', ['AAAA', 'BBBB', 'CCCC'], placed=placed)
    check_text('AAAA\nBBBB\nCCCC', ['AAAA', 'BBBB', 'CCCC'], placed=placed)
    check_text('AAAA\n\nCCCC', ['AAAA', '', 'CCCC'], placed=placed)
    check_text('AAAA\r\nBBBB', ['AAAA', 'BBBB'], placed=placed)
    check_text('ABCDEFGHIJKLMNO', ['ABCDEFGHIJKLMNO'], variant='single', placed=placed)
    check_text('AAAA\nBBBB', ['AAAA', 'BBBB'], variant='single', placed=placed)

# Moving a layer must not change the cached, untransformed source.
widget = validate_layout('dashboard', [{'type': 'text', 'text': 'AAAA\nBBBB\nCCCC',
                                      'x': 7, 'y': 100, 'w': 52, 'h': 18, 'font': 'mono'}])[0]
before = render_layer_atlas([widget], NOW, 'light', 'en')
moved = {**widget, 'placement': {'x': 7, 'y': 9, 'scaleX': 1, 'scaleY': 1}}
after = render_layer_atlas([moved], NOW, 'light', 'en')
assert before.tobytes() == after.tobytes(), 'Moving text changed its cached source'

# The eraser must reach grown rows, preserving the mask in source coordinates.
erased = Image.new('1', SIZE)
ImageDraw.Draw(erased).rectangle((0, 36, 249, 121), fill=1)
mask = {'w': 250, 'h': 122, 'bitmap': b64encode(erased.tobytes()).decode(), 'space': 'source'}
masked = {**moved, 'mask': mask}
assert validate_layout('dashboard', [masked])[0]['mask'] == mask
atlas = render_layer_atlas([masked], NOW, 'light', 'en')
assert atlas.getchannel('A').crop((0, 1 + 36, 250, 123)).getbbox() is None
assert atlas.getchannel('A').crop((0, 1, 250, 1 + 36)).getbbox() is not None
resized = resize_layer(masked, SIZE, (125, 61))
assert (resized['mask']['w'], resized['mask']['h']) == (125, 61)
atlas = render_layer_atlas([resized], NOW, 'light', 'en', size=(125, 61))
assert atlas.getchannel('A').crop((0, 1 + 18, 125, 62)).getbbox() is None

# Old saved masks scale to the original text box, including after a resolution change.
old_mask = Image.new('1', (26, 9), 1)
legacy = {**moved, 'mask': {'w': 26, 'h': 9, 'bitmap': b64encode(old_mask.tobytes()).decode()}}
atlas = render_layer_atlas([legacy], NOW, 'light', 'en')
assert atlas.getchannel('A').crop((0, 1, 250, 1 + 18)).getbbox() is None
assert atlas.getchannel('A').crop((0, 1 + 18, 250, 123)).getbbox() is not None

print('Custom text wrapping, manual line breaks, movement and erasure OK')
