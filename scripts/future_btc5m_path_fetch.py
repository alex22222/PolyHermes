#!/usr/bin/env python3
"""Read public BTC 1s OHLC and published market boundaries for offline research."""
import argparse
import concurrent.futures
import json
import math
from pathlib import Path

from future_btc5m_month_fetch import PublicReads


def candles(raw, start):
    expected = list(range(start - 120, start + 300))
    if not isinstance(raw, list) or [row[0] for row in raw] != [second * 1000 for second in expected]:
        raise ValueError("Incomplete or incorrectly timestamped 1s candles")
    result = []
    for row in raw:
        o, h, low, close, volume = map(float, row[1:6])
        if not all(math.isfinite(value) for value in (o, h, low, close, volume)) or not 0 < low <= min(o, close) <= max(o, close) <= h:
            raise ValueError("Invalid public OHLC candle")
        if row[6] != row[0] + 999:
            raise ValueError("Unexpected candle interval")
        result.append([row[0] // 1000 - start, o, h, low, close, volume, int(row[8])])
    return result


def boundaries(event, start):
    if event.get("slug") != f"btc-updown-5m-{start}" or event.get("closed") is not True:
        raise ValueError("Wrong or unresolved public market")
    metadata = event.get("eventMetadata", {})
    opening, final = float(metadata["priceToBeat"]), float(metadata["finalPrice"])
    if not all(math.isfinite(value) and value > 0 for value in (opening, final)):
        raise ValueError("Missing published opening/final price")
    market = event["markets"][0]
    names, prices = json.loads(market["outcomes"]), json.loads(market["outcomePrices"])
    winners = [name for name, price in zip(names, prices) if float(price) == 1]
    winner = "Up" if final >= opening else "Down"
    if winners != [winner]:
        raise ValueError("Published prices disagree with settled winner")
    return {"priceToBeat": opening, "finalPrice": final, "winner": winner,
            "resolutionSource": market.get("resolutionSource"), "updatedAt": event.get("updatedAt")}


def run(directory):
    directory = Path(directory)
    candidates = json.loads((directory / "candidates.json").read_text())
    target = directory / "btc-seconds.jsonl"
    done = {json.loads(line)["start"] for line in target.open()} if target.exists() else set()
    todo = [row for row in candidates if row["start"] not in done]
    reader = PublicReads()

    def fetch(candidate):
        start = candidate["start"]
        params = {"interval": "1s", "startTime": (start - 120) * 1000,
                  "endTime": (start + 300) * 1000 - 1, "limit": 1000}
        url = "https://data-api.binance.vision/api/v3/klines"
        usdt = candles(reader.get(url, {**params, "symbol": "BTCUSDT"}), start)
        event_url = f"https://gamma-api.polymarket.com/events/slug/btc-updown-5m-{start}"
        settled = boundaries(reader.get(event_url, {}), start)
        if settled["winner"] != candidate["winner"]:
            raise ValueError("Winner changed from original backtest")
        usdc = None
        if candidate["fundedOriginalHedge"] and candidate["hedged"] and not candidate["hedgeWon"]:
            usdc = candles(reader.get(url, {**params, "symbol": "BTCUSDC"}), start)
        return {"start": start, "dataType": "BINANCE_1S_PROXY_WITH_PUBLISHED_CHAINLINK_BOUNDARIES",
                "boundaries": settled, "BTCUSDT": usdt, "BTCUSDC": usdc,
                "sources": [url, event_url], "completeSeconds": True}

    stats = {"cached": len(done), "toFetch": len(todo), "written": 0, "errors": 0}
    print(json.dumps(stats), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool, target.open("a") as output:
        jobs = {pool.submit(fetch, candidate): candidate["start"] for candidate in todo}
        for job in concurrent.futures.as_completed(jobs):
            try:
                output.write(json.dumps(job.result(), separators=(",", ":")) + "\n")
                output.flush()
                stats["written"] += 1
            except Exception as error:
                stats["errors"] += 1
                with (directory / "path-fetch-errors.jsonl").open("a") as errors:
                    errors.write(json.dumps({"start": jobs[job], "error": str(error)[:400]}) + "\n")
            if (stats["written"] + stats["errors"]) % 100 == 0:
                print(json.dumps({**stats, "requests": reader.requests}), flush=True)
    stats["requests"] = reader.requests
    (directory / "path-fetch-summary.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(json.dumps(stats), flush=True)
    if stats["errors"]:
        raise ValueError("Some second-level histories missing; resume before analysis")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    run(parser.parse_args().directory)
