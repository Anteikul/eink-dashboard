from datetime import datetime
from pathlib import Path

from PIL import Image

from dashboard import ROW_BYTES, WIDTH, changed_regions, pack, render, needs_full_refresh

folder = Path(__file__).parent
before = render(datetime(2026, 11, 9, 19, 23), (4, 3, False))
same_minute = render(datetime(2026, 11, 9, 19, 23, 59), (4, 3, False))
assert before == same_minute
assert render(datetime(2025, 11, 10, 19, 23), (4, 3, False)) != before
assert render(datetime(2026, 11, 9, 19, 23), (4, 3, False), 'dark') == bytearray(1 - p for p in before)
assert needs_full_refresh(None, 'light', 0)
assert needs_full_refresh('light', 'dark', 0)
assert not needs_full_refresh('dark', 'dark', 4)
assert needs_full_refresh('dark', 'dark', 5)

for rotation, turn in ((0, Image.Transpose.ROTATE_90), (180, Image.Transpose.ROTATE_270)):
    expected = Image.frombytes('L', (250, 122), bytes(p * 255 for p in before)).convert('1').transpose(turn)
    old = pack(before, rotation)
    assert Image.frombytes('1', (122, 250), old).tobytes() == expected.tobytes()
    assert changed_regions(old, old) == []
    for dt, weather in (
        (datetime(2026, 11, 9, 19, 24), (4, 3, False)),
        (datetime(2026, 11, 9, 19, 23), (-12, 61, False)),
        (datetime(2026, 11, 9, 19, 23), (4, 61, False)),
        (datetime(2026, 11, 10, 0, 0), (4, 3, False)),
    ):
        new = pack(render(dt, weather), rotation)
        regions = changed_regions(old, new)
        restored = bytearray(old)
        for region in regions:
            data = region.extract(new)
            width = region.last_byte - region.first_byte + 1
            for index, row in enumerate(range(region.first_row, region.last_row + 1)):
                start = row * ROW_BYTES + region.first_byte
                restored[start:start+width] = data[index*width:(index+1)*width]
        assert restored == new
        assert regions
        assert sum(len(region.extract(new)) for region in regions) < 1500
    one_digit = pack(render(datetime(2026, 11, 9, 19, 24), (4, 3, False)), rotation)
    assert sum(len(region.extract(one_digit)) for region in changed_regions(old, one_digit)) < 200

for theme in ('light', 'dark'):
    screen = render(datetime(2026, 11, 9, 19, 23), (4, 3, False), theme)
    preview = Image.frombytes('L', (250, 122), bytes(p * 255 for p in screen))
    preview.resize((750, 366), Image.Resampling.NEAREST).save(folder / f'preview-{theme}.png')
print('Clock, date, weather, theme, rotation and partial windows passed.')

now = datetime(2026, 11, 9, 19, 23)
conditions = ((0, True), (0, False), (2, True), (2, False), (3, False), (45, False),
              (61, False), (71, False), (95, False))
icons = set()
for code, is_day in conditions:
    screen = render(now, (4, code, is_day))
    icon = bytes(screen[y * WIDTH + x] for y in range(21, 55) for x in range(162, WIDTH))
    assert 0 in icon
    assert render(now, (4, code, is_day), 'dark') == bytearray(1 - pixel for pixel in screen)
    icons.add(icon)
assert len(icons) == len(conditions)
cloud = render(now, (4, 3, False))
rain = render(now, (4, 61, False))
assert all(cloud[y * WIDTH + x] for y in range(85, 122) for x in range(162, WIDTH))
for y in range(122):
    assert cloud[y*WIDTH:y*WIDTH+162] == rain[y*WIDTH:y*WIDTH+162]
for rotation in (0, 180):
    old = pack(cloud, rotation)
    new = pack(rain, rotation)
    assert all(
        region.first_row > 161 if rotation == 180 else region.last_row < 88
        for region in changed_regions(old, new)
    )
print('Weather icons differ by condition and stay within the weather region.')
