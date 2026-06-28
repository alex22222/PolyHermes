#!/usr/bin/env python3
"""
Sync Polyburg Telegram bot messages into PolyHermes leader research.

Requires Telethon:
  python3 -m pip install telethon

First run will ask Telegram login code in the terminal and save the session.
Use --import for real candidate import; the default is dry-run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_POLYBURG_PEER = "7698624735"
DEFAULT_POLYBURG_URL = "https://web.telegram.org/a/#7698624735"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class Config:
    telegram_api_id: int
    telegram_api_hash: str
    telegram_session: str
    telegram_peer: str
    polyhermes_base_url: str
    polyhermes_token: str | None
    polyhermes_username: str | None
    polyhermes_password: str | None
    state_file: Path
    default_category: str
    source_url: str
    max_items: int
    limit: int
    dry_run: bool


def parse_args() -> argparse.Namespace:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Fetch new Polyburg Telegram bot messages and import leader candidates into PolyHermes."
    )
    parser.add_argument("--import", dest="do_import", action="store_true", help="perform real import and advance state")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="preview only; default behavior")
    parser.add_argument("--limit", type=int, default=int(os.getenv("POLYBURG_TELEGRAM_LIMIT", "50")))
    parser.add_argument("--state-file", default=os.getenv("POLYBURG_SYNC_STATE", ".polyburg_telegram_sync_state.json"))
    parser.add_argument("--peer", default=os.getenv("POLYBURG_TELEGRAM_PEER", DEFAULT_POLYBURG_PEER))
    parser.add_argument("--base-url", default=os.getenv("POLYHERMES_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--default-category", default=os.getenv("POLYBURG_DEFAULT_CATEGORY", "finance"))
    parser.add_argument("--max-items", type=int, default=int(os.getenv("POLYBURG_MAX_ITEMS", "500")))
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> Config:
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        raise SystemExit("Missing TELEGRAM_API_ID and TELEGRAM_API_HASH. Create them at https://my.telegram.org/apps")

    dry_run = not args.do_import
    if args.dry_run:
        dry_run = True

    return Config(
        telegram_api_id=int(api_id),
        telegram_api_hash=api_hash,
        telegram_session=os.getenv("TELEGRAM_SESSION", ".polyburg_telegram"),
        telegram_peer=args.peer,
        polyhermes_base_url=args.base_url.rstrip("/"),
        polyhermes_token=os.getenv("POLYHERMES_TOKEN"),
        polyhermes_username=os.getenv("POLYHERMES_USERNAME"),
        polyhermes_password=os.getenv("POLYHERMES_PASSWORD"),
        state_file=Path(args.state_file),
        default_category=args.default_category,
        source_url=os.getenv("POLYBURG_SOURCE_URL", DEFAULT_POLYBURG_URL),
        max_items=max(1, min(args.max_items, 1000)),
        limit=max(1, min(args.limit, 500)),
        dry_run=dry_run,
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    tmp_path.replace(path)


def http_json(method: str, url: str, payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "polyhermes-polyburg-sync/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail[:300]}") from exc


def resolve_token(config: Config) -> str:
    if config.polyhermes_token:
        return config.polyhermes_token
    if not config.polyhermes_username or not config.polyhermes_password:
        raise SystemExit("Set POLYHERMES_TOKEN or POLYHERMES_USERNAME/POLYHERMES_PASSWORD")

    response = http_json(
        "POST",
        f"{config.polyhermes_base_url}/api/auth/login",
        {"username": config.polyhermes_username, "password": config.polyhermes_password},
    )
    if response.get("code") != 0 or not response.get("data", {}).get("token"):
        raise RuntimeError(f"PolyHermes login failed: {response.get('msg') or response}")
    return response["data"]["token"]


async def fetch_messages(config: Config, min_id: int) -> list[Any]:
    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise SystemExit("Missing Telethon. Install with: python3 -m pip install telethon") from exc

    peer: str | int = config.telegram_peer
    if peer.isdigit():
        peer = int(peer)

    async with TelegramClient(config.telegram_session, config.telegram_api_id, config.telegram_api_hash) as client:
        entity = await client.get_entity(peer)
        messages = await client.get_messages(entity, limit=config.limit, min_id=min_id)
        return sorted([message for message in messages if getattr(message, "message", None)], key=lambda item: item.id)


def build_raw_text(messages: list[Any]) -> str:
    parts = []
    for message in messages:
        date_text = getattr(message, "date", None)
        prefix = f"[telegram_message_id:{message.id}"
        if date_text:
            prefix += f" date:{date_text.isoformat()}"
        prefix += "]"
        parts.append(f"{prefix}\n{message.message}")
    return "\n\n".join(parts)


def import_polyburg(config: Config, raw_text: str, token: str) -> dict[str, Any]:
    return http_json(
        "POST",
        f"{config.polyhermes_base_url}/api/copy-trading/leader-research/polyburg-telegram/import",
        {
            "dryRun": config.dry_run,
            "rawText": raw_text,
            "defaultCategory": config.default_category,
            "sourceUrl": config.source_url,
            "maxItems": config.max_items,
        },
        token=token,
    )


async def main() -> int:
    args = parse_args()
    config = load_config(args)
    state = load_state(config.state_file)
    last_message_id = int(state.get("last_message_id", 0))

    messages = await fetch_messages(config, min_id=last_message_id)
    if not messages:
        print(json.dumps({"status": "no_new_messages", "last_message_id": last_message_id}, ensure_ascii=False))
        return 0

    raw_text = build_raw_text(messages)
    token = resolve_token(config)
    response = import_polyburg(config, raw_text, token)
    if response.get("code") != 0:
        raise RuntimeError(f"Polyburg import failed: {response.get('msg') or response}")

    data = response.get("data") or {}
    newest_message_id = max(message.id for message in messages)
    if not config.dry_run:
        save_state(
            config.state_file,
            {
                **state,
                "last_message_id": newest_message_id,
                "last_imported_at": messages[-1].date.isoformat() if getattr(messages[-1], "date", None) else None,
            },
        )

    print(
        json.dumps(
            {
                "status": "dry_run" if config.dry_run else "imported",
                "messages": len(messages),
                "from_message_id": messages[0].id,
                "to_message_id": newest_message_id,
                "state_advanced": not config.dry_run,
                "parsedTotal": data.get("parsedTotal"),
                "dedupedTotal": data.get("dedupedTotal"),
                "importResult": data.get("importResult"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
