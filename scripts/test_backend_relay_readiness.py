import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("deploy-backend-vps.sh")


class BackendRelayReadinessTest(unittest.TestCase):
    def function(self, name):
        match = re.search(r"^" + name + r"\(\) \{\n(.*?)^\}", SCRIPT.read_text(), re.M | re.S)
        self.assertIsNotNone(match, name + " must provide a shared readiness gate")
        return match.group(0)

    def run_gate(self, relay_exit, rollback=False):
        gate = self.function("wait_for_services")
        if rollback:
            gate += "\n" + self.function("rollback")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = {
                "ssh": '#!/bin/bash\nexec /bin/bash -c "$1"\n',
                "docker": '#!/bin/bash\nprintf "docker %s\\n" "$*" >> "$PROBE_LOG"\nif [ "$1" = inspect ]; then echo healthy; fi\n',
                "curl": '#!/bin/bash\necho 200\n',
                "python3": '#!/bin/bash\nprintf "guard %s\\n" "$*" >> "$PROBE_LOG"\nexit "$GUARD_EXIT"\n',
                "seq": '#!/bin/bash\necho 1\n',
                "sleep": '#!/bin/bash\nexit 0\n',
            }
            for name, source in scripts.items():
                path = root / name
                path.write_text(source)
                path.chmod(0o700)
            env = {**os.environ, "PATH": str(root) + ":/usr/bin:/bin", "GUARD_EXIT": str(relay_exit),
                   "PROBE_LOG": str(root / "calls")}
            source = ('set -euo pipefail\nSSH=("' + str(root / "ssh") + '")\n'
                      'APP_CONTAINER=fixture\nPROD_DIR=/fixture\nBACKUP_JAR=/fixture/backup.jar\n' + gate +
                      "\n" + ("rollback" if rollback else "wait_for_services"))
            result = subprocess.run(["/bin/bash", "-c", source], env=env, text=True, capture_output=True, timeout=5)
            calls = (root / "calls").read_text() if (root / "calls").exists() else ""
            return result, calls

    def test_healthy_backend_is_not_ready_while_relay_is_disconnected(self):
        result, calls = self.run_gate(1)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("--future-relay-only", calls)

    def test_ready_backend_and_relay_pass(self):
        result, calls = self.run_gate(0)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("--future-relay-only", calls)

    def test_rollback_rechecks_relay_and_propagates_failure(self):
        result, calls = self.run_gate(1, rollback=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("docker restart fixture", calls)
        self.assertIn("--future-relay-only", calls)


if __name__ == "__main__":
    unittest.main()
