"""GPIO SPI transport for a one-time Waveshare V4 check without hardware SPI."""

import time

import lgpio


# Pin mapping from Waveshare's Raspberry Pi driver, using BCM numbering.
RST_PIN = 17
DC_PIN = 25
CS_PIN = 8
BUSY_PIN = 24
PWR_PIN = 18
MOSI_PIN = 10
SCLK_PIN = 11

_chip = None


def module_init():
    global _chip
    if _chip is not None:
        return 0
    handle = lgpio.gpiochip_open(0)
    try:
        for pin, level in ((CS_PIN, 1), (SCLK_PIN, 0), (MOSI_PIN, 0),
                           (DC_PIN, 0), (RST_PIN, 1), (PWR_PIN, 1)):
            lgpio.gpio_claim_output(handle, pin, level)
        lgpio.gpio_claim_input(handle, BUSY_PIN, lgpio.SET_PULL_DOWN)
    except Exception:
        lgpio.gpiochip_close(handle)
        raise
    _chip = handle
    return 0


def digital_write(pin, level):
    lgpio.gpio_write(_chip, pin, level)


def digital_read(pin):
    return lgpio.gpio_read(_chip, pin)


def delay_ms(milliseconds):
    time.sleep(milliseconds / 1000)


def spi_writebyte(data):
    write = lgpio.gpio_write
    level = None
    for byte in data:
        for bit in range(7, -1, -1):
            value = (byte >> bit) & 1
            if value != level:
                write(_chip, MOSI_PIN, value)
                level = value
            write(_chip, SCLK_PIN, 1)
            write(_chip, SCLK_PIN, 0)


spi_writebyte2 = spi_writebyte


def module_exit():
    global _chip
    if _chip is not None:
        try:
            digital_write(PWR_PIN, 0)
        finally:
            lgpio.gpiochip_close(_chip)
            _chip = None
