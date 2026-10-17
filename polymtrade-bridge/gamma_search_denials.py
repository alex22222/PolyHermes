"""Stop automatically repeating exact title searches explicitly denied by Gamma."""
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


class GammaSearchDenials:
    def __init__(self, path):
        self.path = Path(path)
        self.entries = {}
        self.unavailable = False
        try:
            saved = json.loads(self.path.read_text())
            if not isinstance(saved, dict) or any(
                len(key) != 64 or any(c not in "0123456789abcdef" for c in key)
                or entry["status"] != 403 or not isinstance(entry["observed_at"], (int, float))
                for key, entry in saved.items()
            ):
                raise ValueError("Invalid search denial state")
            self.entries = saved
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            self.unavailable = True
            logger.error("Gamma search denial state unreadable; title searches quarantined, authentication unchanged")

    @staticmethod
    def applies(url):
        parsed = urlsplit(url)
        return parsed.hostname == "gamma-api.polymarket.com" and parsed.path == "/public-search"

    @staticmethod
    def key(url, params):
        identity = [url, sorted((str(k), str(v)) for k, v in params.items())]
        return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()

    def check(self, url, params):
        if self.applies(url) and (self.unavailable or self.key(url, params) in self.entries):
            raise RuntimeError("Gamma title search quarantined after HTTP 403; provider review required")

    def record(self, url, params, status):
        if status != 403 or not self.applies(url):
            return
        self.entries[self.key(url, params)] = {"status": 403, "observed_at": time.time()}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            with temporary.open("w") as output:
                os.chmod(temporary, 0o600)
                json.dump(self.entries, output)
            temporary.replace(self.path)
        except OSError:
            self.unavailable = True
            logger.exception("Could not persist denied search; title searches remain quarantined")
