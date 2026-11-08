import fcntl
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location("relay_guard_watchdog", Path(__file__).with_name("vps_service_watchdog.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class FutureRelayGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.compose_path = self.root / "compose.json"
        self.compose = {"name": "test-project", "services": {
            "app": {"container_name": "polyhermes"},
            "future-relay": {"container_name": "future-btc5m-relay", "network_mode": "service:app"},
        }}
        self.compose_path.write_text(json.dumps(self.compose))
        patch = mock.patch.object(module, "FUTURE_COMPOSE_FILE", self.compose_path, create=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.now = 1000
        self.app_id = "app-id"
        self.mode = "container:app-id"
        self.app_namespace = "net:[100]"
        self.relay_namespace = "net:[101]"
        self.health = '{"status":"ok"}'
        self.restart_ok = True
        self.docker_health = "healthy"
        self.restore_health = False
        self.project = "test-project"
        self.commands = []
        self.config = module.Config(state_file=self.root / "state.json")
        self.monitor = module.Watchdog(self.config, None, now=lambda: self.now)
        self.monitor._command = self.command

    def command(self, args, **kwargs):
        self.commands.append(args)
        if args[:2] == ["docker", "inspect"]:
            template, name = args[-2:]
            if template == "{{.Id}}":
                return self.app_id
            if template == "{{.HostConfig.NetworkMode}}":
                return self.mode
            if template == "{{.State.Health.Status}}":
                return self.docker_health
            if "com.docker.compose.project" in template:
                return self.project
            if "com.docker.compose.service" in template:
                return "app" if name == "polyhermes" else "future-relay"
        if args[:2] == ["docker", "exec"]:
            if "/proc/self/ns/net" in args[-1]:
                return self.app_namespace if args[2] == "polyhermes" else self.relay_namespace
            if "127.0.0.1:8766/live" in args[-1]:
                return self.health
        if args == ["docker", "restart", "future-btc5m-relay"]:
            if self.restart_ok:
                self.relay_namespace = self.app_namespace
                if self.restore_health:
                    self.health = '{"status":"ok"}'
                return "future-btc5m-relay"
            return ""
        if args[:2] == ["docker", "compose"]:
            self.mode = "container:" + self.app_id
            self.relay_namespace = self.app_namespace
            return ""
        raise AssertionError(args)

    def restarts(self):
        return [c for c in self.commands if c[:2] in (["docker", "restart"], ["docker", "compose"])]

    def test_current_healthy_connection_is_idempotent(self):
        self.relay_namespace = self.app_namespace
        self.assertTrue(self.monitor.rejoin_future_relay())
        self.assertEqual([], self.restarts())

    def test_recreated_app_rebinds_only_its_declared_relay(self):
        self.mode = "container:old-app-id"
        self.assertTrue(self.monitor.rejoin_future_relay())
        commands = self.restarts()
        self.assertEqual(1, len(commands))
        self.assertEqual(["docker", "compose"], commands[0][:2])
        self.assertIn("--no-deps", commands[0])
        self.assertIn("--force-recreate", commands[0])
        self.assertEqual("future-relay", commands[0][-1])

    def test_foreign_compose_owner_is_not_recreated(self):
        self.mode = "container:old-app-id"
        self.project = "other-project"
        self.assertFalse(self.monitor.rejoin_future_relay())
        self.assertEqual([], self.restarts())

    def test_public_or_wrong_service_definition_is_rejected(self):
        self.mode = "container:old-app-id"
        for change in ({"ports": ["8766:8766"]}, {"network_mode": "host"}, {"container_name": "polymtrade-bridge"}):
            with self.subTest(change=change):
                config = json.loads(json.dumps(self.compose))
                config["services"]["future-relay"].update(change)
                self.compose_path.write_text(json.dumps(config))
                self.assertFalse(self.monitor.rejoin_future_relay())
        self.assertEqual([], self.restarts())

    def test_failed_repairs_are_rate_limited_and_bounded_per_app_generation(self):
        self.restart_ok = False
        for _ in range(2):
            self.assertFalse(self.monitor.rejoin_future_relay())
        self.assertEqual(1, len(self.restarts()))
        for _ in range(4):
            self.now += 31
            self.assertFalse(self.monitor.rejoin_future_relay())
        self.assertEqual(3, len(self.restarts()))
        self.app_namespace = "net:[102]"
        self.assertFalse(self.monitor.rejoin_future_relay())
        self.assertEqual(4, len(self.restarts()))

    def test_concurrent_guard_does_not_restart_again(self):
        lock_path = self.root / "future-relay.lock"
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertFalse(self.monitor.rejoin_future_relay())
        self.assertEqual([], self.restarts())

    def test_confirmed_unhealthy_listener_is_recovered_without_restarting_app(self):
        self.relay_namespace = self.app_namespace
        self.health = ""
        self.docker_health = "unhealthy"
        self.restore_health = True
        self.assertTrue(self.monitor.rejoin_future_relay())
        self.assertEqual([["docker", "restart", "future-btc5m-relay"]], self.restarts())

    def test_app_restart_fails_readiness_when_relay_recovery_fails(self):
        self.monitor._command = mock.Mock(return_value="polyhermes")
        self.monitor.rejoin_future_relay = mock.Mock(return_value=False)
        self.assertFalse(self.monitor.restart_app())

    def test_fast_guard_does_not_send_notifications_or_run_global_checks(self):
        for auto_restart in (True, False):
            with self.subTest(auto_restart=auto_restart):
                self.config.auto_restart_app = auto_restart
                self.monitor.rejoin_future_relay = mock.Mock(return_value=True)
                self.monitor._check_future_relay = mock.Mock()
                self.monitor.run_once = mock.Mock(side_effect=AssertionError("global checks must not run"))
                with mock.patch.object(module.Config, "from_env", return_value=self.config), \
                        mock.patch.object(module, "Watchdog", return_value=self.monitor), \
                        mock.patch.object(module, "FeishuNotifier") as notifier, \
                        mock.patch.object(module.sys, "argv", ["watchdog", "--future-relay-only"]):
                    with self.assertRaises(SystemExit) as result:
                        module.main()
                    self.assertEqual(0, result.exception.code)
                notifier.assert_not_called()
                if auto_restart:
                    self.monitor.rejoin_future_relay.assert_called_once()
                else:
                    self.monitor.rejoin_future_relay.assert_not_called()


if __name__ == "__main__":
    unittest.main()
