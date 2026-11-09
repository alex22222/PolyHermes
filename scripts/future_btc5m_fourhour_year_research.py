#!/usr/bin/env python3

import argparse
import concurrent.futures
import csv
import datetime
import gzip
import json
import math
import os
import statistics
import threading
import time
from pathlib import Path

import requests

from future_btc5m_fourhour import model_state, up_probability
from future_btc5m_series import CHECKPOINT_MINUTES, is_et_weekend

START = int(datetime.datetime(2025, 10, 19, tzinfo=datetime.timezone.utc).timestamp())
END = int(datetime.datetime(2026, 10, 19, tzinfo=datetime.timezone.utc).timestamp())
ORIGINAL_START = int(datetime.datetime(2026, 4, 4, tzinfo=datetime.timezone.utc).timestamp())
MODEL_FIT_END = int(datetime.datetime(2026, 4, 4, tzinfo=datetime.timezone.utc).timestamp())
PERIOD = 14400
ROOT = Path(__file__).resolve().parents[1] / "artifacts/4h-year-research"
GAMMA = "https://gamma-api.polymarket.com/events/slug/"
TRADES = "https://data-api.polymarket.com/trades"
KLINES = "https://data-api.binance.vision/api/v3/klines"


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(temporary, path)


def write_gzip_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    os.replace(temporary, path)


def read_gzip_json(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


class PublicHttp:
    def __init__(self, rate=18):
        self.rate = rate
        self.local = threading.local()
        self.lock = threading.Lock()
        self.next_slot = 0.0
        self.requests = 0

    def get(self, url, params=None, allow_404=False):
        if not hasattr(self.local, "session"):
            self.local.session = requests.Session()
            self.local.session.headers["User-Agent"] = "polyhermes-4h-year-research/1.0"
        for attempt in range(5):
            with self.lock:
                slot = max(time.monotonic(), self.next_slot)
                self.next_slot = slot + 1 / self.rate
                self.requests += 1
            time.sleep(max(0, slot - time.monotonic()))
            try:
                response = self.local.session.get(url, params=params, timeout=(8, 30), verify="/etc/ssl/cert.pem")
                if allow_404 and response.status_code == 404:
                    return None
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as error:
                if attempt == 4:
                    raise RuntimeError(f"Public read failed: {url}") from error
                time.sleep(0.5 * (attempt + 1))


def fetch_metadata(root, limit=None):
    root.mkdir(parents=True, exist_ok=True)
    markets = {row["start"]: row for row in json.loads((root / "markets.json").read_text())} if (root / "markets.json").exists() else {}
    missing = set(json.loads((root / "missing.json").read_text())) if (root / "missing.json").exists() else set()
    starts = list(range(START, END, PERIOD))
    if limit:
        starts = starts[:limit]
    todo = [start for start in starts if start not in markets and start not in missing]
    http = PublicHttp()

    def fetch(start):
        slug = f"btc-updown-4h-{start}"
        event = http.get(f"{GAMMA}{slug}", allow_404=True)
        if event is None:
            return start, None
        if event.get("slug") != slug or len(event.get("markets", [])) != 1:
            raise ValueError(f"Wrong event: {slug}")
        market = event["markets"][0]
        outcomes = json.loads(market["outcomes"])
        prices = json.loads(market["outcomePrices"])
        winners = [name for name, price in zip(outcomes, prices) if float(price) == 1]
        if market.get("closed") is not True or len(winners) != 1 or winners[0] not in ("Up", "Down"):
            raise ValueError(f"Unresolved market: {slug}")
        return start, {"start": start, "slug": slug, "conditionId": market["conditionId"], "winner": winners[0],
                       "feesEnabled": bool(market.get("feesEnabled")), "feeType": market.get("feeType"),
                       "feeSchedule": market.get("feeSchedule")}

    print(json.dumps({"stage": "metadata", "cached": len(markets), "missingCached": len(missing), "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(fetch, start): start for start in todo}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            start, row = future.result()
            if row is None:
                missing.add(start)
            else:
                markets[start] = row
            if index % 25 == 0 or index == len(todo):
                atomic_json(root / "markets.json", sorted(markets.values(), key=lambda item: item["start"]))
                atomic_json(root / "missing.json", sorted(missing))
                print(json.dumps({"stage": "metadata", "done": index, "found": len(markets), "missing": len(missing),
                                  "requests": http.requests}), flush=True)
    expected = set(starts)
    atomic_json(root / "metadata-coverage.json", {"expected": len(expected), "found": len(expected & set(markets)),
                "missing": sorted(expected & missing), "requests": http.requests})


def fetch_klines(root, limit=None):
    directory = root / "klines"
    directory.mkdir(parents=True, exist_ok=True)
    chunk_starts = list(range(START - 3600, END, 60000))
    if limit:
        chunk_starts = chunk_starts[:limit]
    todo = [start for start in chunk_starts if not (directory / f"{start}.json.gz").exists()]
    http = PublicHttp(rate=12)

    def fetch(start):
        rows = http.get(KLINES, {"symbol": "BTCUSDT", "interval": "1m", "startTime": start * 1000,
                                 "endTime": min(start + 60000, END) * 1000 - 1, "limit": 1000})
        expected = list(range(start, min(start + 60000, END), 60))
        if not isinstance(rows, list) or [row[0] // 1000 for row in rows] != expected:
            raise ValueError(f"Incomplete klines: {start}")
        write_gzip_json(directory / f"{start}.json.gz", rows)
        return start

    print(json.dumps({"stage": "klines", "cached": len(chunk_starts) - len(todo), "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, start) for start in todo]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            if index % 25 == 0 or index == len(todo):
                print(json.dumps({"stage": "klines", "done": index, "requests": http.requests}), flush=True)


def fetch_trades(root, limit=None):
    directory = root / "trades"
    directory.mkdir(parents=True, exist_ok=True)
    markets = json.loads((root / "markets.json").read_text())
    if limit:
        markets = markets[:limit]
    todo = [row for row in markets if not (directory / f"{row['start']}.json.gz").exists()]
    http = PublicHttp(rate=15)

    def page(condition, lo, hi):
        rows = http.get(TRADES, {"market": condition, "takerOnly": "true", "limit": 1000, "start": lo, "end": hi})
        if not isinstance(rows, list) or any(row["conditionId"] != condition or not lo <= row["timestamp"] <= hi for row in rows):
            raise ValueError("Trade endpoint ignored market/time boundaries")
        if len(rows) < 1000:
            return rows
        if lo == hi:
            raise ValueError("Single-second trade page cap")
        middle = (lo + hi) // 2
        return page(condition, lo, middle) + page(condition, middle + 1, hi)

    def fetch(market):
        start = market["start"]
        rows = page(market["conditionId"], start, start + PERIOD)
        buys = sorted([[row["timestamp"], int(row["outcome"] == "Up"), float(row["price"]), float(row["size"])]
                       for row in rows if row["side"] == "BUY" and row["outcome"] in ("Up", "Down")])
        write_gzip_json(directory / f"{start}.json.gz", {**market, "takerRows": len(rows), "buys": buys,
                                                        "completeRequestedInterval": True})
        return len(rows)

    print(json.dumps({"stage": "trades", "cached": len(markets) - len(todo), "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch, row): row for row in todo}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                future.result()
            except Exception as error:
                with (root / "trade-errors.jsonl").open("a") as stream:
                    stream.write(json.dumps({"start": futures[future]["start"], "error": str(error)[:400]}) + "\n")
            if index % 25 == 0 or index == len(todo):
                print(json.dumps({"stage": "trades", "done": index, "requests": http.requests}), flush=True)


def weighted_price(rows):
    size = sum(row[3] for row in rows)
    return sum(row[2] * row[3] for row in rows) / size if size > 0 else None


def median(values):
    return statistics.median(values) if values else None


def quote_at(buys, checkpoint):
    recent = [row for row in buys if checkpoint - 300 <= row[0] < checkpoint]
    implied = [100 * row[2] if row[1] else 100 * (1 - row[2]) for row in recent][-5:]
    up = median(implied)
    return up, None if up is None else 100 - up


def execution_at(buys, checkpoint, side):
    is_up = int(side == "Up")
    after = [row for row in buys if checkpoint <= row[0] < checkpoint + 120 and row[1] == is_up]
    if not after:
        after = [row for row in buys if checkpoint <= row[0] < checkpoint + 300 and row[1] == is_up]
    price = weighted_price(after)
    before = [row for row in buys if row[0] < checkpoint and row[1] == is_up]
    previous = before[-1][2] if before else None
    return price, previous


def fee_rate(market, price):
    if not market["feesEnabled"]:
        return 0.0
    schedule = market.get("feeSchedule") or {}
    if market.get("feeType") not in ("crypto_fees", "crypto_fees_v2"):
        raise ValueError("Unsupported fee regime")
    exponent = schedule["exponent"]
    return float(schedule["rate"]) * (price * (1 - price)) ** exponent


def pnl(market, price, won):
    shares = 1 / price
    fees = fee_rate(market, price) + 0.01
    return (shares if won else 0) - 1 - fees


def summarize(bets):
    if not bets:
        return {"bets": 0}
    profits = [row["pnl"] for row in bets]
    conservative = [row["conservativePnl"] for row in bets]
    wins = sum(row["won"] for row in bets)
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    longest_loss = 0
    loss_streak = 0
    for row in bets:
        cumulative += row["pnl"]
        peak = max(peak, cumulative)
        max_drawdown = min(max_drawdown, cumulative - peak)
        loss_streak = loss_streak + 1 if not row["won"] else 0
        longest_loss = max(longest_loss, loss_streak)
    mean = statistics.mean(profits)
    t = mean / (statistics.stdev(profits) / math.sqrt(len(profits))) if len(profits) > 1 and statistics.stdev(profits) else None
    return {"bets": len(bets), "wins": wins, "winRate": wins / len(bets), "avgPrice": statistics.mean(row["price"] for row in bets),
            "meanPnlPct": 100 * mean, "t": t, "cumulativeUsd": sum(profits), "maxDrawdownUsd": max_drawdown,
            "longestLossStreak": longest_loss, "conservativeMeanPnlPct": 100 * statistics.mean(conservative),
            "conservativeCumulativeUsd": sum(conservative)}


def group_summaries(bets):
    groups = {
        "all": bets,
        "weekend": [row for row in bets if row["weekend"]],
        "weekday": [row for row in bets if not row["weekend"]],
        "original_6_5m": [row for row in bets if row["start"] >= ORIGINAL_START],
        "original_weekend": [row for row in bets if row["start"] >= ORIGINAL_START and row["weekend"]],
        "overlap_model_fit": [row for row in bets if row["start"] < MODEL_FIT_END],
        "after_model_fit": [row for row in bets if row["start"] >= MODEL_FIT_END],
        "fees_disabled": [row for row in bets if not row["feesEnabled"]],
        "fees_enabled": [row for row in bets if row["feesEnabled"]],
    }
    sorted_bets = sorted(row["start"] for row in bets)
    if sorted_bets:
        midpoint = sorted_bets[len(sorted_bets) // 2]
        groups["first_half"] = [row for row in bets if row["start"] < midpoint]
        groups["second_half"] = [row for row in bets if row["start"] >= midpoint]
    months = sorted({datetime.datetime.fromtimestamp(row["checkpoint"], datetime.timezone.utc).strftime("%Y-%m") for row in bets})
    for month in months:
        groups[f"month_{month}"] = [row for row in bets if datetime.datetime.fromtimestamp(
            row["checkpoint"], datetime.timezone.utc).strftime("%Y-%m") == month]
    return {name: summarize(rows) for name, rows in groups.items()}


def analyze(root, limit=None, checkpoint_mode="current", weekend_only=None):
    markets = json.loads((root / "markets.json").read_text())
    if limit:
        markets = markets[:limit]
    candles = {}
    for path in sorted((root / "klines").glob("*.json.gz")):
        for row in read_gzip_json(path):
            candles[row[0] // 1000] = row
    minutes = CHECKPOINT_MINUTES if checkpoint_mode == "current" else tuple(range(5, 240, 5))
    weekend_only = checkpoint_mode == "current" if weekend_only is None else weekend_only
    suffix = "" if checkpoint_mode == "current" else "-legacy"
    bets = []
    signals = []
    errors = []
    for market in markets:
        trade_path = root / "trades" / f"{market['start']}.json.gz"
        if not trade_path.exists():
            errors.append({"start": market["start"], "error": "TRADES_MISSING"})
            continue
        buys = read_gzip_json(trade_path)["buys"]
        start = market["start"]
        for minute in minutes:
            checkpoint = start + minute * 60
            try:
                window = [candles[start]] + [candles[checkpoint - 60 * (61 - i)] for i in range(61)]
                if checkpoint_mode == "current":
                    p_up = model_state(start, checkpoint, window)["pUp"]
                else:
                    p_up, _, _ = up_probability(float(window[0][1]), [float(row[4]) for row in window[1:]], 240 - minute)
                up, down = quote_at(buys, checkpoint)
                side = "Up" if p_up >= 0.5 else "Down"
                probability = p_up if side == "Up" else 1 - p_up
                ask = up if side == "Up" else down
                other = down if side == "Up" else up
                reasons = []
                if weekend_only and not is_et_weekend(start):
                    reasons.append("NOT_ET_WEEKEND")
                if probability < 0.95:
                    reasons.append("MODEL_BELOW_THRESHOLD")
                if ask is None or other is None:
                    reasons.append("ASK_UNAVAILABLE")
                elif ask <= other:
                    reasons.append("MODEL_SIDE_NOT_FAVORITE")
                elif not 60 <= ask <= 97:
                    reasons.append("ASK_OUT_OF_RANGE")
                elif round(probability * 100 - ask, 6) < 3:
                    reasons.append("EDGE_TOO_SMALL")
                if reasons:
                    continue
                price, previous = execution_at(buys, checkpoint, side)
                signal = {"start": start, "checkpoint": checkpoint, "side": side, "probability": probability,
                          "upAsk": up, "downAsk": down, "weekend": is_et_weekend(start), "price": price}
                if price is None:
                    signals.append({**signal, "executed": False})
                    break
                conservative = max(price, previous or price) + 0.01
                won = market["winner"] == side
                bet = {**signal, "executed": True, "winner": market["winner"], "won": won,
                       "previousPrice": previous, "conservativePrice": conservative,
                       "feesEnabled": market["feesEnabled"], "feeType": market["feeType"],
                       "pnl": pnl(market, price, won), "conservativePnl": pnl(market, conservative, won)}
                bets.append(bet)
                signals.append(bet)
                break
            except (KeyError, ValueError) as error:
                errors.append({"start": start, "checkpoint": checkpoint, "error": str(error)})
    write_gzip_json(root / f"signals{suffix}.json.gz", signals)
    with (root / f"bets{suffix}.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["start", "checkpoint", "weekend", "side", "probability", "upAsk", "downAsk", "price", "previousPrice",
                  "conservativePrice", "winner", "won", "feesEnabled", "pnl", "conservativePnl"]
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(bets)
    report = {"sample": {"start": START, "end": END, "expectedRounds": len(range(START, END, PERIOD)),
                         "resolvedRounds": len(markets), "betsWritten": len(bets), "checkpointMode": checkpoint_mode,
                         "errors": errors[:100], "errorCount": len(errors)}, "groups": group_summaries(bets)}
    atomic_json(root / f"summary{suffix}.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--metadata", action="store_true")
    parser.add_argument("--klines", action="store_true")
    parser.add_argument("--trades", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--checkpoint-mode", choices=("current", "legacy"), default="current")
    parser.add_argument("--all-time", action="store_true")
    args = parser.parse_args()
    if args.all or args.metadata:
        fetch_metadata(args.root, args.limit)
    if args.all or args.klines:
        fetch_klines(args.root, args.limit)
    if args.all or args.trades:
        fetch_trades(args.root, args.limit)
    if args.all or args.analyze:
        analyze(args.root, args.limit, args.checkpoint_mode, False if args.all_time or args.checkpoint_mode == "legacy" else None)


if __name__ == "__main__":
    main()
