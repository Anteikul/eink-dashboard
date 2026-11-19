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
BUSY = ('joining', 'forgetting')


def validate_profile_uuid(value):
    if not isinstance(value, str):
        raise ValueError('Choose a saved Wi-Fi network.')
    try:
        normalized = str(uuid.UUID(value))
    except ValueError as error:
        raise ValueError('Choose a saved Wi-Fi network.') from error
    if normalized != value or value == AP_UUID:
        raise ValueError('Choose a saved Wi-Fi network.')
    return value


def nm_fields(line):
    """Read nmcli's escaped terse columns without losing colons or backslashes."""
    fields, value, escaped = [], [], False
    for char in line:
        if escaped:
            value.append(char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            fields.append(''.join(value))
            value = []
        else:
            value.append(char)
    if escaped:
        value.append('\\')
    return [*fields, ''.join(value)]


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
    _management_supported = None

    def link(self):
        fields = nmcli('-g', 'GENERAL.STATE,GENERAL.CON-UUID,IP4.ADDRESS', 'device', 'show',
                       INTERFACE).splitlines()
        if len(fields) < 3 or fields[0].split(' ', 1)[0] != '100':
            return None, None
        return fields[1], str(ipaddress.IPv4Interface(fields[2]).ip)

    def request(self, payload, *, timeout=95):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as request:
            request.settimeout(timeout)
            request.connect(WIFI_SOCKET)
            request.sendall(json.dumps(payload).encode())
            request.shutdown(socket.SHUT_WR)
            with request.makefile('rb') as response:
                if response.readline(16) != b'OK\n':
                    raise OSError('Wi-Fi change failed')

    def supports_management(self):
        if self._management_supported is None:
            try:
                self.request({'operation': 'capabilities'}, timeout=5)
            except OSError:
                return False  # A busy helper or a transient timeout must be retryable.
            else:
                self._management_supported = True
        return self._management_supported

    def compatible_profiles(self):
        import dbus

        bus = dbus.SystemBus()
        service = 'org.freedesktop.NetworkManager'
        interface = service + '.Settings'
        settings = dbus.Interface(bus.get_object(service, '/org/freedesktop/NetworkManager/Settings'), interface)
        try:
            paths = settings.ListConnections(timeout=5)
        except dbus.DBusException as error:
            raise OSError('Could not read Wi-Fi profiles') from error
        compatible = set()
        for path in paths:
            try:
                connection = dbus.Interface(bus.get_object(service, path), interface + '.Connection')
                values = connection.GetSettings(timeout=5)
                if wifi_profile_compatible(values, bus, service):
                    compatible.add(str(values['connection']['uuid']))
            except (dbus.DBusException, KeyError):
                continue
        return compatible

    def change(self, operation, ssid, password, *, profile=None):
        payload = {'operation': operation, 'ssid': ssid, 'password': password}
        if profile is not None:
            payload['profile'] = profile
        self.request(payload)

    def networks(self, *, rescan=False):
        scan_error = False
        try:
            if rescan and self.supports_management():
                self.request({'operation': 'scan'}, timeout=25)
                rescan = False
            access_points = nmcli('-t', '-e', 'yes', '-f', 'IN-USE,SSID,SIGNAL,SECURITY',
                                  'device', 'wifi', 'list', 'ifname', INTERFACE,
                                  '--rescan', 'yes' if rescan else 'no', wait=15)
        except OSError:
            access_points = ''
            scan_error = True
        available = {}
        for line in access_points.splitlines():
            fields = nm_fields(line)
            if len(fields) != 4:
                continue
            active, ssid, signal, security = fields
            try:
                wifi_credentials(ssid, '')
                strength = int(signal)
            except ValueError:
                continue
            key = ssid, security
            item = {'ssid': ssid, 'signal': max(0, min(100, strength)),
                    'security': '' if security in ('', '--') else security, 'connected': active == '*'}
            previous = available.get(key)
            if previous is None or (item['connected'], item['signal']) > (previous['connected'], previous['signal']):
                available[key] = item

        profiles = nmcli('-t', '-e', 'yes', '-f', 'UUID,TYPE', 'connection', 'show')
        active, _ = self.link()
        compatible = self.compatible_profiles()
        saved = []
        for line in profiles.splitlines():
            fields = nm_fields(line)
            if len(fields) != 2 or fields[1] not in ('wifi', '802-11-wireless') or fields[0] == AP_UUID:
                continue
            identifier = fields[0]
            if identifier not in compatible:
                continue
            try:
                validate_profile_uuid(identifier)
                details = nmcli('-g', 'connection.id,connection.interface-name,802-11-wireless.ssid,802-11-wireless.mode',
                                'connection', 'show', 'uuid', identifier)
            except (OSError, ValueError):
                continue  # A profile may disappear while the list is being read.
            values = [nm_fields(value)[0] for value in details.splitlines()]
            if len(values) != 4:
                continue
            name, interface, ssid, mode = values
            if interface not in ('', '--', INTERFACE) or mode not in ('', '--', 'infrastructure'):
                continue
            try:
                wifi_credentials(ssid, '')
            except ValueError:
                continue
            saved.append({'uuid': identifier, 'ssid': ssid, 'name': name, 'connected': identifier == active})
        order = lambda item: (not item['connected'], item['ssid'].casefold())
        return {'available': sorted(available.values(), key=lambda item: (not item['connected'], -item['signal'], item['ssid'].casefold())),
                'saved': sorted(saved, key=order), 'scanError': scan_error}


@dataclass(frozen=True)
class Hotspot:
    ssid: str
    password: str


@dataclass(frozen=True)
class Link:
    address: str | None = None
    hotspot: Hotspot | None = None


class NetworkSetup:
    def __init__(self, radio=None, password_file=None, *, delay=GRACE):
        self.radio = radio if radio is not None else NetworkManagerRadio()
        self.delay = delay
        self.fixed_password = None
        if password_file is not None and password_file.is_file():
            self.fixed_password = password_file.read_text().strip()
            if not re.fullmatch(r'[0-9]{8}', self.fixed_password):
                raise ValueError('The fixed hotspot password must contain eight digits.')
        self.link = Link()
        self.joined = None
        self.lock = Lock()
        self.pending = None
        self.status = 'ready'
        self.disconnected_at = None
        self.hotspot = None
        self.operation = None
        self.operation_id = 0

    def submit(self, ssid, password):
        credentials = wifi_credentials(ssid, password)
        with self.lock:
            if not self.link.hotspot or self.status in BUSY:
                return False
            self.pending = {'operation': 'join', 'ssid': credentials[0], 'password': credentials[1]}
            self.status = 'joining'
            return True

    def management_status(self):
        with self.lock:
            return {'status': self.status, 'operation': self.operation, 'id': self.operation_id,
                    'address': self.link.address}

    def networks(self, *, rescan=False):
        with self.lock:
            if self.status in BUSY:
                raise ValueError('A Wi-Fi change is already in progress.')
        return {**self.radio.networks(rescan=rescan),
                'canManage': self.radio.supports_management(), **self.management_status()}

    def manage(self, operation, *, ssid='', password='', profile=None):
        if operation not in ('connect', 'forget'):
            raise ValueError('Choose a Wi-Fi action.')
        if profile is not None:
            profile = validate_profile_uuid(profile)
            if ssid or password:
                raise ValueError('Choose a saved network or enter new network details.')
        elif operation == 'forget':
            raise ValueError('Choose a saved Wi-Fi network.')
        else:
            wifi_credentials(ssid, password)
        with self.lock:
            if self.status in BUSY:
                return False
            if not self.radio.supports_management():
                raise ValueError('Update Wi-Fi support on the Pi before changing networks.')
            self.pending = {'operation': operation, 'ssid': ssid, 'password': password}
            if profile is not None:
                self.pending['profile'] = profile
            self.operation = operation
            self.operation_id += 1
            self.status = 'joining' if operation == 'connect' else 'forgetting'
            return True

    def step(self, now, stop):
        with self.lock:
            pending, self.pending = self.pending, None
        if pending is None:
            self.refresh_link(now)
            return
        if stop.wait(0.75):
            return
        status = 'forgotten' if pending['operation'] == 'forget' else 'connected'
        try:
            self.radio.change(**pending)
        except OSError:
            status = 'failed'
        try:
            self.refresh_link(now, restore_hotspot=status == 'failed')
            if status == 'connected' and self.link.address and not self.link.hotspot:
                self.joined = self.link
            elif status == 'connected':
                status = 'failed'
        except (OSError, ValueError):
            status = 'failed'
            raise
        finally:
            with self.lock:
                self.status = status

    def refresh_link(self, now, *, restore_hotspot=False):
        connection, address = self.radio.link()
        if address and connection != AP_UUID:
            if self.joined is not None and self.joined.address != address:
                self.joined = None
            self.link = Link(address)
            self.disconnected_at = None
            self.hotspot = None
            return
        if address == AP_ADDRESS and self.hotspot:
            self.link = Link(address, self.hotspot)
            self.disconnected_at = None
            return

        self.link = Link()
        self.joined = None
        if self.disconnected_at is None:
            self.disconnected_at = now
        if not restore_hotspot and connection != AP_UUID and now - self.disconnected_at < self.delay:
            return
        if self.hotspot is None:
            suffix = ''.join(secrets.choice(AP_ALPHABET) for _ in range(4))
            password = self.fixed_password or ''.join(secrets.choice(AP_ALPHABET) for _ in range(8))
            self.hotspot = Hotspot(f'EinkSetup-{suffix}', password)
            with self.lock:
                self.status = 'ready'
        self.radio.change('hotspot', self.hotspot.ssid, self.hotspot.password)
        self.link = Link(AP_ADDRESS, self.hotspot)
        self.disconnected_at = None

    def poll(self, stop):
        while not stop.is_set():
            try:
                self.step(time.monotonic(), stop)
            except (OSError, ValueError):
                print('Wi-Fi setup is waiting for NetworkManager.', flush=True)
                if stop.wait(5):
                    break
            stop.wait(1)


def wifi_profile_compatible(values, bus, service):
    """Apply the same adapter restrictions to discovery and privileged changes."""
    import dbus

    config = values.get('connection', {})
    wireless = values.get('802-11-wireless', {})
    if (config.get('type') != '802-11-wireless'
            or config.get('interface-name', '') not in ('', INTERFACE)
            or wireless.get('mode', 'infrastructure') != 'infrastructure'
            or any(values.get('match', {}).values())):
        return False
    bound = wireless.get('mac-address')
    denied = [*wireless.get('mac-address-blacklist', []), *wireless.get('mac-address-denylist', [])]
    if not bound and not denied:
        return True
    try:
        manager = dbus.Interface(bus.get_object(service, '/org/freedesktop/NetworkManager'), service)
        path = manager.GetDeviceByIpIface(INTERFACE, timeout=5)
        properties = dbus.Interface(bus.get_object(service, path), 'org.freedesktop.DBus.Properties')
        permanent = str(properties.Get(service + '.Device.Wireless', 'PermHwAddress', timeout=5)).lower()
    except dbus.DBusException:
        return False
    if not re.fullmatch(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', permanent):
        return False
    if bound:
        address = bound.lower() if isinstance(bound, str) else bytes(bound).hex(':')
        if address != permanent:
            return False
    return permanent not in {str(address).lower() for address in denied}


def saved_connection(bus, settings, service, identifier):
    """Only manage infrastructure Wi-Fi profiles compatible with the fixed radio."""
    validate_profile_uuid(identifier)
    path = settings.GetConnectionByUuid(identifier, timeout=5)
    connection = bus.get_object(service, path)
    import dbus

    connection = dbus.Interface(connection, service + '.Settings.Connection')
    values = connection.GetSettings(timeout=5)
    if not wifi_profile_compatible(values, bus, service):
        raise ValueError('Choose a saved Wi-Fi network.')
    return connection


def configure(operation, ssid='', password='', *, profile=None):
    """Root helper: fixed radio, validated credentials and compatible Wi-Fi UUIDs only."""
    import dbus

    if operation == 'capabilities':
        return
    if operation == 'scan':
        nmcli('device', 'wifi', 'list', 'ifname', INTERFACE, '--rescan', 'yes', wait=15)
        return
    managed = operation in ('connect', 'forget')
    if managed and profile is not None:
        validate_profile_uuid(profile)
        if ssid or password:
            raise ValueError('Choose a saved network or enter new network details.')
    elif operation == 'forget':
        raise ValueError('Choose a saved Wi-Fi network.')
    else:
        wifi_credentials(ssid, password)
    active, address = NetworkManagerRadio().link()
    hotspot = operation == 'hotspot'
    if hotspot:
        if (not re.fullmatch(r'EinkSetup-[A-Z2-9]{4}', ssid)
                or not re.fullmatch(r'(?:[A-Z0-9]{8}|[A-Z2-9]{10})', password)
                or (address and active != AP_UUID)):
            raise ValueError('Invalid hotspot request')
        state = nmcli('-g', 'GENERAL.STATE', 'device', 'show', INTERFACE).split(' ', 1)[0]
        if state in ('40', '50', '60', '70', '80', '90'):
            raise ValueError('NetworkManager is still connecting')
    elif not managed and (operation != 'join' or (active, address) != (AP_UUID, AP_ADDRESS)):
        raise ValueError('Wi-Fi setup is only available on the hotspot')

    bus = dbus.SystemBus()
    service = 'org.freedesktop.NetworkManager'
    settings_iface = service + '.Settings'
    settings = dbus.Interface(bus.get_object(service, '/org/freedesktop/NetworkManager/Settings'),
                              settings_iface)
    if managed and profile is not None:
        saved_connection(bus, settings, service, profile)
        if operation == 'forget':
            nmcli('connection', 'delete', 'uuid', profile)
            return
        try:
            nmcli('connection', 'up', 'uuid', profile, 'ifname', INTERFACE, wait=30)
        except OSError:
            restore_connection(bus, settings, service, active)
            raise
        return
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
        if managed:
            restore_connection(bus, settings, service, active)
        raise


def restore_connection(bus, settings, service, identifier):
    """Best effort: keep the old connection usable after a failed manual switch."""
    import dbus

    try:
        saved_connection(bus, settings, service, identifier)
        nmcli('connection', 'up', 'uuid', identifier, 'ifname', INTERFACE, wait=10)
    except (OSError, ValueError, dbus.DBusException):
        pass


def helper():
    import dbus

    try:
        if os.geteuid() != 0 or len(sys.argv) != 1:
            raise ValueError('Invalid helper invocation')
        payload = json.loads(sys.stdin.buffer.read(4097))
        configure(payload['operation'], payload.get('ssid', ''), payload.get('password', ''),
                  profile=payload.get('profile'))
    except (OSError, ValueError, KeyError, TypeError, dbus.DBusException):
        print('ERROR', flush=True)
        return 1
    print('OK', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(helper())
