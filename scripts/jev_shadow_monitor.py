#!/usr/bin/env python3
"""Record read-only, fee-adjusted Yes/No quotes for a short Jev shadow study."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from jev_shadow_probe import CLOB_BASE, GAMMA_BASE, http_json, parse_binary_market, simulate_buy


POLITICS_FINANCE_TERMS = re.compile(
    r"\b(election|president|presidential|senate|congress|parliament|trump|biden|"
    r"democrat|republican|prime minister|government|white house|supreme court|"
    r"governor|mayor|iran|israel|gaza|ukraine|russia|taiwan|war|ceasefire|"
    r"sanctions?|tariff|nato|fed|federal reserve|fomc|interest rates?|rate cuts?|"
    r"rate hikes?|inflation|cpi|gdp|recession|treasury|yield|nasdaq|s&p 500|"
    r"dow jones|stock|earnings|revenue|ipo|gold|silver|oil|unemployment)\b",
    re.IGNORECASE,
)
CRYPTO_TERMS = re.compile(
    r"\b(bitcoin|btc|ethereum|ether|eth|xrp|ripple|solana|sol|dogecoin|doge|"
    r"crypto|cryptocurrency|blockchain|stablecoin|usdc|usdt|binance|coinbase|"
    r"altcoin|memecoin|nft)\b",
    re.IGNORECASE,
)


def select_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for market in markets:
        text = f"{market.get('question') or ''} {market.get('slug') or ''}"
        if CRYPTO_TERMS.search(text) or not POLITICS_FINANCE_TERMS.search(text):
            continue
        try:
            parse_binary_market(market)
        except ValueError:
            continue
        selected.append(market)
    return selected


def scan_market(
    market: dict[str, Any], shares: Decimal, quote_now_fn: Callable[[], datetime],
    http_fn: Callable[..., Any],
) -> tuple[dict[str, Any] | None, str | None]:
    parsed = parse_binary_market(market)
    quotes = {}
    try:
        for side, token in parsed["tokens"].items():
            url = f"{CLOB_BASE}/book?{urllib.parse.urlencode({'token_id': token})}"
            try:
                book = http_fn(url)
            except OSError:
                time.sleep(0.5)
                book = http_fn(url)
            quote = simulate_buy(book, shares, parsed["fee_rate"], quote_now_fn())
            quotes[side] = {
                "vwap": quote["vwap"],
                "fee_per_share": quote["fee"] / shares,
                "net_cost_per_share": (quote["cost"] + quote["fee"]) / shares,
                "book_age_seconds": quote["book_age_seconds"],
                "book_timestamp": quote["book_timestamp"],
                "book_hash": quote["book_hash"],
                "levels_used": quote["levels_used"],
            }
    except (ValueError, RuntimeError, OSError) as error:
        return None, str(error)

    pair_cost = quotes["Yes"]["net_cost_per_share"] + quotes["No"]["net_cost_per_share"]
    return {
        "market_slug": market["slug"],
        "condition_id": market["conditionId"],
        "question": market["question"],
        "end_date": market.get("endDate"),
        "volume24hr": market.get("volume24hr"),
        "fee_rate": parsed["fee_rate"],
        "quotes": quotes,
        "pair_cost_per_share": pair_cost,
        "pair_edge_per_share": Decimal("1") - pair_cost,
    }, None


def collect_snapshot(
    now: datetime, pages: int = 3, shares: Decimal = Decimal("20"),
    http_fn: Callable[..., Any] = http_json,
    quote_now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    if quote_now_fn is None:
        quote_now_fn = lambda: datetime.now(timezone.utc)
    markets = []
    source_errors = []
    for offset in range(0, pages * 100, 100):
        url = (
            f"{GAMMA_BASE}/markets?limit=100&offset={offset}"
            "&active=true&closed=false&order=volume24hr&ascending=false"
        )
        try:
            page = http_fn(url)
        except (RuntimeError, OSError) as error:
            source_errors.append(f"Gamma offset {offset}: {error}")
            continue
        if not isinstance(page, list):
            source_errors.append(f"Gamma offset {offset}: invalid response")
            continue
        markets.extend(page)
        if len(page) < 100:
            break

    selected = select_markets(markets)
    rows = []
    skipped = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(lambda market: scan_market(market, shares, quote_now_fn, http_fn), selected)
        for market, (row, reason) in zip(selected, results):
            if row is None:
                skipped[market["slug"]] = reason
            else:
                rows.append(row)
    rows.sort(key=lambda row: row["pair_edge_per_share"], reverse=True)
    window = now.replace(hour=now.hour - now.hour % 6, minute=0, second=0, microsecond=0)
    return {
        "schema_version": 5,
        "market_scope": "politics_finance_ex_crypto",
        "observed_at": now.isoformat(),
        "window_start": window.isoformat(),
        "markets_fetched": len(markets),
        "eligible_markets": len(selected),
        "fresh_pairs": len(rows),
        "positive_pairs": sum(row["pair_edge_per_share"] > 0 for row in rows),
        "requested_shares": shares,
        "rows": rows,
        "skipped": skipped,
        "source_errors": source_errors,
        "paper_only": True,
        "jev_evaluated": False,
    }


def save_snapshot(path: Path, snapshot: dict[str, Any]) -> bool:
    if path.exists():
        with path.open(encoding="utf-8") as existing:
            for line in existing:
                previous = json.loads(line)
                if (previous["window_start"] == snapshot["window_start"]
                        and previous.get("schema_version") == snapshot.get("schema_version")):
                    return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/jev-shadow-monitor.jsonl"))
    parser.add_argument("--until", type=datetime.fromisoformat, help="UTC end time for this observation window")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.until is not None:
        if args.until.tzinfo is None:
            parser.error("--until requires a timezone")
        if now >= args.until:
            print("Observation window complete")
            return 0
    snapshot = collect_snapshot(now)
    if not snapshot["markets_fetched"]:
        print("No Gamma market page was fetched; snapshot not saved")
        return 1
    saved = save_snapshot(args.output, snapshot)
    print(
        f"{'Saved' if saved else 'Already saved'} {snapshot['window_start']}: "
        f"eligible={snapshot['eligible_markets']}, fresh={snapshot['fresh_pairs']}, "
        f"positive_pairs={snapshot['positive_pairs']}, source_errors={len(snapshot['source_errors'])}"
    )
    return 0 if snapshot["fresh_pairs"] and not snapshot["source_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
