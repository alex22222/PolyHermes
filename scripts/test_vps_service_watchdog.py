import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("vps_service_watchdog.py")
SPEC = importlib.util.spec_from_file_location("vps_service_watchdog", MODULE_PATH)
watchdog_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog_module)


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send(self, title, message):
        self.messages.append((title, message))
        return True


class FailingNotifier(FakeNotifier):
    def send(self, title, message):
        self.messages.append((title, message))
        return False


class FakeHttpResponse:
    def __init__(self, body=b'{"code":0,"msg":"success"}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


class VpsServiceWatchdogTest(unittest.TestCase):
    def config(self, state_file, threshold=2, auto_restart_bridge=False):
        return watchdog_module.Config(
            state_file=state_file,
            failure_threshold=threshold,
            reminder_seconds=1800,
            auto_restart_app=True,
            auto_restart_bridge=auto_restart_bridge,
        )

    def test_restarts_only_main_app_after_consecutive_app_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            notifier = FakeNotifier()
            restarts = []
            monitor = watchdog_module.Watchdog(
                config=self.config(Path(tmp) / "state.json"),
                notifier=notifier,
                issue_collector=lambda: ["backend_business: HTTP 502"],
                app_diagnostics=lambda: None,
                app_restarter=lambda: restarts.append("polyhermes") or True,
                now=lambda: 1000,
            )

            monitor.run_once()
            self.assertEqual([], notifier.messages)
            self.assertEqual([], restarts)

            monitor.run_once()
            self.assertEqual(["polyhermes"], restarts)
            self.assertEqual(1, len(notifier.messages))
            self.assertIn("服务不可用", notifier.messages[0][0])
            self.assertIn("已自动重启主应用", notifier.messages[0][1])

    def test_captures_diagnostics_before_restarting_main_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            diagnostics = []
            restarts = []
            monitor = watchdog_module.Watchdog(
                config=self.config(Path(tmp) / "state.json", threshold=1),
                notifier=FakeNotifier(),
                issue_collector=lambda: ["backend_business: HTTP 502"],
                app_diagnostics=lambda: diagnostics.append("captured"),
                app_restarter=lambda: restarts.append("polyhermes") or True,
                now=lambda: 1000,
            )

            monitor.run_once()

            self.assertEqual(["captured"], diagnostics)
            self.assertEqual(["polyhermes"], restarts)

    def test_bridge_failure_alerts_without_restarting_browser_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            notifier = FakeNotifier()
            restarts = []
            monitor = watchdog_module.Watchdog(
                config=self.config(Path(tmp) / "state.json", threshold=1),
                notifier=notifier,
                issue_collector=lambda: ["bridge_status: ready=false"],
                app_restarter=lambda: restarts.append("polyhermes") or True,
                now=lambda: 1000,
            )

            monitor.run_once()

            self.assertEqual([], restarts)
            self.assertEqual(1, len(notifier.messages))
            self.assertIn("未自动重启 Bridge", notifier.messages[0][1])

    def test_safely_restarts_bridge_once_after_consecutive_bridge_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            restarts = []
            monitor = watchdog_module.Watchdog(
                config=self.config(state_file, threshold=1, auto_restart_bridge=True),
                notifier=FakeNotifier(),
                issue_collector=lambda: ["bridge_status: ready=false"],
                bridge_restarter=lambda: restarts.append("polymtrade-bridge") or True,
                now=lambda: 1000,
            )

            monitor.run_once()
            monitor.run_once()

            self.assertEqual(["polymtrade-bridge"], restarts)
            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertTrue(state["bridge_restart_attempted"])

    def test_bridge_restart_attempt_resets_after_bridge_issue_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            issues = [["bridge_status: ready=false"], ["backend_business: HTTP 502"]]
            monitor = watchdog_module.Watchdog(
                config=self.config(state_file, threshold=1, auto_restart_bridge=True),
                notifier=FakeNotifier(),
                issue_collector=lambda: issues.pop(0),
                app_diagnostics=lambda: None,
                app_restarter=lambda: True,
                bridge_restarter=lambda: True,
                now=lambda: 1000,
            )

            monitor.run_once()
            monitor.run_once()

            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertNotIn("bridge_restart_attempted", state)

    def test_bridge_restart_requires_login_empty_queue_and_successful_drain(self):
        config = self.config(Path("/tmp/unused-state.json"), threshold=1, auto_restart_bridge=True)
        monitor = watchdog_module.Watchdog(config=config, notifier=FakeNotifier())

        with mock.patch.object(monitor, "_fetch_json", side_effect=[
            {"logged_in": True},
            {"metrics": {"signal_queue_depth": 1, "accepting_signals": True}},
        ]), mock.patch.object(monitor, "_command") as command:
            self.assertFalse(monitor.restart_bridge())
            command.assert_not_called()

    def test_bridge_restart_drains_before_restarting_container(self):
        config = self.config(Path("/tmp/unused-state.json"), threshold=1, auto_restart_bridge=True)
        monitor = watchdog_module.Watchdog(config=config, notifier=FakeNotifier())
        responses = [
            {"logged_in": True},
            {"metrics": {"signal_queue_depth": 0, "accepting_signals": True}},
            {"metrics": {"signal_queue_depth": 0, "accepting_signals": False}},
        ]

        with mock.patch.object(monitor, "_fetch_json", side_effect=responses), mock.patch.object(
            monitor,
            "_command",
            side_effect=['{"status":"draining"}', "polymtrade-bridge"],
        ) as command:
            self.assertTrue(monitor.restart_bridge())

        self.assertEqual("exec", command.call_args_list[0].args[0][1])
        self.assertEqual(["docker", "restart", "polymtrade-bridge"], command.call_args_list[1].args[0])

        with mock.patch.object(monitor, "_fetch_json", side_effect=[
            {"logged_in": False},
            {"metrics": {"signal_queue_depth": 0, "accepting_signals": True}},
        ]), mock.patch.object(monitor, "_command") as command:
            self.assertFalse(monitor.restart_bridge())
            command.assert_not_called()

    def test_restarts_app_once_when_app_failure_joins_bridge_incident(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text(
                json.dumps({"failures": 3, "incident": True, "incident_started_at": 900}),
                encoding="utf-8",
            )
            restarts = []
            monitor = watchdog_module.Watchdog(
                config=self.config(state_file, threshold=1),
                notifier=FakeNotifier(),
                issue_collector=lambda: [
                    "bridge_health: HTTP 503",
                    "app_health: unhealthy",
                ],
                app_diagnostics=lambda: None,
                app_restarter=lambda: restarts.append("polyhermes") or True,
                now=lambda: 1000,
            )

            monitor.run_once()
            monitor.run_once()

            self.assertEqual(["polyhermes"], restarts)

    def test_new_app_failure_can_restart_after_app_recovers_during_bridge_incident(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            issues = [
                ["bridge_health: HTTP 503", "app_health: unhealthy"],
                ["bridge_health: HTTP 503"],
                ["bridge_health: HTTP 503", "app_health: unhealthy"],
            ]
            restarts = []
            monitor = watchdog_module.Watchdog(
                config=self.config(state_file, threshold=1),
                notifier=FakeNotifier(),
                issue_collector=lambda: issues.pop(0),
                app_diagnostics=lambda: None,
                app_restarter=lambda: restarts.append("polyhermes") or True,
                now=lambda: 1000,
            )

            monitor.run_once()
            monitor.run_once()
            monitor.run_once()

            self.assertEqual(["polyhermes", "polyhermes"], restarts)

    def test_bridge_status_accepts_ready_logged_in_runtime_with_stale_trade_error(self):
        self.assertTrue(
            watchdog_module.is_bridge_runtime_ready(
                {
                    "ready": True,
                    "logged_in": True,
                    "last_error": "Could not open buy dialog after outcome click",
                }
            )
        )

    def test_bridge_status_rejects_not_ready_or_logged_out_runtime(self):
        self.assertFalse(watchdog_module.is_bridge_runtime_ready({"ready": False, "logged_in": True}))
        self.assertFalse(watchdog_module.is_bridge_runtime_ready({"ready": True, "logged_in": False}))

    def test_bridge_status_issue_identifies_logged_out_runtime(self):
        self.assertEqual(
            "bridge_status: logged_in=false",
            watchdog_module.bridge_runtime_issue({"ready": True, "logged_in": False}),
        )

    def test_bridge_status_issue_identifies_unready_runtime_first(self):
        self.assertEqual(
            "bridge_status: ready=false",
            watchdog_module.bridge_runtime_issue({"ready": False, "logged_in": False}),
        )

    def test_sends_recovery_notification_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            notifier = FakeNotifier()
            issues = [["public_site: timeout"], [], []]
            monitor = watchdog_module.Watchdog(
                config=self.config(Path(tmp) / "state.json", threshold=1),
                notifier=notifier,
                issue_collector=lambda: issues.pop(0),
                app_diagnostics=lambda: None,
                app_restarter=lambda: True,
                now=lambda: 1000,
            )

            monitor.run_once()
            monitor.run_once()
            monitor.run_once()

            self.assertEqual(2, len(notifier.messages))
            self.assertIn("服务不可用", notifier.messages[0][0])
            self.assertIn("服务已恢复", notifier.messages[1][0])

    def test_failed_recovery_notification_does_not_keep_incident_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "state.json"
            state_file.write_text(
                json.dumps({"failures": 3, "incident": True, "incident_started_at": 900}),
                encoding="utf-8",
            )
            notifier = FailingNotifier()
            monitor = watchdog_module.Watchdog(
                config=self.config(state_file, threshold=1),
                notifier=notifier,
                issue_collector=lambda: [],
                now=lambda: 1000,
            )

            self.assertTrue(monitor.run_once())

            state = json.loads(state_file.read_text(encoding="utf-8"))
            self.assertEqual({"failures": 0, "incident": False}, state)
            self.assertEqual(1, len(notifier.messages))

    def test_feishu_notifier_sends_text_payload(self):
        notifier = watchdog_module.FeishuNotifier(
            webhook_url="https://open.feishu.cn/test-hook",
            timeout=1,
        )
        with mock.patch.object(
            watchdog_module.urllib.request,
            "urlopen",
            return_value=FakeHttpResponse(),
        ) as urlopen:
            self.assertTrue(notifier.send("title", "details"))

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual("text", payload["msg_type"])
        self.assertEqual("title\ndetails", payload["content"]["text"])

    def test_feishu_notifier_sends_app_message_to_chat(self):
        notifier = watchdog_module.FeishuNotifier(
            app_id="cli_test",
            app_secret="secret",
            receive_id="oc_test",
            timeout=1,
        )
        responses = [
            FakeHttpResponse(b'{"code":0,"tenant_access_token":"token"}'),
            FakeHttpResponse(),
        ]
        with mock.patch.object(
            watchdog_module.urllib.request,
            "urlopen",
            side_effect=responses,
        ) as urlopen:
            self.assertTrue(notifier.send("title", "details"))

        message_request = urlopen.call_args_list[1].args[0]
        self.assertIn("receive_id_type=chat_id", message_request.full_url)
        self.assertEqual("Bearer token", message_request.headers["Authorization"])
        payload = json.loads(message_request.data.decode("utf-8"))
        self.assertEqual("oc_test", payload["receive_id"])
        self.assertEqual(
            {"text": "title\ndetails"},
            json.loads(payload["content"]),
        )


if __name__ == "__main__":
    unittest.main()
