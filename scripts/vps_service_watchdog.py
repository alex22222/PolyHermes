#!/usr/bin/env python3
"""Monitor the production Docker stack and notify Feishu on incidents."""

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


class Config:
    def __init__(
        self,
        state_file=Path("/var/lib/polyhermes-watchdog/state.json"),
        failure_threshold=3,
        reminder_seconds=1800,
        auto_restart_app=True,
    ):
        self.state_file = Path(state_file)
        self.failure_threshold = failure_threshold
        self.reminder_seconds = reminder_seconds
        self.auto_restart_app = auto_restart_app
        self.public_url = os.getenv(
            "POLYHERMES_PUBLIC_URL",
            "https://polyhermes.66-135-16-16.sslip.io/",
        )
        self.backend_url = os.getenv("POLYHERMES_BACKEND_URL", "http://127.0.0.1:8088")
        self.bridge_url = os.getenv("POLYHERMES_BRIDGE_URL", "http://127.0.0.1:8080")
        self.request_timeout = float(os.getenv("WATCHDOG_REQUEST_TIMEOUT", "8"))
        self.app_memory_warning_percent = float(
            os.getenv("WATCHDOG_APP_MEMORY_WARNING_PERCENT", "75")
        )

    @classmethod
    def from_env(cls):
        return cls(
            state_file=Path(
                os.getenv(
                    "WATCHDOG_STATE_FILE",
                    "/var/lib/polyhermes-watchdog/state.json",
                )
            ),
            failure_threshold=int(os.getenv("WATCHDOG_FAILURE_THRESHOLD", "3")),
            reminder_seconds=int(os.getenv("WATCHDOG_REMINDER_SECONDS", "1800")),
            auto_restart_app=os.getenv("WATCHDOG_AUTO_RESTART_APP", "true").lower()
            == "true",
        )


class FeishuNotifier:
    def __init__(
        self,
        webhook_url=None,
        app_id=None,
        app_secret=None,
        receive_id=None,
        timeout=8,
    ):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
        self.app_id = app_id or os.getenv("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.getenv("FEISHU_APP_SECRET", "")
        self.receive_id = receive_id or os.getenv("FEISHU_RECEIVE_ID", "")
        self.timeout = timeout

    def send(self, title, message):
        text = f"{title}\n{message}"
        if self.webhook_url:
            return self._send_webhook(text)
        if self.app_id and self.app_secret and self.receive_id:
            return self._send_as_app(text)
        print("Feishu alert was not sent: webhook or app credentials are not configured")
        return False

    def _send_webhook(self, text):
        payload = {
            "msg_type": "text",
            "content": {"text": text},
        }
        response = self._request_json(self.webhook_url, payload)
        return self._is_success(response)

    def _send_as_app(self, text):
        token_response = self._request_json(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret},
        )
        token = token_response.get("tenant_access_token")
        if token_response.get("code") != 0 or not token:
            print(f"Feishu tenant token failed: {token_response}")
            return False

        receive_id_type = "chat_id" if self.receive_id.startswith("oc_") else "open_id"
        url = (
            "https://open.feishu.cn/open-apis/im/v1/messages"
            f"?receive_id_type={receive_id_type}"
        )
        response = self._request_json(
            url,
            {
                "receive_id": self.receive_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        return self._is_success(response)

    def _request_json(self, url, payload, headers=None):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                **(headers or {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw)
            except ValueError:
                body = {"code": -1, "msg": raw or str(exc)}
            print(f"Feishu HTTP {exc.code}: {body}")
            return body
        except (OSError, ValueError, urllib.error.URLError) as exc:
            print(f"Feishu alert failed: {exc}")
            return {"code": -1, "msg": str(exc)}

    @staticmethod
    def _is_success(response):
        response_code = response.get("code", response.get("StatusCode"))
        success = response_code == 0
        if not success:
            print(f"Feishu rejected alert: {response}")
        return success


class Watchdog:
    APP_ISSUE_PREFIXES = (
        "app_container:",
        "app_health:",
        "app_memory:",
        "app_oom:",
        "backend_actuator:",
        "backend_business:",
        "public_site:",
    )

    def __init__(
        self,
        config,
        notifier,
        issue_collector=None,
        app_diagnostics=None,
        app_restarter=None,
        now=None,
    ):
        self.config = config
        self.notifier = notifier
        self.issue_collector = issue_collector or self.collect_issues
        self.app_diagnostics = app_diagnostics or self.capture_app_diagnostics
        self.app_restarter = app_restarter or self.restart_app
        self.now = now or (lambda: int(time.time()))

    def run_once(self):
        state = self._load_state()
        issues = self.issue_collector()
        now = self.now()

        if not issues:
            if state.get("incident"):
                duration = max(0, now - int(state.get("incident_started_at", now)))
                sent = self.notifier.send(
                    "✅ PolyHermes 服务已恢复",
                    f"主机: {socket.gethostname()}\n中断持续: {duration} 秒\n所有健康检查已通过。",
                )
                if not sent:
                    print("PolyHermes watchdog: recovery alert failed; incident state cleared")
            self._save_state({"failures": 0, "incident": False})
            print("PolyHermes watchdog: healthy")
            return True

        failures = int(state.get("failures", 0)) + 1
        state["failures"] = failures
        state["last_issues"] = issues
        print(f"PolyHermes watchdog: failure {failures}/{self.config.failure_threshold}: {issues}")

        if failures < self.config.failure_threshold:
            self._save_state(state)
            return False

        app_issue = any(issue.startswith(self.APP_ISSUE_PREFIXES) for issue in issues)
        action = ""
        if app_issue and self.config.auto_restart_app and not state.get("incident"):
            self.app_diagnostics()
            restarted = self.app_restarter()
            action = "已自动重启主应用 polyhermes。" if restarted else "自动重启主应用失败。"
        elif any(issue.startswith("bridge_") for issue in issues):
            action = "未自动重启 Bridge，以保护浏览器登录态和正在执行的交易。"

        should_alert = not state.get("incident") or (
            now - int(state.get("last_alert_at", 0)) >= self.config.reminder_seconds
        )
        state["incident"] = True
        state.setdefault("incident_started_at", now)
        if should_alert:
            details = "\n".join(f"- {issue}" for issue in issues)
            sent = self.notifier.send(
                "🚨 PolyHermes 服务不可用",
                f"主机: {socket.gethostname()}\n连续失败: {failures} 次\n{details}\n{action}".rstrip(),
            )
            if sent:
                state["last_alert_at"] = now

        self._save_state(state)
        return False

    def collect_issues(self):
        issues = []
        self._check_container("polyhermes", require_health=True, issue_prefix="app", issues=issues)
        self._check_container("polyhermes-mysql", require_health=True, issue_prefix="mysql", issues=issues)
        self._check_container("polymtrade-bridge", require_health=False, issue_prefix="bridge", issues=issues)

        self._check_json(
            f"{self.config.backend_url}/api/auth/check-first-use",
            "backend_business",
            lambda body: body.get("code") == 0,
            issues,
            method="POST",
        )
        self._check_http(self.config.public_url, "public_site", issues)
        self._check_json(
            f"{self.config.bridge_url}/health",
            "bridge_health",
            lambda body: body.get("status") == "ok" and body.get("executor_ready") is True,
            issues,
        )
        self._check_json(
            f"{self.config.bridge_url}/status",
            "bridge_status",
            lambda body: body.get("ready") is True and not body.get("last_error"),
            issues,
        )

        memory = self._command(
            ["docker", "stats", "--no-stream", "--format", "{{.MemPerc}}", "polyhermes"]
        )
        try:
            memory_percent = float(memory.rstrip("%"))
            if memory_percent >= self.config.app_memory_warning_percent:
                issues.append(f"app_memory: {memory_percent:.1f}%")
        except ValueError:
            issues.append(f"app_memory: unreadable ({memory or 'empty'})")

        logs = self._command(["docker", "logs", "--since", "3m", "polyhermes"], stderr=True)
        if "OutOfMemoryError" in logs:
            issues.append("app_oom: OutOfMemoryError detected in recent logs")
        return issues

    def restart_app(self):
        return self._command(["docker", "restart", "polyhermes"], check=False).strip() == "polyhermes"

    def capture_app_diagnostics(self):
        """Save a bounded, redacted snapshot before restarting a wedged app."""
        diagnostic_dir = self.config.state_file.parent / "incidents"
        diagnostic_dir.mkdir(parents=True, exist_ok=True)
        diagnostic_path = diagnostic_dir / f"app-wedge-{int(time.time())}.log"
        commands = [
            (
                "container_state",
                [
                    "docker",
                    "inspect",
                    "--format",
                    "status={{.State.Status}} health={{.State.Health.Status}} "
                    "oom={{.State.OOMKilled}} restartCount={{.RestartCount}} "
                    "started={{.State.StartedAt}}",
                    "polyhermes",
                ],
            ),
            ("container_stats", ["docker", "stats", "--no-stream", "polyhermes"]),
            ("container_processes", ["docker", "top", "polyhermes", "-eo", "pid,stat,%cpu,%mem,etime,cmd"]),
            ("backend_listeners", ["docker", "exec", "polyhermes", "sh", "-lc", "ss -lnt"]),
            (
                "java_thread_dump_signal",
                [
                    "docker",
                    "exec",
                    "polyhermes",
                    "sh",
                    "-lc",
                    "pid=$(pgrep -f 'java -jar /app/app.jar' | head -n 1); "
                    "if [ -n \"$pid\" ]; then kill -QUIT \"$pid\"; echo java_pid=$pid; "
                    "else echo java_pid_not_found; fi",
                ],
            ),
        ]
        try:
            sections = []
            for label, command in commands:
                result = subprocess.run(
                    command,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
                sections.append(f"[{label}]\n{result.stdout.strip()}\n")

            time.sleep(1)
            logs = self._command(["docker", "logs", "--tail", "1200", "polyhermes"], stderr=True)
            marker = logs.rfind("Full thread dump")
            if marker >= 0:
                sections.append(f"[java_thread_dump]\n{self._redact(logs[marker:])}\n")
            else:
                sections.append("[java_thread_dump]\nnot found in recent container logs\n")

            diagnostic_path.write_text("\n".join(sections), encoding="utf-8")
            diagnostic_path.chmod(0o600)
            print(f"PolyHermes watchdog: saved app diagnostics to {diagnostic_path}")
        except OSError as exc:
            print(f"PolyHermes watchdog: failed to save app diagnostics: {exc}")

    @staticmethod
    def _redact(text):
        return re.sub(
            r"(?i)(authorization:?\\s*(?:bearer\\s+)?|token=)[^\\s&]+",
            r"\\1[REDACTED]",
            text,
        )

    def _check_container(self, name, require_health, issue_prefix, issues):
        running = self._command(
            ["docker", "inspect", "--format", "{{.State.Running}}", name], check=False
        )
        if running.strip() != "true":
            issues.append(f"{issue_prefix}_container: not running")
            return
        if require_health:
            health = self._command(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", name],
                check=False,
            )
            if health.strip() != "healthy":
                issues.append(f"{issue_prefix}_health: {health.strip() or 'unknown'}")

    def _check_http(self, url, name, issues, method="GET"):
        try:
            request = urllib.request.Request(url, data=b"" if method == "POST" else None, method=method)
            with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
                if not 200 <= response.status < 400:
                    issues.append(f"{name}: HTTP {response.status}")
        except (OSError, urllib.error.URLError) as exc:
            issues.append(f"{name}: {exc}")

    def _check_json(self, url, name, validator, issues, method="GET"):
        try:
            request = urllib.request.Request(url, data=b"" if method == "POST" else None, method=method)
            with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            if not validator(body):
                issues.append(f"{name}: unexpected response")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            issues.append(f"{name}: {exc}")

    @staticmethod
    def _command(command, check=False, stderr=False):
        result = subprocess.run(
            command,
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if stderr else subprocess.PIPE,
        )
        return result.stdout.strip()

    def _load_state(self):
        try:
            return json.loads(self.config.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"failures": 0, "incident": False}

    def _save_state(self, state):
        self.config.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.config.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.config.state_file)


def main():
    config = Config.from_env()
    notifier = FeishuNotifier(timeout=config.request_timeout)
    if "--test-alert" in sys.argv:
        sent = notifier.send(
            "✅ PolyHermes 飞书预警测试",
            f"主机: {socket.gethostname()}\nVPS 健康监控已启用。",
        )
        raise SystemExit(0 if sent else 1)
    Watchdog(config=config, notifier=notifier).run_once()


if __name__ == "__main__":
    main()
