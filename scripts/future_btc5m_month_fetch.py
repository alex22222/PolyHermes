#!/usr/bin/env python3
"""Fetch September 2026 public BTC5m history for offline bankroll research."""
import argparse
from collections import Counter
import concurrent.futures
import json
from pathlib import Path
import threading
import time
import requests

from future_btc5m_late_hedge_backtest import replay

START = 1788192000  # 2026-09-01 00:00 Asia/Shanghai
END = 1790784000    # 2026-10-01 00:00 Asia/Shanghai


class PublicReads:
    def __init__(self):
        self.local = threading.local()
        self.lock = threading.Lock()
        self.next_slot = 0.0
        self.requests = 0
        self.split_pages = 0

    def get(self, url, params):
        if not hasattr(self.local, "session"):
            self.local.session = requests.Session()
            self.local.session.headers["User-Agent"] = "polyhermes-offline-month-research/1.0"
        for attempt in range(4):
            with self.lock:
                slot = max(time.monotonic(), self.next_slot)
                self.next_slot = slot + 0.065
                self.requests += 1
            time.sleep(max(0, slot - time.monotonic()))
            try:
                response = self.local.session.get(url, params=params, timeout=(8, 25), verify="/etc/ssl/cert.pem")
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError):
                if attempt == 3:
                    raise
                time.sleep(attempt + 1)

    def trades(self, condition, lo, hi):
        rows = self.get("https://data-api.polymarket.com/trades", {
            "market": condition, "takerOnly": "true", "limit": 1000, "start": lo, "end": hi})
        if not isinstance(rows, list) or any(row["conditionId"] != condition or
                                             not lo <= row["timestamp"] <= hi for row in rows):
            raise ValueError("Public endpoint ignored market/time boundaries")
        if len(rows) < 1000:
            return rows
        if lo == hi:
            raise ValueError("Single-second page cap; complete history unavailable")
        with self.lock:
            self.split_pages += 1
        middle = (lo + hi) // 2
        return self.trades(condition, lo, middle) + self.trades(condition, middle + 1, hi)


def fetch_metadata(directory, reader):
    target = directory / "markets.json"
    old = json.loads(target.read_text()) if target.exists() else []
    markets = {row["start"]: row for row in old if not row.get("missing")}
    todo = [start for start in range(START, END, 300) if start not in markets]
    batches = [todo[index:index + 50] for index in range(0, len(todo), 50)]

    def market_row(event, start):
        if event.get("slug") != f"btc-updown-5m-{start}" or len(event.get("markets", [])) != 1:
            return None
        market = event["markets"][0]
        names = json.loads(market["outcomes"])
        prices = json.loads(market["outcomePrices"])
        winners = [name for name, price in zip(names, prices) if float(price) == 1]
        if market.get("closed") is not True or len(winners) != 1 or winners[0] not in ("Up", "Down"):
            return None
        return {"start": start, "slug": event["slug"], "conditionId": market["conditionId"], "winner": winners[0],
                "feeType": market.get("feeType"), "feeSchedule": market.get("feeSchedule"),
                "resolutionSource": market.get("resolutionSource")}

    def batch(starts):
        slugs = {f"btc-updown-5m-{start}": start for start in starts}
        events = reader.get("https://gamma-api.polymarket.com/events",
                            [("limit", 100)] + [("slug", slug) for slug in slugs])
        output = []
        for event in events:
            if event.get("slug") not in slugs:
                continue
            row = market_row(event, slugs[event["slug"]])
            if row:
                output.append(row)
        return output

    print(json.dumps({"metadataCached": len(markets), "metadataToFetch": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(batch, starts) for starts in batches]
        for future in concurrent.futures.as_completed(futures):
            for row in future.result():
                markets[row["start"]] = row
            target.write_text(json.dumps(sorted(markets.values(), key=lambda row: row["start"]), separators=(",", ":")))
    # The listing omits some inactive, zero-volume markets. Read the exact slug
    # rather than treating a missing list row as an absent historical round.
    for start in range(START, END, 300):
        if start not in markets:
            event = reader.get(f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{start}", {})
            row = market_row(event, start)
            if row:
                markets[start] = row
    target.write_text(json.dumps(sorted(markets.values(), key=lambda row: row["start"]), separators=(",", ":")))
    missing = [start for start in range(START, END, 300) if start not in markets]
    (directory / "metadata-coverage.json").write_text(json.dumps({
        "expected": 8640, "found": len(markets), "missing": missing, "requests": reader.requests,
        "feeTypes": dict(Counter(row["feeType"] for row in markets.values()))}, indent=2) + "\n")
    print(json.dumps({"metadataFound": len(markets), "metadataMissing": len(missing)}), flush=True)
    if missing:
        raise ValueError("Missing resolved markets; resume metadata collection before full-month replay")
    return list(markets.values())


def fetch_trades(directory, markets, reader, limit=None):
    target = directory / "trades.jsonl"
    done = {json.loads(line)["start"] for line in target.open()} if target.exists() else set()
    todo = sorted((market for market in markets if market["start"] not in done), key=lambda row: row["start"])
    if limit:
        todo = todo[:limit]
    stats = {"cached": len(done), "toFetch": len(todo), "written": 0, "errors": 0, "lateIntervalsAvoided": 0}

    def fetch(market):
        start = market["start"]
        rows = reader.trades(market["conditionId"], start + 30, start + 79)
        def compact(raw):
            return sorted([[row["timestamp"] - start, int(row["outcome"] == "Up"), float(row["price"]),
                            float(row["size"])] for row in raw if row["side"] == "BUY" and
                           row["outcome"] in ("Up", "Down")], key=lambda trade: trade[0])
        buys = compact(rows)
        entry = replay({**market, "buys": buys})
        if "skip" in entry:
            return {**market, "buys": buys, "takerRows": len(rows), "entrySkip": entry["skip"],
                    "completeRequestedIntervals": True, "lateFetched": False}
        rows += reader.trades(market["conditionId"], start + 190, start + 299)
        return {**market, "buys": compact(rows), "takerRows": len(rows),
                "completeRequestedIntervals": True, "lateFetched": True}

    print(json.dumps(stats), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool, target.open("a") as output:
        futures = {pool.submit(fetch, market): market for market in todo}
        for future in concurrent.futures.as_completed(futures):
            try:
                row = future.result()
                output.write(json.dumps(row, separators=(",", ":")) + "\n")
                output.flush()
                stats["written"] += 1
                stats["lateIntervalsAvoided"] += not row["lateFetched"]
            except Exception as error:
                stats["errors"] += 1
                with (directory / "fetch-errors.jsonl").open("a") as errors:
                    errors.write(json.dumps({"start": futures[future]["start"], "error": str(error)[:300]}) + "\n")
            if (stats["written"] + stats["errors"]) % 250 == 0:
                print(json.dumps({**stats, "requests": reader.requests, "splitPages": reader.split_pages}), flush=True)
    stats.update(requests=reader.requests, splitPages=reader.split_pages)
    (directory / "fetch-summary.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    reads = PublicReads()
    items = fetch_metadata(args.directory, reads)
    if not args.metadata_only:
        fetch_trades(args.directory, items, reads, args.limit)
