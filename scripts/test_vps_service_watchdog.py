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
    def config(self, state_file, threshold=2):
        return watchdog_module.Config(
            state_file=state_file,
            failure_threshold=threshold,
            reminder_seconds=1800,
            auto_restart_app=True,
        )

    def test_restarts_only_main_app_after_consecutive_app_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            notifier = FakeNotifier()
            restarts = []
            monitor = watchdog_module.Watchdog(
                config=self.config(Path(tmp) / "state.json"),
                notifier=notifier,
                issue_collector=lambda: ["backend_business: HTTP 502"],
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

    def test_sends_recovery_notification_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            notifier = FakeNotifier()
            issues = [["public_site: timeout"], [], []]
            monitor = watchdog_module.Watchdog(
                config=self.config(Path(tmp) / "state.json", threshold=1),
                notifier=notifier,
                issue_collector=lambda: issues.pop(0),
                app_restarter=lambda: True,
                now=lambda: 1000,
            )

            monitor.run_once()
            monitor.run_once()
            monitor.run_once()

            self.assertEqual(2, len(notifier.messages))
            self.assertIn("服务不可用", notifier.messages[0][0])
            self.assertIn("服务已恢复", notifier.messages[1][0])

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
