#!/usr/bin/env python3
"""Monitor the production Docker stack and notify Feishu on incidents."""

import json
import os
import socket
import subprocess
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
    def __init__(self, webhook_url=None, timeout=8):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")
        self.timeout = timeout

    def send(self, title, message):
        if not self.webhook_url:
            print("Feishu alert was not sent: FEISHU_WEBHOOK_URL is not configured")
            return False

        payload = json.dumps(
            {
                "msg_type": "text",
                "content": {"text": f"{title}\n{message}"},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            response_code = body.get("code", body.get("StatusCode"))
            success = response_code == 0
            if not success:
                print(f"Feishu rejected alert: {body}")
            return success
        except (OSError, ValueError, urllib.error.URLError) as exc:
            print(f"Feishu alert failed: {exc}")
            return False


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
        app_restarter=None,
        now=None,
    ):
        self.config = config
        self.notifier = notifier
        self.issue_collector = issue_collector or self.collect_issues
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
                    state["failures"] = 0
                    self._save_state(state)
                    print("PolyHermes watchdog: healthy; recovery alert will be retried")
                    return True
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
    Watchdog(config=config, notifier=notifier).run_once()


if __name__ == "__main__":
    main()
