import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SCRIPT = Path(__file__).with_name("start-future-btc5m-tunnel.sh")
MOCK = r'''
import errno, json, os, socket, subprocess, sys, time
from pathlib import Path
root = Path(os.environ["FUTURE_TUNNEL_TEST_DIR"])
plan = json.loads((root / "plan.json").read_text())
trace = root / "trace.jsonl"
def record(kind, **fields):
    with trace.open("a") as output:
        output.write(json.dumps({"kind": kind, **fields}) + "\n")
def events():
    return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
command = Path(sys.argv[0]).name
args = sys.argv[1:]
path = root / "assistant.sock"
if command == "curl":
    record("curl", args=args)
    raise SystemExit(0 if plan.get("helperAvailable", True) else 22)
if command == "sleep":
    record("sleep", seconds=int(args[0]), pid=os.getpid())
    time.sleep(plan.get("sleepDelay", 0.02))
    raise SystemExit(0)
if "-N" not in args:
    number = sum(event["kind"] == "check" for event in events())
    if plan.get("checkHold"):
        record("check", args=args, code="hold", pid=os.getpid(), removed=False)
        while True:
            time.sleep(60)
    if number < plan.get("checkFailures", 0):
        record("check", args=args, code=255, removed=False)
        raise SystemExit(255)
    code = sys.stdin.read().replace("/opt/polyhermes/future-btc5m/assistant.sock", str(path))
    if plan.get("guardConnectErrno"):
        code = code.replace("connection.connect(path)",
                            "raise OSError(%s, 'fixture socket error')" % plan["guardConnectErrno"])
    if plan.get("changeDuringGuard"):
        code = code.replace("after = os.lstat(path)",
                            "os.rename(path, path + '.old')\nreplacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\nreplacement.bind(path)\nreplacement.close()\nafter = os.lstat(path)")
    existed = path.exists()
    remote_args = args[args.index("python3") + 2:]
    result = subprocess.run([sys.executable, "-", *remote_args], input=code, text=True)
    record("check", args=args, code=result.returncode, removed=existed and not path.exists())
    raise SystemExit(result.returncode)
number = sum(event["kind"] == "forward" for event in events())
codes = plan.get("forwardCodes", [0])
code = codes[min(number, len(codes) - 1)]
record("forward", args=args, pid=os.getpid(), code=code)
if not path.exists():
    bound = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    bound.bind(str(path))
    if code == "hold":
        bound.listen()
    else:
        bound.close()
if code == "hold":
    while True:
        time.sleep(60)
raise SystemExit(code)
'''


class FutureTunnelTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.socket_path = self.root / "assistant.sock"
        key = self.root / "fixture-key"
        key.write_text("test fixture only")
        source = SCRIPT.read_text().replace(
            'FUTURE_TUNNEL_KEY="$HOME/.ssh/polymtrade_vultr_ed25519"',
            f'FUTURE_TUNNEL_KEY="{key}"',
        )
        self.script = self.root / "tunnel.sh"
        self.script.write_text(source)
        for name in ("ssh", "curl", "sleep"):
            mock = self.root / name
            mock.write_text(f"#!{sys.executable}\n{MOCK}")
            mock.chmod(0o700)
        self.env = {**os.environ, "PATH": str(self.root) + os.pathsep + os.environ["PATH"],
                    "FUTURE_TUNNEL_TEST_DIR": str(self.root)}
        self.plan = {}

    def trace(self, kind=None):
        path = self.root / "trace.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [row for row in rows if row["kind"] == kind] if kind else rows

    def start(self, *args):
        (self.root / "plan.json").write_text(json.dumps(self.plan))
        process = subprocess.Popen(["bash", str(self.script), *args], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        self.addCleanup(self.stop, process)
        return process

    def stop(self, process):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=3)

    def run_tunnel(self, *args):
        process = self.start(*args)
        stdout, stderr = process.communicate(timeout=4)
        return process.returncode, stdout, stderr

    def wait_for(self, kind, count=1):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if len(self.trace(kind)) >= count:
                return self.trace(kind)[-1]
            time.sleep(0.01)
        self.fail(f"No {kind} event; trace={self.trace()}")

    def stale_socket(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.bind(str(self.socket_path))
        connection.close()

    def active_socket(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.bind(str(self.socket_path))
        connection.listen()
        self.addCleanup(connection.close)

    def test_disconnect_cleans_only_refused_socket_and_reconnects(self):
        self.plan["forwardCodes"] = [255, 0]
        code, _, stderr = self.run_tunnel()
        self.assertEqual(0, code, stderr)
        self.assertEqual(2, len(self.trace("forward")))
        self.assertEqual([5], [row["seconds"] for row in self.trace("sleep")])
        self.assertTrue(self.trace("check")[-1]["removed"])

    def test_backoff_is_capped_and_forward_is_still_private(self):
        self.plan["forwardCodes"] = [255] * 5 + [0]
        code, _, stderr = self.run_tunnel()
        self.assertEqual(0, code, stderr)
        self.assertEqual([5, 10, 20, 30, 30], [row["seconds"] for row in self.trace("sleep")])
        for row in self.trace("forward"):
            args = row["args"]
            for option in ("BatchMode=yes", "ConnectTimeout=10", "ControlMaster=no", "ControlPath=none",
                           "ExitOnForwardFailure=yes", "ServerAliveInterval=15", "ServerAliveCountMax=3",
                           "StreamLocalBindUnlink=no", "StreamLocalBindMask=0177"):
                self.assertIn(option, args)
            self.assertEqual("/opt/polyhermes/future-btc5m/assistant.sock:127.0.0.1:8766", args[args.index("-R") + 1])
            self.assertEqual("root@66.135.16.16", args[-1])
            self.assertNotIn("-f", args)
        for row in self.trace("check"):
            for option in ("ControlMaster=no", "ControlPath=none", "ServerAliveInterval=15", "ServerAliveCountMax=3"):
                self.assertIn(option, row["args"])

    def test_default_first_start_preserves_existing_stale_socket(self):
        self.stale_socket()
        inode = self.socket_path.lstat().st_ino
        code, _, _ = self.run_tunnel()
        self.assertNotEqual(0, code)
        self.assertEqual([], self.trace("forward"))
        self.assertEqual(inode, self.socket_path.lstat().st_ino)

    def test_explicit_first_recovery_removes_confirmed_stale_socket(self):
        self.stale_socket()
        code, _, stderr = self.run_tunnel("--remove-stale-socket")
        self.assertEqual(0, code, stderr)
        self.assertTrue(self.trace("check")[0]["removed"])
        self.assertEqual(1, len(self.trace("forward")))

    def test_active_socket_is_never_replaced(self):
        self.active_socket()
        inode = self.socket_path.lstat().st_ino
        code, _, stderr = self.run_tunnel("--remove-stale-socket")
        self.assertNotEqual(0, code)
        self.assertIn("active", stderr)
        self.assertEqual([], self.trace("forward"))
        self.assertEqual(inode, self.socket_path.lstat().st_ino)

    def test_active_socket_after_disconnect_stops_recovery(self):
        self.plan.update(forwardCodes=[255, 0], sleepDelay=0.4)
        process = self.start()
        self.wait_for("sleep")
        self.socket_path.unlink()
        self.active_socket()
        inode = self.socket_path.lstat().st_ino
        _, stderr = process.communicate(timeout=3)
        self.assertNotEqual(0, process.returncode)
        self.assertIn("active", stderr)
        self.assertEqual(1, len(self.trace("forward")))
        self.assertEqual(inode, self.socket_path.lstat().st_ino)

    def test_other_socket_errors_stop_without_removal(self):
        self.stale_socket()
        self.plan["guardConnectErrno"] = 13
        inode = self.socket_path.lstat().st_ino
        code, _, stderr = self.run_tunnel("--remove-stale-socket")
        self.assertNotEqual(0, code)
        self.assertIn("not confirmed stale", stderr)
        self.assertEqual(inode, self.socket_path.lstat().st_ino)
        self.assertEqual([], self.trace("forward"))

    def test_inode_change_stops_without_removing_replacement(self):
        self.stale_socket()
        self.plan["changeDuringGuard"] = True
        code, _, stderr = self.run_tunnel("--remove-stale-socket")
        self.assertNotEqual(0, code)
        self.assertIn("changed during inspection", stderr)
        self.assertTrue(self.socket_path.exists())
        self.assertEqual([], self.trace("forward"))

    def test_non_socket_path_is_never_removed(self):
        self.socket_path.write_text("preserve fixture")
        code, _, stderr = self.run_tunnel("--remove-stale-socket")
        self.assertNotEqual(0, code)
        self.assertIn("not a Unix socket", stderr)
        self.assertEqual("preserve fixture", self.socket_path.read_text())

    def test_symlink_to_socket_is_never_removed(self):
        self.stale_socket()
        target = self.root / "target.sock"
        self.socket_path.rename(target)
        self.socket_path.symlink_to(target)
        code, _, stderr = self.run_tunnel("--remove-stale-socket")
        self.assertNotEqual(0, code)
        self.assertIn("not a Unix socket", stderr)
        self.assertTrue(self.socket_path.is_symlink())
        self.assertTrue(target.exists())

    def test_symlink_after_disconnect_stops_recovery(self):
        self.plan.update(forwardCodes=[255, 0], sleepDelay=0.4)
        process = self.start()
        self.wait_for("sleep")
        target = self.root / "target.sock"
        self.socket_path.rename(target)
        self.socket_path.symlink_to(target)
        _, stderr = process.communicate(timeout=3)
        self.assertNotEqual(0, process.returncode)
        self.assertIn("not a Unix socket", stderr)
        self.assertEqual(1, len(self.trace("forward")))
        self.assertTrue(self.socket_path.is_symlink())
        self.assertTrue(target.exists())

    def test_helper_unavailable_is_fail_fast(self):
        self.plan["helperAvailable"] = False
        code, _, stderr = self.run_tunnel()
        self.assertNotEqual(0, code)
        self.assertIn("Local Future assistant is unavailable", stderr)
        self.assertEqual([], self.trace("forward"))
        self.assertEqual([], self.trace("check"))

    def test_check_transport_retry_does_not_enable_first_cleanup(self):
        self.stale_socket()
        self.plan["checkFailures"] = 1
        inode = self.socket_path.lstat().st_ino
        code, _, _ = self.run_tunnel()
        self.assertNotEqual(0, code)
        self.assertEqual([5], [row["seconds"] for row in self.trace("sleep")])
        self.assertEqual(inode, self.socket_path.lstat().st_ino)
        self.assertEqual([], self.trace("forward"))

    def test_normal_ssh_exit_completes_without_retry(self):
        code, _, stderr = self.run_tunnel()
        self.assertEqual(0, code, stderr)
        self.assertEqual(1, len(self.trace("forward")))
        self.assertEqual([], self.trace("sleep"))

    def test_other_ssh_exit_does_not_retry(self):
        self.plan["forwardCodes"] = [1]
        code, _, _ = self.run_tunnel()
        self.assertEqual(1, code)
        self.assertEqual(1, len(self.trace("forward")))
        self.assertEqual([], self.trace("sleep"))

    def test_int_and_term_stop_child_without_reconnect(self):
        for stop_signal, expected in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
            with self.subTest(signal=stop_signal):
                trace = self.root / "trace.jsonl"
                trace.unlink(missing_ok=True)
                self.socket_path.unlink(missing_ok=True)
                self.plan["forwardCodes"] = ["hold"]
                process = self.start()
                row = self.wait_for("forward")
                os.kill(process.pid, stop_signal)
                process.communicate(timeout=3)
                self.assertEqual(expected, process.returncode)
                self.assertEqual(1, len(self.trace("forward")))
                self.assertEqual([], self.trace("sleep"))
                with self.assertRaises(ProcessLookupError):
                    os.kill(row["pid"], 0)

    def test_term_during_backoff_does_not_retry(self):
        self.plan.update(forwardCodes=[255, 0], sleepDelay=60)
        process = self.start()
        row = self.wait_for("sleep")
        os.kill(process.pid, signal.SIGTERM)
        process.communicate(timeout=3)
        self.assertEqual(143, process.returncode)
        self.assertEqual(1, len(self.trace("forward")))
        with self.assertRaises(ProcessLookupError):
            os.kill(row["pid"], 0)

    def test_term_during_socket_check_stops_child_without_forwarding(self):
        self.plan["checkHold"] = True
        process = self.start()
        row = self.wait_for("check")
        os.kill(process.pid, signal.SIGTERM)
        process.communicate(timeout=3)
        self.assertEqual(143, process.returncode)
        self.assertEqual([], self.trace("forward"))
        self.assertEqual([], self.trace("sleep"))
        with self.assertRaises(ProcessLookupError):
            os.kill(row["pid"], 0)


if __name__ == "__main__":
    unittest.main()
