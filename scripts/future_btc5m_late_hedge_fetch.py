#!/usr/bin/env python3
"""Read public historical trades into an isolated research cache; never place orders."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.parse


def collect(directory, limit=None):
    directory = Path(directory)
    markets = json.loads((directory / "markets.json").read_text())
    if limit:
        markets = markets[:limit]
    target = directory / "trades.jsonl"
    done = {json.loads(line)["start"] for line in target.read_text().splitlines()} if target.exists() else set()
    lock = threading.Lock()
    next_slot = [0.0]
    stats = {"requests": 0, "split_pages": 0, "errors": 0, "written": 0, "cached": len(done)}

    def request(condition, lo, hi):
        url = "https://data-api.polymarket.com/trades?" + urllib.parse.urlencode({
            "market": condition, "takerOnly": "true", "limit": 1000, "start": lo, "end": hi})
        for attempt in range(3):
            with lock:
                slot = max(time.monotonic(), next_slot[0])
                next_slot[0] = slot + 0.09
                stats["requests"] += 1
            time.sleep(max(0, slot - time.monotonic()))
            result = subprocess.run(["curl", "-fsS", "--max-time", "20", url], capture_output=True, text=True)
            if result.returncode == 0:
                rows = json.loads(result.stdout)
                if not isinstance(rows, list) or any(not lo <= row["timestamp"] <= hi or
                        row["conditionId"] != condition for row in rows):
                    raise ValueError("Historical endpoint ignored requested market/time boundaries")
                return rows
            if attempt == 2:
                raise RuntimeError("Public trade read failed: " + result.stderr[:200])
            time.sleep(attempt + 1)

    def interval(condition, lo, hi):
        rows = request(condition, lo, hi)
        if len(rows) < 1000:
            return rows
        if lo == hi:
            raise ValueError("A single second still hit the page cap; complete history unavailable")
        with lock:
            stats["split_pages"] += 1
        mid = (lo + hi) // 2
        return interval(condition, lo, mid) + interval(condition, mid + 1, hi)

    def fetch(market):
        start = market["start"]
        rows = interval(market["conditionId"], start + 30, start + 79)
        rows += interval(market["conditionId"], start + 190, start + 299)
        buys = sorted([[row["timestamp"] - start, int(row["outcome"] == "Up"),
                        float(row["price"]), float(row["size"])] for row in rows
                       if row["side"] == "BUY" and row["outcome"] in ("Up", "Down")], key=lambda x: x[0])
        return {**market, "buys": buys, "takerRows": len(rows), "completeRequestedIntervals": True}

    todo = [market for market in markets if market["start"] not in done]
    print(json.dumps({"toFetch": len(todo), "cached": len(done)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool, target.open("a") as output:
        futures = {pool.submit(fetch, market): market for market in todo}
        for future in concurrent.futures.as_completed(futures):
            try:
                output.write(json.dumps(future.result(), separators=(",", ":")) + "\n")
                output.flush()
                stats["written"] += 1
            except Exception as error:
                stats["errors"] += 1
                with (directory / "fetch-errors.jsonl").open("a") as errors:
                    errors.write(json.dumps({"slug": futures[future]["slug"], "error": str(error)}) + "\n")
            if (stats["written"] + stats["errors"]) % 100 == 0:
                print(json.dumps(stats), flush=True)
    (directory / "fetch-summary.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    collect(args.directory, args.limit)
