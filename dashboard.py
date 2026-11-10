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
from itertools import groupby
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from control import PanelState, preview_png, start_server
from device_settings import DeviceSettings
from spotify_playback import SpotifyPlayback
from wifi_setup import AP_ADDRESS, Link, NetworkSetup

WIDTH, HEIGHT = 250, 122
ROW_BYTES = (HEIGHT + 7) // 8
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
    displayed_hotspot = None
    partial_count = 0
    previous = None
    state = PanelState(FOLDER / 'theme.txt')
    network = NetworkSetup(password_file=FOLDER / '.hotspot-password') if wifi_setup else None
    if network:
        threading.Thread(target=network.poll, args=(stop,), daemon=True).start()
    active_link = Link(listen)
    server = start_server(listen, port, state, settings, reload_settings) if listen else None
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
                                          wifi=network if hotspot else None)
                active_link = link
            now = datetime.now(timezone)
            theme = state.theme
            language = settings.values['language']
            current_weather = weather.current
            prepared = spotify.current if spotify else None
            music = prepared is not None and hotspot is None
            advancing = False
            if hotspot:
                track = None
                content = (theme, hotspot, language)
            elif music:
                playback, cover = prepared
                track = playback.track
                music_view = (theme, track, id(cover))
                filled = progress_pixels(playback.progress_at(time.monotonic()), cover)
                if displayed_music and last_content[:-1] == music_view:
                    previous_fill = last_content[-1]
                    # A one-pixel correction can come from normal API timing jitter.
                    if filled == previous_fill - 1:
                        filled = previous_fill
                    advancing = filled > previous_fill
                content = (*music_view, filled)
            else:
                track = None
                content = (theme, *screen_content(now, current_weather, units, language))
            if content == last_content:
                stop.wait(min(1 - now.microsecond / 1_000_000, deadline - time.monotonic()))
                continue
            started = time.monotonic()
            if hotspot:
                screen = render_wifi(hotspot, theme, language)
            elif music:
                screen = render_music(track, theme, cover, filled)
            else:
                screen = render(now, current_weather, theme, units, language)
            pixels = pack(screen, rotation)
            # An advancing bar touches fresh pixels. Defer maintenance until
            # another part of the image changes instead of flashing mid-track.
            full = (displayed_music != music or displayed_hotspot != hotspot
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
            displayed_hotspot = hotspot
            last_content = content
            if not hotspot and (server or network):
                state.publish(theme, preview_png(screen, WIDTH, HEIGHT), track.url if track else None)
            mode = 'full' if full else 'partial'
            counts[mode] += 1
            page = 'wifi setup' if hotspot else 'music' if music else 'weather'
            print(f'{now:%H:%M:%S} {detail} {page} {time.monotonic() - started:.3f}s', flush=True)
    finally:
        stop.set()
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
