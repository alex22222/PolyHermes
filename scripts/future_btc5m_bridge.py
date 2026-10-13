"""Local Future BTC5m control and order facts; no execution adapter is installed."""

import copy
import json
import math
import os
import re
import secrets
import threading
import time
from pathlib import Path


BRIDGE_ID = "future-btc5m"
OPEN_PRICE_SOURCE = "polymarket_crypto_price_fiveminute_twap60_openPrice"
FILL_FIELDS = ("submittedAt", "filledAt", "platformOrderId", "filledQuantity", "avgFilledPrice", "feeUsd")
PREFLIGHT_FIELDS = {"schemaVersion", "marketUrl", "pagePeriodStart", "checkedAt", "navigation",
                    "ticketStatus", "amountUsd", "selectedSide", "buyButtonEnabled"}
PREFLIGHT_V2_FIELDS = PREFLIGHT_FIELDS | {"upQuoteCents", "downQuoteCents"}
PREPARATION_INTENT_FIELDS = {"schemaVersion", "id", "slug", "periodStart", "periodEnd", "side", "amountUsd",
    "createdAt", "expiresAt", "priceObservedAt", "openPrice", "currentPrice", "priceSource", "openPriceSource",
    "twapLookbackSeconds", "mode", "noSubmission", "operatorAuthorized", "authorizationSource", "claimToken"}
PREPARATION_RECORD_FIELDS = PREPARATION_INTENT_FIELDS | {"state", "updatedAt", "claimedAt", "reason", "receipt"}
PREPARATION_V2_INTENT_FIELDS = PREPARATION_INTENT_FIELDS | {"upQuoteCents", "downQuoteCents", "quoteObservedAt", "selectionSource"}
PREPARATION_V2_RECORD_FIELDS = PREPARATION_V2_INTENT_FIELDS | {"state", "updatedAt", "claimedAt", "reason", "receipt"}
PREFLIGHT_PASS_FIELDS = {"periodStart", "checkedAt", "marketUrl", "signalSide", "amountUsd", "noSubmission"}
PREFLIGHT_V2_PASS_FIELDS = PREFLIGHT_PASS_FIELDS | {"schemaVersion", "selectionSource", "upQuoteCents", "downQuoteCents", "preferredSide"}
PREPARATION_REPORT_FIELDS = {"schemaVersion", "id", "claimToken", "checkedAt", "status", "marketUrl",
                             "amountUsd", "selectedSide", "reason", "noSubmission"}
PREPARATION_FAILURES = {"PREPARATION_FAILED", "MARKET_MISMATCH", "TICKET_CHANGED", "UNSAFE_DIRECTION_CONTROL",
                        "AMOUNT_WRITE_FAILED", "DIRECTION_WRITE_FAILED", "POSTCHECK_FAILED", "PREPARATION_REVOKED",
                        "BUTTON_QUOTES_UNAVAILABLE", "BUTTON_QUOTES_TIED", "BUTTON_QUOTES_NOT_FRESH", "HIGHER_BUTTON_SIDE_CHANGED"}
# One extension Buy attempt (or refusal) bound to a READY preparation. A click attempt is
# not an order or fill fact; platform fills are reconciled separately.
BUY_AUDIT_FIELDS = {"schemaVersion", "auditId", "id", "claimToken", "periodStart", "side", "amountUsd", "state",
                    "reason", "armedAt", "attemptedAt", "marketUrl", "upQuoteCents", "downQuoteCents",
                    "selectedSide", "ticketAmountUsd", "extensionVersion"}
# Schema 2 adds the independent Polymarket CLOB asks the price gates compared, or nulls when none was read.
BUY_AUDIT_V2_FIELDS = BUY_AUDIT_FIELDS | {"marketUpAskCents", "marketDownAskCents", "marketQuoteObservedAt"}
BUY_AUDIT_REASONS = {"CLICK_ATTEMPTED": {"PLATFORM_RESULT_UNKNOWN", "CLICK_THROWN_RESULT_UNKNOWN"},
                     "BLOCKED": {"TICKET_CHANGED", "BUY_BUTTON_UNSAFE", "READY_CHANGED", "STORAGE_FAILED",
                                 "FINAL_CHECK_FAILED", "ALREADY_CONSUMED", "PRICE_BELOW_MIN",
                                 "MARKET_QUOTE_UNAVAILABLE", "MARKET_QUOTE_MISMATCH", "PRICE_ABOVE_MAX"}}


class PreparationConflict(ValueError):
    pass


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def valid_button_quote(value):
    return finite_number(value) and 0 <= value <= 100 and value == round(value, 2)


def higher_button_side(up, down):
    if not valid_button_quote(up) or not valid_button_quote(down) or up == down:
        return None
    return "Up" if up > down else "Down"


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
        self.preparations = {}
        self.last_preparation = None
        self.preparation_error = None
        self.buy_audits = {}
        self.buy_audit_error = None
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
        preparation_ledger = self.state_dir / "preparations.jsonl"
        if preparation_ledger.exists():
            try:
                with preparation_ledger.open(encoding="utf-8") as stream:
                    for line in stream:
                        record = json.loads(line, object_pairs_hook=strict_json_object)
                        previous = self.preparations.get(record.get("id")) if isinstance(record, dict) else None
                        if not line.endswith("\n") or not self._valid_preparation_record(record, previous):
                            raise ValueError("Invalid preparation ledger")
                        self.preparations[record["id"]] = record
                        if self.last_preparation is None or record["periodStart"] >= self.last_preparation["periodStart"]:
                            self.last_preparation = record
            except (OSError, ValueError, TypeError):
                self.preparation_error = "PREPARATION_LEDGER_INVALID"
                self.last_preparation = None
        buy_audit_ledger = self.state_dir / "buy_attempts.jsonl"
        if buy_audit_ledger.exists():
            try:
                with buy_audit_ledger.open(encoding="utf-8") as stream:
                    for line in stream:
                        record = json.loads(line, object_pairs_hook=strict_json_object)
                        fields = self._buy_audit_fields(record)
                        if (not line.endswith("\n") or fields is None or set(record) != fields | {"receivedAt"}
                                or not self._valid_buy_audit(record) or not finite_number(record["receivedAt"])
                                or record["auditId"] in self.buy_audits):
                            raise ValueError("Invalid buy audit ledger")
                        self.buy_audits[record["auditId"]] = record
            except (OSError, ValueError, TypeError):
                self.buy_audit_error = "BUY_AUDIT_LEDGER_INVALID"
        # A process restart never resumes a persisted request to trade.
        try:
            self._save_control(self.now_fn())
        except OSError:
            self.storage_error = self.storage_error or "CONTROL_STATE_WRITE_FAILED"
        self._revoke_preparation(self.now_fn(), "PROCESS_RESTARTED")

    @classmethod
    def _valid_preparation_record(cls, record, previous=None):
        if type(record) is not dict or type(record.get("schemaVersion")) is not int or record["schemaVersion"] not in (1, 2):
            return False
        version = record["schemaVersion"]
        intent_fields = PREPARATION_V2_INTENT_FIELDS if version == 2 else PREPARATION_INTENT_FIELDS
        if set(record) != (PREPARATION_V2_RECORD_FIELDS if version == 2 else PREPARATION_RECORD_FIELDS):
            return False
        start, created, updated = record["periodStart"], record["createdAt"], record["updatedAt"]
        if (type(start) is not int or start < 0 or start % 300 or record["id"] != f"future-btc5m-prepare:{start}"
                or record["slug"] != f"btc-updown-5m-{start}" or record["periodEnd"] != start + 300
                or record["mode"] != "PREPARE_ONLY" or record["noSubmission"] is not True
                or record["operatorAuthorized"] is not True or record["authorizationSource"] != "USER_REQUEST"
                or not finite_number(record["amountUsd"]) or record["amountUsd"] != 1
                or not finite_number(created) or not start + 60 <= created < start + 80
                or record["expiresAt"] != start + 80 or not finite_number(updated) or updated < created
                or record["priceSource"] != "chainlink" or record["openPriceSource"] != OPEN_PRICE_SOURCE
                or record["twapLookbackSeconds"] != 60 or not finite_number(record["priceObservedAt"])
                or not 0 <= created - record["priceObservedAt"] <= 5
                or not finite_number(record["openPrice"]) or record["openPrice"] <= 0
                or not finite_number(record["currentPrice"]) or record["currentPrice"] <= 0
                or record["side"] not in ("Up", "Down")):
            return False
        if version == 1:
            if record["side"] != ("Up" if record["currentPrice"] > record["openPrice"] else
                                   "Down" if record["currentPrice"] < record["openPrice"] else None):
                return False
        elif (record["selectionSource"] != "HIGHER_BUTTON_PRICE"
              or record["side"] != higher_button_side(record["upQuoteCents"], record["downQuoteCents"])
              or not finite_number(record["quoteObservedAt"]) or not 0 <= created - record["quoteObservedAt"] <= 5):
            return False
        token, claimed, receipt = record["claimToken"], record["claimedAt"], record["receipt"]
        if token is None:
            if claimed is not None:
                return False
        elif (not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{32}", token) is None
              or not finite_number(claimed) or not created <= claimed < record["expiresAt"] or updated < claimed):
            return False
        if receipt is not None:
            if (type(receipt) is not dict or set(receipt) != {"checkedAt", "marketUrl", "amountUsd", "selectedSide"}
                    or token is None or cls._market_url_start(receipt["marketUrl"]) != start
                    or not finite_number(receipt["checkedAt"]) or abs(updated - receipt["checkedAt"]) > 3
                    or receipt["checkedAt"] < claimed - 3
                    or receipt["amountUsd"] is not None and (not finite_number(receipt["amountUsd"]) or receipt["amountUsd"] < 0)
                    or receipt["selectedSide"] not in (None, "Up", "Down")):
                return False
        state, reason = record["state"], record["reason"]
        if state == "PENDING":
            valid = token is None and receipt is None and reason is None and updated == created
        elif state == "CLAIMED":
            valid = (token is not None and receipt is None and reason is None and updated == claimed
                     and 0 <= claimed - record["priceObservedAt"] <= 5
                     and (version == 1 or 0 <= claimed - record["quoteObservedAt"] <= 5))
        elif state == "READY":
            valid = (token is not None and reason is None and receipt is not None
                     and receipt["amountUsd"] == 1 and receipt["selectedSide"] == record["side"]
                     and start + 60 <= receipt["checkedAt"] < record["expiresAt"] and updated < record["expiresAt"]
                     and 0 <= updated - record["priceObservedAt"] <= 5
                     and (version == 1 or 0 <= updated - record["quoteObservedAt"] <= 5))
        elif state == "FAILED":
            valid = token is not None and receipt is not None and reason in PREPARATION_FAILURES
        elif state == "EXPIRED":
            valid = (updated >= record["expiresAt"] and (reason == "INTENT_EXPIRED"
                     or reason == "PREPARATION_RECEIPT_UNKNOWN" and token is not None and receipt is None))
        elif state == "REVOKED":
            valid = reason in ("PREPARATION_REVOKED", "PROCESS_RESTARTED") and receipt is None
        else:
            return False
        if not valid:
            return False
        if previous is None:
            return state == "PENDING"
        transitions = {"PENDING": {"CLAIMED", "EXPIRED", "REVOKED"}, "CLAIMED": {"READY", "FAILED", "EXPIRED", "REVOKED"}}
        return (state in transitions.get(previous["state"], set()) and updated >= previous["updatedAt"]
                and previous["schemaVersion"] == version
                and all(record[field] == previous[field] for field in intent_fields - {"claimToken"})
                and (previous["state"] == "PENDING" and state == "CLAIMED"
                     or token == previous["claimToken"] and claimed == previous["claimedAt"]))

    def _save_preparation(self, record):
        if self.preparation_error:
            raise OSError(self.preparation_error)
        previous = self.preparations.get(record["id"])
        if not self._valid_preparation_record(record, previous):
            raise ValueError("INVALID_PREPARATION_EVENT")
        try:
            ledger_path = self.state_dir / "preparations.jsonl"
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
        except OSError:
            self.preparation_error = "PREPARATION_LEDGER_WRITE_FAILED"
            raise
        self.preparations[record["id"]] = record
        self.last_preparation = record

    def _revoke_preparation(self, now, reason="PREPARATION_REVOKED"):
        record = self.last_preparation
        if not self.preparation_error and record and record["state"] in ("PENDING", "CLAIMED"):
            try:
                self._save_preparation({**record, "state": "REVOKED", "updatedAt": max(now, record["updatedAt"]), "reason": reason})
            except OSError:
                pass

    def _expire_preparation(self, now):
        record = self.last_preparation
        if not self.preparation_error and record and record["state"] in ("PENDING", "CLAIMED") and now >= record["expiresAt"]:
            reason = "INTENT_EXPIRED" if record["state"] == "PENDING" else "PREPARATION_RECEIPT_UNKNOWN"
            self._save_preparation({**record, "state": "EXPIRED", "updatedAt": now, "reason": reason})

    def _preparation_reasons(self, source, error, now):
        if self.preparation_error:
            return [self.preparation_error]
        if self.storage_error:
            return [self.storage_error]
        if self.preflight_error:
            return [self.preflight_error]
        if self._stopped(source):
            return ["STOP_FILE_PRESENT"]
        if error:
            return [error]
        if not self.requested_enabled:
            return ["AUTO_PREPARATION_DISABLED"]
        if not self._current_signal(source, now, allow_flat=True):
            return ["WAITING_CURRENT_SIGNAL"]
        report = self.browser_report
        if (not report or self.browser_received_at is None or not 0 <= now - self.browser_received_at <= 5
                or abs(now - report["checkedAt"]) > 5):
            return ["BROWSER_NOT_CONNECTED"]
        if report["navigation"] != "CURRENT" or report["pagePeriodStart"] != int(now // 300) * 300:
            return ["MARKET_NOT_CURRENT"]
        if report["ticketStatus"] != "PASS":
            return ["TICKET_CHECK_FAILED"]
        if (report["schemaVersion"] != 2 or report["upQuoteCents"] is None or report["downQuoteCents"] is None):
            return ["BUTTON_QUOTES_UNAVAILABLE"]
        if report["upQuoteCents"] == report["downQuoteCents"]:
            return ["BUTTON_QUOTES_TIED"]
        return []

    def _preparation_intent_reasons(self, record, now):
        if record["schemaVersion"] != 2:
            return ["BUTTON_QUOTES_UNAVAILABLE"]
        if not 0 <= now - record["quoteObservedAt"] <= 5:
            return ["BUTTON_QUOTES_NOT_FRESH"]
        if not 0 <= now - record["priceObservedAt"] <= 5:
            return ["WAITING_CURRENT_SIGNAL"]
        if higher_button_side(self.browser_report.get("upQuoteCents"), self.browser_report.get("downQuoteCents")) != record["side"]:
            return ["HIGHER_BUTTON_SIDE_CHANGED"]
        return []

    def _preparation_view(self, source, error, now):
        reasons = self._preparation_reasons(source, error, now)
        record = self.last_preparation
        if (not reasons and record and record["periodStart"] == int(now // 300) * 300
                and record["state"] in ("PENDING", "CLAIMED", "READY")):
            reasons = self._preparation_intent_reasons(record, now)
        intent = None
        if self.preparation_error or self.storage_error or self.preflight_error or error or self._stopped(source):
            state = "BLOCKED"
        elif not self.requested_enabled:
            state = "DISABLED"
        elif record and record["periodStart"] == int(now // 300) * 300:
            state = record["state"]
            if state in ("PENDING", "CLAIMED") and now >= record["expiresAt"]:
                state = "EXPIRED" if state == "PENDING" else "RECEIPT_UNKNOWN"
                reasons = ["INTENT_EXPIRED" if state == "EXPIRED" else "PREPARATION_RECEIPT_UNKNOWN"]
            elif state == "EXPIRED" and record["reason"] == "PREPARATION_RECEIPT_UNKNOWN":
                state, reasons = "RECEIPT_UNKNOWN", [record["reason"]]
            elif state in ("FAILED", "EXPIRED", "REVOKED"):
                reasons = [record["reason"]]
            elif state == "READY":
                if now >= record["expiresAt"]:
                    state, reasons = "EXPIRED", ["INTENT_EXPIRED"]
                elif reasons:
                    state = "WAITING_SIGNAL" if reasons == ["WAITING_CURRENT_SIGNAL"] else "WAITING_BROWSER"
                elif (self.browser_report["amountUsd"] != 1 or self.browser_report["selectedSide"] != record["side"]
                      or not self.browser_report["buyButtonEnabled"]):
                    state, reasons = "BLOCKED", ["PREPARED_TICKET_CHANGED"]
            elif reasons:
                state = "WAITING_SIGNAL" if reasons == ["WAITING_CURRENT_SIGNAL"] else "WAITING_BROWSER"
            else:
                intent = {field: copy.deepcopy(record[field]) for field in PREPARATION_V2_INTENT_FIELDS}
        else:
            state = "WAITING_SIGNAL" if reasons == ["WAITING_CURRENT_SIGNAL"] or not reasons else "WAITING_BROWSER"
        return {"mode": "PREPARE_ONLY", "noSubmission": True, "operatorAuthorized": True,
                "authorizationSource": "USER_REQUEST", "enabled": self.requested_enabled, "state": state,
                "intent": intent, "lastAttempt": copy.deepcopy(record), "reasons": reasons}

    def preparation(self):
        with self.lock:
            source, error = self._read_source()
            now = self.now_fn()
            self._disable_for_stop(source, now)
            return {"bridgeId": BRIDGE_ID, "serverTime": now, "preparation": self._preparation_view(source, error, now)}

    def claim_preparation(self, payload):
        if (type(payload) is not dict or set(payload) != {"schemaVersion", "id"}
                or type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1
                or not isinstance(payload["id"], str)):
            raise ValueError("INVALID_PREPARATION_CLAIM")
        with self.lock:
            source, error = self._read_source()
            now = self.now_fn()
            self._disable_for_stop(source, now)
            self._expire_preparation(now)
            record = self.last_preparation
            if (self._preparation_reasons(source, error, now) or not record or record["id"] != payload["id"]
                    or record["state"] != "PENDING" or record["periodStart"] != int(now // 300) * 300
                    or self._preparation_intent_reasons(record, now)):
                raise PreparationConflict("PREPARATION_NOT_CLAIMABLE")
            self._save_preparation({**record, "state": "CLAIMED", "updatedAt": now,
                                    "claimedAt": now, "claimToken": secrets.token_hex(16)})
            return self.preparation()

    def report_preparation(self, payload):
        if (type(payload) is not dict or set(payload) != PREPARATION_REPORT_FIELDS
                or type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1
                or not isinstance(payload["id"], str) or not isinstance(payload["claimToken"], str)
                or re.fullmatch(r"[0-9a-f]{32}", payload["claimToken"]) is None
                or payload["noSubmission"] is not True or not finite_number(payload["checkedAt"])
                or self._market_url_start(payload["marketUrl"]) is None
                or payload["amountUsd"] is not None and (not finite_number(payload["amountUsd"]) or payload["amountUsd"] < 0)
                or payload["selectedSide"] not in (None, "Up", "Down")
                or payload["status"] not in ("READY", "FAILED", "EXPIRED")
                or payload["reason"] is not None and not isinstance(payload["reason"], str)
                or payload["status"] == "READY" and payload["reason"] is not None
                or payload["status"] == "FAILED" and payload["reason"] not in PREPARATION_FAILURES
                or payload["status"] == "EXPIRED" and payload["reason"] != "INTENT_EXPIRED"):
            raise ValueError("INVALID_PREPARATION_REPORT")
        with self.lock:
            now = self.now_fn()
            source, error = self._read_source()
            self._disable_for_stop(source, now)
            self._expire_preparation(now)
            record = self.last_preparation
            if (not self.requested_enabled or self.preparation_error or self._stopped(source) or not record
                    or record["state"] != "CLAIMED" or record["id"] != payload["id"]
                    or record["schemaVersion"] != 2
                    or record["claimToken"] != payload["claimToken"]):
                raise PreparationConflict("PREPARATION_REPORT_NOT_CURRENT")
            if (abs(now - payload["checkedAt"]) > 3 or payload["checkedAt"] < record["claimedAt"] - 3
                    or self._market_url_start(payload["marketUrl"]) != record["periodStart"]):
                raise ValueError("INVALID_PREPARATION_REPORT_TIME_OR_MARKET")
            if payload["status"] == "EXPIRED" and now < record["expiresAt"]:
                raise ValueError("PREPARATION_NOT_EXPIRED")
            if payload["status"] == "READY":
                report = self.browser_report
                if (self._preparation_reasons(source, error, now) or payload["amountUsd"] != 1
                        or self._preparation_intent_reasons(record, now)
                        or self._preflight(source, error, now)["result"] != "READ_ONLY_READY"
                        or self.browser_received_at < record["claimedAt"]
                        or payload["selectedSide"] != record["side"]
                        or not record["periodStart"] + 60 <= payload["checkedAt"] < record["expiresAt"]
                        or report["amountUsd"] != 1 or report["selectedSide"] != record["side"]
                        or not report["buyButtonEnabled"]):
                    raise ValueError("PREPARATION_READY_NOT_CONFIRMED")
            receipt = {field: copy.deepcopy(payload[field]) for field in ("checkedAt", "marketUrl", "amountUsd", "selectedSide")}
            self._save_preparation({**record, "state": payload["status"], "updatedAt": now,
                                    "reason": payload["reason"], "receipt": receipt})
            return self.preparation()

    @staticmethod
    def _buy_audit_fields(value):
        # The exact key set for the audit's own schema version, or None for anything else.
        version = value.get("schemaVersion") if type(value) is dict else None
        return {1: BUY_AUDIT_FIELDS, 2: BUY_AUDIT_V2_FIELDS}.get(version) if type(version) is int else None

    @classmethod
    def _valid_buy_audit(cls, value):
        start = value.get("periodStart")
        quote_ok = lambda quote: quote is None or valid_button_quote(quote)
        return (type(value["schemaVersion"]) is int and value["schemaVersion"] in (1, 2)
                and type(start) is int and start >= 0 and start % 300 == 0
                and value["id"] == f"future-btc5m-prepare:{start}"
                and isinstance(value["claimToken"], str) and re.fullmatch(r"[0-9a-f]{32}", value["claimToken"]) is not None
                and value["side"] in ("Up", "Down") and finite_number(value["amountUsd"]) and value["amountUsd"] == 1
                and value["state"] in BUY_AUDIT_REASONS and value["reason"] in BUY_AUDIT_REASONS[value["state"]]
                and finite_number(value["armedAt"]) and finite_number(value["attemptedAt"])
                and value["armedAt"] <= value["attemptedAt"]
                and value["auditId"] == f"{value['id']}:{math.floor(value['attemptedAt'] * 1000)}"
                and cls._market_url_start(value["marketUrl"]) == start
                and quote_ok(value["upQuoteCents"]) and quote_ok(value["downQuoteCents"])
                and value["selectedSide"] in (None, "Up", "Down")
                and (value["ticketAmountUsd"] is None or finite_number(value["ticketAmountUsd"]) and value["ticketAmountUsd"] >= 0)
                and isinstance(value["extensionVersion"], str)
                and re.fullmatch(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}", value["extensionVersion"]) is not None
                and (value["schemaVersion"] == 1
                     or quote_ok(value["marketUpAskCents"]) and quote_ok(value["marketDownAskCents"])
                     and (value["marketQuoteObservedAt"] is None or finite_number(value["marketQuoteObservedAt"]))))

    def report_buy_attempt(self, payload):
        fields = self._buy_audit_fields(payload)
        if fields is None or set(payload) != fields or not self._valid_buy_audit(payload):
            raise ValueError("INVALID_BUY_AUDIT")
        with self.lock:
            if self.buy_audit_error:
                raise OSError(self.buy_audit_error)
            previous = self.buy_audits.get(payload["auditId"])
            if previous is not None:
                # The extension outbox resends until acknowledged; an identical resend is a no-op.
                # A resend under another schema version has another field set and is a reuse.
                if {field: value for field, value in previous.items() if field != "receivedAt"} != payload:
                    raise PreparationConflict("BUY_AUDIT_ID_REUSED")
                return {"bridgeId": BRIDGE_ID, "auditId": payload["auditId"], "stored": True, "duplicate": True}
            record = self.preparations.get(payload["id"])
            # Audits stay accepted after the switch is turned off or the round ends; they
            # only have to describe a READY preparation the bridge actually issued.
            if (not record or record["state"] != "READY" or record["claimToken"] != payload["claimToken"]
                    or record["periodStart"] != payload["periodStart"] or record["side"] != payload["side"]
                    or not record["createdAt"] - 3 <= payload["attemptedAt"] <= record["expiresAt"] + 5):
                raise PreparationConflict("BUY_AUDIT_NOT_BOUND_TO_READY")
            stored = {**copy.deepcopy(payload), "receivedAt": self.now_fn()}
            try:
                ledger_path = self.state_dir / "buy_attempts.jsonl"
                first_write = not ledger_path.exists()
                with ledger_path.open("a", encoding="utf-8") as ledger:
                    ledger.write(json.dumps(stored, ensure_ascii=False, allow_nan=False) + "\n")
                    ledger.flush()
                    os.fsync(ledger.fileno())
                if first_write:
                    descriptor = os.open(self.state_dir, os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
            except OSError:
                self.buy_audit_error = "BUY_AUDIT_LEDGER_WRITE_FAILED"
                raise
            self.buy_audits[payload["auditId"]] = stored
            return {"bridgeId": BRIDGE_ID, "auditId": payload["auditId"], "stored": True, "duplicate": False}

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
        if type(record) is not dict:
            return False
        legacy = set(record) == PREFLIGHT_PASS_FIELDS
        if not legacy and (set(record) != PREFLIGHT_V2_PASS_FIELDS or type(record["schemaVersion"]) is not int
                           or record["schemaVersion"] != 2 or record["selectionSource"] != "HIGHER_BUTTON_PRICE"
                           or record["preferredSide"] not in ("Up", "Down")
                           or record["preferredSide"] != higher_button_side(record["upQuoteCents"], record["downQuoteCents"])):
            return False
        start = record["periodStart"]
        return (type(start) is int and start >= 0 and start % 300 == 0
                and cls._market_url_start(record["marketUrl"]) == start
                and finite_number(record["checkedAt"]) and start + 60 <= record["checkedAt"] < start + 80
                and record["signalSide"] in (("Up", "Down") if legacy else ("Up", "Down", None))
                and finite_number(record["amountUsd"]) and record["amountUsd"] == 1
                and record["noSubmission"] is True)

    def report_preflight(self, payload):
        with self.lock:
            now = self.now_fn()
            if (type(payload) is not dict or type(payload.get("schemaVersion")) is not int
                    or payload["schemaVersion"] not in (1, 2)
                    or set(payload) != (PREFLIGHT_V2_FIELDS if payload["schemaVersion"] == 2 else PREFLIGHT_FIELDS)
                    or type(payload["pagePeriodStart"]) is not int
                    or self._market_url_start(payload["marketUrl"]) != payload["pagePeriodStart"]
                    or not finite_number(payload["checkedAt"]) or abs(now - payload["checkedAt"]) > 3
                    or payload["navigation"] not in ("CURRENT", "ENDED", "MISMATCH")
                    or payload["ticketStatus"] not in ("PASS", "FAIL")
                    or payload["amountUsd"] is not None and (not finite_number(payload["amountUsd"]) or payload["amountUsd"] < 0)
                    or payload["selectedSide"] not in ("Up", "Down", None)
                    or type(payload["buyButtonEnabled"]) is not bool):
                raise ValueError("INVALID_PREFLIGHT_REPORT")
            if payload["schemaVersion"] == 2 and any(payload[field] is not None and not valid_button_quote(payload[field])
                                                    for field in ("upQuoteCents", "downQuoteCents")):
                raise ValueError("INVALID_BUTTON_QUOTES")
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
        signal = self._current_signal(source, now, require_enabled=False, allow_flat=True) if not source_error and not self._stopped(source) else None
        up = report.get("upQuoteCents") if report else None
        down = report.get("downQuoteCents") if report else None
        preferred = higher_button_side(up, down)
        side_matches = bool(preferred and connected and report["selectedSide"] == preferred)
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
            if up is None or down is None:
                reasons.append("BUTTON_QUOTES_UNAVAILABLE")
            elif preferred is None:
                reasons.append("BUTTON_QUOTES_TIED")
            if not side_matches:
                reasons.append("SIDE_MISMATCH")
            if signal and not signal["period_start"] + 60 <= report["checkedAt"] < signal["period_start"] + 80:
                reasons.append("BROWSER_CHECK_OUTSIDE_ENTRY")
        if not signal:
            reasons.append("SIGNAL_NOT_FRESH")
        if not reasons and persist and signal["period_start"] not in self.preflight_seen:
            record = {"periodStart": signal["period_start"], "checkedAt": report["checkedAt"],
                      "marketUrl": report["marketUrl"], "signalSide": signal["side"],
                      "amountUsd": 1, "noSubmission": True, "schemaVersion": 2,
                      "selectionSource": "HIGHER_BUTTON_PRICE", "upQuoteCents": up, "downQuoteCents": down,
                      "preferredSide": preferred}
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
                "upQuoteCents": up, "downQuoteCents": down, "preferredSide": preferred,
                "selectionSource": "HIGHER_BUTTON_PRICE" if report and report["schemaVersion"] == 2 else None,
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
        if self._stopped(source):
            self._revoke_preparation(now)

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
            "preparation": self._preparation_view(source, source_error, now),
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
            if not enabled:
                self._revoke_preparation(now)
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

    def _current_signal(self, source, now, require_enabled=True, allow_flat=False):
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
                or "side" not in signal
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
        return signal if signal.get("side") == expected and (expected in ("Up", "Down") or allow_flat and expected is None) else None

    def observe(self):
        with self.lock:
            now = self.now_fn()
            source, error = self._read_source()
            self._disable_for_stop(source, now)
            try:
                self._expire_preparation(now)
            except OSError:
                pass
            signal = self._current_signal(source, now, allow_flat=True) if not self._preparation_reasons(source, error, now) else None
            if signal:
                start = signal["period_start"]
                id = f"future-btc5m-prepare:{start}"
                if id not in self.preparations and f"{BRIDGE_ID}:{start}" not in self.seen:
                    record = {
                        "schemaVersion": 2, "id": id, "slug": signal["slug"],
                        "periodStart": start, "periodEnd": start + 300,
                        "side": higher_button_side(self.browser_report["upQuoteCents"], self.browser_report["downQuoteCents"]),
                        "upQuoteCents": self.browser_report["upQuoteCents"], "downQuoteCents": self.browser_report["downQuoteCents"],
                        "quoteObservedAt": self.browser_received_at, "selectionSource": "HIGHER_BUTTON_PRICE",
                        "amountUsd": 1, "createdAt": now, "expiresAt": start + 80,
                        "priceObservedAt": signal["price_observed_at"], "openPrice": signal["open_price"],
                        "currentPrice": signal["current_price"], "priceSource": "chainlink", "openPriceSource": OPEN_PRICE_SOURCE,
                        "twapLookbackSeconds": 60, "mode": "PREPARE_ONLY", "noSubmission": True,
                        "operatorAuthorized": True, "authorizationSource": "USER_REQUEST", "claimToken": None,
                        "state": "PENDING", "updatedAt": now, "claimedAt": None, "reason": None, "receipt": None,
                    }
                    try:
                        self._save_preparation(record)
                    except OSError:
                        pass
            return self._status(source, error, now, persist_preflight=True)
