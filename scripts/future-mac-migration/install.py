#!/usr/bin/env python3
"""Verify and prepare the Future helper on an Intel Mac. Default: read-only plan."""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit


APP_FILES = {
    'app/scripts/future_btc5m_assistant.py', 'app/scripts/future_btc5m_bridge.py',
    'app/scripts/future_btc5m_series.py', 'app/scripts/future_btc5m_runtime.py',
    'app/scripts/requirements-future-btc5m.txt', 'app/scripts/start-future-btc5m-tunnel.sh',
    *('app/scripts/future-btc5m-extension/' + name for name in
      ('manifest.json', 'content.js', 'background.js', 'buy_once.js', 'renderer.js')),
}
TOP_FILES = {'install.py', 'install.command', 'manage.py', 'manage.command', 'profile.json',
             'README.md', 'HANDOFF.md', 'SHA256SUMS', 'server-known-hosts'}
STRATEGIES = {'btc5m_favorite': '5m', 'btc15m_counter_1h': '15m'}
PROFILE_FIELDS = {'strategy', 'weekendOnly', 'amountUsd', 'serverHost', 'proxyHttp', 'proxySocks', 'extensionVersion'}
DEFAULT_ROOT = Path.home() / 'Library/Application Support/PolyHermesFuture'
REQUIRED = APP_FILES | {'install.py', 'install.command', 'manage.py', 'manage.command', 'profile.json', 'server-known-hosts'}
MANIFEST_FIELDS = {'schemaVersion', 'files', 'target', 'createdAt', 'extensionVersion', 'installationStartsTrading',
                   'containsCredentials', 'offlineWheels', 'sourceHashes'}
LABELS = ('com.polyhermes.future-btc5m-assistant', 'com.polyhermes.future-btc5m-tunnel')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def no_duplicate_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_FIELD')
        result[key] = value
    return result


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=no_duplicate_fields)


def relative_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\x00' in name or
            PurePosixPath(name).is_absolute() or PurePosixPath(name).as_posix() != name or
            any(part in ('.', '..') for part in PurePosixPath(name).parts)):
        raise ValueError('UNSAFE_MANIFEST_PATH')
    return name


def allowed_file(name):
    return name in APP_FILES | TOP_FILES or bool(re.fullmatch(
        r'vendor/(?:wheels/(?:websockets-16\.0|python_socks-3\.1\.1|async_timeout-5\.0\.1)-py3-none-any\.whl|'
        r'python-3\.13\.[0-9]+-macos11\.pkg|googlechrome\.dmg|provenance\.json)', name))


def reject_symlinks(path):
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('SYMLINK_PATH_REFUSED')


def verify_bundle(bundle):
    reject_symlinks(bundle)
    manifest_path = bundle / 'BUNDLE-MANIFEST.json'
    if manifest_path.is_symlink():
        raise ValueError('SYMLINK_MANIFEST_REFUSED')
    manifest = load_json(manifest_path)
    if (type(manifest) is not dict or not {'schemaVersion', 'files'} <= set(manifest) <= MANIFEST_FIELDS or
            type(manifest['schemaVersion']) is not int or manifest['schemaVersion'] != 1 or
            type(manifest['files']) is not dict or not REQUIRED <= manifest['files'].keys()):
        raise ValueError('INVALID_BUNDLE_MANIFEST')
    files = manifest['files']
    for name, digest in files.items():
        relative_name(name)
        if not allowed_file(name):
            raise ValueError('BUNDLE_FILE_NOT_IN_ALLOWLIST: ' + name)
        if not isinstance(digest, str) or re.fullmatch(r'[0-9a-f]{64}', digest) is None:
            raise ValueError('INVALID_FILE_HASH')
    expected = set(files) | {'BUNDLE-MANIFEST.json'}
    directories = {str(parent) for name in expected for parent in PurePosixPath(name).parents if str(parent) != '.'}
    for path in bundle.rglob('*'):
        name = path.relative_to(bundle).as_posix()
        if path.is_symlink():
            raise ValueError('SYMLINK_BUNDLE_ENTRY_REFUSED: ' + name)
        if path.is_dir():
            if name not in directories:
                raise ValueError('UNLISTED_BUNDLE_DIRECTORY: ' + name)
        elif path.name == '.DS_Store' and path.is_file():
            # Finder creates this mutable metadata while the operator opens the bundle.
            # It is never part of the verified runtime allowlist or installation copy.
            continue
        elif not path.is_file() or name not in expected:
            raise ValueError('UNLISTED_BUNDLE_FILE: ' + name)
    for name, digest in files.items():
        if not (bundle / name).is_file() or sha256(bundle / name) != digest:
            raise ValueError('BUNDLE_HASH_MISMATCH: ' + name)
    return manifest


def proxy_settings(profile, proxy_http, proxy_socks, direct):
    if direct and (proxy_http is not None or proxy_socks is not None):
        raise ValueError('PROXY_OPTIONS_CONFLICT')
    http = None if direct else profile['proxyHttp'] if proxy_http is None else proxy_http
    socks = None if direct else profile['proxySocks'] if proxy_socks is None else proxy_socks
    if http == '':
        http = None
    if socks == '':
        socks = None
    if http is not None:
        if not isinstance(http, str):
            raise ValueError('INVALID_HTTP_PROXY')
        parsed = urlsplit(http)
        if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password or
                parsed.path not in ('', '/') or parsed.query or parsed.fragment or not parsed.port or parsed.port > 65535):
            raise ValueError('INVALID_HTTP_PROXY')
    if socks is not None:
        if not isinstance(socks, str):
            raise ValueError('INVALID_SOCKS_PROXY')
        match = re.fullmatch(r'127\.0\.0\.1:([1-9][0-9]{0,4})', socks)
        if not match or int(match[1]) > 65535:
            raise ValueError('INVALID_SOCKS_PROXY')
    return http, socks


def profile_config(bundle):
    profile = load_json(bundle / 'profile.json')
    if (type(profile) is not dict or set(profile) != PROFILE_FIELDS or not isinstance(profile['strategy'], str) or profile['strategy'] not in STRATEGIES or
            type(profile['weekendOnly']) is not bool or type(profile['amountUsd']) not in (int, float) or profile['amountUsd'] != 1 or
            profile['serverHost'] != 'root@107.191.42.75' or
            not isinstance(profile['extensionVersion'], str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', profile['extensionVersion'])):
        raise ValueError('INVALID_BUNDLE_PROFILE')
    extension = load_json(bundle / 'app/scripts/future-btc5m-extension/manifest.json')
    if extension.get('version') != profile['extensionVersion']:
        raise ValueError('EXTENSION_VERSION_MISMATCH')
    return profile


def ports_in_use():
    ports = []
    for port in (8766, 8767):
        with socket.socket() as connection:
            connection.settimeout(0.25)
            if connection.connect_ex(('127.0.0.1', port)) == 0:
                ports.append(port)
    return ports


def clean_environment():
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('PIP_') and key not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV')}
    environment.update(PIP_CONFIG_FILE=os.devnull, PYTHONDONTWRITEBYTECODE='1')
    return environment


def choose_python(requested, runner):
    candidates = [requested] if requested else [
        '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',
        shutil.which('python3.13'), sys.executable, shutil.which('python3')]
    for candidate in dict.fromkeys(value for value in candidates if value):
        try:
            result = runner([str(candidate), '-c', 'import json,platform,sys; print(json.dumps({"version":list(sys.version_info[:3]),'
                            '"machine":platform.machine(),"system":platform.system()}))'], check=True,
                            capture_output=True, text=True, env=clean_environment())
            details = json.loads(result.stdout)
            version = details['version']
            if len(version) == 3 and all(type(value) is int for value in version) and version[0] == 3 and version >= [3, 10, 0]:
                return str(Path(candidate).absolute()), details
        except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError):
            pass
    return None, None


def host_details(runner):
    result = {'system': platform.system(), 'machine': platform.machine(), 'macos': platform.mac_ver()[0], 'translated': False}
    if result['system'] == 'Darwin':
        try:
            probe = runner(['/usr/sbin/sysctl', '-n', 'sysctl.proc_translated'], check=False,
                           capture_output=True, text=True, env=clean_environment())
            # The OID is absent on Intel; Rosetta reports 1 even though machine() says x86_64.
            if probe.returncode == 0 and probe.stdout.strip() in ('0', '1'):
                result['translated'] = probe.stdout.strip() == '1'
            elif probe.returncode == 1 and 'unknown oid' in probe.stderr.lower():
                result['translated'] = False
            else:
                result['translated'] = None
        except OSError:
            result['translated'] = None
    return result


def inspect_installed(root, bundle_hash):
    receipt = root / 'install-receipt.json'
    if not receipt.is_file() or receipt.is_symlink():
        raise ValueError('DESTINATION_NOT_EMPTY_OR_INCOMPLETE')
    data = load_json(receipt)
    expected_files = APP_FILES | {'manage.py', 'manage.command', 'ssh/known_hosts',
                                 *('launchd/' + label + '.plist' for label in LABELS)}
    if (type(data) is not dict or data.get('schemaVersion') != 1 or data.get('bundleManifestSha256') != bundle_hash or
            data.get('targetRoot') != str(root) or not isinstance(data.get('files'), dict) or set(data['files']) != expected_files):
        raise ValueError('DESTINATION_NOT_SAME_INSTALLATION')
    for name, digest in data['files'].items():
        relative_name(name)
        path = root / name
        reject_symlinks(path)
        if not path.is_file() or sha256(path) != digest:
            raise ValueError('DESTINATION_INSTALLATION_CHANGED: ' + name)
    config_path = root / 'config.json'
    reject_symlinks(config_path)
    config = load_json(config_path)
    if (config.get('targetRoot') != str(root) or config.get('amountUsd') != 1 or
            config.get('python') != str(root / '.venv/bin/python') or not (root / '.venv/bin/python').is_file()):
        raise ValueError('DESTINATION_CONFIG_INVALID')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    path.chmod(0o600)


def write_plists(root, config):
    environment = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin'}
    if config['proxyHttp']:
        environment.update(HTTP_PROXY=config['proxyHttp'], HTTPS_PROXY=config['proxyHttp'])
    if config['proxySocks']:
        environment['ALL_PROXY'] = 'socks5://' + config['proxySocks']
    arguments = [[config['python'], str(root / 'app/scripts/future_btc5m_assistant.py'), '--watch', '--state-dir', str(root / 'state')],
                 ['/bin/bash', str(root / 'app/scripts/start-future-btc5m-tunnel.sh'), '--remove-stale-socket']]
    if config['proxySocks']:
        arguments[1] += ['--socks-proxy', config['proxySocks']]
    for index, label in enumerate(LABELS):
        log_directory = root / 'logs' / ('assistant' if index == 0 else 'tunnel')
        log_directory.mkdir(parents=True, exist_ok=True)
        value = {'Label': label, 'ProgramArguments': arguments[index], 'WorkingDirectory': str(root),
                 'EnvironmentVariables': environment if index == 0 else {'PATH': environment['PATH']},
                 'StandardOutPath': str(log_directory / 'stdout.log'), 'StandardErrorPath': str(log_directory / 'stderr.log'),
                 'KeepAlive': True, 'RunAtLoad': True, 'ThrottleInterval': 15, 'AbandonProcessGroup': False}
        path = root / 'launchd' / (label + '.plist')
        path.write_bytes(plistlib.dumps(value))
        path.chmod(0o600)


def install_bundle(bundle, target_root=DEFAULT_ROOT, *, python=None, proxy_http=None, proxy_socks=None,
                   direct=False, write=False, runner=None, host=None):
    runner = runner or subprocess.run
    bundle = Path(os.path.abspath(Path(bundle).expanduser()))
    root = Path(os.path.abspath(Path(target_root).expanduser()))
    reject_symlinks(root)
    if root == bundle or bundle in root.parents or root in bundle.parents:
        raise ValueError('DESTINATION_OVERLAPS_BUNDLE')
    manifest = verify_bundle(bundle)
    profile = profile_config(bundle)
    host_key = (bundle / 'server-known-hosts').read_text(encoding='ascii').strip().split()
    if (len(host_key) != 3 or host_key[:2] != ['107.191.42.75', 'ssh-ed25519'] or
            re.fullmatch(r'[A-Za-z0-9+/=]+', host_key[2]) is None):
        raise ValueError('INVALID_PUBLIC_SERVER_HOST_KEY')
    http, socks = proxy_settings(profile, proxy_http, proxy_socks, direct)
    bundle_hash = sha256(bundle / 'BUNDLE-MANIFEST.json')
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        inspect_installed(root, bundle_hash)
        return {'status': 'ALREADY_INSTALLED', 'targetRoot': str(root), 'statePreserved': True, 'servicesStarted': False}
    host = host or host_details(runner)
    host_ok = (host['system'] == 'Darwin' and host['machine'] == 'x86_64' and
               host.get('translated', False) is False and re.match(r'^[0-9]+', host['macos']) is not None and
               int(host['macos'].split('.')[0]) >= 13)
    executable, runtime = choose_python(python, runner)
    blockers = []
    if not host_ok:
        blockers.append('HOST_REQUIRES_MACOS_13_OR_NEWER_X86_64 (x86_64 Intel Mac)')
    if not executable:
        blockers.append('PYTHON_3_10_OR_NEWER_REQUIRED; install bundled vendor/python-3.13.*-macos11.pkg manually')
    elif runtime['machine'] != 'x86_64' or runtime['system'] != 'Darwin':
        blockers.append('PYTHON_REQUIRES_NATIVE_X86_64_MACOS')
    occupied = ports_in_use()
    if occupied:
        blockers.append('LOCAL_PORT_ALREADY_IN_USE: ' + ','.join(map(str, occupied)))
    wheels = {Path(name).name for name in manifest['files'] if name.startswith('vendor/wheels/')}
    if wheels != {'websockets-16.0-py3-none-any.whl', 'python_socks-3.1.1-py3-none-any.whl',
                  'async_timeout-5.0.1-py3-none-any.whl'}:
        blockers.append('OFFLINE_WHEELS_MISSING')
    result = {'status': 'PLAN', 'targetRoot': str(root), 'strategy': profile['strategy'], 'amountUsd': 1,
              'extensionVersion': profile['extensionVersion'], 'python': executable, 'blockers': blockers,
              'proxyHttp': http, 'proxySocks': socks, 'servicesStarted': False,
              'nextSteps': ['确认目标机代理或使用 --direct；安装不会验证网络已就绪。',
                            '安装 Chrome，手动登录 Future 并加载 app/scripts/future-btc5m-extension。',
                            '用 manage.command 为新机生成 SSH key 并单独授权；不会复制私钥。',
                            '完成旧机停止交接后，才可移除 STOP 并开启自动准备。']}
    if not write:
        return result
    if blockers:
        raise ValueError('; '.join(blockers))
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    for directory in ('state/bridge', 'ssh', 'launchd'):
        (root / directory).mkdir(parents=True, exist_ok=True)
        (root / directory).chmod(0o700)
    for name in ('state/STOP', 'state/bridge/STOP'):
        (root / name).write_text('Migration prepared disabled; complete the source-stop handoff before enabling.\n')
    write_json(root / 'state/bridge/control.json', {'requestedEnabled': False, 'enabledAt': None, 'amountUsd': 1,
               'series': STRATEGIES[profile['strategy']], 'strategy': profile['strategy'], 'updatedAt': time.time()})
    installed_files = []
    for name in sorted(APP_FILES | {'manage.py', 'manage.command'}):
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle / name, destination)
        destination.chmod(0o700 if name.endswith(('.command', '.sh')) else 0o600)
        installed_files.append(name)
    known_hosts = root / 'ssh/known_hosts'
    shutil.copyfile(bundle / 'server-known-hosts', known_hosts)
    known_hosts.chmod(0o600)
    installed_files.append('ssh/known_hosts')
    tunnel = root / 'app/scripts/start-future-btc5m-tunnel.sh'
    text = tunnel.read_text(encoding='utf-8')
    substitutions = {'FUTURE_TUNNEL_HOST="root@107.191.42.75"': 'FUTURE_TUNNEL_HOST=' + shlex.quote(profile['serverHost']),
                     'FUTURE_TUNNEL_KEY="$HOME/.ssh/polymtrade_vultr_ed25519"': 'FUTURE_TUNNEL_KEY=' + shlex.quote(str(root / 'ssh/id_ed25519'))}
    for old, new in substitutions.items():
        if text.count(old) != 1:
            raise ValueError('TUNNEL_TEMPLATE_MISMATCH; installation remains disabled')
        text = text.replace(old, new)
    if text.count('ssh -T') != 2:
        raise ValueError('TUNNEL_SSH_TEMPLATE_MISMATCH; installation remains disabled')
    text = text.replace('ssh -T', 'ssh -o UserKnownHostsFile=' + shlex.quote(str(known_hosts)) +
                        ' -o StrictHostKeyChecking=yes -T')
    tunnel.write_text(text, encoding='utf-8')
    config = {**profile, 'schemaVersion': 1, 'targetRoot': str(root), 'python': str(root / '.venv/bin/python'),
              'sshKey': str(root / 'ssh/id_ed25519'), 'proxyHttp': http or '', 'proxySocks': socks or ''}
    write_json(root / 'config.json', config)
    environment = clean_environment()
    runner([executable, '-m', 'venv', str(root / '.venv')], check=True, capture_output=True, text=True, env=environment)
    runner([config['python'], '-m', 'pip', 'install', '--disable-pip-version-check', '--no-cache-dir', '--no-index',
            '--find-links', str(bundle / 'vendor/wheels'), '-r', str(root / 'app/scripts/requirements-future-btc5m.txt')],
           check=True, capture_output=True, text=True, env=environment)
    write_plists(root, config)
    installed_files += ['launchd/' + label + '.plist' for label in LABELS]
    write_json(root / 'install-receipt.json', {'schemaVersion': 1, 'targetRoot': str(root),
               'bundleManifestSha256': bundle_hash, 'installedAt': time.time(),
               'files': {name: sha256(root / name) for name in installed_files}})
    return {**result, 'status': 'INSTALLED_DISABLED', 'blockers': [], 'statePreserved': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--plan', action='store_true', help='verify and show the read-only plan (default)')
    action.add_argument('--install', action='store_true', help='prepare a disabled installation; never starts services')
    parser.add_argument('--bundle-root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--target-root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--python')
    parser.add_argument('--proxy-http')
    parser.add_argument('--proxy-socks')
    parser.add_argument('--direct', action='store_true')
    args = parser.parse_args(argv)
    try:
        result = install_bundle(args.bundle_root, args.target_root, python=args.python, proxy_http=args.proxy_http,
                                proxy_socks=args.proxy_socks, direct=args.direct, write=args.install)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        message = 'RUNTIME_SETUP_FAILED; installation remains disabled' if isinstance(error, subprocess.CalledProcessError) else str(error)
        print(json.dumps({'status': 'REFUSED', 'error': message}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
