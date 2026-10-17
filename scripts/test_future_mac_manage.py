import importlib.util
import json
import plistlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("future-mac-migration") / "manage.py"
spec = importlib.util.spec_from_file_location("future_mac_manage", SCRIPT)
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class FakeSystem:
    def __init__(self):
        self.calls = []
        self.clock = 1791907202.0
        self.agents = {}
        self.listeners = set()
        self.enabled = False
        self.weekend_only = False
        self.strategy = "btc15m_counter_1h"
        self.reject_off = False

    def now(self):
        return self.clock

    def sleep(self, seconds):
        self.clock += seconds

    def agent(self, label):
        return self.agents.get(label)

    def listener_pids(self, port):
        return {42} if port in self.listeners else set()

    def run(self, args, **kwargs):
        self.calls.append(tuple(map(str, args)))
        if args[0] == "launchctl":
            action, target = args[1:3]
            if action == "bootstrap":
                config = plistlib.loads(Path(args[3]).read_bytes())
                self.agents[config["Label"]] = {"pid": 42, "text": "\n".join(config["ProgramArguments"])}
                if config["Label"] == manage.ASSISTANT:
                    self.listeners.update({8766, 8767})
            elif action == "bootout":
                label = target.split("/")[-1]
                self.agents.pop(label, None)
                if label == manage.ASSISTANT:
                    self.listeners.clear()
        return ""

    def http(self, path, payload=None, preparation=False):
        self.calls.append(("http", path, payload, preparation))
        if payload == {"enabled": False} and not self.reject_off:
            self.enabled = False
        if path.endswith("/schedule"):
            if payload is not None:
                self.weekend_only = payload["weekendOnly"]
            return {"weekendOnly": self.weekend_only}
        if path == "/status":
            return {"schema_version": 1, "mode": "ASSIST_ONLY", "live_enabled": False,
                    "amount_usd": 1, "server_time": self.clock, "feed_status": "CURRENT"}
        return {"bridgeId": "future-btc5m", "online": True, "serverTime": self.clock,
                "strategy": self.strategy, "series": manage.STRATEGIES[self.strategy], "amountUsd": 1,
                "requestedEnabled": self.enabled, "effectiveEnabled": False, "executorReady": False,
                "preparation": {"enabled": self.enabled}, "preflight": {"browserConnected": False}}

    def environment(self, python):
        return {"platform": "Darwin", "macos": "13.7", "machine": "x86_64", "pythonOk": True,
                "dependenciesOk": True, "tlsOk": True, "zoneinfoOk": True, "chromeMajor": 141}

    def proxy_available(self, endpoint):
        return True


class FutureMacManageTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name).resolve()
        self.root = self.base / "target"
        self.home = self.base / "home"
        self.root.mkdir()
        self.system = FakeSystem()
        self.config = {"schemaVersion": 1, "targetRoot": str(self.root), "python": str(self.root / ".venv/bin/python"),
                       "sshKey": str(self.root / "ssh/id_ed25519"), "strategy": "btc15m_counter_1h",
                       "weekendOnly": False, "amountUsd": 1, "serverHost": "root@107.191.42.75",
                       "proxyHttp": "", "proxySocks": "", "extensionVersion": "0.7.3"}
        (self.root / "config.json").write_text(json.dumps(self.config))
        for name in ("future_btc5m_assistant.py", "start-future-btc5m-tunnel.sh"):
            path = self.root / "app/scripts" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture")
        for marker in ("STOP", "bridge/STOP"):
            path = self.root / "state" / marker
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Installed disabled\n")
        (self.root / "state/bridge/control.json").write_text(json.dumps({"requestedEnabled": False, "amountUsd": 1,
            "strategy": "btc15m_counter_1h", "series": "15m"}))
        for label, name in ((manage.ASSISTANT, "future_btc5m_assistant.py"), (manage.TUNNEL, "start-future-btc5m-tunnel.sh")):
            args = ([self.config["python"], str(self.root / "app/scripts" / name), "--watch", "--state-dir", str(self.root / "state")]
                    if label == manage.ASSISTANT else ["/bin/bash", str(self.root / "app/scripts" / name), "--remove-stale-socket"])
            path = self.root / "launchd" / (label + ".plist")
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": args,
                                           "WorkingDirectory": str(self.root)}))
        self.manager = manage.Manager(self.root, self.system, home=self.home)

    def assert_no_enable_or_remote(self):
        for call in self.system.calls:
            self.assertNotEqual(call[0], "ssh")
            if call[0] == "http":
                self.assertNotEqual(call[2], {"enabled": True})

    def source(self):
        root = self.base / "source"
        state = root / "reports/future-btc5m-assistant"
        (state / "bridge").mkdir(parents=True)
        (state / "rounds.jsonl").write_text('{"period_start":1791906300,"series":"15m"}\n')
        (state / "bridge/buy_attempts.jsonl").write_text('{"state":"CLICK_ATTEMPTED"}\n')
        (state / "bridge/control.json").write_text('{"requestedEnabled":false,"amountUsd":1,"strategy":"btc15m_counter_1h"}\n')
        for label, filename in ((manage.ASSISTANT, "future_btc5m_assistant.py"), (manage.TUNNEL, "start-future-btc5m-tunnel.sh")):
            script = root / "scripts" / filename
            script.parent.mkdir(exist_ok=True)
            script.write_text("fixture")
            args = ([str(root / "scripts/future-btc5m-runtime/.venv/bin/python"), str(script), "--watch"] if label == manage.ASSISTANT
                    else ["/bin/bash", str(script), "--remove-stale-socket", "--socks-proxy", "127.0.0.1:7890"])
            path = self.home / "Library/LaunchAgents" / (label + ".plist")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": args, "WorkingDirectory": str(root)}))
            self.system.agents[label] = {"pid": 42, "text": "\n".join(args)}
        self.system.listeners = {8766, 8767}
        return root, state

    def handoff(self):
        source, state = self.source()
        output = self.base / "handoff"
        self.manager.handoff_source(source, state, output, confirm=True)
        return output

    def test_doctor_is_read_only_and_does_not_claim_legacy_executor_flags_mean_off(self):
        result = self.manager.doctor()
        self.assertTrue(result["readyToObserve"])
        self.assertEqual([], self.system.calls)
        self.assertFalse((self.home / "Library/LaunchAgents").exists())

    def test_doctor_reports_auto_on_from_real_controls_despite_legacy_false_flags(self):
        self.manager.start_observe()
        self.system.enabled = True
        self.system.calls.clear()
        value = self.manager.doctor()
        self.assertTrue(value["autoEnabled"])
        self.assertFalse(value["browserReportFresh"])
        self.assertTrue(all(call[0] == "http" and call[2] is None for call in self.system.calls))

    def test_observe_only_starts_owned_assistant_with_both_stop_files_intact(self):
        self.manager.start_observe()
        self.assertIn(manage.ASSISTANT, self.system.agents)
        self.assertNotIn(manage.TUNNEL, self.system.agents)
        self.assertTrue((self.root / "state/STOP").exists())
        self.assertTrue((self.root / "state/bridge/STOP").exists())
        self.assert_no_enable_or_remote()

    def test_observe_refuses_unrelated_existing_agent_before_replacing_it(self):
        path = self.home / "Library/LaunchAgents" / (manage.ASSISTANT + ".plist")
        path.parent.mkdir(parents=True)
        path.write_bytes(plistlib.dumps({"Label": manage.ASSISTANT, "ProgramArguments": ["/unrelated/job"]}))
        original = path.read_bytes()
        with self.assertRaises(manage.ManageError):
            self.manager.start_observe()
        self.assertEqual(original, path.read_bytes())
        self.assertEqual([], self.system.calls)

    def test_observe_does_not_claim_success_when_service_never_binds(self):
        def no_listener(*args):
            self.system.calls.append(tuple(map(str, args[0])))
            return ""
        self.system.run = no_listener
        with self.assertRaises(manage.ManageError):
            self.manager.start_observe()
        self.assertTrue((self.root / "state/STOP").exists())
        self.assertNotIn(manage.TUNNEL, self.system.agents)

    def test_handoff_requires_explicit_flag_and_trusted_local_service(self):
        source, state = self.source()
        for confirm in (False,):
            with self.assertRaises(manage.ManageError):
                self.manager.handoff_source(source, state, self.base / "handoff", confirm=confirm)
        self.system.agents[manage.ASSISTANT]["text"] = "/some/other/script"
        with self.assertRaises(manage.ManageError):
            self.manager.handoff_source(source, state, self.base / "handoff", confirm=True)
        self.assertEqual([], self.system.calls)

    def test_source_handoff_stops_both_jobs_waits_and_preserves_only_allowlisted_history(self):
        source, state = self.source()
        (state / "secret.env").write_text("DO NOT COPY")
        (state / "status.json").write_text('{"wallet":"not copied"}')
        output = self.base / "handoff"
        began = self.system.clock
        result = self.manager.handoff_source(source, state, output, confirm=True)
        receipt = json.loads((output / "receipt.json").read_text())
        self.assertTrue(result["sourceStopped"])
        self.assertTrue(receipt["sourceStopped"])
        self.assertGreaterEqual(self.system.clock - began, 6)
        self.assertGreater(receipt["notBefore"], self.system.clock)
        self.assertEqual(False, receipt["profile"]["weekendOnly"])
        self.assertEqual({"rounds.jsonl", "bridge/control.json", "bridge/buy_attempts.jsonl"}, set(receipt["files"]))
        self.assertEqual({}, self.system.agents)
        self.assertTrue((state / "STOP").exists())
        self.assertTrue((state / "bridge/STOP").exists())
        self.assert_no_enable_or_remote()

    def test_unconfirmed_switch_off_aborts_before_stopping_or_snapshotting(self):
        source, state = self.source()
        self.system.enabled = True
        self.system.reject_off = True
        with self.assertRaises(manage.ManageError):
            self.manager.handoff_source(source, state, self.base / "handoff", confirm=True)
        self.assertFalse((state / "STOP").exists())
        self.assertFalse((self.base / "handoff").exists())
        self.assertFalse(any(call[0] == "launchctl" for call in self.system.calls))

    def test_accept_preserves_history_separately_and_future_cutover_cannot_start(self):
        output = self.handoff()
        self.manager.accept_handoff(output)
        pointer = json.loads((self.root / "accepted-handoff.json").read_text())
        self.assertTrue((self.root / pointer["path"] / "bridge/buy_attempts.jsonl").is_file())
        self.assertFalse((self.root / "state/bridge/buy_attempts.jsonl").exists())
        self.system.calls.clear()
        with self.assertRaises(manage.ManageError):
            self.manager.start_target()
        self.assertEqual([], self.system.calls)
        self.assertTrue((self.root / "state/STOP").exists())

    def test_handoff_rejects_tampered_hash_extra_files_symlinks_and_duplicate_json(self):
        output = self.handoff()
        ledger = output / "bridge/buy_attempts.jsonl"
        original = ledger.read_bytes()
        ledger.write_bytes(original + b'{}\n')
        with self.assertRaises(manage.ManageError):
            self.manager.accept_handoff(output)
        ledger.write_bytes(original)
        (output / "private-key").write_text("not allowed")
        with self.assertRaises(manage.ManageError):
            self.manager.accept_handoff(output)
        (output / "private-key").unlink()
        ledger.unlink()
        ledger.symlink_to(self.root / "config.json")
        with self.assertRaises(manage.ManageError):
            self.manager.accept_handoff(output)
        with self.assertRaises(manage.ManageError):
            manage.strict_json('{"enabled":false,"enabled":true}')

    def test_generate_key_never_overwrites_an_existing_private_key(self):
        key = Path(self.config["sshKey"])
        key.parent.mkdir()
        key.write_text("existing private key")
        key.chmod(0o600)
        with self.assertRaises(manage.ManageError):
            self.manager.generate_key()
        self.assertEqual("existing private key", key.read_text())
        self.assertEqual([], self.system.calls)

    def test_stop_target_refuses_unrelated_listener(self):
        self.system.listeners.add(8766)
        with self.assertRaises(manage.ManageError):
            self.manager.stop_target()
        self.assertEqual([], self.system.calls)

    def test_stop_target_disables_an_owned_service_after_a_legitimate_strategy_change(self):
        self.manager.start_observe()
        self.system.strategy = "btc5m_favorite"
        self.system.enabled = True
        result = self.manager.stop_target()
        self.assertTrue(result["stopped"])
        self.assertFalse(self.system.enabled)
        self.assertEqual({}, self.system.agents)
        self.assertTrue((self.root / "state/STOP").exists())
        self.assert_no_enable_or_remote()

    def test_target_start_requires_key_and_starts_only_after_the_receipt_boundary_with_auto_off(self):
        output = self.handoff()
        self.manager.accept_handoff(output)
        self.system.clock = json.loads((output / "receipt.json").read_text())["notBefore"] + 1
        # Source and target are separate Macs; target has no source LaunchAgent files.
        for path in (self.home / "Library/LaunchAgents").glob("*.plist"):
            path.unlink()
        self.system.calls.clear()
        with self.assertRaises(manage.ManageError):
            self.manager.start_target()
        self.assertEqual([], self.system.calls)
        key = Path(self.config["sshKey"])
        key.parent.mkdir()
        key.write_text("fixture key: no actual ssh-keygen is run")
        key.chmod(0o600)
        result = self.manager.start_target()
        self.assertEqual("OFF", result["automaticBuying"])
        self.assertEqual(set(manage.LABELS), set(self.system.agents))
        self.assertFalse((self.root / "state/STOP").exists())
        self.assertFalse((self.root / "state/bridge/STOP").exists())
        self.assertFalse(self.system.enabled)
        self.assertFalse(self.system.weekend_only)
        self.assert_no_enable_or_remote()
        self.manager.stop_target()
        self.assertEqual({}, self.system.agents)
        self.assertTrue((self.root / "state/STOP").exists())

    def test_target_start_with_unknown_or_enabled_control_keeps_stop_files_and_does_not_start_tunnel(self):
        output = self.handoff()
        self.manager.accept_handoff(output)
        self.system.clock = json.loads((output / "receipt.json").read_text())["notBefore"] + 1
        for path in (self.home / "Library/LaunchAgents").glob("*.plist"):
            path.unlink()
        key = Path(self.config["sshKey"])
        key.parent.mkdir()
        key.write_text("fixture")
        key.chmod(0o600)
        self.manager.start_observe()
        self.system.enabled = True
        with self.assertRaises(manage.ManageError):
            self.manager.start_target()
        self.assertTrue((self.root / "state/STOP").exists())
        self.assertNotIn(manage.TUNNEL, self.system.agents)

    def test_configuration_rejects_boolean_amount_wrong_host_and_foreign_key_path(self):
        for change in ({"amountUsd": True}, {"serverHost": "root@other-host"},
                       {"strategy": []}, {"sshKey": "/tmp/unrelated-private-key"}, {"python": None}):
            (self.root / "config.json").write_text(json.dumps({**self.config, **change}))
            with self.assertRaises(manage.ManageError):
                self.manager.doctor()
        self.assertEqual([], self.system.calls)

    def test_port_inspection_errors_are_unknown_and_cannot_establish_a_stopped_source(self):
        result = type("Result", (), {"returncode": 1, "stdout": "", "stderr": "permission denied"})()
        with patch.object(manage.subprocess, "run", return_value=result):
            with self.assertRaises(manage.ManageError):
                manage.System().listener_pids(8766)
        result.stderr = ""
        with patch.object(manage.subprocess, "run", return_value=result):
            self.assertEqual(set(), manage.System().listener_pids(8766))

    def test_partial_or_nonfinite_source_ledgers_never_get_a_completed_receipt(self):
        source, state = self.source()
        (state / "bridge/buy_attempts.jsonl").write_text('{"bad":NaN}\n')
        output = self.base / "handoff"
        with self.assertRaises(manage.ManageError):
            self.manager.handoff_source(source, state, output, confirm=True)
        self.assertFalse((output / "receipt.json").exists())
        self.assertTrue((state / "STOP").exists())
        self.assertEqual({}, self.system.agents)

    def test_target_start_rejects_a_foreign_stop_parent_before_removing_any_marker(self):
        output = self.handoff()
        self.manager.accept_handoff(output)
        self.system.clock = json.loads((output / "receipt.json").read_text())["notBefore"] + 1
        for path in (self.home / "Library/LaunchAgents").glob("*.plist"):
            path.unlink()
        key = Path(self.config["sshKey"])
        key.parent.mkdir()
        key.write_text("fixture")
        key.chmod(0o600)
        bridge = self.root / "state/bridge"
        for item in bridge.iterdir():
            item.unlink()
        bridge.rmdir()
        foreign = self.base / "foreign"
        foreign.mkdir()
        (foreign / "STOP").write_text("unrelated state")
        bridge.symlink_to(foreign, target_is_directory=True)
        with self.assertRaises(manage.ManageError):
            self.manager.start_target()
        self.assertTrue((self.root / "state/STOP").exists())
        self.assertEqual("unrelated state", (foreign / "STOP").read_text())


if __name__ == "__main__":
    unittest.main()
