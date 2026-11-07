import importlib.util
import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "future_trade_notifier", Path(__file__).with_name("future_trade_notifier.py"))
notifier_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notifier_module)


class FutureTradeNotifierTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = time.time()
        self.control_path = self.root / "state/bridge/control.json"
        self.control_path.parent.mkdir(parents=True)
        self.set_control(True)
        self.notifier = notifier_module.Notifier(self.root)
        self.notifier.trade_enabled = True
        self.notifier.deliver = mock.Mock(return_value=(True, None))

    def set_control(self, enabled, enabled_at=None):
        self.control_path.write_text(json.dumps({
            "requestedEnabled": enabled,
            "enabledAt": (self.now - 10 if enabled_at is None else enabled_at) if enabled else None,
        }))

    def audit(self, reason="CLICK_THROWN_RESULT_UNKNOWN", audit_id="audit-1"):
        return {"auditId": audit_id, "state": "CLICK_ATTEMPTED", "reason": reason,
                "attemptedAt": self.now - 1, "side": "Down", "amountUsd": 1,
                "marketUrl": "https://future.news/zh/event/btc-updown-15m-1794045600"}

    def event(self):
        return {**notifier_module.audit_notification(self.audit()),
                "reason": "CLICK_THROWN_RESULT_UNKNOWN", "attemptedAt": self.now - 1}

    def test_error_message_does_not_claim_platform_rejection_or_fill(self):
        event = notifier_module.audit_notification(self.audit())
        self.assertIn("异常", event["text"])
        self.assertIn("成交待确认", event["text"])
        self.assertNotIn("下单失败", event["text"])

    def test_store_deduplicates_sent_events_across_restart(self):
        event = self.event()
        self.notifier.store.add(event)
        self.notifier.store.mark_sent(event["eventId"])
        store = notifier_module.EventStore(self.notifier.store.state_dir)
        self.assertFalse(store.add(event))
        self.assertEqual([], store.pending(time.time()))

    def test_service_alerts_remain_independent_of_trading_switch(self):
        self.set_control(False)
        self.notifier.trade_enabled = False
        self.notifier.queue_incident("service-1", "SERVICE_DOWN", "助手连续无响应")
        self.notifier.process_outbox()
        self.notifier.deliver.assert_called_once()

    def test_ordinary_unconfirmed_click_is_silent(self):
        self.assertIsNone(notifier_module.audit_notification(self.audit("PLATFORM_RESULT_UNKNOWN")))

    def test_error_event_carries_time_and_reason_for_switch_gate(self):
        event = notifier_module.audit_notification(self.audit())
        self.assertEqual(self.now - 1, event.get("attemptedAt"))
        self.assertEqual("CLICK_THROWN_RESULT_UNKNOWN", event.get("reason"))

    def test_disabled_switch_suppresses_pending_error(self):
        self.notifier.store.add(self.event())
        self.set_control(False)
        self.notifier.trade_enabled = False
        self.notifier.process_outbox()
        self.notifier.deliver.assert_not_called()
        self.assertEqual([], self.notifier.store.pending(time.time()))

    def test_switch_closed_after_health_poll_is_checked_again_before_delivery(self):
        self.notifier.store.add(self.event())
        self.set_control(False)
        self.notifier.process_outbox()
        self.notifier.deliver.assert_not_called()

    def test_suppressed_event_is_not_replayed_after_restart_and_enable(self):
        event = self.event()
        self.notifier.store.add(event)
        self.set_control(False)
        self.notifier.process_outbox()
        self.set_control(True)
        store = notifier_module.EventStore(self.notifier.store.state_dir)
        self.assertFalse(store.add(event))
        self.assertEqual([], store.pending(time.time()))
        self.assertNotIn(event["eventId"], store.sent)

    def test_enabled_error_notifies_once(self):
        self.notifier.store.add(self.event())
        self.notifier.process_outbox()
        self.notifier.process_outbox()
        self.notifier.deliver.assert_called_once()

    def test_old_error_before_latest_enable_is_silent(self):
        self.notifier.store.add(self.event())
        self.set_control(True, self.now)
        self.notifier.process_outbox()
        self.notifier.deliver.assert_not_called()

    def test_unknown_control_defers_without_sending_or_marking_sent(self):
        for control in (None, "invalid json", '{"requestedEnabled": true}',
                        '{"requestedEnabled": "true", "enabledAt": 1}'):
            with self.subTest(control=control):
                if control is None:
                    self.control_path.unlink(missing_ok=True)
                else:
                    self.control_path.write_text(control)
                self.notifier.store = notifier_module.EventStore(self.root / str(control))
                event = self.event()
                self.notifier.store.add(event)
                self.notifier.process_outbox()
                self.assertIn(event["eventId"], self.notifier.store.events)
                self.assertNotIn(event["eventId"], self.notifier.store.sent)
        self.notifier.deliver.assert_not_called()

    def test_unavailable_status_does_not_send(self):
        self.notifier.store.add(self.event())
        self.notifier.trade_enabled = None
        self.notifier.process_outbox()
        self.notifier.deliver.assert_not_called()

    def test_legacy_ordinary_click_in_outbox_is_suppressed_even_when_enabled(self):
        self.notifier.store.add({"eventId": "legacy", "kind": "BUY_CLICK_UNCONFIRMED",
                                 "text": "买入点击已执行（成交待确认）"})
        self.notifier.process_outbox()
        self.notifier.deliver.assert_not_called()

    def test_disabled_audit_is_consumed_without_reenable_backlog(self):
        self.notifier.poll_audits()
        self.set_control(False)
        self.notifier.trade_enabled = False
        notifier_module.append_jsonl(self.notifier.audit_path, self.audit())
        self.notifier.poll_audits()
        self.assertEqual({}, self.notifier.store.events)
        self.set_control(True)
        self.notifier.trade_enabled = True
        self.notifier.poll_audits()
        self.notifier.process_outbox()
        self.notifier.deliver.assert_not_called()

    def test_risk_skip_and_intentional_disable_are_not_order_errors(self):
        for reason in ("PRICE_BELOW_MIN", "AUTO_DISABLED", "AUTO_PREPARATION_DISABLED",
                       "EXECUTOR_NOT_CONNECTED", "INTENT_EXPIRED"):
            with self.subTest(reason=reason):
                audit = {**self.audit(reason), "state": "BLOCKED"}
                self.assertIsNone(notifier_module.audit_notification(audit))

    def run_with_status(self, enabled):
        status = {"bridgeId": "future-btc5m", "online": True, "requestedEnabled": enabled,
                  "preparation": {"enabled": enabled}, "preflight": {"browserConnected": True}}
        with mock.patch.object(self.notifier.local_opener, "open",
                               return_value=io.BytesIO(json.dumps(status).encode())), \
                mock.patch.object(notifier_module.subprocess, "run", return_value=mock.Mock(returncode=0)):
            self.notifier.run_once()

    def test_run_once_uses_live_disabled_status_despite_cached_enabled(self):
        self.notifier.store.add(self.event())
        self.run_with_status(False)
        self.assertIs(self.notifier.trade_enabled, False)
        self.notifier.deliver.assert_not_called()

    def test_run_once_delivers_current_enabled_exception(self):
        self.notifier.store.add(self.event())
        self.run_with_status(True)
        self.notifier.deliver.assert_called_once()

    def test_failed_health_poll_does_not_reuse_enabled_status(self):
        self.notifier.store.add(self.event())
        with mock.patch.object(self.notifier.local_opener, "open", side_effect=OSError), \
                mock.patch.object(notifier_module.subprocess, "run", return_value=mock.Mock(returncode=0)):
            self.notifier.run_once()
        self.assertIsNone(self.notifier.trade_enabled)
        self.notifier.deliver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
