"""Local Future BTC5m control and order facts; no execution adapter is installed."""

import copy
import json
import math
import os
import re
import threading
import time
from pathlib import Path


BRIDGE_ID = "future-btc5m"
OPEN_PRICE_SOURCE = "polymarket_crypto_price_fiveminute_twap60_openPrice"
FILL_FIELDS = ("submittedAt", "filledAt", "platformOrderId", "filledQuantity", "avgFilledPrice", "feeUsd")
PREFLIGHT_FIELDS = {"schemaVersion", "marketUrl", "pagePeriodStart", "checkedAt", "navigation",
                    "ticketStatus", "amountUsd", "selectedSide", "buyButtonEnabled"}


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def strict_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


class FutureBridge:
    def __init__(self, state_dir, status_fn, now_fn=time.time):
        self.state_dir = Path(state_dir)
        self.status_fn = status_fn
        self.now_fn = now_fn
        self.lock = threading.RLock()
        self.requested_enabled = False
        self.enabled_at = None
        self.records = []
        self.seen = set()
        self.storage_error = None
        self.browser_report = None
        self.browser_received_at = None
        self.preflight_error = None
        self.preflight_seen = set()
        self.last_preflight_pass = None
        self.state_dir.mkdir(parents=True, exist_ok=True)
        ledger = self.state_dir / "orders.jsonl"
        if ledger.exists():
            try:
                with ledger.open(encoding="utf-8") as stream:
                    for line in stream:
                        record = json.loads(line)
                        if not line.endswith("\n") or not self._valid_record(record) or record["id"] in self.seen:
                            raise ValueError("Invalid order ledger")
                        self.records.append(record)
                        self.seen.add(record["id"])
            except (OSError, ValueError, TypeError):
                self.storage_error = "ORDER_LEDGER_INVALID"
        preflight_ledger = self.state_dir / "preflight.jsonl"
        if preflight_ledger.exists():
            try:
                with preflight_ledger.open(encoding="utf-8") as stream:
                    for line in stream:
                        record = json.loads(line, object_pairs_hook=strict_json_object)
                        if (not line.endswith("\n") or not self._valid_preflight_record(record)
                                or record["periodStart"] in self.preflight_seen):
                            raise ValueError("Invalid preflight ledger")
                        self.preflight_seen.add(record["periodStart"])
                        if self.last_preflight_pass is None or record["periodStart"] > self.last_preflight_pass["periodStart"]:
                            self.last_preflight_pass = record
            except (OSError, ValueError, TypeError):
                self.preflight_error = "PREFLIGHT_LEDGER_INVALID"
                self.last_preflight_pass = None
        # A process restart never resumes a persisted request to trade.
        try:
            self._save_control(self.now_fn())
        except OSError:
            self.storage_error = self.storage_error or "CONTROL_STATE_WRITE_FAILED"

    @staticmethod
    def _valid_record(record):
        if not isinstance(record, dict):
            return False
        start = record.get("periodStart")
        at = record.get("createdAt")
        return (
            type(start) is int and start >= 0 and start % 300 == 0
            and record.get("id") == f"{BRIDGE_ID}:{start}" and record.get("bridgeId") == BRIDGE_ID
            and record.get("slug") == f"btc-updown-5m-{start}" and record.get("periodEnd") == start + 300
            and record.get("side") in ("Up", "Down")
            and finite_number(record.get("amountUsd")) and record["amountUsd"] == 1
            and record.get("status") == "SKIPPED" and record.get("reason") == "EXECUTOR_NOT_CONNECTED"
            and finite_number(at) and start + 60 <= at < start + 80 and record.get("updatedAt") == at
            and all(field in record and record[field] is None for field in FILL_FIELDS)
            and record.get("events") == [
                {"stage": "SIGNAL_ACCEPTED", "at": at, "reason": None},
                {"stage": "EXECUTION_BLOCKED", "at": at, "reason": "EXECUTOR_NOT_CONNECTED"},
            ]
        )

    @staticmethod
    def _market_url_start(url):
        if not isinstance(url, str):
            return None
        match = re.fullmatch(r"https://future\.news/(?:zh/)?event/btc-updown-5m-([0-9]{1,15})/?", url)
        if not match:
            return None
        start = int(match[1])
        return start if str(start) == match[1] and start % 300 == 0 else None

    @classmethod
    def _valid_preflight_record(cls, record):
        if not isinstance(record, dict) or set(record) != {"periodStart", "checkedAt", "marketUrl", "signalSide", "amountUsd", "noSubmission"}:
            return False
        start = record["periodStart"]
        return (type(start) is int and start >= 0 and start % 300 == 0
                and cls._market_url_start(record["marketUrl"]) == start
                and finite_number(record["checkedAt"]) and start + 60 <= record["checkedAt"] < start + 80
                and record["signalSide"] in ("Up", "Down")
                and finite_number(record["amountUsd"]) and record["amountUsd"] == 1
                and record["noSubmission"] is True)

    def report_preflight(self, payload):
        with self.lock:
            now = self.now_fn()
            if (type(payload) is not dict or set(payload) != PREFLIGHT_FIELDS
                    or type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1
                    or type(payload["pagePeriodStart"]) is not int
                    or self._market_url_start(payload["marketUrl"]) != payload["pagePeriodStart"]
                    or not finite_number(payload["checkedAt"]) or abs(now - payload["checkedAt"]) > 3
                    or payload["navigation"] not in ("CURRENT", "ENDED", "MISMATCH")
                    or payload["ticketStatus"] not in ("PASS", "FAIL")
                    or payload["amountUsd"] is not None and (not finite_number(payload["amountUsd"]) or payload["amountUsd"] < 0)
                    or payload["selectedSide"] not in ("Up", "Down", None)
                    or type(payload["buyButtonEnabled"]) is not bool):
                raise ValueError("INVALID_PREFLIGHT_REPORT")
            start = int(now // 300) * 300
            if (payload["pagePeriodStart"] > start
                    or payload["navigation"] == "CURRENT" and payload["pagePeriodStart"] != start
                    or payload["navigation"] == "ENDED" and payload["pagePeriodStart"] >= start
                    or self.browser_report is not None and payload["checkedAt"] < self.browser_report["checkedAt"]):
                raise ValueError("INVALID_PREFLIGHT_MARKET_OR_TIME")
            self.browser_report = copy.deepcopy(payload)
            self.browser_received_at = now
            source, error = self._read_source()
            return self._status(source, error, now, persist_preflight=True)

    def _preflight(self, source, source_error, now, persist=False):
        report = self.browser_report
        connected = bool(report and self.browser_received_at is not None
                         and 0 <= now - self.browser_received_at <= 5 and abs(now - report["checkedAt"]) <= 5)
        signal = self._current_signal(source, now, require_enabled=False) if not source_error and not self._stopped(source) else None
        side_matches = bool(signal and connected and report["selectedSide"] == signal["side"])
        reasons = [self.preflight_error] if self.preflight_error else []
        if source_error:
            reasons.append(source_error)
        if self._stopped(source):
            reasons.append("STOP_FILE_PRESENT")
        if not connected:
            reasons.append("BROWSER_NOT_CONNECTED")
        else:
            if report["navigation"] != "CURRENT" or report["pagePeriodStart"] != int(now // 300) * 300:
                reasons.append("MARKET_NOT_CURRENT")
            if report["ticketStatus"] != "PASS":
                reasons.append("TICKET_CHECK_FAILED")
            if report["amountUsd"] != 1:
                reasons.append("AMOUNT_NOT_ONE_USD")
            if not report["buyButtonEnabled"]:
                reasons.append("BUY_BUTTON_DISABLED")
            if not side_matches:
                reasons.append("SIDE_MISMATCH")
            if signal and not signal["period_start"] + 60 <= report["checkedAt"] < signal["period_start"] + 80:
                reasons.append("BROWSER_CHECK_OUTSIDE_ENTRY")
        if not signal:
            reasons.append("SIGNAL_NOT_FRESH")
        if not reasons and persist and signal["period_start"] not in self.preflight_seen:
            record = {"periodStart": signal["period_start"], "checkedAt": report["checkedAt"],
                      "marketUrl": report["marketUrl"], "signalSide": signal["side"],
                      "amountUsd": 1, "noSubmission": True}
            try:
                ledger_path = self.state_dir / "preflight.jsonl"
                first_write = not ledger_path.exists()
                with ledger_path.open("a", encoding="utf-8") as ledger:
                    ledger.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                    ledger.flush()
                    os.fsync(ledger.fileno())
                if first_write:
                    descriptor = os.open(self.state_dir, os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
                self.preflight_seen.add(record["periodStart"])
                self.last_preflight_pass = record
            except OSError:
                self.preflight_error = "PREFLIGHT_LEDGER_WRITE_FAILED"
                self.last_preflight_pass = None
                reasons.append(self.preflight_error)
        result = "READ_ONLY_READY" if not reasons else (
            "WAITING_BROWSER" if not connected and not self.preflight_error and not source_error and not self._stopped(source) else "BLOCKED"
        )
        return {"mode": "READ_ONLY", "noSubmission": True, "browserConnected": connected,
                "checkedAt": report["checkedAt"] if report else None, "receivedAt": self.browser_received_at,
                "marketUrl": report["marketUrl"] if report else None,
                "pagePeriodStart": report["pagePeriodStart"] if report else None,
                "navigation": report["navigation"] if report else "UNKNOWN",
                "ticketStatus": report["ticketStatus"] if report else "UNKNOWN",
                "amountUsd": report["amountUsd"] if report else None,
                "selectedSide": report["selectedSide"] if report else None,
                "buyButtonEnabled": report["buyButtonEnabled"] if report else False,
                "signalFresh": bool(signal), "signalSide": signal["side"] if signal else None,
                "sideMatches": side_matches, "result": result, "reasons": reasons,
                "lastPassed": copy.deepcopy(self.last_preflight_pass)}

    def _save_control(self, now):
        temporary = self.state_dir / "control.json.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump({"requestedEnabled": self.requested_enabled, "enabledAt": self.enabled_at,
                       "amountUsd": 1, "series": "5m", "updatedAt": now}, stream, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.state_dir / "control.json")
        descriptor = os.open(self.state_dir, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _read_source(self):
        try:
            source = self.status_fn()
            if not isinstance(source, dict):
                return {}, "SIGNAL_SOURCE_INVALID"
            # Reject non-JSON/nonfinite upstream data before exposing it to the page.
            json.dumps(source, allow_nan=False)
            return copy.deepcopy(source), None
        except Exception:
            return {}, "SIGNAL_SOURCE_UNAVAILABLE"

    def _stopped(self, source):
        return (self.state_dir / "STOP").exists() or source.get("status") == "STOPPED"

    def _disable_for_stop(self, source, now):
        if self._stopped(source) and self.requested_enabled:
            self.requested_enabled = False
            self.enabled_at = None
            try:
                self._save_control(now)
            except OSError:
                self.storage_error = self.storage_error or "CONTROL_STATE_WRITE_FAILED"

    def _status(self, source, source_error, now, persist_preflight=False):
        self._disable_for_stop(source, now)
        reasons = [self.storage_error] if self.storage_error else []
        if self._stopped(source):
            reasons.append("STOP_FILE_PRESENT")
        if source_error:
            reasons.append(source_error)
        reasons.append("EXECUTOR_NOT_CONNECTED")
        reason = reasons[0] if self.storage_error or self._stopped(source) else (
            "EXECUTOR_NOT_CONNECTED" if self.requested_enabled else "AUTO_DISABLED"
        )
        start = source.get("period_start")
        if type(start) is not int or start % 300 != 0:
            start = None
        return {
            "bridgeId": BRIDGE_ID, "online": True, "requestedEnabled": self.requested_enabled,
            "effectiveEnabled": False, "amountUsd": 1, "series": "5m",
            "mode": "BLOCKED" if self.requested_enabled else "DISABLED", "serverTime": now,
            "periodStart": start, "feedStatus": source.get("feed_status", "UNAVAILABLE"),
            "reason": reason, "blockReasons": reasons, "executorReady": False,
            "signal": copy.deepcopy(source.get("signal")) if isinstance(source.get("signal"), dict) else None,
            "orderCounts": {"total": len(self.records), "pending": 0, "submitted": 0,
                            "filled": 0, "failed": 0, "skipped": len(self.records)},
            "preflight": self._preflight(source, source_error, now, persist_preflight),
        }

    def status(self):
        with self.lock:
            source, error = self._read_source()
            return self._status(source, error, self.now_fn())

    def control(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("ENABLED_MUST_BE_BOOLEAN")
        with self.lock:
            now = self.now_fn()
            source, error = self._read_source()
            self._disable_for_stop(source, now)
            if enabled and self.storage_error:
                raise ValueError(self.storage_error)
            if enabled and self._stopped(source):
                raise ValueError("STOP_FILE_PRESENT")
            if enabled and not self.requested_enabled:
                self.enabled_at = now
            elif not enabled:
                self.enabled_at = None
            self.requested_enabled = enabled
            try:
                self._save_control(now)
            except OSError:
                self.requested_enabled = False
                self.enabled_at = None
                self.storage_error = self.storage_error or "CONTROL_STATE_WRITE_FAILED"
                raise
            return self._status(source, error, now)

    def orders(self, page=1, size=20, status=None):
        if type(page) is not int or page < 1 or type(size) is not int or not 1 <= size <= 100:
            raise ValueError("INVALID_PAGINATION")
        if status is not None and not isinstance(status, str):
            raise ValueError("INVALID_STATUS")
        with self.lock:
            if self.storage_error in ("ORDER_LEDGER_INVALID", "ORDER_LEDGER_WRITE_FAILED"):
                raise OSError(self.storage_error)
            records = [record for record in reversed(self.records) if not status or record["status"] == status]
            offset = (page - 1) * size
            return {"list": copy.deepcopy(records[offset:offset + size]), "total": len(records), "page": page, "size": size}

    def detail(self, id):
        with self.lock:
            if self.storage_error in ("ORDER_LEDGER_INVALID", "ORDER_LEDGER_WRITE_FAILED"):
                raise OSError(self.storage_error)
            return next((copy.deepcopy(record) for record in self.records if record["id"] == id), None)

    def _current_signal(self, source, now, require_enabled=True):
        if (type(source.get("schema_version")) is not int or source["schema_version"] != 1
                or source.get("mode") != "ASSIST_ONLY" or source.get("live_enabled") is not False
                or not finite_number(source.get("amount_usd")) or source["amount_usd"] != 1
                or source.get("status") not in ("WAITING", "OBSERVING", "READY", "EXPIRED", "SKIPPED")
                or source.get("feed_status") != "CURRENT" or not finite_number(source.get("server_time"))
                or abs(now - source["server_time"]) > 3):
            return None
        start = int(now // 300) * 300
        signal = source.get("signal")
        if not isinstance(signal, dict) or type(source.get("period_start")) is not int or source["period_start"] != start:
            return None
        if (not start + 60 <= now < start + 80 or type(signal.get("period_start")) is not int
                or signal["period_start"] != start or signal.get("period_end") != start + 300
                or signal.get("id") != f"5m:{start}" or signal.get("slug") != f"btc-updown-5m-{start}"
                or signal.get("series") != "5m" or signal.get("price_source") != "chainlink"
                or signal.get("open_price_source") != OPEN_PRICE_SOURCE or signal.get("twap_lookback_seconds") != 60
                or not finite_number(signal.get("price_observed_at"))
                or signal["price_observed_at"] > now
                or now - signal["price_observed_at"] > 5
                or require_enabled and (self.enabled_at is None or signal["price_observed_at"] < self.enabled_at)
                or not finite_number(signal.get("open_price")) or signal["open_price"] <= 0
                or not finite_number(signal.get("current_price")) or signal["current_price"] <= 0):
            return None
        expected = "Up" if signal["current_price"] > signal["open_price"] else (
            "Down" if signal["current_price"] < signal["open_price"] else None
        )
        return signal if expected in ("Up", "Down") and signal.get("side") == expected else None

    def observe(self):
        with self.lock:
            now = self.now_fn()
            source, error = self._read_source()
            self._disable_for_stop(source, now)
            signal = self._current_signal(source, now) if self.requested_enabled and not self.storage_error and not error else None
            if signal and not self._stopped(source):
                start = signal["period_start"]
                id = f"{BRIDGE_ID}:{start}"
                if id not in self.seen:
                    record = {
                        "id": id, "bridgeId": BRIDGE_ID, "slug": signal["slug"],
                        "periodStart": start, "periodEnd": start + 300, "side": signal["side"],
                        "amountUsd": 1, "status": "SKIPPED", "reason": "EXECUTOR_NOT_CONNECTED",
                        "createdAt": now, "updatedAt": now, **{field: None for field in FILL_FIELDS},
                        "events": [{"stage": "SIGNAL_ACCEPTED", "at": now, "reason": None},
                                   {"stage": "EXECUTION_BLOCKED", "at": now, "reason": "EXECUTOR_NOT_CONNECTED"}],
                    }
                    try:
                        ledger_path = self.state_dir / "orders.jsonl"
                        first_write = not ledger_path.exists()
                        with ledger_path.open("a", encoding="utf-8") as ledger:
                            ledger.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                            ledger.flush()
                            os.fsync(ledger.fileno())
                        if first_write:
                            descriptor = os.open(self.state_dir, os.O_RDONLY)
                            try:
                                os.fsync(descriptor)
                            finally:
                                os.close(descriptor)
                        self.records.append(record)
                        self.seen.add(id)
                    except OSError:
                        self.storage_error = "ORDER_LEDGER_WRITE_FAILED"
                        self.requested_enabled = False
                        self.enabled_at = None
            return self._status(source, error, now, persist_preflight=True)
