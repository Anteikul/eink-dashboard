import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from control import PanelState, start_server
from dashboard import HEIGHT, WIDTH, render_joined, render_wifi
from device_settings import DeviceSettings
from wifi_setup import AP_ADDRESS, AP_UUID, NetworkSetup, wifi_credentials


class Radio:
    def __init__(self):
        self.connection = (None, None)
        self.started = []
        self.joined = []
        self.succeed = False

    def link(self):
        return self.connection

    def change(self, operation, ssid, password):
        if operation == 'hotspot':
            self.started.append((ssid, password))
            self.connection = (AP_UUID, AP_ADDRESS)
        else:
            self.joined.append((ssid, password))
            self.connection = (None, None)
            if not self.succeed:
                raise OSError('Test authentication failure')
            self.connection = ('saved-network', '192.168.1.99')


radio = Radio()
network = NetworkSetup(radio)
stop = Event()
network.step(0, stop)
network.step(29, stop)
assert not radio.started
radio.connection = ('known', '192.168.1.9')
network.step(30, stop)
assert network.link.address == '192.168.1.9'
radio.connection = (None, None)
network.step(31, stop)
network.step(61, stop)
assert network.link.address == AP_ADDRESS
hotspot = network.link.hotspot
assert hotspot and len(hotspot.password) == 8
frame = render_wifi(hotspot)
assert len(frame) == WIDTH * HEIGHT and set(frame) == {0, 1}

radio.connection = (None, None)
network.step(61.1, stop)
assert len(radio.started) == 1, 'Do not interrupt an external connection attempt'
radio.connection = (AP_UUID, AP_ADDRESS)
network.step(61.2, stop)

for bad_ssid, bad_password in [('', ''), ('é' * 17, ''), ('Home', 'short'), ('Home', 'bad\npassword')]:
    try:
        wifi_credentials(bad_ssid, bad_password)
    except ValueError:
        pass
    else:
        raise AssertionError('Accepted invalid Wi-Fi credentials')
assert wifi_credentials('A:b é', 'some password') == ('A:b é', 'some password')
assert wifi_credentials('Open', '') == ('Open', '')

with TemporaryDirectory() as folder:
    root = Path(folder)
    password_file = root / '.hotspot-password'
    password_file.write_text('12345678\n')
    fixed_radio = Radio()
    fixed_network = NetworkSetup(fixed_radio, password_file=password_file)
    fixed_network.step(0, stop)
    fixed_network.step(30, stop)
    assert fixed_network.link.hotspot.password == '12345678'
    settings = DeviceSettings(root)
    state = PanelState(root / 'theme.txt')
    server = start_server('127.0.0.1', 0, state, settings, lambda: None, wifi=network)
    base = f'http://127.0.0.1:{server.server_port}'

    def request(path, payload=None, origin=base):
        headers = {'Origin': origin, 'Content-Type': 'application/json'}
        data = json.dumps(payload).encode() if payload is not None else None
        try:
            with urlopen(Request(base + path, data=data, headers=headers), timeout=3) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()

    try:
        assert b'Set up Wi-Fi' in request('/')[1]
        assert request('/screen.png')[0] == request('/api/settings')[0] == 404
        assert hotspot.password.encode() not in request('/api/wifi')[1]
        assert request('/api/wifi', {'ssid': 'Home', 'password': 'abc12345'}, origin='http://other')[0] == 403
        assert request('/api/wifi', {'ssid': 'Home', 'password': 'short'})[0] == 400
        assert request('/api/wifi', {'ssid': 'Home', 'password': 'abc12345'})[0] == 202
        assert request('/api/wifi', {'ssid': 'Other', 'password': ''})[0] == 409
        network.step(62, stop)
        assert network.link.hotspot == hotspot and radio.started == [(hotspot.ssid, hotspot.password)] * 2
        assert network.joined is None
        assert json.loads(request('/api/wifi')[1])['status'] == 'failed'
        radio.succeed = True
        assert request('/api/wifi', {'ssid': 'Home', 'password': 'abc12345'})[0] == 202
        network.step(63, stop)
        assert network.link.address == '192.168.1.99' and network.link.hotspot is None
        assert network.joined.address == '192.168.1.99'
        joined = network.joined
        network.step(64, stop)
        assert network.joined is joined
        first = render_joined(joined.address, 15, language='cs')
        next_frame = render_joined(joined.address, 14, language='cs')
        assert len(first) == WIDTH * HEIGHT
        assert first[:90 * WIDTH] == next_frame[:90 * WIDTH] and first != next_frame
        assert request('/api/wifi', {'ssid': 'Other', 'password': ''})[0] == 409
    finally:
        server.shutdown()
        server.server_close()

print('Known networks, hotspot fallback, credential validation, failed and successful joins passed.')
