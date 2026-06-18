import json
import logging
import re
import sys
import time
from datetime import datetime
from typing import Optional

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class PolyHermesLogWatcher:
    def __init__(
        self,
        bridge_url: str = "http://localhost:8080/signal",
        log_command: Optional[str] = None,
        poll_interval: float = 1.0,
    ):
        self.bridge_url = bridge_url
        self.log_command = log_command or (
            # Default: tail the local backend log when running backend via run_backend_local.sh
            "tail -n 0 -F /tmp/polyhermes-backend.log 2>&1"
        )
        self.poll_interval = poll_interval
        self.seen_trades = set()

    def parse_leader_trade(self, line: str) -> Optional[dict]:
        """Parse a PolyHermes leader trade log line."""
        # Match lines like: 2026-06-17 23:42:20 - 发现leader交易：{json_payload}
        match = re.search(r"发现leader交易：(.+)$", line)
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
        if transaction_hash in self.seen_trades:
            return None
        self.seen_trades.add(transaction_hash)

        # Prefer the nested trader object, fall back to proxyWallet / name.
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

    def send_signal(self, signal: dict):
        """Send signal to bridge service."""
        try:
            response = httpx.post(self.bridge_url, json=signal, timeout=10.0)
            if response.status_code == 200:
                logger.info(f"Signal sent successfully: {signal['transactionHash']}")
            else:
                logger.error(f"Failed to send signal: {response.status_code} {response.text}")
        except Exception as e:
            logger.error(f"Error sending signal: {e}")

    def run(self):
        """Run the log watcher using subprocess."""
        import subprocess

        logger.info(f"Starting PolyHermes log watcher, bridge: {self.bridge_url}")
        logger.info(f"Log command: {self.log_command}")

        process = subprocess.Popen(
            self.log_command,
            shell=True,
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

                signal = self.parse_leader_trade(line)
                if signal:
                    logger.info(f"Detected leader trade: {signal['side']} {signal['outcome']} on {signal['marketSlug']}")
                    self.send_signal(signal)
        except KeyboardInterrupt:
            logger.info("Log watcher stopped")
        finally:
            process.terminate()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Watch PolyHermes logs and send signals to Polymtrade bridge")
    parser.add_argument("--bridge-url", default="http://localhost:8080/signal", help="Bridge service signal URL")
    parser.add_argument("--log-command", help="Command to stream PolyHermes logs")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval (unused for stream)")

    args = parser.parse_args()

    watcher = PolyHermesLogWatcher(
        bridge_url=args.bridge_url,
        log_command=args.log_command,
        poll_interval=args.poll_interval,
    )
    watcher.run()
