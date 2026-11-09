"""Reproduce a weather update followed by a clock-only update with RAM ping-pong."""
import sys
from datetime import datetime
from types import ModuleType

from dashboard import ROW_BYTES, changed_regions, pack, render

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


for rotation in (0, 180):
    for theme in ('light', 'dark'):
        before = datetime(2026, 11, 9, 18, 39)
        after = datetime(2026, 11, 9, 18, 40)
        weather = (4, 3, False)
        empty = pack(render(before, None, theme), rotation)
        cloud = pack(render(before, weather, theme), rotation)
        next_minute = pack(render(after, weather, theme), rotation)
        panel = PingPongPanel(empty)
        panel.display_regions(cloud, changed_regions(empty, cloud))
        assert panel.visible == cloud
        clock_regions = changed_regions(cloud, next_minute)
        assert all(
            region.last_row < 161 if rotation == 180 else region.first_row > 88
            for region in clock_regions
        )
        panel.display_regions(next_minute, clock_regions)
        assert panel.visible == next_minute, 'Clock-only refresh reverted the weather pixels'
        assert panel.ram[0x24] == panel.ram[0x26] == next_minute
print('Cloud survives a clock-only refresh with RAM ping-pong in both themes and rotations.')
