"""Reproduce a weather update followed by a clock-only update with RAM ping-pong."""
import sys
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest.mock import Mock, patch

from PIL import Image

from dashboard import (
    JOIN_CONFIRM_SECONDS, PANEL_SIZE, ROW_BYTES, canvas_defaults, changed_regions, fit_panel, pack, render,
    render_joined, render_wifi, run,
)
from device_settings import DeviceSettings
from layout_editor import panel_view_size, render_custom
from wifi_setup import AP_ADDRESS, Link, NetworkSetup

# The controller simulation replaces all GPIO-facing operations.
sys.modules.setdefault('lgpio', ModuleType('lgpio'))
from panel import VerifiedEPD


class PingPongPanel(VerifiedEPD):
    def __init__(self, pixels):
        super().__init__()
        self.ram = {0x24: bytearray(pixels), 0x26: bytearray(pixels)}
        self.visible = bytes(pixels)

    def preparePartial(self):
        pass

    def SetWindow(self, x_start, y_start, x_end, y_end):
        self.window = x_start // 8, y_start, x_end // 8, y_end

    def SetCursor(self, x, y):
        assert (x, y) == self.window[:2]

    def send_command(self, command):
        self.command = command

    def send_data2(self, data):
        first_byte, first_row, last_byte, last_row = self.window
        width = last_byte - first_byte + 1
        assert len(data) == width * (last_row - first_row + 1)
        for i, row in enumerate(range(first_row, last_row + 1)):
            offset = row * ROW_BYTES + first_byte
            self.ram[self.command][offset:offset+width] = data[i*width:(i+1)*width]

    def TurnOnDisplayPart(self):
        self.visible = bytes(self.ram[0x24])
        self.ram[0x24], self.ram[0x26] = self.ram[0x26], self.ram[0x24]


width, height = PANEL_SIZE
portrait = bytearray([1]) * (width * height)
portrait[0] = 0
portrait[height - 1] = 0
portrait_image = Image.frombytes('L', (height, width), bytes(portrait))
for rotation, transpose in ((90, Image.Transpose.ROTATE_270), (270, Image.Transpose.ROTATE_90)):
    turned = fit_panel(portrait, (height, width), 'light', rotation=rotation)
    assert bytes(turned) == portrait_image.transpose(transpose).tobytes()

for rotation in (0, 90, 180, 270):
    size = panel_view_size(rotation)
    for theme in ('light', 'dark'):
        before = datetime(2026, 11, 9, 18, 39)
        after = datetime(2026, 11, 9, 18, 40)
        weather = (4, 3, False)
        if size == PANEL_SIZE:
            frames = [render(now, current_weather, theme) for now, current_weather in (
                (before, None), (before, weather), (after, weather))]
        else:
            frames = [render_custom(canvas_defaults(size)['dashboard'], now, theme, 'en',
                                    size=size, view_size=size, weather=current_weather)
                      for now, current_weather in ((before, None), (before, weather), (after, weather))]
        empty, cloud, next_minute = (
            pack(fit_panel(frame, size, theme, rotation=rotation), 0) for frame in frames
        )
        panel = PingPongPanel(empty)
        panel.display_regions(cloud, changed_regions(empty, cloud))
        assert panel.visible == cloud
        clock_regions = changed_regions(cloud, next_minute)
        assert clock_regions
        if rotation in (0, 180):
            assert cloud == pack(frames[1], rotation)
            assert all(
                region.last_row < 161 if rotation == 180 else region.first_row > 88
                for region in clock_regions
            )
        elif rotation == 90:
            assert all(region.last_row < 80 for region in clock_regions)
        else:
            assert all(region.first_row >= 170 for region in clock_regions)
        panel.display_regions(next_minute, clock_regions)
        assert panel.visible == next_minute, 'Clock-only refresh reverted the weather pixels'
        assert panel.ram[0x24] == panel.ram[0x26] == next_minute
print('Panel rotation and clock-only refresh passed in both themes at all four angles.')


class SetupClock:
    def __init__(self):
        self.seconds = 0

    def monotonic(self):
        return self.seconds

    def wait(self, timeout):
        self.seconds += timeout


class SetupRadio:
    def __init__(self):
        self.password = None

    def link(self):
        return None, None

    def change(self, operation, ssid, password):
        assert operation == 'hotspot'
        self.password = password


class SetupSequence:
    def __init__(self, clock, hotspot):
        self.clock = clock
        self.hotspot = hotspot
        self.joined = None

    @property
    def link(self):
        self.clock.seconds += 1
        if self.clock.seconds == 1:
            return Link(AP_ADDRESS, self.hotspot)
        if self.joined is None:
            self.joined = Link('192.168.1.99')
        return self.joined

    def poll(self, stop):
        pass


now = datetime(2026, 11, 18, 12)
for rotation in (0, 90, 180, 270):
    for theme in ('light', 'dark'):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            settings = DeviceSettings(root)
            language = 'cs' if theme == 'dark' else 'en'
            settings.save({**settings.values, 'rotation': rotation, 'weather_enabled': False,
                           'language': language})
            root.joinpath('theme.txt').write_text(theme)
            password_path = root / '.hotspot-password'
            password_path.write_text('12345678\n')
            radio = SetupRadio()
            network = NetworkSetup(radio, password_file=password_path)
            network.step(0, Mock())
            network.step(30, Mock())
            hotspot = network.link.hotspot
            assert radio.password == hotspot.password == password_path.read_text().strip()
            clock = SetupClock()
            sequence = SetupSequence(clock, hotspot)
            panel = Mock()
            frames = []
            panel.init.return_value = 0
            panel.displayPartBaseImage.side_effect = lambda pixels: frames.append(bytes(pixels))
            server = Mock()
            with patch('builtins.print'), patch('dashboard.NetworkSetup', return_value=sequence), \
                    patch('dashboard.LocalName'), patch('dashboard.start_server', return_value=server), \
                    patch('dashboard.threading.Thread'), patch('dashboard.signal.signal'), \
                    patch('dashboard.datetime') as date, \
                    patch('dashboard.time.monotonic', clock.monotonic), \
                    patch('dashboard.threading.Event') as event, \
                    patch('panel.VerifiedEPD', return_value=panel), patch('panel.epdconfig.module_exit'), \
                    patch('dashboard.render_wifi', wraps=render_wifi) as wifi_renderer, \
                    patch('dashboard.render_joined', wraps=render_joined) as joined_renderer:
                date.now.return_value = now
                event.return_value.is_set.return_value = False
                event.return_value.wait.side_effect = clock.wait
                assert run(rotation, JOIN_CONFIRM_SECONDS + 4, None, 80, settings, wifi_setup=True) is False
            assert wifi_renderer.call_args.args == (hotspot, 'light', language)
            assert [call.args for call in joined_renderer.call_args_list] == [
                ('192.168.1.99', seconds, 'light', language)
                for seconds in range(JOIN_CONFIRM_SECONDS, 0, -1)
            ]
            setup_rotation = rotation - rotation % 180
            assert frames[0] == pack(render_wifi(hotspot, 'light', language), setup_rotation)
            assert frames[1] == pack(render_joined('192.168.1.99', JOIN_CONFIRM_SECONDS, 'light', language),
                                     setup_rotation)
            size = panel_view_size(rotation)
            screen = (render(now, None, theme, language=language, weather_enabled=False) if size == PANEL_SIZE
                      else render_custom(canvas_defaults(size)['dashboard'], now, theme, language,
                                         size=size, view_size=size, weather_enabled=False))
            assert frames[-1] == pack(fit_panel(screen, size, theme, rotation=rotation), 0)
            assert root.joinpath('theme.txt').read_text() == theme
            assert DeviceSettings(root).values['rotation'] == rotation

print('Wi-Fi credentials, light landscape setup and confirmation, and restored dashboard passed at all four angles.')
