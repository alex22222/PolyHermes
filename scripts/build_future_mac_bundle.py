"""Freeze the isolated Future helper into a credential-free Intel Mac deployment bundle."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import plistlib
import re
import tempfile
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    'scripts/future_btc5m_assistant.py', 'scripts/future_btc5m_bridge.py',
    'scripts/future_btc5m_series.py', 'scripts/future_btc5m_runtime.py',
    'scripts/requirements-future-btc5m.txt', 'scripts/start-future-btc5m-tunnel.sh',
    'scripts/future-btc5m-extension/manifest.json', 'scripts/future-btc5m-extension/background.js',
    'scripts/future-btc5m-extension/content.js', 'scripts/future-btc5m-extension/buy_once.js',
    'scripts/future-btc5m-extension/renderer.js',
)
TOOL_FILES = ('install.py', 'install.command', 'manage.py', 'manage.command', 'server-known-hosts')
PROFILE_FIELDS = {'strategy', 'weekendOnly', 'amountUsd', 'serverHost', 'proxyHttp', 'proxySocks', 'extensionVersion'}
WHEELS = {'websockets-16.0-py3-none-any.whl', 'python_socks-3.1.1-py3-none-any.whl',
          'async_timeout-5.0.1-py3-none-any.whl'}
VENDOR_FILES = {'googlechrome.dmg', 'python-3.13.16-macos11.pkg', 'provenance.json'} | {'wheels/' + name for name in WHEELS}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_profile(profile):
    if (not isinstance(profile, dict) or set(profile) != PROFILE_FIELDS or
            profile['strategy'] not in ('btc5m_favorite', 'btc15m_counter_1h') or
            type(profile['weekendOnly']) is not bool or type(profile['amountUsd']) is not int or profile['amountUsd'] != 1 or
            not re.fullmatch(r'[A-Za-z0-9._-]+@[A-Za-z0-9.-]+', profile['serverHost']) or
            not re.fullmatch(r'\d+\.\d+\.\d+', profile['extensionVersion'])):
        raise ValueError('Invalid or unexpected migration profile')
    for field, pattern in [('proxyHttp', r'http://127\.0\.0\.1:([1-9]\d{0,4})'),
                           ('proxySocks', r'127\.0\.0\.1:([1-9]\d{0,4})')]:
        value = profile[field]
        match = re.fullmatch(pattern, value) if isinstance(value, str) else None
        if value != '' and (not match or int(match[1]) > 65535):
            raise ValueError('Only an explicit loopback proxy is supported')


def capture_profile(source_root=ROOT):
    # Loopback requests explicitly bypass any environment proxy. Do not capture wallet fields.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path, headers=None):
        request = urllib.request.Request('http://127.0.0.1:8766' + path, headers=headers or {})
        with opener.open(request, timeout=3) as response:
            return json.load(response)
    status = get('/bridge/status')
    schedule = get('/bridge/preparation/schedule', {'X-PolyHermes-Future-Preparation': '1'})
    extension = json.loads((source_root / 'scripts/future-btc5m-extension/manifest.json').read_text())
    agent = plistlib.loads((source_root / 'scripts/launchd/com.polyhermes.future-btc5m-assistant.plist').read_bytes())
    proxy = agent.get('EnvironmentVariables', {}).get('HTTPS_PROXY', '')
    profile = {'strategy': status.get('strategy'), 'weekendOnly': schedule.get('weekendOnly'),
               'amountUsd': status.get('amountUsd'), 'serverHost': 'root@107.191.42.75',
               'proxyHttp': proxy, 'proxySocks': proxy.removeprefix('http://') if proxy else '',
               'extensionVersion': extension['version']}
    validate_profile(profile)
    return profile


def regular_file(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError('Missing or linked bundle input: ' + str(path))
    return path


def build_bundle(source_root, tools_root, docs_path, output_dir, profile, vendor_dir=None):
    validate_profile(profile)
    source_root, tools_root, output_dir = Path(source_root), Path(tools_root), Path(output_dir)
    # Read only the exact runtime allowlist, never the checkout, browser profile, state or credentials.
    source = {name: regular_file(source_root / name).read_bytes() for name in RUNTIME_FILES}
    extension = json.loads(source['scripts/future-btc5m-extension/manifest.json'])
    if extension.get('version') != profile['extensionVersion']:
        raise ValueError('Profile and frozen extension versions disagree')
    inputs = {'app/' + name: data for name, data in source.items()}
    tools = {name: regular_file(tools_root / name).read_bytes() for name in TOOL_FILES}
    inputs.update(tools)
    inputs['README.md'] = regular_file(docs_path).read_bytes()
    inputs['profile.json'] = (json.dumps(profile, ensure_ascii=False, indent=2) + '\n').encode()
    if vendor_dir is not None:
        vendor_dir = Path(vendor_dir)
        for path in sorted(vendor_dir.rglob('*')):
            if path.is_symlink():
                raise ValueError('Linked vendor input refused')
            if path.is_file():
                relative = path.relative_to(vendor_dir).as_posix()
                if relative not in VENDOR_FILES:
                    raise ValueError('Unexpected vendor input: ' + relative)
                inputs['vendor/' + relative] = regular_file(path).read_bytes()
        if not all('vendor/wheels/' + name in inputs for name in WHEELS):
            raise ValueError('All architecture-independent pinned wheels are required')
    name = 'PolyHermesFuture-Intel-' + datetime.now(timezone.utc).strftime('%Y%m%d')
    output_dir.mkdir(parents=True, exist_ok=True)
    folder, archive = output_dir / name, output_dir / (name + '.zip')
    if folder.exists() or archive.exists():
        raise ValueError('Bundle destination already exists; choose a new output directory')
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(inputs.items())}
    manifest = {'schemaVersion': 1, 'createdAt': datetime.now(timezone.utc).isoformat(),
                'target': 'Intel Mac / macOS 13+', 'extensionVersion': extension['version'],
                'installationStartsTrading': False, 'containsCredentials': False,
                'offlineWheels': all('vendor/wheels/' + name in inputs for name in WHEELS),
                'sourceHashes': {name: hashlib.sha256(data).hexdigest() for name, data in source.items()},
                'files': hashes}
    for name, data in source.items():
        if regular_file(source_root / name).read_bytes() != data:
            raise ValueError('Runtime source changed while freezing the package; build again')
    for name, data in tools.items():
        if regular_file(tools_root / name).read_bytes() != data:
            raise ValueError('Deployment tooling changed while freezing the package; build again')
    with tempfile.TemporaryDirectory(prefix='.future-bundle-', dir=output_dir) as staging:
        staged = Path(staging) / folder.name
        staged.mkdir()
        for name, data in inputs.items():
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o755 if name.endswith('.command') or name.endswith('.sh') else 0o600)
        (staged / 'BUNDLE-MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        staged.rename(folder)
    try:
        with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as packed:
            for path in sorted(folder.rglob('*')):
                if path.is_file():
                    packed.write(path, folder.name + '/' + path.relative_to(folder).as_posix(),
                                 compress_type=zipfile.ZIP_STORED if path.suffix in ('.pkg', '.dmg', '.whl') else zipfile.ZIP_DEFLATED)
        checksum = archive.with_suffix('.zip.sha256')
        checksum.write_text(sha256(archive) + '  ' + archive.name + '\n')
    except Exception:
        # Keep the frozen directory available for inspection; never alter source state.
        archive.unlink(missing_ok=True)
        raise
    return folder, archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', type=Path, help='Explicit sanitized profile; otherwise read the running helper without changing it')
    parser.add_argument('--vendor-dir', type=Path)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text()) if args.profile else capture_profile()
    folder, archive = build_bundle(ROOT, ROOT / 'scripts/future-mac-migration',
                                   ROOT / 'docs/future-intel-mac-migration.md', args.output, profile, args.vendor_dir)
    print(json.dumps({'folder': str(folder.resolve()), 'archive': str(archive.resolve()),
                      'sha256': sha256(archive), 'profile': profile, 'sourceChanged': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
