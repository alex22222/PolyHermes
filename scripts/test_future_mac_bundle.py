import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).with_name('build_future_mac_bundle.py')
spec = importlib.util.spec_from_file_location('future_mac_bundle', SCRIPT)
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class FutureMacBundleTest(unittest.TestCase):
    def fixture(self, root):
        source = root / 'source'
        tools = root / 'tools'
        for relative in bundle.RUNTIME_FILES:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'version': '0.7.3'}) if relative.endswith('manifest.json') else '# fixture\n')
        for name in bundle.TOOL_FILES:
            path = tools / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture\n')
        docs = root / 'README.md'
        docs.write_text('迁移说明\n')
        profile = {'strategy': 'btc15m_counter_1h', 'weekendOnly': False, 'amountUsd': 1,
                   'serverHost': 'root@107.191.42.75', 'proxyHttp': 'http://127.0.0.1:7890',
                   'proxySocks': '127.0.0.1:7890', 'extensionVersion': '0.7.3'}
        return source, tools, docs, profile

    def test_bundle_freezes_only_allowlisted_source_and_excludes_live_state_and_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, tools, docs, profile = self.fixture(root)
            for name in ['.env', '.ssh/id_ed25519', 'reports/future-btc5m-assistant/bridge/control.json',
                         'scripts/future-btc5m-runtime/.venv/bin/python', 'browser/Cookies']:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('SECRET_SENTINEL')
            folder, archive = bundle.build_bundle(source, tools, docs, root / 'out', profile)
            manifest = json.loads((folder / 'BUNDLE-MANIFEST.json').read_text())
            self.assertEqual(1, manifest['schemaVersion'])
            self.assertIn('app/scripts/future-btc5m-extension/renderer.js', manifest['files'])
            self.assertTrue(manifest['installationStartsTrading'] is False)
            for path in folder.rglob('*'):
                if path.is_file():
                    self.assertNotIn(b'SECRET_SENTINEL', path.read_bytes())
            with zipfile.ZipFile(archive) as packed:
                names = packed.namelist()
                self.assertTrue(all(name.startswith(folder.name + '/') for name in names))
                self.assertFalse(any('.venv' in name or 'Cookies' in name for name in names))
            original = (source / bundle.RUNTIME_FILES[0]).read_bytes()
            self.assertEqual(original, (folder / 'app' / bundle.RUNTIME_FILES[0]).read_bytes())

    def test_symlinks_and_missing_renderer_are_rejected_without_a_partial_bundle(self):
        for symlink in [False, True]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source, tools, docs, profile = self.fixture(root)
                renderer = source / 'scripts/future-btc5m-extension/renderer.js'
                renderer.unlink()
                if symlink:
                    renderer.symlink_to(docs)
                with self.assertRaises(ValueError):
                    bundle.build_bundle(source, tools, docs, root / 'out', profile)
                self.assertFalse(list((root / 'out').glob('*.zip')))

    def test_profiles_are_exact_and_amount_or_unknown_strategy_cannot_change(self):
        for changes in [{'amountUsd': 2}, {'amountUsd': True}, {'strategy': 'martingale'},
                        {'weekendOnly': 'false'}, {'apiToken': 'SECRET'},
                        {'serverHost': 'root@host; echo injected'}, {'proxyHttp': 'http://user:password@127.0.0.1:7890'}]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source, tools, docs, profile = self.fixture(root)
                with self.assertRaises(ValueError):
                    bundle.build_bundle(source, tools, docs, root / 'out', {**profile, **changes})

    def test_portable_wheels_only_and_every_packaged_file_has_a_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, tools, docs, profile = self.fixture(root)
            vendor = root / 'vendor'
            (vendor / 'wheels').mkdir(parents=True)
            wheel = vendor / 'wheels/websockets-16.0-py3-none-any.whl'
            wheel.write_bytes(b'fixture wheel')
            (vendor / 'wheels/python_socks-3.1.1-py3-none-any.whl').write_bytes(b'fixture socks')
            (vendor / 'wheels/async_timeout-5.0.1-py3-none-any.whl').write_bytes(b'fixture timeout')
            folder, _ = bundle.build_bundle(source, tools, docs, root / 'out', profile, vendor)
            files = json.loads((folder / 'BUNDLE-MANIFEST.json').read_text())['files']
            for name, digest in files.items():
                self.assertEqual(bundle.sha256(folder / name), digest)
            wheel.rename(vendor / 'wheels/websockets-16.0-cp314-macosx_arm64.whl')
            with self.assertRaises(ValueError):
                bundle.build_bundle(source, tools, docs, root / 'out2', profile, vendor)


if __name__ == '__main__':
    unittest.main()
