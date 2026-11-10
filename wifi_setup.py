#!/usr/bin/python3 -I
"""Monitor Wi-Fi and configure NetworkManager through a restricted helper."""
import ipaddress
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from threading import Lock

INTERFACE = 'wlan0'
AP_ADDRESS = '10.42.0.1'
AP_UUID = 'de988050-9b54-49e2-8a76-6989fdfb8d27'
AP_ALPHABET = '34679ACDEFHJKMNPRTUVWXY'
WIFI_SOCKET = '/run/eink-wifi.sock'
NMCLI = '/usr/bin/nmcli'
GRACE = 30


def wifi_credentials(ssid, password):
    if (not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8', 'surrogatepass')) <= 32
            or any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in ssid)):
        raise ValueError('Enter a Wi-Fi network name of up to 32 bytes.')
    if (not isinstance(password, str) or (password and not re.fullmatch(
            r'(?:[ -~]{8,63}|[0-9a-fA-F]{64})', password))):
        raise ValueError('Enter a password of 8–63 characters or leave it empty for an open network.')
    return ssid, password


def nmcli(*args, wait=5):
    try:
        return subprocess.run([NMCLI, '--wait', str(wait), *args],
                              check=True, capture_output=True, text=True, timeout=wait + 4).stdout
    except (subprocess.SubprocessError, OSError) as error:
        raise OSError('NetworkManager command failed') from error


class NetworkManagerRadio:
    def link(self):
        fields = nmcli('-g', 'GENERAL.STATE,GENERAL.CON-UUID,IP4.ADDRESS', 'device', 'show',
                       INTERFACE).splitlines()
        if len(fields) < 3 or fields[0].split(' ', 1)[0] != '100':
            return None, None
        return fields[1], str(ipaddress.IPv4Interface(fields[2]).ip)

    def change(self, operation, ssid, password):
        payload = json.dumps({'operation': operation, 'ssid': ssid, 'password': password}).encode()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as request:
            request.settimeout(60)
            request.connect(WIFI_SOCKET)
            request.sendall(payload)
            request.shutdown(socket.SHUT_WR)
            with request.makefile('rb') as response:
                if response.readline(16) != b'OK\n':
                    raise OSError('Wi-Fi change failed')


@dataclass(frozen=True)
class Hotspot:
    ssid: str
    password: str


@dataclass(frozen=True)
class Link:
    address: str | None = None
    hotspot: Hotspot | None = None


class NetworkSetup:
    def __init__(self, radio=None, password_file=None):
        self.radio = radio if radio is not None else NetworkManagerRadio()
        self.fixed_password = None
        if password_file is not None and password_file.is_file():
            self.fixed_password = password_file.read_text().strip()
            if not re.fullmatch(r'[0-9]{8}', self.fixed_password):
                raise ValueError('The fixed hotspot password must contain eight digits.')
        self.link = Link()
        self.lock = Lock()
        self.pending = None
        self.status = 'ready'
        self.disconnected_at = None
        self.hotspot = None

    def submit(self, ssid, password):
        credentials = wifi_credentials(ssid, password)
        with self.lock:
            if not self.link.hotspot or self.status == 'joining':
                return False
            self.pending = credentials
            self.status = 'joining'
            return True

    def step(self, now, stop):
        with self.lock:
            credentials, self.pending = self.pending, None
        if credentials is None:
            self.refresh_link(now)
            return
        if stop.wait(0.75):
            return
        status = 'connected'
        try:
            self.radio.change('join', *credentials)
        except OSError:
            status = 'failed'
        try:
            self.refresh_link(now)
        finally:
            with self.lock:
                self.status = status

    def refresh_link(self, now):
        connection, address = self.radio.link()
        if address and connection != AP_UUID:
            self.link = Link(address)
            self.disconnected_at = None
            self.hotspot = None
            return
        if address == AP_ADDRESS and self.hotspot:
            self.link = Link(address, self.hotspot)
            return

        self.link = Link()
        if self.disconnected_at is None:
            self.disconnected_at = now
        if self.hotspot is None and connection != AP_UUID and now - self.disconnected_at < GRACE:
            return
        if self.hotspot is None:
            suffix = ''.join(secrets.choice(AP_ALPHABET) for _ in range(4))
            password = self.fixed_password or ''.join(secrets.choice(AP_ALPHABET) for _ in range(8))
            self.hotspot = Hotspot(f'EinkSetup-{suffix}', password)
            with self.lock:
                self.status = 'ready'
        self.radio.change('hotspot', self.hotspot.ssid, self.hotspot.password)
        self.link = Link(AP_ADDRESS, self.hotspot)

    def poll(self, stop):
        while not stop.is_set():
            try:
                self.step(time.monotonic(), stop)
            except (OSError, ValueError):
                print('Wi-Fi setup is waiting for NetworkManager.', flush=True)
                if stop.wait(5):
                    break
            stop.wait(1)


def configure(operation, ssid, password):
    """Root helper. Only allow the fixed interface and the two supported operations."""
    import dbus

    wifi_credentials(ssid, password)
    active, address = NetworkManagerRadio().link()
    hotspot = operation == 'hotspot'
    if hotspot:
        if (not re.fullmatch(r'EinkSetup-[A-Z2-9]{4}', ssid)
                or not re.fullmatch(r'(?:[A-Z0-9]{8}|[A-Z2-9]{10})', password)
                or (address and active != AP_UUID)):
            raise ValueError('Invalid hotspot request')
    elif operation != 'join' or (active, address) != (AP_UUID, AP_ADDRESS):
        raise ValueError('Wi-Fi setup is only available on the hotspot')

    bus = dbus.SystemBus()
    service = 'org.freedesktop.NetworkManager'
    settings_iface = service + '.Settings'
    settings = dbus.Interface(bus.get_object(service, '/org/freedesktop/NetworkManager/Settings'),
                              settings_iface)
    profile_uuid = AP_UUID if hotspot else str(uuid.uuid4())
    if hotspot:
        try:
            previous = settings.GetConnectionByUuid(AP_UUID, timeout=5)
        except dbus.DBusException as error:
            if error.get_dbus_name() != settings_iface + '.InvalidConnection':
                raise
        else:
            dbus.Interface(bus.get_object(service, previous), settings_iface + '.Connection').Delete(timeout=5)

    profile = {
        'connection': {'type': '802-11-wireless', 'id': ssid, 'uuid': profile_uuid,
                       'interface-name': INTERFACE, 'autoconnect': dbus.Boolean(False)},
        '802-11-wireless': {'ssid': dbus.ByteArray(ssid.encode()),
                            'mode': 'ap' if hotspot else 'infrastructure'},
        'ipv4': {'method': 'shared' if hotspot else 'auto', 'may-fail': dbus.Boolean(False)},
        'ipv6': {'method': 'disabled' if hotspot else 'auto'},
    }
    if hotspot:
        profile['802-11-wireless']['band'] = 'bg'
        profile['ipv4']['address-data'] = dbus.Array(
            [dbus.Dictionary({'address': AP_ADDRESS, 'prefix': dbus.UInt32(24)}, signature='sv')],
            signature='a{sv}')
    if password:
        profile['802-11-wireless-security'] = {'key-mgmt': 'wpa-psk', 'psk': password}
        if hotspot:
            profile['802-11-wireless-security']['proto'] = dbus.Array(['rsn'], signature='s')

    path = settings.AddConnectionUnsaved(profile, timeout=8)
    try:
        nmcli('connection', 'up', 'uuid', profile_uuid, 'ifname', INTERFACE, wait=18 if hotspot else 30)
        if not hotspot:
            nmcli('connection', 'modify', 'uuid', profile_uuid,
                  'connection.autoconnect', 'yes')
    except OSError:
        dbus.Interface(bus.get_object(service, path), settings_iface + '.Connection').Delete(timeout=5)
        raise


def helper():
    import dbus

    try:
        if os.geteuid() != 0 or len(sys.argv) != 1:
            raise ValueError('Invalid helper invocation')
        payload = json.loads(sys.stdin.buffer.read(4097))
        configure(payload['operation'], payload['ssid'], payload['password'])
    except (OSError, ValueError, KeyError, TypeError, dbus.DBusException):
        print('ERROR', flush=True)
        return 1
    print('OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(helper())
