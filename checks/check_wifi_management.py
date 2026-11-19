"""Wi-Fi discovery, saved profiles and authenticated settings operations."""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from control import PanelState, start_server
from device_settings import DeviceSettings
from wifi_setup import AP_UUID, NetworkManagerRadio, NetworkSetup, configure

HOME = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'
WIRED = '33333333-3333-4333-8333-333333333333'


class Radio:
    def __init__(self):
        self.connection = (HOME, '192.168.1.20')
        self.operations = []
        self.fail = False

    def link(self):
        return self.connection

    def supports_management(self):
        return True

    def networks(self, *, rescan=False):
        return {'available': [{'ssid': 'Home', 'signal': 80, 'security': 'WPA2', 'connected': True}],
                'saved': [{'uuid': HOME, 'ssid': 'Home', 'name': 'Home', 'connected': True}]}

    def change(self, operation, ssid, password, *, profile=None):
        self.operations.append((operation, ssid, password, profile))
        if self.fail:
            raise OSError('Simulated Wi-Fi failure')
        if operation == 'connect':
            self.connection = (profile or OTHER, '192.168.2.20')


class DiscoveryChecks(unittest.TestCase):
    def setUp(self):
        self.compatible = patch.object(NetworkManagerRadio, 'compatible_profiles', create=True,
                                       return_value={HOME, OTHER})
        self.compatible.start()
        self.addCleanup(self.compatible.stop)

    def test_capabilities_recovers_after_a_transient_helper_failure(self):
        radio = NetworkManagerRadio()
        with patch.object(radio, 'request', side_effect=[OSError('Busy socket'), None]):
            self.assertFalse(radio.supports_management())
            self.assertTrue(radio.supports_management())

    def test_discovery_keeps_names_and_strongest_access_point(self):
        def command(*args, **kwargs):
            if 'list' in args:
                return '*:Home:80:WPA2\n:Home:40:WPA2\n:Cafe\\: \\\\ čaj:60:--\n::90:WPA2\n'
            if args[-1] == 'show':
                return f'{HOME}:wifi\n{OTHER}:802-11-wireless\n{WIRED}:802-3-ethernet\n{AP_UUID}:wifi\n'
            if args[-1] == HOME:
                return 'Home profile\nwlan0\nHome\ninfrastructure\n'
            if args[-1] == OTHER:
                return 'Offline profile\n\nOffline\\: síť\ninfrastructure\n'
            self.fail(f'Unexpected NetworkManager request: {args}')

        with patch('wifi_setup.nmcli', side_effect=command), patch.object(NetworkManagerRadio, 'link', return_value=(HOME, '192.168.1.20')), patch.object(NetworkManagerRadio, 'supports_management', return_value=False):
            data = NetworkManagerRadio().networks(rescan=True)
        self.assertEqual(data['available'], [
            {'ssid': 'Home', 'signal': 80, 'security': 'WPA2', 'connected': True},
            {'ssid': 'Cafe: \\ čaj', 'signal': 60, 'security': '', 'connected': False},
        ])
        self.assertEqual(data['saved'], [
            {'uuid': HOME, 'ssid': 'Home', 'name': 'Home profile', 'connected': True},
            {'uuid': OTHER, 'ssid': 'Offline: síť', 'name': 'Offline profile', 'connected': False},
        ])

    def test_only_profiles_compatible_with_wlan0_are_listed(self):
        with patch('wifi_setup.nmcli', side_effect=[
            '', f'{OTHER}:802-11-wireless\n', 'Other radio\nwlan1\nHome\ninfrastructure\n',
        ]), patch.object(NetworkManagerRadio, 'link', return_value=(None, None)):
            self.assertEqual(NetworkManagerRadio().networks()['saved'], [])

    def test_scan_failure_does_not_hide_saved_networks(self):
        with patch('wifi_setup.nmcli', side_effect=[
            OSError('Radio unavailable'), f'{OTHER}:wifi\n', 'Saved\nwlan0\nHome\ninfrastructure\n',
        ]), patch.object(NetworkManagerRadio, 'link', return_value=(None, None)):
            data = NetworkManagerRadio().networks()
        self.assertEqual(data['available'], [])
        self.assertEqual(data['saved'][0]['uuid'], OTHER)
        self.assertTrue(data['scanError'])


class QueueChecks(unittest.TestCase):
    def setUp(self):
        self.radio = Radio()
        self.network = NetworkSetup(self.radio)
        self.network.refresh_link(0)

    def test_connection_runs_after_acceptance_and_serializes_changes(self):
        self.assertTrue(self.network.manage('connect', ssid='Cafe', password='abc12345'))
        self.assertEqual(self.radio.operations, [])
        self.assertFalse(self.network.manage('forget', profile=HOME))
        self.network.step(1, Event())
        self.assertEqual(self.radio.operations, [('connect', 'Cafe', 'abc12345', None)])
        self.assertEqual(self.network.management_status()['status'], 'connected')
        self.assertNotIn('password', json.dumps(self.network.management_status()))

    def test_saved_connections_do_not_require_a_password(self):
        self.assertTrue(self.network.manage('connect', profile=OTHER))
        self.network.step(1, Event())
        self.assertEqual(self.radio.operations, [('connect', '', '', OTHER)])

    def test_forget_does_not_report_connected(self):
        self.assertTrue(self.network.manage('forget', profile=OTHER))
        self.network.step(1, Event())
        self.assertEqual(self.network.management_status()['status'], 'forgotten')

    def test_failure_is_reported_without_losing_existing_link(self):
        self.radio.fail = True
        self.network.manage('connect', profile=OTHER)
        self.network.step(1, Event())
        self.assertEqual(self.network.management_status()['status'], 'failed')
        self.assertEqual(self.network.link.address, '192.168.1.20')

    def test_invalid_requests_never_reach_the_radio(self):
        for action, options in [('forget', {'profile': AP_UUID}), ('forget', {'profile': 'Home'}),
                                ('connect', {'ssid': 'Home', 'password': 'short'}), ('delete', {})]:
            with self.subTest(action=action, options=options), self.assertRaises(ValueError):
                self.network.manage(action, **options)
        self.assertEqual(self.radio.operations, [])

    def test_old_helper_is_explained_and_does_not_queue_a_change(self):
        self.radio.supports_management = lambda: False
        self.assertFalse(self.network.networks()['canManage'])
        with self.assertRaisesRegex(ValueError, 'Update Wi-Fi support'):
            self.network.manage('connect', profile=OTHER)
        self.assertIsNone(self.network.pending)

    def test_connection_without_an_ipv4_link_is_not_reported_as_connected(self):
        self.radio.change = lambda **kwargs: setattr(self.radio, 'connection', (OTHER, None))
        self.network.manage('connect', profile=OTHER)
        self.network.step(1, Event())
        self.assertEqual(self.network.management_status()['status'], 'failed')

    def test_failed_link_verification_cannot_publish_connection_success(self):
        self.network.manage('connect', profile=OTHER)
        self.radio.link = lambda: (_ for _ in ()).throw(OSError('NetworkManager restarting'))
        with self.assertRaises(OSError):
            self.network.step(1, Event())
        self.assertEqual(self.network.management_status()['status'], 'failed')


class HttpChecks(unittest.TestCase):
    def test_settings_endpoints_require_access_and_same_origin(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            settings = DeviceSettings(root)
            settings.change_code('', 'test-password')
            settings.set_password_required(True)
            network = NetworkSetup(Radio())
            server = start_server('127.0.0.1', 0, PanelState(root / 'theme.txt'), settings,
                                  lambda: None, wifi_manager=network)
            base = f'http://127.0.0.1:{server.server_port}'

            def request(path, payload=None, *, authorized=True, origin=base):
                headers = {'Origin': origin, 'Content-Type': 'application/json'}
                if authorized:
                    headers['X-Setup-Code'] = settings.code
                body = json.dumps(payload).encode() if payload is not None else None
                try:
                    with urlopen(Request(base + path, data=body, headers=headers), timeout=5) as reply:
                        return reply.status, json.load(reply)
                except HTTPError as error:
                    body = error.read()
                    return error.code, json.loads(body) if error.headers.get_content_type() == 'application/json' else None

            try:
                self.assertEqual(request('/api/wifi-networks', authorized=False)[0], 403)
                self.assertEqual(request('/api/wifi-status', authorized=False)[0], 403)
                self.assertEqual(request('/api/wifi-status', {})[0], 404)
                self.assertEqual(request('/api/wifi-networks')[1]['saved'][0]['uuid'], HOME)
                self.assertEqual(request('/api/wifi-networks', {})[0], 200)
                self.assertEqual(request('/api/wifi-connect', {'uuid': OTHER}, origin='http://other')[0], 403)
                self.assertEqual(request('/api/wifi-connect', {'uuid': OTHER}, authorized=False)[0], 403)
                self.assertEqual(request('/api/wifi-forget', {'uuid': AP_UUID})[0], 400)
                self.assertEqual(request('/api/wifi-connect', {'uuid': OTHER})[0], 202)
                self.assertEqual(request('/api/wifi-forget', {'uuid': HOME})[0], 409)
                network.step(1, Event())
                self.assertEqual(request('/api/wifi-status')[1]['status'], 'connected')
                self.assertEqual(request('/api/wifi-forget', {'uuid': OTHER})[0], 202)
                network.step(2, Event())
                self.assertEqual(request('/api/wifi-status')[1]['status'], 'forgotten')
            finally:
                server.shutdown()
                server.server_close()


class HelperChecks(unittest.TestCase):
    def setUp(self):
        class Connection:
            def __init__(self, values):
                self.values = values
                self.deleted = False

            def GetSettings(self, **kwargs):
                return self.values

            def Delete(self, **kwargs):
                self.deleted = True

        self.connections = {
            HOME: Connection({'connection': {'type': '802-11-wireless', 'interface-name': 'wlan0'},
                              '802-11-wireless': {'mode': 'infrastructure'}}),
            WIRED: Connection({'connection': {'type': '802-3-ethernet'}}),
        }

        def add(values, **kwargs):
            self.new_profile = values['connection']['uuid']
            self.connections[self.new_profile] = Connection(values)
            return self.new_profile

        settings = SimpleNamespace(GetConnectionByUuid=lambda value, **kwargs: value,
                                   AddConnectionUnsaved=add)
        def get_object(service, path):
            if path.endswith('/Settings'):
                return settings
            if path == '/org/freedesktop/NetworkManager':
                return SimpleNamespace(GetDeviceByIpIface=lambda interface, **kwargs: '/wireless')
            if path == '/wireless':
                return SimpleNamespace(Get=lambda interface, name, **kwargs: '00:11:22:33:44:55')
            return self.connections[path]

        bus = SimpleNamespace(get_object=get_object)
        module = SimpleNamespace(SystemBus=lambda: bus, Interface=lambda obj, interface: obj,
                                 Boolean=bool, ByteArray=bytes, DBusException=RuntimeError)
        self.dbus = patch.dict(sys.modules, {'dbus': module})
        self.dbus.start()
        self.link = patch.object(NetworkManagerRadio, 'link', return_value=(HOME, '192.168.1.20'))
        self.link.start()
        self.addCleanup(self.dbus.stop)
        self.addCleanup(self.link.stop)

    def test_saved_connect_uses_the_selected_uuid(self):
        with patch('wifi_setup.nmcli', return_value='') as command:
            configure('connect', '', '', profile=HOME)
        self.assertIn(unittest.mock.call('connection', 'up', 'uuid', HOME, 'ifname', 'wlan0', wait=30), command.call_args_list)

    def test_scan_is_restricted_to_the_wifi_interface(self):
        with patch('wifi_setup.nmcli', return_value='') as command:
            configure('scan')
        self.assertEqual(command.call_args.args, ('device', 'wifi', 'list', 'ifname', 'wlan0', '--rescan', 'yes'))

    def test_forget_deletes_only_the_selected_wifi_profile(self):
        with patch('wifi_setup.nmcli', return_value='') as command:
            configure('forget', '', '', profile=HOME)
        self.assertIn(unittest.mock.call('connection', 'delete', 'uuid', HOME), command.call_args_list)
        self.assertFalse(self.connections[WIRED].deleted)

    def test_wired_hotspot_and_other_radio_profiles_cannot_be_managed(self):
        self.connections[OTHER] = SimpleNamespace(GetSettings=lambda **kwargs: {
            'connection': {'type': '802-11-wireless', 'interface-name': 'wlan1'},
            '802-11-wireless': {'mode': 'infrastructure'}})
        for action in ('connect', 'forget'):
            for identifier in (WIRED, AP_UUID, OTHER):
                with self.subTest(action=action, identifier=identifier), patch('wifi_setup.nmcli') as command:
                    with self.assertRaises(ValueError):
                        configure(action, '', '', profile=identifier)
                    command.assert_not_called()

    def test_profiles_with_other_adapter_restrictions_cannot_be_forgotten(self):
        for extra in ({'match': {'interface-name': ['wlan1']}},
                      {'802-11-wireless': {'mode': 'infrastructure', 'mac-address': bytes.fromhex('aabbccddeeff')}},
                      {'802-11-wireless': {'mac-address-blacklist': ['00:11:22:33:44:55']}},
                      {'802-11-wireless': {'mac-address-denylist': ['00:11:22:33:44:55']}}):
            self.connections[HOME].values = {'connection': {'type': '802-11-wireless'}, **extra}
            with self.subTest(extra=extra), patch('wifi_setup.nmcli', return_value=''), self.assertRaises(ValueError):
                configure('forget', '', '', profile=HOME)

    def test_saved_profile_bound_to_this_radio_can_be_managed(self):
        self.connections[HOME].values['802-11-wireless']['mac-address'] = bytes.fromhex('001122334455')
        with patch('wifi_setup.nmcli', return_value=''):
            configure('forget', '', '', profile=HOME)

    def test_failed_new_connection_is_deleted_and_previous_network_restored(self):
        commands = []

        def command(*args, **kwargs):
            commands.append(args)
            if args[:2] == ('connection', 'up') and args[3] != HOME:
                raise OSError('Wrong password')
            return ''

        with patch('wifi_setup.nmcli', side_effect=command), self.assertRaises(OSError):
            configure('connect', 'Cafe', 'abc12345')
        self.assertTrue(self.connections[self.new_profile].deleted)
        self.assertIn(('connection', 'up', 'uuid', HOME, 'ifname', 'wlan0'), commands)

    def test_hotspot_join_remains_unavailable_from_the_lan(self):
        with self.assertRaises(ValueError):
            configure('join', 'Cafe', 'abc12345')


if __name__ == '__main__':
    unittest.main()
