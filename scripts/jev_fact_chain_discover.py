#!/usr/bin/env python3
"""Find unverified official-source/market pairs for manual Jev fact-chain review."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jev_fact_chain import SOURCE_CATEGORIES, collect_source, fetch_text, run_review
from jev_shadow_monitor import CRYPTO_TERMS
from jev_shadow_probe import GAMMA_BASE, http_json, parse_binary_market


_BILL_ID = re.compile(
    r"\b(?P<chamber>H|S)\s*\.?\s*(?P<kind>(?:Con|J)\s*\.?\s*Res|R)?\s*[.\-]?\s*(?P<number>\d{1,5})\b",
    re.IGNORECASE,
)


def bill_ids(text: str) -> list[str]:
    prefixes = {
        ("H", "r"): "H.R.", ("S", ""): "S.",
        ("H", "conres"): "H.Con.Res.", ("S", "conres"): "S.Con.Res.",
        ("H", "jres"): "H.J.Res.", ("S", "jres"): "S.J.Res.",
    }
    found = []
    for match in _BILL_ID.finditer(text):
        prefix = prefixes.get((match.group("chamber").upper(), re.sub(r"\W", "", match.group("kind") or "").lower()))
        number = int(match.group("number"))
        if prefix and number > 0:
            found.append(f"{prefix} {number}")
    return list(dict.fromkeys(found))


def discover_records(
    source_kind: str, source_url: str, query: str | None, now: datetime,
    fetch_fn: Callable[[str], str] = fetch_text,
    http_fn: Callable[..., Any] = http_json,
    category: str | None = None,
    market_phrase: str | None = None,
) -> list[dict[str, Any]]:
    category = category or SOURCE_CATEGORIES[source_kind]
    if category not in ("politics", "finance"):
        raise ValueError("category must be politics or finance")
    if query is not None:
        query = query.strip()
    if query is not None and (len(query) < 3 or len(query) > 100):
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

    source = collect_source(source_kind, source_url, now, cached_fetch)
    queries = [query] if query is not None else bill_ids(source["title"] + " " + source["text"])
    if not queries or len(queries) > 10:
        raise ValueError("official source has no supported bill identifier or too many; provide a manual search query")

    rows = []
    seen = set()
    for search_query in queries:
        search_url = f"{GAMMA_BASE}/public-search?{urllib.parse.urlencode({'q': search_query, 'limit_per_type': 10})}"
        search = http_fn(search_url)
        if not isinstance(search, dict) or not isinstance(search.get("events"), list):
            raise ValueError("Gamma search response is invalid")
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
                if market.get("active") is False or market.get("closed") is True or market.get("acceptingOrders") is False:
                    continue
                complete_card = all(field in market for field in (
                    "active", "closed", "acceptingOrders", "question", "description", "conditionId",
                    "outcomes", "clobTokenIds", "feesEnabled",
                )) and (market["feesEnabled"] is False or "feeSchedule" in market)
                if complete_card:
                    try:
                        parse_binary_market(market)
                    except ValueError:
                        continue
                slug = market.get("slug")
                if not isinstance(slug, str) or slug in seen:
                    continue
                result = run_review(
                    {"market_slug": slug, "category": category,
                     "source_kind": source_kind, "source_url": source_url},
                    now, cached_fetch, http_fn,
                )
                if result["status"] == "OUT_OF_SCOPE":
                    continue
                detail_text = " ".join(str(result.get(field) or "") for field in ("question", "resolution_rules"))
                detail_ids = bill_ids(detail_text)
                if query is None and search_query not in (detail_ids or bill_ids(market_text)):
                    continue
                seen.add(slug)
                if result["status"] == "RULE_REVIEW_REQUIRED":
                    result["reason"] = "keyword association and full settlement rules have not been reviewed"
                result["discovery_query"] = search_query
                result["discovery_basis"] = "UNVERIFIED_KEYWORD_SEARCH"
                rows.append(result)
                if len(rows) >= 10:
                    return rows
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-kind", choices=tuple(SOURCE_CATEGORIES), required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--query", help="operator-selected Gamma search terms; omit only for official bill-number discovery")
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
