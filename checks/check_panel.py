"""Reproduce a weather update followed by a clock-only update with RAM ping-pong."""
import sys
from datetime import datetime
from types import ModuleType

from PIL import Image

from dashboard import PANEL_SIZE, ROW_BYTES, changed_regions, fit_panel, pack, render

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
    for theme in ('light', 'dark'):
        before = datetime(2026, 11, 9, 18, 39)
        after = datetime(2026, 11, 9, 18, 40)
        weather = (4, 3, False)
        empty_frame = render(before, None, theme)
        cloud_frame = render(before, weather, theme)
        minute_frame = render(after, weather, theme)
        empty, cloud, next_minute = (
            pack(fit_panel(frame, PANEL_SIZE, theme, rotation=rotation), 0)
            for frame in (empty_frame, cloud_frame, minute_frame)
        )
        panel = PingPongPanel(empty)
        panel.display_regions(cloud, changed_regions(empty, cloud))
        assert panel.visible == cloud
        clock_regions = changed_regions(cloud, next_minute)
        assert clock_regions
        if rotation in (0, 180):
            assert cloud == pack(cloud_frame, rotation)
            assert all(
                region.last_row < 161 if rotation == 180 else region.first_row > 88
                for region in clock_regions
            )
        panel.display_regions(next_minute, clock_regions)
        assert panel.visible == next_minute, 'Clock-only refresh reverted the weather pixels'
        assert panel.ram[0x24] == panel.ram[0x26] == next_minute
print('Panel rotation and clock-only refresh passed in both themes at all four angles.')
