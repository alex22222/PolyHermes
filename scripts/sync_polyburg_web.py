#!/usr/bin/env python3
"""
Sync Polyburg Telegram Web messages into PolyHermes leader research.

This fallback does not require Telegram API credentials. It launches a persistent
browser profile, opens Telegram Web, scrapes visible Polyburg chat text, and
posts it to PolyHermes. First run must be headful so you can login once.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLYBURG_URL = "https://web.telegram.org/a/#7698624735"
WALLET_REGEX = re.compile(r"0x[a-fA-F0-9]{40}")
MESSAGE_ID_REGEX = re.compile(r"\b(?:telegram_)?message[_ ]?id[:# ]+(\d+)\b", re.IGNORECASE)


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
    telegram_url: str
    profile_dir: Path
    polyhermes_base_url: str
    polyhermes_token: str | None
    polyhermes_username: str | None
    polyhermes_password: str | None
    state_file: Path
    default_category: str
    source_url: str
    max_items: int
    scrolls: int
    headless: bool
    dry_run: bool
    setup: bool


def parse_args() -> argparse.Namespace:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Scrape logged-in Telegram Web Polyburg messages and import leader candidates into PolyHermes."
    )
    parser.add_argument("--import", dest="do_import", action="store_true", help="perform real import and advance state")
    parser.add_argument("--dry-run", action="store_true", help="preview only; default behavior")
    parser.add_argument("--setup", action="store_true", help="open browser for Telegram Web login and wait")
    parser.add_argument("--headless", action="store_true", help="run browser headless")
    parser.add_argument("--scrolls", type=int, default=int(os.getenv("POLYBURG_WEB_SCROLLS", "8")))
    parser.add_argument("--profile-dir", default=os.getenv("POLYBURG_WEB_PROFILE", str(PROJECT_ROOT / ".polyburg_web_profile")))
    parser.add_argument("--state-file", default=os.getenv("POLYBURG_WEB_SYNC_STATE", str(PROJECT_ROOT / ".polyburg_web_sync_state.json")))
    parser.add_argument("--url", default=os.getenv("POLYBURG_WEB_URL", DEFAULT_POLYBURG_URL))
    parser.add_argument("--base-url", default=os.getenv("POLYHERMES_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--default-category", default=os.getenv("POLYBURG_DEFAULT_CATEGORY", "finance"))
    parser.add_argument("--max-items", type=int, default=int(os.getenv("POLYBURG_MAX_ITEMS", "500")))
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> Config:
    dry_run = not args.do_import
    if args.dry_run:
        dry_run = True
    return Config(
        telegram_url=args.url,
        profile_dir=Path(args.profile_dir),
        polyhermes_base_url=args.base_url.rstrip("/"),
        polyhermes_token=os.getenv("POLYHERMES_TOKEN"),
        polyhermes_username=os.getenv("POLYHERMES_USERNAME"),
        polyhermes_password=os.getenv("POLYHERMES_PASSWORD"),
        state_file=Path(args.state_file),
        default_category=args.default_category,
        source_url=os.getenv("POLYBURG_SOURCE_URL", DEFAULT_POLYBURG_URL),
        max_items=max(1, min(args.max_items, 1000)),
        scrolls=max(0, min(args.scrolls, 80)),
        headless=args.headless,
        dry_run=dry_run,
        setup=args.setup,
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
        "User-Agent": "polyhermes-polyburg-web-sync/1.0",
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


async def scrape_telegram_web(config: Config) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit("Missing Playwright. Install with: python3 -m pip install playwright") from exc

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(config.profile_dir),
            headless=config.headless,
            viewport={"width": 1360, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(config.telegram_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)

        if config.setup:
            print(
                json.dumps(
                    {
                        "status": "setup_waiting",
                        "message": "Login to Telegram Web in the opened browser, open the Polyburg chat, then press Enter here.",
                    },
                    ensure_ascii=False,
                )
            )
            await asyncio.to_thread(input)

        for _ in range(config.scrolls):
            await page.mouse.wheel(0, -2600)
            await page.wait_for_timeout(350)

        messages = await page.evaluate(
            """() => Array.from(document.querySelectorAll('[data-message-id]')).map((el) => ({
                id: el.getAttribute('data-message-id'),
                text: el.innerText || el.textContent || '',
                links: Array.from(el.querySelectorAll('a[href]')).map((a) => a.href)
            }))"""
        )
        await context.close()
        return build_text_from_dom_messages(messages)


def build_text_from_dom_messages(messages: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for message in messages:
        text = str(message.get("text") or "").strip()
        links = [str(link) for link in message.get("links", []) if link]
        wallets = []
        for link in links:
            decoded = urllib.parse.unquote(link)
            wallets.extend(WALLET_REGEX.findall(decoded))
        wallet_lines = [f"full_wallet:{wallet.lower()}" for wallet in dict.fromkeys(wallets)]
        block = "\n".join(
            [
                f"telegram_message_id:{message.get('id')}",
                text,
                *wallet_lines,
                *[f"link:{link}" for link in links],
            ]
        ).strip()
        if block:
            blocks.append(block)
    return "\n\n".join(blocks)


def filter_new_text(raw_text: str, state: dict[str, Any], max_items: int) -> tuple[str, int | None]:
    last_hashes = set(state.get("recent_hashes", []))
    blocks = [block.strip() for block in re.split(r"\n{2,}", raw_text) if block.strip()]
    selected: list[str] = []
    newest_message_id: int | None = None

    for block in blocks:
        if not WALLET_REGEX.search(block):
            continue
        message_ids = [int(match.group(1)) for match in MESSAGE_ID_REGEX.finditer(block)]
        if message_ids:
            newest_message_id = max(newest_message_id or 0, max(message_ids))
        digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
        if digest in last_hashes:
            continue
        selected.append(block)
        if len(selected) >= max_items:
            break

    return "\n\n".join(selected), newest_message_id


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
    page_text = await scrape_telegram_web(config)
    visible_wallets = len(WALLET_REGEX.findall(page_text))
    raw_text, newest_message_id = filter_new_text(page_text, state, config.max_items)

    if not raw_text:
        status = "no_visible_wallets" if visible_wallets == 0 else "no_new_wallet_messages"
        print(
            json.dumps(
                {"status": status, "state_advanced": False, "visibleWallets": visible_wallets},
                ensure_ascii=False,
            )
        )
        return 0

    token = resolve_token(config)
    response = import_polyburg(config, raw_text, token)
    if response.get("code") != 0:
        raise RuntimeError(f"Polyburg web import failed: {response.get('msg') or response}")

    data = response.get("data") or {}
    if not config.dry_run:
        hashes = [
            hashlib.sha256(block.strip().encode("utf-8")).hexdigest()
            for block in re.split(r"\n{2,}", raw_text)
            if block.strip()
        ]
        save_state(
            config.state_file,
            {
                **state,
                "recent_hashes": (hashes + state.get("recent_hashes", []))[:500],
                "last_message_id": newest_message_id or state.get("last_message_id"),
            },
        )

    print(
        json.dumps(
            {
                "status": "dry_run" if config.dry_run else "imported",
                "state_advanced": not config.dry_run,
                "visibleWallets": len(WALLET_REGEX.findall(raw_text)),
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
