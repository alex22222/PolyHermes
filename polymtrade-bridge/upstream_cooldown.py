"""Host-scoped denial cooldowns; persists only status and retry timestamps."""
import json
import logging
import os
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
                host: {"status": int(entry["status"]), "retry_at": float(entry["retry_at"]), "failures": int(entry["failures"])}
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

    def record(self, url, status, headers=None):
        host = urlsplit(url).hostname
        if not host:
            return
        if status not in (401, 403, 429):
            # A response already in flight before a denial cannot cancel it.
            if 200 <= status < 400 and host in self.entries and time.time() >= self.entries[host]["retry_at"]:
                self.entries.pop(host)
                self._save()
            return
        failures = min(self.entries.get(host, {}).get("failures", 0) + 1, 8)
        delay = min(1800 * 2 ** (failures - 1), 21600) if status == 403 else 300
        try:
            delay = max(delay, float((headers or {}).get("retry-after", "0")))
        except (ValueError, TypeError):
            pass
        self.entries[host] = {"status": status, "retry_at": time.time() + delay, "failures": failures}
        self._save()
        logger.warning("Upstream %s HTTP %s; all host requests deferred for %.0fs", host, status, delay)

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
