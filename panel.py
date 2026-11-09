import time

from waveshare_epd import epd2in13_V4, epdconfig


class VerifiedEPD(epd2in13_V4.EPD):
    def __init__(self):
        super().__init__()
        self.awaiting_busy = None

    def write_regions(self, command, pixels, regions):
        for region in regions:
            self.SetWindow(region.first_byte * 8, region.first_row,
                           region.last_byte * 8 + 7, region.last_row)
            self.SetCursor(region.first_byte, region.first_row)
            self.send_command(command)
            self.send_data2(region.extract(pixels))

    def display_regions(self, pixels, regions):
        self.preparePartial()
        self.write_regions(0x24, pixels, regions)
        self.TurnOnDisplayPart()
        # Mode 2 can swap the RAM planes. Seed both copies of the updated pixels
        # so subsequent windows cannot expose an older image elsewhere.
        self.write_regions(0x26, pixels, regions)
        self.write_regions(0x24, pixels, regions)

    def send_command(self, command):
        super().send_command(command)
        if command in (0x12, 0x20):
            self.awaiting_busy = command

    def ReadBusy(self):
        started = time.monotonic()
        command = self.awaiting_busy
        self.awaiting_busy = None
        if command is not None:
            deadline = time.monotonic() + 0.5
            while not epdconfig.digital_read(self.busy_pin):
                if time.monotonic() > deadline:
                    raise TimeoutError(f'No BUSY assertion after command 0x{command:02x}')
                time.sleep(0.0005)

        deadline = time.monotonic() + 12
        while epdconfig.digital_read(self.busy_pin):
            if time.monotonic() > deadline:
                raise TimeoutError('The display did not release BUSY within 12 seconds')
            time.sleep(0.005)

        if command is not None:
            busy_seconds = time.monotonic() - started
            print(f'Panel BUSY after 0x{command:02x}: {busy_seconds:.3f}s', flush=True)
