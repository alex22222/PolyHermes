#!/usr/bin/env python3

import datetime
import json
import math
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLL_SECONDS = 10
BRIDGE_URL = "http://127.0.0.1:8766/bridge/status"
TUNNEL_PATTERN = "start-future-btc5m-tunnel.sh"


def append_jsonl(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path):
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.endswith("\n"):
                continue
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def audit_notification(record):
    audit_id = record.get("auditId")
    if not isinstance(audit_id, str) or not audit_id or record.get("state") != "CLICK_ATTEMPTED":
        return None
    reason = record.get("reason")
    # An ordinary click with an unknown platform result is not an order failure.
    if reason != "CLICK_THROWN_RESULT_UNKNOWN":
        return None
    attempted_at = record.get("attemptedAt")
    when = (datetime.datetime.fromtimestamp(attempted_at).astimezone().strftime("%H:%M:%S")
            if type(attempted_at) in (int, float) else "时间未知")
    title = "买入操作异常（成交待确认）"
    text = (f"[PolyHermes] {title} ({when})\n"
            f"方向:{record.get('side')} 金额:${record.get('amountUsd', 1)}\n"
            f"市场:{record.get('marketUrl', '')}\n"
            f"状态:{record.get('state')} 备注:{reason}\n"
            "点击时发生异常；Future 平台结果仍未知，请勿据此重复下单")
    return {"eventId": f"buy-click:{audit_id}", "kind": "BUY_CLICK_UNCONFIRMED", "text": text,
            "reason": reason, "attemptedAt": attempted_at}


def wallet_fund_line(wallet):
    if not isinstance(wallet, dict):
        return "钱包现金:未知（无钱包报告）"
    observed_at = wallet.get("observedAt")
    when = (datetime.datetime.fromtimestamp(observed_at).astimezone().strftime("%H:%M:%S")
            if type(observed_at) in (int, float) else "时间未知")
    cash = wallet.get("cashUsd")
    if (wallet.get("fresh") is True and type(cash) in (int, float)
            and math.isfinite(cash) and cash >= 0):
        return f"钱包现金:${cash:.2f}（{when} 更新）"
    if when != "时间未知":
        return f"钱包现金:未知（最近报告已过期，最后更新 {when}）"
    return "钱包现金:未知（无新鲜钱包报告）"


class EventStore:
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self.events_path = self.state_dir / "events.jsonl"
        self.sent_path = self.state_dir / "sent.jsonl"
        self.suppressed_path = self.state_dir / "suppressed.jsonl"
        self.events = {}
        self.sent = set()
        self.suppressed = set()
        for record in read_jsonl(self.events_path):
            event_id = record.get("eventId")
            if isinstance(event_id, str) and isinstance(record.get("text"), str):
                record.setdefault("attempts", 0)
                record.setdefault("nextAttemptAt", 0)
                self.events[event_id] = record
        for path, terminal_ids in ((self.sent_path, self.sent), (self.suppressed_path, self.suppressed)):
            for record in read_jsonl(path):
                event_id = record.get("eventId")
                if isinstance(event_id, str):
                    terminal_ids.add(event_id)
                    self.events.pop(event_id, None)

    def add(self, event):
        event_id = event["eventId"]
        if event_id in self.events or event_id in self.sent or event_id in self.suppressed:
            return False
        record = {**event, "createdAt": time.time(), "attempts": 0, "nextAttemptAt": 0}
        append_jsonl(self.events_path, record)
        self.events[event_id] = record
        return True

    def pending(self, now):
        return sorted((record for record in self.events.values() if record["nextAttemptAt"] <= now),
                      key=lambda record: record["createdAt"])

    def defer(self, event_id, now):
        record = self.events[event_id]
        record["attempts"] += 1
        delay = min(300, 15 * 2 ** min(record["attempts"] - 1, 4))
        record["nextAttemptAt"] = now + delay
        return delay

    def mark_sent(self, event_id):
        append_jsonl(self.sent_path, {"eventId": event_id, "sentAt": time.time()})
        self.sent.add(event_id)
        self.events.pop(event_id, None)

    def suppress(self, event_id, reason):
        append_jsonl(self.suppressed_path, {"eventId": event_id, "suppressedAt": time.time(), "reason": reason})
        self.suppressed.add(event_id)
        self.events.pop(event_id, None)


class Notifier:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.audit_path = self.root / "state" / "bridge" / "buy_attempts.jsonl"
        self.control_path = self.root / "state" / "bridge" / "control.json"
        self.sender = self.root / "app" / "scripts" / "feishu_notify.py"
        self.store = EventStore(self.root / "state" / "notifier")
        self.local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.seen_audit_ids = set()
        self.audits_initialized = False
        self.assistant_bad = 0
        self.assistant_down = False
        self.browser_bad = 0
        self.browser_down = False
        self.tunnel_down = False
        self.latest_wallet = None
        self.trade_enabled = None

    def trade_gate(self, event):
        if event.get("kind") != "BUY_CLICK_UNCONFIRMED":
            return "READY"
        attempted_at = event.get("attemptedAt")
        if (event.get("reason") != "CLICK_THROWN_RESULT_UNKNOWN"
                or type(attempted_at) not in (int, float) or not math.isfinite(attempted_at)
                or not 0 < attempted_at <= time.time()):
            return "NOT_ORDER_FAILURE"
        try:
            control = json.loads(self.control_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "CONTROL_UNKNOWN"
        if not isinstance(control, dict):
            return "CONTROL_UNKNOWN"
        if control.get("requestedEnabled") is False:
            return "AUTO_DISABLED"
        enabled_at = control.get("enabledAt")
        if (control.get("requestedEnabled") is not True or type(enabled_at) not in (int, float)
                or not math.isfinite(enabled_at) or enabled_at <= 0):
            return "CONTROL_UNKNOWN"
        if attempted_at < enabled_at:
            return "BEFORE_CURRENT_ENABLE"
        if self.trade_enabled is False:
            return "AUTO_DISABLED"
        return "READY" if self.trade_enabled is True else "STATUS_UNKNOWN"

    def message_text(self, event):
        if event.get("kind") != "BUY_CLICK_UNCONFIRMED":
            return event["text"]
        return event["text"] + "\n" + wallet_fund_line(self.latest_wallet)

    def deliver(self, event):
        try:
            result = subprocess.run([sys.executable, str(self.sender), self.message_text(event)],
                                    capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except OSError as error:
            return False, type(error).__name__
        if result.returncode == 0 and result.stdout.strip() == "sent":
            return True, None
        return False, f"sender_exit_{result.returncode}"

    def process_outbox(self):
        now = time.time()
        for event in self.store.pending(now):
            event_id = event["eventId"]
            gate = self.trade_gate(event)
            if gate in ("AUTO_DISABLED", "BEFORE_CURRENT_ENABLE", "NOT_ORDER_FAILURE"):
                self.store.suppress(event_id, gate)
                print(f"NOTIFY_SUPPRESSED {event_id} reason={gate}", flush=True)
                continue
            if gate != "READY":
                delay = self.store.defer(event_id, now)
                print(f"NOTIFY_DEFERRED {event_id} delay={delay}s reason={gate}", flush=True)
                continue
            ok, error = self.deliver(event)
            if ok:
                self.store.mark_sent(event_id)
                print(f"NOTIFY_SENT {event_id} {event['kind']}", flush=True)
            else:
                delay = self.store.defer(event_id, now)
                print(f"NOTIFY_RETRY {event_id} attempts={event['attempts']} delay={delay}s reason={error}", flush=True)

    def poll_audits(self):
        records = read_jsonl(self.audit_path)
        if not self.audits_initialized:
            self.seen_audit_ids = {record.get("auditId") for record in records if isinstance(record.get("auditId"), str)}
            self.audits_initialized = True
            return
        for record in records:
            audit_id = record.get("auditId")
            if not isinstance(audit_id, str) or audit_id in self.seen_audit_ids:
                continue
            self.seen_audit_ids.add(audit_id)
            event = audit_notification(record)
            if not event:
                continue
            gate = self.trade_gate(event)
            if gate in ("AUTO_DISABLED", "BEFORE_CURRENT_ENABLE", "NOT_ORDER_FAILURE"):
                self.store.suppress(event["eventId"], gate)
            elif self.store.add(event):
                print(f"NOTIFY_QUEUED {event['eventId']} {event['kind']}", flush=True)

    def queue_incident(self, event_id, kind, text):
        self.store.add({"eventId": event_id, "kind": kind, "text": text})

    def poll_health(self):
        now = time.time()
        self.trade_enabled = None
        try:
            with self.local_opener.open(BRIDGE_URL, timeout=3) as response:
                status = json.load(response)
            if status.get("bridgeId") != "future-btc5m" or status.get("online") is not True:
                raise ValueError("INVALID_BRIDGE_STATUS")
        except Exception:
            self.assistant_bad += 1
            self.latest_wallet = None
            if self.assistant_bad >= 3 and not self.assistant_down:
                self.assistant_down = True
                self.queue_incident(f"assistant-down:{int(now)}", "SERVICE_DOWN",
                                    "[PolyHermes] 服务故障\n助手/桥连续无响应超过30秒，请检查进程与隧道")
            status = None
        else:
            preparation = status.get("preparation") or {}
            if status.get("requestedEnabled") is False or preparation.get("enabled") is False:
                self.trade_enabled = False
            elif status.get("requestedEnabled") is True and preparation.get("enabled") is True:
                self.trade_enabled = True
            wallet = status.get("wallet")
            self.latest_wallet = wallet if isinstance(wallet, dict) else None
            self.assistant_bad = 0
            if self.assistant_down:
                self.assistant_down = False
                self.queue_incident(f"assistant-recovered:{int(now)}", "SERVICE_RECOVERED",
                                    "[PolyHermes] 服务已恢复\n助手/桥重新可达")
            browser_connected = (status.get("preflight") or {}).get("browserConnected") is True
            if browser_connected:
                self.browser_bad = 0
                if self.browser_down:
                    self.browser_down = False
                    self.queue_incident(f"browser-recovered:{int(now)}", "SERVICE_RECOVERED",
                                        "[PolyHermes] 浏览器扩展已恢复")
            else:
                self.browser_bad += 1
                if self.browser_bad >= 12 and not self.browser_down:
                    self.browser_down = True
                    self.queue_incident(f"browser-down:{int(now)}", "SERVICE_DOWN",
                                        "[PolyHermes] 服务故障\n浏览器扩展已断连约2分钟，页面报告停滞")
        tunnel_alive = subprocess.run(["pgrep", "-f", TUNNEL_PATTERN], stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL).returncode == 0
        if not tunnel_alive and not self.tunnel_down:
            self.tunnel_down = True
            self.queue_incident(f"tunnel-down:{int(now)}", "SERVICE_DOWN",
                                "[PolyHermes] 服务故障\nSSH隧道进程消失，生产relay已断开")
        elif tunnel_alive and self.tunnel_down:
            self.tunnel_down = False
            self.queue_incident(f"tunnel-recovered:{int(now)}", "SERVICE_RECOVERED",
                                "[PolyHermes] SSH隧道已恢复")

    def run_once(self):
        self.poll_health()
        self.poll_audits()
        self.process_outbox()

    def run(self):
        print(f"NOTIFIER_START audits={self.audit_path}", flush=True)
        while True:
            try:
                self.run_once()
            except Exception as error:
                print(f"NOTIFIER_POLL_ERROR {type(error).__name__}", flush=True)
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    notifier = Notifier()
    if "--once" in sys.argv[1:]:
        notifier.run_once()
    else:
        notifier.run()
