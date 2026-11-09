"""Build the monochrome font atlas used by the Pi."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path('/System/Library/Fonts')
MONO = FONTS / 'Menlo.ttc'
BOLD = FONTS / 'Supplemental/Arial Bold.ttf'
REGULAR = FONTS / 'Supplemental/Arial.ttf'
folder = Path(__file__).parent


def cloud(draw, x=0, y=0):
    draw.ellipse((x+1, y+10, x+15, y+22), fill=1)
    draw.ellipse((x+7, y+4, x+23, y+21), fill=1)
    draw.ellipse((x+17, y+9, x+30, y+22), fill=1)
    draw.rectangle((x+8, y+15, x+23, y+22), fill=1)
    draw.ellipse((x+3, y+12, x+15, y+20), fill=0)
    draw.ellipse((x+9, y+6, x+21, y+20), fill=0)
    draw.ellipse((x+17, y+11, x+28, y+20), fill=0)
    draw.rectangle((x+8, y+15, x+23, y+20), fill=0)


def sun(draw, x, y):
    draw.ellipse((x-6, y-6, x+6, y+6), outline=1, width=2)
    for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
        draw.line((x+9*dx, y+9*dy, x+12*dx, y+12*dy), fill=1, width=2)
    for dx, dy in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        draw.line((x+6*dx, y+6*dy, x+9*dx, y+9*dy), fill=1, width=2)


def moon(draw, x, y):
    draw.ellipse((x-10, y-10, x+10, y+10), fill=1)
    draw.ellipse((x-3, y-12, x+12, y+4), fill=0)


def weather_icon(name):
    image = Image.new('1', (36, 34))
    draw = ImageDraw.Draw(image)
    if name == 'sun':
        sun(draw, 17, 16)
    elif name == 'moon':
        moon(draw, 17, 16)
    elif name in ('partly-sun', 'partly-moon'):
        if name == 'partly-sun':
            sun(draw, 12, 12)
        else:
            moon(draw, 12, 12)
        draw.rounded_rectangle((5, 16, 35, 30), radius=6, fill=0)
        draw.ellipse((11, 10, 30, 29), fill=0)
        cloud(draw, 5, 7)
    elif name == 'fog':
        for x, y, end in ((4, 9, 30), (8, 16, 33), (2, 23, 28)):
            draw.line((x, y, end, y), fill=1, width=2)
    else:
        cloud(draw, 2, 4 if name == 'cloud' else 0)
        if name == 'rain':
            for x in (11, 19, 27):
                draw.line((x, 25, x-3, 31), fill=1, width=2)
        elif name == 'snow':
            for x in (12, 23):
                draw.line((x-3, 28, x+3, 28), fill=1)
                draw.line((x, 25, x, 31), fill=1)
                draw.line((x-2, 26, x+2, 30), fill=1)
                draw.line((x-2, 30, x+2, 26), fill=1)
        elif name == 'storm':
            draw.polygon(((17, 19), (22, 19), (19, 24), (24, 24),
                          (15, 33), (17, 27), (13, 27)), fill=1)
    return [(x, y) for y in range(image.height) for x in range(image.width)
            if image.getpixel((x, y))]


digits = '0123456789:'
czech = 'ěščřžýáíéúůďťňĚŠČŘŽÝÁÍÉÚŮĎŤŇ'
styles = {
    'clock': (MONO, 47, digits),
    'date': (REGULAR, 14, czech + ' .0123456789' + 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'),
    'temperature': (BOLD, 27, '0123456789−°CF—'),
}
atlas = {}
for name, (path, size, chars) in styles.items():
    font = ImageFont.truetype(str(path), size)
    glyphs = {}
    for char in chars:
        left, top, right, bottom = font.getbbox(char, anchor='ls')
        mask = Image.new('1', (right-left, bottom-top))
        if mask.height and mask.width:
            ImageDraw.Draw(mask).text((-left, -top), char, fill=1, font=font, anchor='ls')
        dots = [(x+left, y+top) for y in range(mask.height) for x in range(mask.width)
                if mask.getpixel((x, y))]
        glyphs[char] = (round(font.getlength(char)), dots)
    atlas[name] = glyphs
atlas['weather'] = {
    name: weather_icon(name)
    for name in ('sun', 'moon', 'partly-sun', 'partly-moon', 'cloud', 'fog', 'rain', 'snow', 'storm')
}
(folder / 'atlas.json').write_text(json.dumps(atlas, separators=(',', ':')), encoding='utf-8')
