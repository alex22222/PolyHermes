#!/usr/bin/env python3
"""Manage an isolated Future Mac install. No command enables automatic buying."""

import argparse
import hashlib
import json
import math
import os
import platform
import plistlib
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ASSISTANT = "com.polyhermes.future-btc5m-assistant"
TUNNEL = "com.polyhermes.future-btc5m-tunnel"
LABELS = (ASSISTANT, TUNNEL)
STRATEGIES = {"btc5m_favorite": "5m", "btc15m_counter_1h": "15m"}
HISTORY = {"rounds.jsonl", "bridge/control.json", "bridge/orders.jsonl", "bridge/preflight.jsonl",
           "bridge/preparations.jsonl", "bridge/strategy_decisions.jsonl", "bridge/buy_attempts.jsonl",
           "bridge/fills.jsonl", "bridge/resolutions.json"}
MAX_FILE = 128 * 1024 * 1024


class ManageError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ManageError(message)


def strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            require(key not in result, "Duplicate JSON field")
            result[key] = item
        return result

    try:
        return json.loads(value, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ManageError("Nonfinite JSON value")))
    except (ValueError, UnicodeError) as error:
        raise ManageError("Invalid JSON") from error


def safe_file(path):
    require(not path.is_symlink() and path.is_file(), "Expected a regular file: " + path.name)
    require(path.stat().st_size <= MAX_FILE, "File exceeds the migration size limit")
    return path.read_bytes()


def read_json(path):
    return strict_json(safe_file(path))


def write_json(path, value):
    require(not path.is_symlink(), "Refusing a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + ".tmp")
    require(not temporary.exists() and not temporary.is_symlink(), "Temporary file already exists")
    with temporary.open("x", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def touch_stop(state):
    for relative in ("STOP", "bridge/STOP"):
        path = state / relative
        require(path.resolve().is_relative_to(state.resolve()), "STOP path leaves state directory")
        require(not path.is_symlink(), "Refusing a symbolic STOP file")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.exists():
            require(path.is_file(), "STOP is not a regular file")
        else:
            path.write_text("Future migration: automatic buying must remain disabled.\n", encoding="utf-8")
            path.chmod(0o600)


def utc(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def validate_history(relative, raw):
    require(relative in HISTORY, "History file is outside the allowlist")
    if relative.endswith(".jsonl"):
        require(not raw or raw.endswith(b"\n"), "Incomplete JSONL ledger")
        for line in raw.splitlines():
            require(bool(line.strip()) and isinstance(strict_json(line), dict), "Invalid JSONL row")
    else:
        require(isinstance(strict_json(raw), dict), "Invalid history object")


class System:
    """Fixed local endpoints and argument arrays; tests inject a non-operating backend."""

    def now(self):
        return time.time()

    def sleep(self, seconds):
        time.sleep(seconds)

    def run(self, args, check=True, timeout=20, **kwargs):
        try:
            result = subprocess.run([str(arg) for arg in args], capture_output=True, text=True,
                                    timeout=timeout, **kwargs)
        except (OSError, subprocess.SubprocessError) as error:
            raise ManageError("Command unavailable or timed out: " + Path(args[0]).name) from error
        if check:
            require(result.returncode == 0, "Command failed: " + Path(args[0]).name)
        return result.stdout if result.returncode == 0 else None

    def agent(self, label):
        text = self.run(["launchctl", "print", f"gui/{os.getuid()}/{label}"], check=False)
        if text is None:
            return None
        match = re.search(r"^\s*pid = ([0-9]+)\s*$", text, re.MULTILINE)
        return {"pid": int(match[1]) if match else None, "text": text}

    def listener_pids(self, port):
        try:
            result = subprocess.run(["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                                    capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError) as error:
            raise ManageError("Cannot verify local port ownership") from error
        require(result.returncode in (0, 1) and not result.stderr.strip() and
                (result.returncode == 0 or not result.stdout.strip()), "Cannot verify local port ownership")
        values = result.stdout.split()
        require(all(value.isdigit() for value in values), "Invalid local port ownership reply")
        return {int(value) for value in values}

    def http(self, path, payload=None, preparation=False):
        allowed = {"/status", "/bridge/status", "/bridge/control", "/bridge/preparation", "/bridge/preparation/schedule"}
        require(path in allowed, "Unexpected local endpoint")
        require(payload is None or payload == {"enabled": False} or
                set(payload) == {"weekendOnly"} and type(payload["weekendOnly"]) is bool,
                "Only disabling and the weekend schedule are supported")
        headers = {"Accept": "application/json"}
        if preparation:
            headers["X-PolyHermes-Future-Preparation"] = "1"
        if payload is not None:
            headers["Content-Type"] = "application/json"
            if path == "/bridge/control":
                headers["X-PolyHermes-Future-Control"] = "1"
        request = urllib.request.Request("http://127.0.0.1:8766" + path,
            data=None if payload is None else json.dumps(payload).encode(), headers=headers)
        try:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs):
                    raise ManageError("Local endpoint redirect refused")
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=3) as response:
                raw = response.read(1024 * 1024 + 1)
                require(len(raw) <= 1024 * 1024, "Local response exceeds limit")
                value = strict_json(raw)
                require(isinstance(value, dict), "Invalid local response")
                return value
        except OSError as error:
            raise ManageError("Local assistant request was not confirmed") from error

    def proxy_available(self, endpoint):
        if not endpoint:
            return True
        value = endpoint.split("://", 1)[-1]
        match = re.fullmatch(r"127\.0\.0\.1:([1-9][0-9]{0,4})", value)
        if not match or int(match[1]) > 65535:
            return False
        try:
            with socket.create_connection(("127.0.0.1", int(match[1])), timeout=2):
                return True
        except OSError:
            return False

    def environment(self, python):
        probe = """import json,platform,ssl,sys
from zoneinfo import ZoneInfo
import websockets, python_socks
c=ssl.create_default_context()
if c.cert_store_stats()['x509_ca']==0:
    c.load_verify_locations(cafile='/etc/ssl/cert.pem')
print(json.dumps({'pythonOk':sys.version_info>=(3,10),'machine':platform.machine(),
'dependenciesOk':websockets.__version__=='16.0' and python_socks.__version__=='3.1.1',
'tlsOk':c.cert_store_stats()['x509_ca']>0,'zoneinfoOk':bool(ZoneInfo('America/New_York'))}))
"""
        value = {"platform": platform.system(), "macos": platform.mac_ver()[0], "machine": platform.machine(),
                 "pythonOk": False, "dependenciesOk": False, "tlsOk": False, "zoneinfoOk": False, "chromeMajor": 0}
        try:
            reply = self.run([python, "-c", probe], check=False)
            if reply:
                value.update(strict_json(reply))
        except ManageError:
            pass
        for app in (Path("/Applications/Google Chrome.app"), Path.home() / "Applications/Google Chrome.app"):
            try:
                data = plistlib.loads((app / "Contents/Info.plist").read_bytes())
                value["chromeMajor"] = int(data["CFBundleShortVersionString"].split(".")[0])
                break
            except (OSError, ValueError, KeyError):
                continue
        return value


class Manager:
    def __init__(self, root, system=None, home=None):
        self.root = Path(root).expanduser().resolve()
        self.system = system or System()
        self.home = Path(home) if home is not None else Path.home()
        self.domain = f"gui/{os.getuid()}"

    def config(self):
        value = read_json(self.root / "config.json")
        require(isinstance(value, dict) and type(value.get("schemaVersion")) is int and value["schemaVersion"] == 1 and
                value.get("targetRoot") == str(self.root) and type(value.get("amountUsd")) is int and value["amountUsd"] == 1 and
                isinstance(value.get("strategy"), str) and value["strategy"] in STRATEGIES and type(value.get("weekendOnly")) is bool and
                value.get("serverHost") == "root@107.191.42.75", "Invalid target configuration")
        require(isinstance(value.get("python"), str) and isinstance(value.get("sshKey"), str) and Path(value["python"]).is_absolute() and
                Path(value.get("sshKey", "")).resolve() == self.root / "ssh/id_ed25519", "Unexpected runtime/key path")
        for key in ("proxyHttp", "proxySocks"):
            require(isinstance(value.get(key), str), "Invalid proxy configuration")
        require((self.root / "state").resolve() == self.root / "state", "State directory cannot be a symlink")
        return value

    def installed(self, label):
        return self.home / "Library/LaunchAgents" / (label + ".plist")

    def validate_agent(self, path, label, source_root=None, state=None):
        try:
            value = plistlib.loads(safe_file(path))
        except (ValueError, plistlib.InvalidFileException) as error:
            raise ManageError("Invalid LaunchAgent") from error
        base = source_root or self.root
        scripts = base / ("scripts" if source_root else "app/scripts")
        expected = scripts / ("future_btc5m_assistant.py" if label == ASSISTANT else "start-future-btc5m-tunnel.sh")
        args = value.get("ProgramArguments", [])
        require(value.get("Label") == label and isinstance(args, list) and len(args) >= 2 and
                args[1] == str(expected) and Path(args[0]).is_absolute() and
                value.get("WorkingDirectory") == str(base), "LaunchAgent is not owned by this install")
        if label == ASSISTANT:
            expected_state = state or self.root / "state"
            tail = args[2:]
            require(tail == ["--watch", "--state-dir", str(expected_state)] or
                    source_root is not None and expected_state == base / "reports/future-btc5m-assistant" and tail == ["--watch"],
                    "LaunchAgent uses a different state directory")
            if source_root is None:
                require(args[0] == self.config()["python"], "LaunchAgent uses a different Python runtime")
        else:
            proxy = "127.0.0.1:7890" if source_root is not None else self.config()["proxySocks"]
            require(args[0] == "/bin/bash" and args[2:] in (["--remove-stale-socket"],
                    ["--remove-stale-socket", "--socks-proxy", proxy]), "Unexpected tunnel arguments")
        return value, expected

    def ownership(self, source_root=None, state=None):
        result = {}
        for label in LABELS:
            info = self.system.agent(label)
            path = self.installed(label)
            if path.exists() or path.is_symlink():
                _, script = self.validate_agent(path, label, source_root, state)
            else:
                require(info is None, "Loaded job has no verifiable installed LaunchAgent")
                script = None
            if info is not None:
                require(script is not None and str(script) in {line.strip() for line in info["text"].splitlines()},
                        "Loaded job belongs to another installation")
            result[label] = info
        listeners = self.system.listener_pids(8766)
        pid = result[ASSISTANT].get("pid") if result[ASSISTANT] else None
        require(not listeners or pid is not None and listeners == {pid}, "Port 8766 is owned by another process")
        runtime = self.system.listener_pids(8767)
        require(not runtime or pid is not None and runtime == {pid}, "Port 8767 is owned by another process")
        return result

    def validate_bridge(self, value, profile=None, off=False):
        require(value.get("bridgeId") == "future-btc5m" and value.get("online") is True and
                type(value.get("amountUsd")) in (int, float) and value["amountUsd"] == 1 and
                isinstance(value.get("strategy"), str) and value["strategy"] in STRATEGIES and value.get("series") == STRATEGIES[value["strategy"]] and
                type(value.get("requestedEnabled")) is bool and isinstance(value.get("preparation"), dict) and
                type(value["preparation"].get("enabled")) is bool and
                type(value.get("serverTime")) in (int, float) and math.isfinite(value["serverTime"]) and
                abs(self.system.now() - value["serverTime"]) <= 3, "Bridge identity, profile or time is invalid")
        if profile:
            require(value["strategy"] == profile["strategy"], "Bridge strategy differs from the migration profile")
        if off:
            require(value["requestedEnabled"] is False and value["preparation"]["enabled"] is False,
                    "Automatic buying was not confirmed OFF")
        return value

    def doctor(self):
        config = self.config()
        env = self.system.environment(config["python"])
        checks = {"macOS13OrNewer": env["platform"] == "Darwin" and bool(re.match(r"^(1[3-9]|[2-9][0-9])(?:\.|$)", env["macos"])),
                  "nativeIntelPython": env["machine"] == "x86_64" and env["pythonOk"],
                  "dependencies": env["dependenciesOk"], "tlsRoots": env["tlsOk"], "newYorkTimezone": env["zoneinfoOk"],
                  "chrome116OrNewer": env["chromeMajor"] >= 116,
                  "httpProxy": self.system.proxy_available(config["proxyHttp"]),
                  "socksProxy": self.system.proxy_available(config["proxySocks"])}
        try:
            owned = self.ownership()
            checks["ownedPortsAndAgents"] = True
        except ManageError:
            checks["ownedPortsAndAgents"] = False
            owned = {}
        value = {"readyToObserve": all(checks.values()), "checks": checks, "environment": env,
                 "autoEnabled": None, "note": "Doctor is read-only. No command enables automatic buying."}
        if owned.get(ASSISTANT) and self.system.listener_pids(8766):
            try:
                bridge = self.validate_bridge(self.system.http("/bridge/status"), config)
                value["autoEnabled"] = bridge["requestedEnabled"] or bridge["preparation"]["enabled"]
                value["strategy"] = bridge["strategy"]
                value["browserConnected"] = bridge.get("preflight", {}).get("browserConnected") is True
                preflight = bridge.get("preflight", {})
                value["browserReportFresh"] = all(isinstance(preflight.get(key), (int, float)) and
                    math.isfinite(preflight[key]) and 0 <= self.system.now() - preflight[key] <= 5 for key in ("checkedAt", "receivedAt"))
                source = self.system.http("/status")
                checks["assistantAmountOne"] = type(source.get("amount_usd")) in (int, float) and source["amount_usd"] == 1 and source.get("mode") == "ASSIST_ONLY" and source.get("live_enabled") is False
                value["feedStatus"] = source.get("feed_status", "UNKNOWN")
                schedule = self.system.http("/bridge/preparation/schedule", preparation=True)
                require(set(schedule) == {"weekendOnly"} and type(schedule["weekendOnly"]) is bool, "Local weekend schedule is unknown")
                value["weekendOnly"] = schedule["weekendOnly"]
                value["scheduleMatchesProfile"] = schedule["weekendOnly"] == config["weekendOnly"]
            except ManageError:
                checks["localStatus"] = False
                value["readyToObserve"] = False
        value["readyToObserve"] = all(checks.values())
        return value

    def load_agent(self, label):
        source = self.root / "launchd" / (label + ".plist")
        self.validate_agent(source, label)
        destination = self.installed(label)
        if destination.exists() or destination.is_symlink():
            require(safe_file(destination) == safe_file(source), "Existing LaunchAgent differs; refusing replacement")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o600)
        self.system.run(["launchctl", "enable", f"{self.domain}/{label}"])
        if self.system.agent(label) is None:
            self.system.run(["launchctl", "bootstrap", self.domain, str(destination)])

    def start_observe(self):
        self.config()
        require(all((self.root / "state" / item).is_file() for item in ("STOP", "bridge/STOP")), "Both STOP files must remain present")
        require(self.doctor()["readyToObserve"], "Doctor prerequisites failed")
        self.load_agent(ASSISTANT)
        self.wait_local_off(self.config())
        return {"started": "assistant-only", "localServiceVerified": True,
                "automaticBuying": "OFF", "stopFilesRetained": True}

    def wait_local_off(self, profile):
        for _ in range(60):
            try:
                self.ownership()
                require(bool(self.system.listener_pids(8766)), "Assistant is not listening")
                return self.validate_bridge(self.system.http("/bridge/status"), profile, off=True)
            except ManageError:
                self.system.sleep(0.25)
        raise ManageError("Target assistant did not confirm a ready local service with automatic buying OFF")

    def disable_jobs(self, owned):
        for label in LABELS:
            if self.installed(label).exists():
                self.system.run(["launchctl", "disable", f"{self.domain}/{label}"])
            if owned.get(label) is not None:
                self.system.run(["launchctl", "bootout", f"{self.domain}/{label}"])

    def quiet_ports(self):
        deadline = self.system.now() + 25
        quiet_since = None
        while self.system.now() < deadline:
            if self.system.listener_pids(8766) or self.system.listener_pids(8767):
                quiet_since = None
            elif quiet_since is None:
                quiet_since = self.system.now()
            elif self.system.now() - quiet_since >= 6:
                require(all(self.system.agent(label) is None for label in LABELS), "A launch job is still loaded")
                return
            self.system.sleep(0.25)
        raise ManageError("Assistant/runtime ports did not remain stopped for six seconds")

    def stop_target(self):
        self.config()
        owned = self.ownership()
        if self.system.listener_pids(8766):
            self.validate_bridge(self.system.http("/bridge/status"))
            self.system.http("/bridge/control", {"enabled": False})
            self.validate_bridge(self.system.http("/bridge/status"), off=True)
        touch_stop(self.root / "state")
        self.disable_jobs(owned)
        self.quiet_ports()
        return {"stopped": True, "automaticBuying": "OFF", "stopFilesPresent": True}

    def generate_key(self):
        config = self.config()
        key = Path(config["sshKey"])
        public = key.with_name(key.name + ".pub")
        require(key.parent.resolve() == self.root / "ssh", "SSH directory cannot be a symlink")
        if key.exists() or key.is_symlink() or public.exists() or public.is_symlink():
            require(key.is_file() and not key.is_symlink() and public.is_file() and not public.is_symlink(),
                    "Incomplete existing keypair; refusing overwrite")
        else:
            key.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            key.parent.chmod(0o700)
            self.system.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "polyhermes-future-migration", "-f", str(key)], input="")
        require(key.stat().st_uid == os.getuid() and key.stat().st_mode & 0o077 == 0, "Private key must belong to this user with permissions 600 or stricter")
        value = safe_file(public).decode("ascii").strip()
        require(re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]+={0,2}(?: [^\r\n]*)?", value) is not None, "Invalid public key")
        return {"publicKey": value, "serverChanged": False}

    def handoff_source(self, source_root, source_state, output, confirm=False):
        require(confirm, "Requires --confirm-source-cutover; this stops the source Mac services")
        source_root, source_state, output = (Path(path).expanduser().resolve() for path in (source_root, source_state, output))
        require(source_state.is_relative_to(source_root) and source_state.is_dir() and not output.exists() and
                not output.is_relative_to(source_state), "Invalid source or existing handoff output")
        owned = self.ownership(source_root, source_state)
        require(owned.get(ASSISTANT) is not None and bool(self.system.listener_pids(8766)), "A trusted running source assistant is required")
        bridge = self.validate_bridge(self.system.http("/bridge/status"))
        schedule = self.system.http("/bridge/preparation/schedule", preparation=True)
        require(set(schedule) == {"weekendOnly"} and type(schedule["weekendOnly"]) is bool, "Source weekend schedule is unknown")
        profile = {"strategy": bridge["strategy"], "weekendOnly": schedule["weekendOnly"], "amountUsd": 1}
        self.system.http("/bridge/control", {"enabled": False})
        self.validate_bridge(self.system.http("/bridge/status"), profile, off=True)
        touch_stop(source_state)
        self.disable_jobs(owned)
        self.quiet_ports()
        output.mkdir(mode=0o700, parents=True)
        files = {}
        for relative in sorted(HISTORY):
            source = source_state / relative
            require(source.resolve().is_relative_to(source_state), "Source ledger leaves the state directory")
            if source.exists() or source.is_symlink():
                raw = safe_file(source)
                validate_history(relative, raw)
                require(raw == safe_file(source), "Source ledger changed during snapshot")
                destination = output / relative
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                destination.write_bytes(raw)
                destination.chmod(0o600)
                files[relative] = {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
        created = self.system.now()
        receipt = {"schemaVersion": 1, "sourceStopped": True, "createdAt": utc(created), "createdEpoch": created,
                   "notBefore": (int(created) // 900 + 1) * 900 + 1, "profile": profile, "files": files,
                   "browserAuditOutbox": "Not exported: operator must preserve/acknowledge the old browser outbox before cutover."}
        write_json(output / "receipt.json", receipt)
        return {"sourceStopped": True, "receipt": str(output / "receipt.json"), "notBefore": receipt["notBefore"],
                "notBeforeUTC": utc(receipt["notBefore"]), "copiedFiles": len(files), "automaticBuying": "OFF"}

    def verify_handoff(self, directory):
        directory = Path(directory).expanduser().resolve()
        receipt = read_json(directory / "receipt.json")
        require(isinstance(receipt, dict) and type(receipt.get("schemaVersion")) is int and receipt["schemaVersion"] == 1 and receipt.get("sourceStopped") is True and
                type(receipt.get("createdEpoch")) in (int, float) and math.isfinite(receipt["createdEpoch"]) and
                receipt["createdEpoch"] >= 0 and receipt.get("createdAt") == utc(receipt["createdEpoch"]) and
                receipt.get("notBefore") == (int(receipt["createdEpoch"]) // 900 + 1) * 900 + 1 and
                isinstance(receipt.get("files"), dict) and "bridge/control.json" in receipt["files"] and
                set(receipt["files"]) <= HISTORY, "Invalid source-stop receipt")
        config = self.config()
        require(receipt.get("profile") == {"strategy": config["strategy"], "weekendOnly": config["weekendOnly"], "amountUsd": 1},
                "Handoff profile differs from target configuration")
        actual = set()
        for path in directory.rglob("*"):
            require(not path.is_symlink(), "Handoff contains a symbolic link")
            if path.is_file():
                actual.add(path.relative_to(directory).as_posix())
        require(actual == set(receipt["files"]) | {"receipt.json"}, "Handoff contains missing or unexpected files")
        for relative, expected in receipt["files"].items():
            raw = safe_file(directory / relative)
            validate_history(relative, raw)
            require(expected == {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}, "Handoff ledger hash/size mismatch")
        if "bridge/control.json" in receipt["files"]:
            control = read_json(directory / "bridge/control.json")
            require(control.get("requestedEnabled") is False and control.get("amountUsd") == 1 and
                    control.get("strategy") == config["strategy"], "Handoff control was not disabled")
        return receipt

    def accept_handoff(self, directory):
        directory = Path(directory).expanduser().resolve()
        receipt = self.verify_handoff(directory)
        digest = hashlib.sha256(safe_file(directory / "receipt.json")).hexdigest()
        destination = self.root / "history" / digest
        require(destination.resolve().is_relative_to(self.root), "History directory leaves target root")
        if destination.exists():
            self.verify_handoff(destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copytree(directory, destination)
            self.verify_handoff(destination)
            for path in destination.rglob("*"):
                path.chmod(0o500 if path.is_dir() else 0o400)
            destination.chmod(0o500)
        write_json(self.root / "accepted-handoff.json", {"schemaVersion": 1, "path": "history/" + digest,
                   "receiptSha256": digest})
        return {"accepted": True, "history": str(destination), "notBefore": receipt["notBefore"],
                "automaticBuying": "OFF", "historyReplayed": False}

    def accepted(self):
        pointer = read_json(self.root / "accepted-handoff.json")
        require(isinstance(pointer, dict) and pointer.get("schemaVersion") == 1 and
                re.fullmatch(r"[0-9a-f]{64}", pointer.get("receiptSha256", "")) is not None and
                pointer.get("path") == "history/" + pointer["receiptSha256"], "Invalid accepted handoff pointer")
        directory = self.root / pointer["path"]
        require(directory.resolve().is_relative_to(self.root), "History pointer leaves target root")
        require(hashlib.sha256(safe_file(directory / "receipt.json")).hexdigest() == pointer["receiptSha256"], "Accepted receipt changed")
        return self.verify_handoff(directory)

    def start_target(self):
        config = self.config()
        receipt = self.accepted()
        require(self.system.now() >= receipt["notBefore"], "Cutover boundary has not arrived; automatic waiting/enabling is disabled")
        key = Path(config["sshKey"])
        require(key.is_file() and not key.is_symlink() and key.stat().st_uid == os.getuid() and key.stat().st_mode & 0o077 == 0,
                "A private target SSH key with restricted permissions is required")
        require(self.system.run(["ssh-keygen", "-y", "-P", "", "-f", str(key)], input="") is not None, "Target key cannot be read without interaction")
        require(self.doctor()["readyToObserve"], "Doctor prerequisites failed")
        self.ownership()
        if self.system.listener_pids(8766):
            self.validate_bridge(self.system.http("/bridge/status"), config, off=True)
        markers = []
        for relative in ("STOP", "bridge/STOP"):
            marker = self.root / "state" / relative
            require(marker.resolve().is_relative_to(self.root / "state"), "STOP path leaves target state directory")
            if marker.exists() or marker.is_symlink():
                safe_file(marker)
                markers.append(marker)
        try:
            for marker in markers:
                marker.unlink()
            self.load_agent(ASSISTANT)
            self.wait_local_off(config)
            self.system.http("/bridge/preparation/schedule", {"weekendOnly": config["weekendOnly"]}, preparation=True)
            require(self.system.http("/bridge/preparation/schedule", preparation=True) == {"weekendOnly": config["weekendOnly"]},
                    "Weekend schedule was not confirmed")
            self.validate_bridge(self.system.http("/bridge/status"), config, off=True)
            self.load_agent(TUNNEL)
        except (ManageError, OSError):
            touch_stop(self.root / "state")
            self.disable_jobs(self.ownership())
            raise
        return {"localServiceVerified": True, "tunnelStartRequested": True,
                "transportVerification": "REQUIRED", "automaticBuying": "OFF", "weekendOnly": config["weekendOnly"],
                "strategy": config["strategy"], "note": "Verify the production relay and fresh Chrome report before manually enabling the existing control."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("doctor", "start-observe", "stop-target", "generate-key", "start-target"):
        commands.add_parser(command)
    source = commands.add_parser("handoff-source", help="Explicitly stop the source Mac and export allowlisted history")
    source.add_argument("--source-root", type=Path, required=True)
    source.add_argument("--source-state", type=Path, required=True)
    source.add_argument("--output", type=Path, required=True)
    source.add_argument("--confirm-source-cutover", action="store_true")
    accept = commands.add_parser("accept-handoff")
    accept.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    manager = Manager(args.root)
    try:
        if args.command == "handoff-source":
            value = manager.handoff_source(args.source_root, args.source_state, args.output, args.confirm_source_cutover)
        elif args.command == "accept-handoff":
            value = manager.accept_handoff(args.directory)
        else:
            value = getattr(manager, args.command.replace("-", "_"))()
        print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ManageError, OSError, ValueError) as error:
        # Never print subprocess output, HTTP bodies, key material, cookies or tokens.
        message = str(error) if isinstance(error, ManageError) else "Filesystem or configuration operation failed"
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
