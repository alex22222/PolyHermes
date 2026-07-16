import subprocess
import tempfile
import unittest
import os
from pathlib import Path


class TestSupervisorHealthPolicy(unittest.TestCase):
    def test_restart_requires_three_consecutive_failures(self):
        helper = Path(__file__).with_name("supervisor_health.sh")
        script = f"""
set -e
source {helper}
HEALTH_FAILURE_THRESHOLD=3
HEALTH_FAILURES=0
record_health_probe failure
health_restart_required && exit 11
record_health_probe failure
health_restart_required && exit 12
record_health_probe success
[[ "$HEALTH_FAILURES" -eq 0 ]]
record_health_probe failure
record_health_probe failure
record_health_probe failure
health_restart_required
"""

        result = subprocess.run(
            ["/bin/bash", "-c", script],
            capture_output=True,
            text=True,
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_health_probe_events_are_persisted_for_stability_audit(self):
        helper = Path(__file__).with_name("supervisor_health.sh")
        with tempfile.TemporaryDirectory() as tmp:
            event_log = Path(tmp) / "health.jsonl"
            script = f"""
set -e
source {helper}
BRIDGE_HEALTH_EVENT_LOG={event_log}
BRIDGE_CODE_SHA=abc123
BRIDGE_CODE_FINGERPRINT=fingerprint123
HEALTH_FAILURE_THRESHOLD=3
HEALTH_FAILURES=0
record_health_event service_start
record_health_probe failure
record_health_probe success
"""
            result = subprocess.run(
                ["/bin/bash", "-c", script],
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            content = event_log.read_text(encoding="utf-8")
            self.assertIn('"event":"service_start"', content)
            self.assertIn('"code_sha":"abc123"', content)
            self.assertIn('"code_fingerprint":"fingerprint123"', content)
            self.assertIn('"event":"probe_failure"', content)
            self.assertIn('"event":"probe_recovered"', content)

    def test_safe_restart_drains_admission_before_execute_restart(self):
        helper = Path(__file__).with_name("safe_restart_bridge.sh")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            state_file = tmp_path / "state"
            launch_marker = tmp_path / "launchctl_called"

            curl = bin_dir / "curl"
            curl.write_text(
                """#!/bin/bash
set -e
url="${@: -1}"
if [[ "$url" == *"/health" ]]; then
    exit 0
fi
if [[ "$url" == *"/admin/drain"* ]]; then
    echo drained > "$FAKE_BRIDGE_STATE"
    exit 0
fi
if [[ "$url" == *"/metrics" ]]; then
    if [[ -f "$FAKE_BRIDGE_STATE" ]]; then
        echo '{"metrics":{"signals_received":15,"signal_queue_depth":0,"accepting_signals":false}}'
    else
        echo '{"metrics":{"signals_received":1,"signal_queue_depth":0,"accepting_signals":true}}'
    fi
    exit 0
fi
exit 1
""",
                encoding="utf-8",
            )
            curl.chmod(0o755)

            launchctl = bin_dir / "launchctl"
            launchctl.write_text(
                """#!/bin/bash
echo launchctl > "$FAKE_LAUNCH_MARKER"
exit 0
""",
                encoding="utf-8",
            )
            launchctl.chmod(0o755)

            env = {
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                "FAKE_BRIDGE_STATE": str(state_file),
                "FAKE_LAUNCH_MARKER": str(launch_marker),
                "BRIDGE_RESTART_DRAIN_TIMEOUT": "2",
                "BRIDGE_RESTART_POST_START_TIMEOUT": "2",
                "BRIDGE_RESTART_QUIET_SECONDS": "999",
            }

            result = subprocess.run(
                ["/bin/bash", str(helper), "--execute"],
                cwd=helper.parent,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(state_file.exists())
            self.assertTrue(launch_marker.exists())

    def test_safe_restart_retries_metrics_after_health_recovers(self):
        helper = Path(__file__).with_name("safe_restart_bridge.sh")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            state_file = tmp_path / "state"
            launch_marker = tmp_path / "launchctl_called"
            metrics_failed = tmp_path / "metrics_failed"

            curl = bin_dir / "curl"
            curl.write_text(
                """#!/bin/bash
set -e
url="${@: -1}"
if [[ "$url" == *"/health" ]]; then
    exit 0
fi
if [[ "$url" == *"/admin/drain"* ]]; then
    echo drained > "$FAKE_BRIDGE_STATE"
    exit 0
fi
if [[ "$url" == *"/metrics" ]]; then
    if [[ -f "$FAKE_LAUNCH_MARKER" && ! -f "$FAKE_METRICS_FAILED" ]]; then
        echo failed > "$FAKE_METRICS_FAILED"
        exit 7
    fi
    if [[ -f "$FAKE_BRIDGE_STATE" ]]; then
        echo '{"metrics":{"signals_received":15,"signal_queue_depth":0,"accepting_signals":false}}'
    else
        echo '{"metrics":{"signals_received":1,"signal_queue_depth":0,"accepting_signals":true}}'
    fi
    exit 0
fi
exit 1
""",
                encoding="utf-8",
            )
            curl.chmod(0o755)

            launchctl = bin_dir / "launchctl"
            launchctl.write_text(
                """#!/bin/bash
echo launchctl > "$FAKE_LAUNCH_MARKER"
exit 0
""",
                encoding="utf-8",
            )
            launchctl.chmod(0o755)

            env = {
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                "FAKE_BRIDGE_STATE": str(state_file),
                "FAKE_LAUNCH_MARKER": str(launch_marker),
                "FAKE_METRICS_FAILED": str(metrics_failed),
                "BRIDGE_RESTART_DRAIN_TIMEOUT": "2",
                "BRIDGE_RESTART_POST_START_TIMEOUT": "5",
                "BRIDGE_RESTART_QUIET_SECONDS": "999",
            }

            result = subprocess.run(
                ["/bin/bash", str(helper), "--execute"],
                cwd=helper.parent,
                env=env,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(metrics_failed.exists())
            self.assertTrue(launch_marker.exists())
            self.assertIn("Admission drained", result.stdout)


if __name__ == "__main__":
    unittest.main()
