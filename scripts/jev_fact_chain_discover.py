#!/usr/bin/env python3
"""Find unverified official-source/market pairs for manual Jev fact-chain review."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jev_fact_chain import SOURCE_CATEGORIES, collect_source, fetch_text, run_review
from jev_shadow_monitor import CRYPTO_TERMS
from jev_shadow_probe import GAMMA_BASE, http_json, parse_binary_market


def discover_records(
    source_kind: str, source_url: str, query: str, now: datetime,
    fetch_fn: Callable[[str], str] = fetch_text,
    http_fn: Callable[..., Any] = http_json,
    category: str | None = None,
    market_phrase: str | None = None,
) -> list[dict[str, Any]]:
    category = category or SOURCE_CATEGORIES[source_kind]
    if category not in ("politics", "finance"):
        raise ValueError("category must be politics or finance")
    query = query.strip()
    if len(query) < 3 or len(query) > 100:
        raise ValueError("search query must contain 3 to 100 characters")
    if market_phrase is not None:
        market_phrase = market_phrase.strip()
        if len(market_phrase) < 3 or len(market_phrase) > 100:
            raise ValueError("market phrase must contain 3 to 100 characters")
    cached_text: dict[str, str] = {}

    def cached_fetch(url: str) -> str:
        if url not in cached_text:
            cached_text[url] = fetch_fn(url)
        return cached_text[url]

    collect_source(source_kind, source_url, now, cached_fetch)
    search_url = f"{GAMMA_BASE}/public-search?{urllib.parse.urlencode({'q': query, 'limit_per_type': 10})}"
    search = http_fn(search_url)
    if not isinstance(search, dict) or not isinstance(search.get("events"), list):
        raise ValueError("Gamma search response is invalid")

    rows = []
    seen = set()
    for event in search["events"]:
        if not isinstance(event, dict) or not isinstance(event.get("markets"), list):
            raise ValueError("Gamma search event is invalid")
        if not all(isinstance(market, dict) for market in event["markets"]):
            raise ValueError("Gamma search market is invalid")
        for market in event["markets"]:
            market_text = " ".join(str(market.get(field) or "") for field in ("question", "slug", "description"))
            if market_phrase and market_phrase.casefold() not in market_text.casefold():
                continue
            if CRYPTO_TERMS.search(market_text):
                continue
            try:
                parse_binary_market(market)
            except ValueError:
                continue
            slug = market.get("slug")
            if not isinstance(slug, str) or slug in seen:
                continue
            seen.add(slug)
            result = run_review(
                {"market_slug": slug, "category": category,
                 "source_kind": source_kind, "source_url": source_url},
                now, cached_fetch, http_fn,
            )
            if result["status"] == "OUT_OF_SCOPE":
                continue
            if result["status"] == "RULE_REVIEW_REQUIRED":
                result["reason"] = "keyword association and full settlement rules have not been reviewed"
            result["discovery_query"] = query
            result["discovery_basis"] = "UNVERIFIED_KEYWORD_SEARCH"
            rows.append(result)
            if len(rows) >= 10:
                return rows
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-kind", choices=tuple(SOURCE_CATEGORIES), required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--query", required=True, help="operator-selected Gamma search terms; never evidence of rule fit")
    parser.add_argument("--category", choices=("politics", "finance"), help="Gamma market category; defaults to the source's usual category")
    parser.add_argument("--market-contains", help="literal phrase required in market question, slug, or description; not rule evidence")
    parser.add_argument("--output", type=Path, default=Path("data/jev-fact-chain.jsonl"))
    args = parser.parse_args()
    try:
        rows = discover_records(args.source_kind, args.source_url, args.query, datetime.now(timezone.utc),
                                category=args.category, market_phrase=args.market_contains)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Discovery unavailable: {error}", file=sys.stderr)
        return 1
    if rows:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("a", encoding="utf-8") as output:
            for row in rows:
                output.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    print(f"Saved {len(rows)} unverified search suggestions; keyword matches are not settlement evidence or edge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
