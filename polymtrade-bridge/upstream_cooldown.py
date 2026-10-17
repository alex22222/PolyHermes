"""Host-scoped denial cooldowns; persists only status and retry timestamps."""
import json
import logging
import math
import os
from email.utils import parsedate_to_datetime
from pathlib import Path
import time
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class UpstreamAccessDeferred(RuntimeError):
    def __init__(self, host, status, retry_at):
        self.status = status
        self.retry_at = retry_at
        super().__init__(f"Upstream {host} HTTP {status}; cooldown until {retry_at:.0f}")


class UpstreamCooldown:
    def __init__(self, path):
        self.path = Path(path)
        self.entries = {}
        try:
            saved = json.loads(self.path.read_text())
            self.entries = {
                host: {"status": int(entry["status"]), "retry_at": float(entry["retry_at"]), "failures": int(entry["failures"]),
                       **({"last_denied_at": float(entry.get("last_denied_at", entry["retry_at"]))} if entry["status"] == 429 else {}),
                       **({"denied_path": str(entry["denied_path"])[:160] or "/"} if "denied_path" in entry else {}),
                       **({key: float(entry[key]) for key in ("provider_retry_at", "challenge_completed_at") if key in entry}),
                       **({"mitigation": entry["mitigation"]} if entry.get("mitigation") in ("challenge", "deny") else {})}
                for host, entry in saved.items() if entry["status"] in (401, 403, 429)
            }
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            logger.warning("Could not load upstream cooldown state; no authentication data was changed")

    def check(self, url):
        host = urlsplit(url).hostname
        entry = self.entries.get(host)
        if entry and time.time() < entry["retry_at"]:
            raise UpstreamAccessDeferred(host, entry["status"], entry["retry_at"])

    def navigation_interval(self, url):
        entry = self.entries.get(urlsplit(url).hostname, {})
        if entry.get("challenge_completed_at", 0) >= entry.get("last_denied_at", 1):
            return 10.0
        if entry.get("status") == 429 and time.time() - entry.get("last_denied_at", entry["retry_at"]) < 3600:
            return 30.0
        return 10.0

    def complete_challenge(self, url, proof):
        """Accept only a later official main-document success, never a bypass."""
        host = urlsplit(url).hostname
        entry = self.entries.get(host, {})
        now = time.time()
        if entry.get("status") != 429 or entry.get("mitigation") != "challenge":
            return False
        if ("provider_retry_at" not in entry or not math.isfinite(entry["provider_retry_at"])
                or entry["provider_retry_at"] < 0 or now < entry["provider_retry_at"]):
            return False
        try:
            target, received = urlsplit(url), urlsplit(proof["url"])
            same_target = (target.scheme, target.netloc, target.path or "/", target.query) == (received.scheme, received.netloc, received.path or "/", received.query)
            started = float(proof["started_at"])
            valid = (same_target and entry.get("denied_path") == (target.path or "/")
                     and proof.get("status") == 200 and proof.get("main_frame") is True
                     and proof.get("from_service_worker") is False and proof.get("transfer_size", 0) > 0
                     and proof.get("denied_at") == entry.get("last_denied_at")
                     and math.isfinite(started) and entry["last_denied_at"] < started <= now
                     and now - started < 3600)
        except (KeyError, TypeError, ValueError):
            return False
        if not valid:
            return False
        self.entries[host] = {**entry, "retry_at": now, "challenge_completed_at": started}
        self._save()
        logger.info("Official browser challenge completed for %s; later same-document network HTTP 200 verified", host)
        return True

    def record(self, url, status, headers=None):
        host = urlsplit(url).hostname
        if not host:
            return
        if status not in (401, 403, 429):
            # A response already in flight before a denial cannot cancel it.
            if 200 <= status < 400 and host in self.entries and time.time() >= self.entries[host]["retry_at"]:
                previous = self.entries[host]
                if previous["status"] == 429 and time.time() - previous.get("last_denied_at", previous["retry_at"]) < 21600:
                    return
                if previous.get("denied_path") and previous["denied_path"] != urlsplit(url).path:
                    return
                self.entries.pop(host)
                self._save()
            return
        now = time.time()
        previous = self.entries.get(host, {})
        active = now < previous.get("retry_at", 0)
        # Time spent blocked is not evidence of recovery. Only a successful
        # response after the quiet period can retire persistent denial history.
        failures = previous["failures"] if active else min(
            (previous.get("failures", 0) if previous.get("status") == status else 0) + 1, 8,
        )
        if active:
            retry_at = previous["retry_at"]
            # Concurrent responses belong to the same denial, not new probes.
            if status == 403 and previous["status"] != 403:
                retry_at = max(retry_at, now + 1800)
            if previous["status"] == 403:
                status = 403
        else:
            delay = (min(1800 * 2 ** (failures - 1), 21600) if status == 403 else
                     min(300 * 2 ** (failures - 1), 21600) if status == 429 else 300)
            retry_at = now + delay
        mitigation = next((str(value).lower() for key, value in (headers or {}).items()
                           if str(key).lower() == "x-vercel-mitigated"), "")
        if mitigation in ("challenge", "deny"):
            retry_at = max(retry_at, now + 21600)
        retry_after = next((value for key, value in (headers or {}).items()
                            if str(key).lower() == "retry-after"), "0")
        try:
            delay = float(retry_after)
        except (ValueError, TypeError):
            try:
                delay = parsedate_to_datetime(retry_after).timestamp() - now
            except (ValueError, TypeError, OverflowError, AttributeError):
                delay = 0
        if math.isfinite(delay):
            retry_at = max(retry_at, now + delay)
        entry = {"status": status, "retry_at": retry_at, "failures": failures}
        if status == 429:
            entry["last_denied_at"] = previous.get("last_denied_at", previous.get("retry_at", now)) if active else now
            path = urlsplit(url).path[:160] or "/"
            entry["denied_path"] = previous.get("denied_path", path) if active else path
            entry["provider_retry_at"] = max(previous.get("provider_retry_at", 0) if active else 0,
                                               now + delay if math.isfinite(delay) and delay > 0 else 0)
        if mitigation in ("challenge", "deny") or (active and previous.get("mitigation") in ("challenge", "deny")):
            entry["mitigation"] = mitigation if mitigation in ("challenge", "deny") else previous["mitigation"]
        if entry == previous:
            return
        self.entries[host] = entry
        self._save()
        logger.warning("Upstream %s HTTP %s; all host requests deferred for %.0fs", host, status, retry_at - now)

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            with temporary.open("w") as output:
                os.chmod(temporary, 0o600)
                json.dump(self.entries, output)
            temporary.replace(self.path)
        except OSError:
            logger.exception("Could not persist upstream cooldown; in-process protection remains active")
