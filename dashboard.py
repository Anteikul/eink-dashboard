"""Clock and current Prague weather for a Waveshare 2.13-inch V4."""
import argparse
import fcntl
import json
import signal
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from itertools import groupby
from math import ceil
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from control import PanelState, preview_png, start_server
from device_settings import DeviceSettings
from layout_editor import PANEL_SIZE, clock_has_seconds, content_key, editor_schema, render_custom, render_layer_atlas
from local_name import LocalName
from spotify_playback import SpotifyPlayback, Track
from wifi_setup import AP_ADDRESS, Link, NetworkSetup

WIDTH, HEIGHT = PANEL_SIZE
ROW_BYTES = (HEIGHT + 7) // 8
JOIN_CONFIRM_SECONDS = 15
WEEKDAYS = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
WEEKDAYS_CS = ('Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne')
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
FOLDER = Path(__file__).resolve().parent
ATLAS = json.loads((FOLDER / 'atlas.json').read_text(encoding='utf-8'))


def weather_icon(code, is_day):
    if code == 0:
        return 'sun' if is_day else 'moon'
    if code <= 2:
        return 'partly-sun' if is_day else 'partly-moon'
    if code == 3:
        return 'cloud'
    if code in (45, 48):
        return 'fog'
    if code in (71, 73, 75, 77, 85, 86):
        return 'snow'
    if code >= 95:
        return 'storm'
    return 'rain'


def label(image, x, baseline, text, style, *, centered=False):
    glyphs = [ATLAS[style][char] for char in text]
    if centered:
        x -= sum(advance for advance, _ in glyphs) // 2
    for advance, dots in glyphs:
        for dx, dy in dots:
            image[(baseline + dy) * WIDTH + x + dx] = 0
        x += advance


def screen_content(now, weather, units='celsius', language='en'):
    if language == 'cs':
        day = f'{WEEKDAYS_CS[now.weekday()]} {now.day}. {now.month}. {now.year}'
    else:
        day = f'{WEEKDAYS[now.weekday()]} {now.day} {MONTHS[now.month - 1]} {now.year}'
    if weather is None:
        temperature, icon = '—', None
    else:
        degrees, code, is_day = weather
        unit = 'F' if units == 'fahrenheit' else 'C'
        temperature = f'{degrees}°{unit}'.replace('-', '−')
        icon = weather_icon(code, is_day)
    return now.strftime('%H:%M'), day, temperature, icon


def render(now, weather, theme='light', units='celsius', language='en'):
    clock, day, temperature, icon = screen_content(now, weather, units, language)
    image = bytearray(b'\x01' * (WIDTH * HEIGHT))
    for y in range(30, 95):
        image[y * WIDTH + 161] = 0
    label(image, 10, 69, clock, 'clock')
    label(image, 12, 92, day, 'date')
    label(image, 206, 84, temperature, 'temperature', centered=True)
    if icon:
        for x, y in ATLAS['weather'][icon]:
            image[(21 + y) * WIDTH + 188 + x] = 0
    return bytearray(1 - pixel for pixel in image) if theme == 'dark' else image


@lru_cache(maxsize=1)
def sample_cover():
    from PIL import Image, ImageDraw

    cover = Image.new('1', (96, 96), 0)
    draw = ImageDraw.Draw(cover)
    draw.ellipse((12, 12, 83, 83), fill=1)
    draw.polygon(((0, 86), (35, 37), (63, 68), (74, 56), (95, 83), (95, 95), (0, 95)), fill=0)
    draw.line(((0, 86), (35, 37), (63, 68), (74, 56), (95, 83)), fill=1, width=2)
    return cover


@lru_cache(maxsize=4)
def canvas_defaults(size):
    return editor_schema(size)['defaults']


def fit_panel(pixels, size, theme):
    if size == PANEL_SIZE:
        return pixels
    from PIL import Image, ImageOps

    source = Image.frombytes('L', size, bytes(pixels))
    resized = ImageOps.contain(source, PANEL_SIZE, Image.Resampling.NEAREST)
    panel = Image.new('L', PANEL_SIZE, int(theme == 'light'))
    panel.paste(resized, ((WIDTH - resized.width) // 2, (HEIGHT - resized.height) // 2))
    return bytearray(panel.tobytes())


def render_layout_preview(screen, layout, theme, language, units, *, layers=False, size=PANEL_SIZE):
    from io import BytesIO
    from music_screen import progress_pixels, render_music

    now = datetime(2026, 11, 10, 14, 38, 27)
    weather = (16 if units == 'celsius' else 61, 2, True)
    music = screen == 'playback'
    sample = {'weather': weather, 'units': units, 'size': size}
    if music:
        sample.update(track=Track('preview', 'Night Drive', 'The Midnight'), cover=sample_cover(),
                      progress=0.42, duration_ms=242_000)
    if layers:
        atlas = render_layer_atlas(layout, now, theme, language, **sample)
        with BytesIO() as png:
            atlas.save(png, format='PNG')
            return png.getvalue()
    if layout is None and size != PANEL_SIZE:
        layout = canvas_defaults(size)[screen]
    if layout is not None:
        pixels = render_custom(layout, now, theme, language, **sample)
    elif music:
        track, cover, progress = (sample[key] for key in ('track', 'cover', 'progress'))
        pixels = render_music(track, theme, cover, progress_pixels(progress, cover))
    else:
        pixels = render(now, weather, theme, units, language)
    return preview_png(pixels, *size)


def render_wifi(hotspot, theme='light', language='en'):
    from PIL import Image, ImageDraw
    from music_screen import font

    image = Image.new('1', (WIDTH, HEIGHT), theme == 'light')
    draw = ImageDraw.Draw(image)
    ink = int(theme == 'dark')
    title, password = ('Nastavení Wi-Fi', 'Heslo') if language == 'cs' else ('Wi-Fi setup', 'Password')
    draw.text((12, 7), title, font=font(21, bold=True), fill=ink)
    for radius in (8, 15, 22):
        draw.arc((217 - radius, 31 - radius, 217 + radius, 31 + radius),
                 224, 316, fill=ink, width=2)
    draw.ellipse((215, 29, 219, 33), fill=ink)
    draw.line((12, 40, 238, 40), fill=ink)
    for y, text in ((47, f'Wi-Fi: {hotspot.ssid}'),
                    (71, f'{password}: {hotspot.password}'),
                    (95, f'http://{AP_ADDRESS}')):
        draw.text((12, y), text, font=font(17), fill=ink)
    return bytearray(image.getdata())


def render_joined(address, seconds, theme='light', language='en'):
    from PIL import Image, ImageDraw
    from music_screen import font

    image = Image.new('1', (WIDTH, HEIGHT), theme == 'light')
    draw = ImageDraw.Draw(image)
    ink = int(theme == 'dark')
    title, timer = ('Připojeno', 'Návrat za') if language == 'cs' else ('Connected', 'Dashboard in')
    draw.text((12, 8), title, font=font(23, bold=True), fill=ink)
    draw.line(((205, 22), (214, 31), (234, 11)), fill=ink, width=3)
    draw.line((12, 43, 238, 43), fill=ink)
    draw.text((12, 55), f'http://{address}', font=font(19), fill=ink)
    draw.text((12, 94), timer, font=font(16), fill=ink)
    draw.text((238, 91), f'{seconds:02d} s', font=font(19, bold=True), fill=ink, anchor='ra')
    return bytearray(image.getdata())


def pack(image, rotation):
    """Pack the landscape image into the controller's 122×250 rows."""
    pixels = bytearray()
    for column in range(WIDTH):
        if rotation == 0:
            row = image[WIDTH - 1 - column::WIDTH]
        else:
            row = image[column::WIDTH][::-1]
        row.extend((1,) * 6)
        pixels.extend(
            sum(bit << (7 - index) for index, bit in enumerate(row[start:start+8]))
            for start in range(0, ROW_BYTES * 8, 8)
        )
    return pixels


@dataclass(frozen=True)
class Region:
    first_row: int
    last_row: int
    first_byte: int
    last_byte: int

    def extract(self, pixels):
        return b''.join(
            pixels[row * ROW_BYTES + self.first_byte:row * ROW_BYTES + self.last_byte + 1]
            for row in range(self.first_row, self.last_row + 1)
        )


def changed_regions(previous, pixels):
    changed = {}
    for offset, (old, new) in enumerate(zip(previous, pixels)):
        if old != new:
            row, column = divmod(offset, ROW_BYTES)
            changed.setdefault(row, []).append(column)

    regions = []
    # A gap in native rows separates unrelated parts of the landscape image.
    for _, group in groupby(enumerate(changed), key=lambda entry: entry[1] - entry[0]):
        rows = [row for _, row in group]
        regions.append(Region(rows[0], rows[-1],
                              min(changed[row][0] for row in rows),
                              max(changed[row][-1] for row in rows)))
    return regions


def needs_full_refresh(displayed_theme, theme, partial_count, *, advancing=False):
    return displayed_theme != theme or (partial_count >= 5 and not advancing)


class Weather:
    def __init__(self, config):
        self.current = None
        query = urlencode({
            'latitude': config['latitude'], 'longitude': config['longitude'],
            'temperature_unit': config['units'], 'current': 'temperature_2m,weather_code,is_day',
        })
        self.url = 'https://api.open-meteo.com/v1/forecast?' + query

    def poll(self, stop):
        while not stop.is_set():
            try:
                with urlopen(self.url, timeout=7) as response:
                    current = json.load(response)['current']
                self.current = (round(current['temperature_2m']), int(current['weather_code']),
                                bool(current['is_day']))
                print(f'Weather: {current["temperature_2m"]}, code {self.current[1]}', flush=True)
                stop.wait(900)
            except (OSError, KeyError, ValueError, TypeError) as error:
                print(f'Weather update failed: {error}', flush=True)
                stop.wait(60)


def run(rotation, duration, listen, port, settings, wifi_setup=False):
    from panel import VerifiedEPD, epdconfig

    stop = threading.Event()
    reload_requested = threading.Event()

    def reload_settings():
        reload_requested.set()
        stop.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    config = settings.values
    timezone = ZoneInfo(config['timezone'])
    units = config['units']
    weather = Weather(config)
    threading.Thread(target=weather.poll, args=(stop,), daemon=True).start()
    credentials = settings.credentials
    spotify = None
    if credentials.is_file():
        from music_screen import prepare_cover, progress_pixels, render_music

        spotify = SpotifyPlayback(credentials, settings.lock)
        threading.Thread(target=spotify.poll, args=(stop, prepare_cover), daemon=True).start()
    panel = VerifiedEPD()
    counts = {'full': 0, 'partial': 0}
    deadline = time.monotonic() + duration if duration else float('inf')
    initialized = False
    last_content = None
    displayed_theme = None
    displayed_music = False
    displayed_track = None
    displayed_layout = None
    displayed_size = PANEL_SIZE
    displayed_hotspot = None
    displayed_join = False
    join_notice = None
    join_until = None
    partial_count = 0
    previous = None
    state = PanelState(FOLDER / 'theme.txt')
    network = NetworkSetup(password_file=FOLDER / '.hotspot-password') if wifi_setup else None
    if network:
        threading.Thread(target=network.poll, args=(stop,), daemon=True).start()
    active_link = Link(listen)
    server = (start_server(listen, port, state, settings, reload_settings, layout_preview=render_layout_preview)
              if listen else None)
    local_name = LocalName()
    try:
        while not stop.is_set() and time.monotonic() < deadline:
            link = network.link if network else active_link
            hotspot = link.hotspot
            if link != active_link:
                if server:
                    server.shutdown()
                    server.server_close()
                    server = None
                if link.address:
                    server = start_server(link.address, port, state, settings, reload_settings,
                                          wifi=network if hotspot else None, layout_preview=render_layout_preview)
                active_link = link
            local_name.update(link.address if server and not hotspot and settings.values['local_name'] else None)
            now = datetime.now(timezone)
            theme = state.theme
            language = settings.values['language']
            current_weather = weather.current
            joined = network.joined if network else None
            if joined is not join_notice:
                join_notice = joined
                join_until = None
            seconds = JOIN_CONFIRM_SECONDS if join_until is None else ceil(join_until - time.monotonic())
            showing_join = joined is not None and seconds > 0
            prepared = spotify.current if spotify else None
            music = prepared is not None and hotspot is None and not showing_join
            size, layouts = settings.layout_state
            page = 'playback' if music else 'dashboard'
            layout = None if hotspot or showing_join else layouts[page]
            if layout is None and size != PANEL_SIZE and not (hotspot or showing_join):
                layout = canvas_defaults(size)[page]
            track, cover, progress, duration_ms = None, None, 0, 0
            if music:
                playback, cover = prepared
                track = playback.track
                progress = playback.progress_at(time.monotonic())
                duration_ms = playback.duration_ms
            advancing = False
            if hotspot:
                content = (theme, hotspot, language)
            elif showing_join:
                advancing = True
                content = (theme, joined.address, seconds, language)
            elif layout is not None:
                widgets = content_key(layout, now, current_weather, track, cover, progress,
                                      duration_ms=duration_ms, units=units, language=language)
                content = (theme, language, size, layout, track, widgets)
                advancing = displayed_layout == layout and (
                    (music and displayed_music and displayed_track == track)
                    or (partial_count < 120 and any(
                        clock_has_seconds(widget) for widget in layout
                    ))
                )
            elif music:
                music_view = (theme, track, id(cover))
                filled = progress_pixels(progress, cover)
                if displayed_music and last_content[:-1] == music_view:
                    previous_fill = last_content[-1]
                    # A one-pixel correction can come from normal API timing jitter.
                    if filled == previous_fill - 1:
                        filled = previous_fill
                    advancing = filled > previous_fill
                content = (*music_view, filled)
            else:
                content = (theme, *screen_content(now, current_weather, units, language))
            if content == last_content:
                stop.wait(min(1 - now.microsecond / 1_000_000, deadline - time.monotonic()))
                continue
            started = time.monotonic()
            if hotspot:
                screen = render_wifi(hotspot, theme, language)
            elif showing_join:
                screen = render_joined(joined.address, seconds, theme, language)
            elif layout is not None:
                screen = render_custom(layout, now, theme, language, weather=current_weather, units=units,
                                       track=track, cover=cover, progress=progress, duration_ms=duration_ms, size=size)
                screen = fit_panel(screen, size, theme)
            elif music:
                screen = render_music(track, theme, cover, filled)
            else:
                screen = render(now, current_weather, theme, units, language)
            pixels = pack(screen, rotation)
            # An advancing bar touches fresh pixels. Defer maintenance until
            # another part of the image changes instead of flashing mid-track.
            full = (displayed_music != music or displayed_layout != layout or displayed_size != size
                    or displayed_hotspot != hotspot or displayed_join != showing_join
                    or needs_full_refresh(displayed_theme, theme, partial_count, advancing=advancing))
            if full:
                if panel.init() != 0:
                    raise RuntimeError('Display initialisation failed')
                initialized = True
                panel.displayPartBaseImage(pixels)
                partial_count = 0
                detail = f'full ({theme})'
            else:
                regions = changed_regions(previous, pixels)
                if not regions:
                    last_content = content
                    displayed_track = track
                    if not hotspot and (server or network):
                        state.publish(theme, state.frame, track.url if track else None)
                    continue
                panel.display_regions(pixels, regions)
                partial_count += 1
                size = sum((region.last_row - region.first_row + 1)
                           * (region.last_byte - region.first_byte + 1) for region in regions)
                detail = f'partial ({len(regions)} regions, {size}/{len(pixels)} bytes per plane)'
            previous = pixels
            displayed_theme = theme
            displayed_music = music
            displayed_track = track
            displayed_layout = layout
            displayed_size = size
            displayed_hotspot = hotspot
            displayed_join = showing_join
            last_content = content
            if showing_join and join_until is None:
                join_until = time.monotonic() + JOIN_CONFIRM_SECONDS
            if not hotspot and (server or network):
                state.publish(theme, preview_png(screen, WIDTH, HEIGHT), track.url if track else None)
            mode = 'full' if full else 'partial'
            counts[mode] += 1
            page = 'wifi setup' if hotspot else 'connected' if showing_join else 'music' if music else 'weather'
            print(f'{now:%H:%M:%S} {detail} {page} {time.monotonic() - started:.3f}s', flush=True)
    finally:
        stop.set()
        local_name.close()
        try:
            if initialized:
                panel.sleep()
        finally:
            epdconfig.module_exit()
            if server:
                server.shutdown()
                server.server_close()
    print(f'Panel asleep. Full frames: {counts["full"]}, partial frames: {counts["partial"]}', flush=True)
    return reload_requested.is_set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rotation', choices=(0, 180), type=int)
    parser.add_argument('--seconds', type=int, default=90, help='Demo length, 0 runs until stopped')
    parser.add_argument('--listen', help='IPv4 address for the local control page')
    parser.add_argument('--port', type=int, default=80)
    parser.add_argument('--wifi-setup', action='store_true', help='Manage Wi-Fi with a fallback hotspot')
    args = parser.parse_args()
    if args.seconds < 0:
        parser.error('--seconds must be nonnegative')
    if args.wifi_setup and (args.listen or args.port != 80):
        parser.error('--wifi-setup selects its own listen address and uses port 80')
    with (FOLDER / '.panel.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, 'Dashboard already running.\n')
        settings = DeviceSettings(FOLDER)
        rotation = settings.values['rotation'] if args.rotation is None else args.rotation
        restart = run(rotation, args.seconds, args.listen, args.port, settings, args.wifi_setup)
    if restart:
        os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])


if __name__ == '__main__':
    main()
