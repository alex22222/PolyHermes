import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class LeaderEventPoller:
    """Tail PolyHermes backend log and forward leader trade signals to Bridge.

    PolyHermes writes structured leader trade events to its local log file as
    ``发现leader交易：<json>``. This poller reads that file directly (no Docker,
    no log parsing indirection) and POSTs the parsed signal to the Bridge
    ``/signal`` endpoint.
    """

    # Regex to extract the JSON payload after the Chinese marker.
    LEADER_TRADE_RE = re.compile(r"发现leader交易：(.+)$")

    def __init__(
        self,
        bridge_url: str = "http://localhost:8080/signal",
        log_file: str = "/tmp/polyhermes-backend.log",
        poll_interval: float = 1.0,
    ):
        self.bridge_url = bridge_url
        self.log_file = log_file
        self.poll_interval = poll_interval
        self._running = True
        self._seen_trades: set[str] = set()

    def _send_signal(self, signal: dict):
        try:
            response = httpx.post(self.bridge_url, json=signal, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"Signal sent successfully: {signal['transactionHash']}")
            else:
                logger.error(f"Failed to send signal: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error sending signal: {e}")

    def _parse_leader_trade(self, line: str) -> Optional[dict]:
        match = self.LEADER_TRADE_RE.search(line)
        if not match:
            return None

        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse leader trade JSON: {e}")
            return None

        trade_payload = payload.get("payload", {})
        if not trade_payload:
            return None

        transaction_hash = trade_payload.get("transactionHash") or payload.get("transactionHash")
        if not transaction_hash:
            return None
        if transaction_hash in self._seen_trades:
            return None
        self._seen_trades.add(transaction_hash)

        trader = trade_payload.get("trader") or {}
        leader_address = trader.get("address") or trade_payload.get("proxyWallet", "")
        leader_name = trader.get("name") or trade_payload.get("name", "")

        return {
            "event": "leader_trade",
            "timestamp": payload.get("timestamp", int(time.time() * 1000)),
            "leaderAddress": leader_address,
            "leaderName": leader_name,
            "transactionHash": transaction_hash,
            "conditionId": trade_payload.get("conditionId", ""),
            "marketSlug": trade_payload.get("slug", ""),
            "title": trade_payload.get("title", ""),
            "side": trade_payload.get("side", "BUY"),
            "outcome": trade_payload.get("outcome", ""),
            "outcomeIndex": trade_payload.get("outcomeIndex"),
            "price": trade_payload.get("price", 0),
            "size": trade_payload.get("size", 0),
            "source": payload.get("topic", "activity"),
        }

    def _run_tail(self):
        """Run ``tail -n 0 -F`` on the backend log and yield lines."""
        cmd = ["tail", "-n", "0", "-F", self.log_file]
        logger.info(f"Starting tail: {' '.join(cmd)} -> bridge: {self.bridge_url}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        try:
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                signal = self._parse_leader_trade(line)
                if signal:
                    logger.info(
                        f"Detected leader trade: {signal['side']} {signal['outcome']} on {signal['marketSlug']}"
                    )
                    self._send_signal(signal)

                if not self._running:
                    break
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def run(self):
        logger.info("Starting leader event poller")

        def _handle_signal(signum, _frame):
            logger.info(f"Received signal {signum}, stopping poller...")
            self._running = False

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        while self._running:
            try:
                self._run_tail()
            except Exception:
                logger.exception("Error in tail loop, restarting...")
                time.sleep(self.poll_interval)

        logger.info("Leader event poller stopped")


if __name__ == "__main__":
    bridge_url = os.getenv("BRIDGE_SIGNAL_URL", "http://localhost:8080/signal")
    log_file = os.getenv("POLYHERMES_BACKEND_LOG", "/tmp/polyhermes-backend.log")
    poll_interval = float(os.getenv("LEADER_POLL_INTERVAL", "1.0"))

    poller = LeaderEventPoller(
        bridge_url=bridge_url,
        log_file=log_file,
        poll_interval=poll_interval,
    )
    poller.run()
