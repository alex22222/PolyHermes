import hashlib
import importlib.util
import json
import plistlib
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT = Path(__file__).with_name('future-mac-migration') / 'install.py'


class FutureMacInstallTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        self.target = self.root / 'Intel Mac' / 'PolyHermesFuture'
        spec = importlib.util.spec_from_file_location('future_mac_install', SCRIPT)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.profile = {'strategy': 'btc15m_counter_1h', 'weekendOnly': False, 'amountUsd': 1,
                        'serverHost': 'root@107.191.42.75', 'proxyHttp': 'http://127.0.0.1:7890',
                        'proxySocks': '127.0.0.1:7890', 'extensionVersion': '0.7.3'}
        names = ['install.py', 'install.command', 'manage.py', 'manage.command', 'README.md', 'server-known-hosts',
                 'app/scripts/future_btc5m_assistant.py', 'app/scripts/future_btc5m_bridge.py',
                 'app/scripts/future_btc5m_series.py', 'app/scripts/future_btc5m_runtime.py',
                 'app/scripts/requirements-future-btc5m.txt', 'app/scripts/start-future-btc5m-tunnel.sh',
                 'app/scripts/future-btc5m-extension/manifest.json',
                 'app/scripts/future-btc5m-extension/content.js', 'app/scripts/future-btc5m-extension/background.js',
                 'app/scripts/future-btc5m-extension/buy_once.js', 'app/scripts/future-btc5m-extension/renderer.js',
                 'vendor/wheels/websockets-16.0-py3-none-any.whl',
                 'vendor/wheels/python_socks-3.1.1-py3-none-any.whl',
                 'vendor/wheels/async_timeout-5.0.1-py3-none-any.whl']
        for name in names:
            self.write(name, 'fixture only\n')
        self.write('app/scripts/start-future-btc5m-tunnel.sh',
                   '#!/bin/bash\nFUTURE_TUNNEL_HOST="root@107.191.42.75"\n'
                   'FUTURE_TUNNEL_KEY="$HOME/.ssh/polymtrade_vultr_ed25519"\n'
                   'SSH=(ssh -T -o BatchMode=yes)\nssh -T -N\n')
        self.write('server-known-hosts', '107.191.42.75 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixtureOnlyPublicHostKey\n')
        self.write('app/scripts/requirements-future-btc5m.txt', 'websockets==16.0\npython-socks[asyncio]==3.1.1\n')
        self.write('app/scripts/future-btc5m-extension/manifest.json', '{"version":"0.7.3"}\n')
        self.write('profile.json', json.dumps(self.profile))
        self.manifest()
        self.commands = []

    def write(self, name, value):
        path = self.bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def manifest(self):
        files = {str(path.relative_to(self.bundle)): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in self.bundle.rglob('*') if path.is_file() and path.name != 'BUNDLE-MANIFEST.json'}
        self.write('BUNDLE-MANIFEST.json', json.dumps({'schemaVersion': 1, 'files': files}))

    def runner(self, command, **kwargs):
        self.commands.append(command)
        if '-c' in command:
            output = json.dumps({'version': [3, 13, 16], 'machine': 'x86_64', 'system': 'Darwin'})
        elif '-m' in command and 'venv' in command:
            python = Path(command[-1]) / 'bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('native x86_64 runtime fixture')
            output = ''
        else:
            output = ''
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr='')

    def execute(self, **kwargs):
        with patch.object(self.module, 'ports_in_use', return_value=[]):
            return self.module.install_bundle(self.bundle, self.target, python='/fixture/python3.13',
                runner=self.runner, host={'system': 'Darwin', 'machine': 'x86_64', 'macos': '13.7.4'}, **kwargs)

    def test_default_plan_is_read_only_even_on_arm(self):
        with patch.object(self.module, 'ports_in_use', return_value=[]):
            result = self.module.install_bundle(self.bundle, self.target, python='/fixture/python3.13',
                runner=self.runner, host={'system': 'Darwin', 'machine': 'arm64', 'macos': '15.7'})
        self.assertEqual('PLAN', result['status'])
        self.assertFalse(self.target.exists())
        self.assertTrue(any('x86_64' in value for value in result['blockers']))
        self.assertFalse(any('-m' in command for command in self.commands))

    def test_install_creates_only_disabled_portable_files_and_native_venv(self):
        before = {str(path.relative_to(self.bundle)): path.read_bytes() for path in self.bundle.rglob('*') if path.is_file()}
        result = self.execute(write=True)
        self.assertEqual('INSTALLED_DISABLED', result['status'])
        self.assertTrue((self.target / 'state/STOP').is_file())
        self.assertTrue((self.target / 'state/bridge/STOP').is_file())
        control = json.loads((self.target / 'state/bridge/control.json').read_text())
        self.assertEqual({'requestedEnabled': False, 'enabledAt': None, 'amountUsd': 1,
                          'series': '15m', 'strategy': 'btc15m_counter_1h'},
                         {key: value for key, value in control.items() if key != 'updatedAt'})
        self.assertIsInstance(control['updatedAt'], (int, float))
        config = json.loads((self.target / 'config.json').read_text())
        self.assertEqual(str(self.target), config['targetRoot'])
        self.assertEqual(str(self.target / '.venv/bin/python'), config['python'])
        self.assertEqual(str(self.target / 'ssh/id_ed25519'), config['sshKey'])
        self.assertFalse(config['weekendOnly'])
        self.assertEqual(self.profile['proxyHttp'], config['proxyHttp'])
        assistant = plistlib.loads((self.target / 'launchd/com.polyhermes.future-btc5m-assistant.plist').read_bytes())
        self.assertEqual([config['python'], str(self.target / 'app/scripts/future_btc5m_assistant.py'),
                          '--watch', '--state-dir', str(self.target / 'state')], assistant['ProgramArguments'])
        self.assertEqual(str(self.target), assistant['WorkingDirectory'])
        self.assertEqual(self.profile['proxyHttp'], assistant['EnvironmentVariables']['HTTPS_PROXY'])
        tunnel = plistlib.loads((self.target / 'launchd/com.polyhermes.future-btc5m-tunnel.plist').read_bytes())
        self.assertEqual(['/bin/bash', str(self.target / 'app/scripts/start-future-btc5m-tunnel.sh'),
                          '--remove-stale-socket', '--socks-proxy', '127.0.0.1:7890'], tunnel['ProgramArguments'])
        self.assertIn('FUTURE_TUNNEL_KEY=' + "'" + config['sshKey'] + "'", (self.target / 'app/scripts/start-future-btc5m-tunnel.sh').read_text())
        self.assertTrue((self.target / 'manage.py').is_file())
        self.assertFalse((self.target / 'ssh/id_ed25519').exists())
        self.assertTrue(any(command[1:3] == ['-m', 'venv'] for command in self.commands))
        pip = next(command for command in self.commands if 'pip' in command)
        self.assertIn('--no-index', pip)
        self.assertIn(str(self.bundle / 'vendor/wheels'), pip)
        self.assertFalse(any('launchctl' in command for command in self.commands))
        self.assertEqual(before, {str(path.relative_to(self.bundle)): path.read_bytes() for path in self.bundle.rglob('*') if path.is_file()})

    def test_existing_valid_install_is_inspected_without_overwriting_state(self):
        self.execute(write=True)
        state = self.target / 'state/bridge/control.json'
        state.write_text('{"fixtureOperatorState":true}\n')
        commands = len(self.commands)
        self.assertEqual('ALREADY_INSTALLED', self.execute(write=True)['status'])
        self.assertEqual('{"fixtureOperatorState":true}\n', state.read_text())
        self.assertFalse(any('-m' in command for command in self.commands[commands:]))

    def test_tunnel_uses_only_bundled_public_host_trust_without_global_ssh_changes(self):
        self.execute(write=True)
        known_hosts = self.target / 'ssh/known_hosts'
        self.assertEqual((self.bundle / 'server-known-hosts').read_bytes(), known_hosts.read_bytes())
        self.assertEqual(0o600, known_hosts.stat().st_mode & 0o777)
        script = (self.target / 'app/scripts/start-future-btc5m-tunnel.sh').read_text()
        self.assertEqual(2, script.count('StrictHostKeyChecking=yes'))
        self.assertEqual(2, script.count('UserKnownHostsFile='))
        self.assertIn(str(known_hosts), script)

    def test_public_bundle_provenance_metadata_is_verified_with_the_payload(self):
        self.write('vendor/provenance.json', '{"downloadSource":"https://www.python.org/"}')
        self.manifest()
        value = json.loads((self.bundle / 'BUNDLE-MANIFEST.json').read_text())
        value.update(target='Intel Mac Pro', createdAt='2026-10-17', extensionVersion='0.7.3',
                     installationStartsTrading=False, containsCredentials=False, offlineWheels=[], sourceHashes={})
        self.write('BUNDLE-MANIFEST.json', json.dumps(value))
        self.assertEqual('PLAN', self.execute()['status'])

    def test_nonempty_destination_or_symlink_destination_never_overwrites(self):
        self.target.mkdir(parents=True)
        unrelated = self.target / 'unrelated'
        unrelated.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'DESTINATION'):
            self.execute(write=True)
        self.assertEqual('keep', unrelated.read_text())
        other = self.root / 'linked'
        other.symlink_to(self.target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'):
            self.module.install_bundle(self.bundle, other, runner=self.runner)

    def test_hash_mismatch_fails_before_any_destination_is_created(self):
        self.write('app/scripts/future_btc5m_assistant.py', 'changed')
        with self.assertRaisesRegex(ValueError, 'HASH'):
            self.execute(write=True)
        self.assertFalse(self.target.exists())

    def test_manifest_paths_and_unlisted_payloads_fail_closed(self):
        original = json.loads((self.bundle / 'BUNDLE-MANIFEST.json').read_text())
        for name in ('../secret', '/private/tmp/secret', 'app/../secret', 'app//secret', r'app\secret'):
            value = {'schemaVersion': 1, 'files': {**original['files'], name: '0' * 64}}
            self.write('BUNDLE-MANIFEST.json', json.dumps(value))
            with self.assertRaises(ValueError):
                self.execute(write=True)
        self.write('BUNDLE-MANIFEST.json', json.dumps(original))
        self.write('.ssh/private_key', 'must never copy')
        with self.assertRaisesRegex(ValueError, 'UNLISTED|ALLOWLIST'):
            self.execute(write=True)
        self.assertFalse(self.target.exists())

    def test_finder_metadata_is_ignored_without_installing_it_or_ignoring_unsafe_entries(self):
        for name in ('.DS_Store', 'vendor/wheels/.DS_Store', 'app/scripts/future-btc5m-extension/.DS_Store'):
            self.write(name, 'Finder metadata changes independently of the runtime package')
        self.assertEqual('INSTALLED_DISABLED', self.execute(write=True)['status'])
        self.assertFalse(list(self.target.rglob('.DS_Store')))
        metadata = self.bundle / '.DS_Store'
        metadata.unlink()
        metadata.symlink_to(self.root / 'secret')
        with self.assertRaisesRegex(ValueError, 'SYMLINK'):
            self.execute()
        metadata.unlink()
        metadata.mkdir()
        with self.assertRaisesRegex(ValueError, 'UNLISTED'):
            self.execute()

    def test_bundle_symlink_and_arm_virtual_environment_are_not_copied(self):
        path = self.bundle / 'app/scripts/arm-venv'
        path.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'SYMLINK'):
            self.execute(write=True)
        path.unlink()
        self.write('app/scripts/future-btc5m-runtime/.venv/bin/python', 'ARM binary fixture')
        self.manifest()
        with self.assertRaisesRegex(ValueError, 'ALLOWLIST'):
            self.execute(write=True)
        self.assertFalse(self.target.exists())

    def test_unsupported_host_python_or_live_port_cannot_install(self):
        for host in ({'system': 'Darwin', 'machine': 'arm64', 'macos': '15.7'},
                     {'system': 'Darwin', 'machine': 'x86_64', 'macos': '12.7'},
                     {'system': 'Linux', 'machine': 'x86_64', 'macos': ''}):
            with self.assertRaisesRegex(ValueError, 'HOST'):
                self.module.install_bundle(self.bundle, self.target, python='/fixture/python3.13',
                                           runner=self.runner, host=host, write=True)
        with patch.object(self.module, 'ports_in_use', return_value=[8766]):
            with self.assertRaisesRegex(ValueError, 'PORT'):
                self.module.install_bundle(self.bundle, self.target, python='/fixture/python3.13',
                    runner=self.runner, host={'system': 'Darwin', 'machine': 'x86_64', 'macos': '13.7'}, write=True)
        self.assertFalse(self.target.exists())

    def test_proxy_choices_are_explicit_and_shell_metacharacters_cannot_enter_tunnel(self):
        self.execute(write=True, direct=True)
        config = json.loads((self.target / 'config.json').read_text())
        self.assertEqual('', config['proxyHttp'])
        self.assertEqual('', config['proxySocks'])
        assistant = plistlib.loads((self.target / 'launchd/com.polyhermes.future-btc5m-assistant.plist').read_bytes())
        self.assertNotIn('ALL_PROXY', assistant['EnvironmentVariables'])
        tunnel = plistlib.loads((self.target / 'launchd/com.polyhermes.future-btc5m-tunnel.plist').read_bytes())
        self.assertNotIn('--socks-proxy', tunnel['ProgramArguments'])
        separate = self.root / 'other'
        for proxy in ('http://user:secret@127.0.0.1:7890', 'http://evil.example:7890', 'http://127.0.0.1:7890/route'):
            with self.assertRaisesRegex(ValueError, 'PROXY'):
                self.module.install_bundle(self.bundle, separate, proxy_http=proxy, runner=self.runner)

    def test_destination_cannot_overlap_the_verified_bundle(self):
        destination = self.bundle / 'new-install'
        with self.assertRaisesRegex(ValueError, 'OVERLAP'):
            self.module.install_bundle(self.bundle, destination, runner=self.runner)
        self.assertFalse(destination.exists())

    def test_old_or_non_native_python_cannot_install(self):
        for details in ({'version': [3, 9, 1], 'machine': 'x86_64', 'system': 'Darwin'},
                        {'version': [3, 13, 16], 'machine': 'arm64', 'system': 'Darwin'}):
            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(details), stderr='')
            with patch.object(self.module, 'ports_in_use', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'PYTHON'):
                    self.module.install_bundle(self.bundle, self.target, python='/fixture/python', runner=runner,
                        host={'system': 'Darwin', 'machine': 'x86_64', 'macos': '13.7'}, write=True)
        self.assertFalse(self.target.exists())

    def test_offline_bundle_includes_the_python310_asyncio_marker_dependency(self):
        (self.bundle / 'vendor/wheels/async_timeout-5.0.1-py3-none-any.whl').unlink()
        self.manifest()
        with self.assertRaisesRegex(ValueError, 'WHEELS'):
            self.execute(write=True)
        self.assertFalse(self.target.exists())

    def test_rosetta_process_cannot_pass_as_a_native_intel_mac(self):
        with patch.object(self.module, 'ports_in_use', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'HOST'):
                self.module.install_bundle(self.bundle, self.target, python='/fixture/python3.13', runner=self.runner,
                    host={'system': 'Darwin', 'machine': 'x86_64', 'macos': '15.7', 'translated': True}, write=True)
        self.assertFalse(self.target.exists())

    def test_host_probe_distinguishes_intel_absent_oid_rosetta_and_unknown_probe_failure(self):
        for code, output, error, expected in [(1, '', "sysctl: unknown oid 'sysctl.proc_translated'", False),
                                              (0, '1\n', '', True), (0, '', '', None)]:
            def runner(command, **kwargs):
                self.assertEqual(['/usr/sbin/sysctl', '-n', 'sysctl.proc_translated'], command)
                return subprocess.CompletedProcess(command, code, stdout=output, stderr=error)
            with patch.object(self.module.platform, 'system', return_value='Darwin'), \
                    patch.object(self.module.platform, 'machine', return_value='x86_64'), \
                    patch.object(self.module.platform, 'mac_ver', return_value=('13.7', (), '')):
                self.assertIs(expected, self.module.host_details(runner)['translated'])

    def test_installer_command_uses_bundle_python_or_shows_bundled_pkg_without_admin_install(self):
        command = SCRIPT.with_name('install.command').read_text()
        self.assertIn('3.13', command)
        self.assertIn('python-3.13.', command)
        self.assertNotIn('sudo ', command)
        self.assertNotIn('brew ', command)


if __name__ == '__main__':
    unittest.main()
