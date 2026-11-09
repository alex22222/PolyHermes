#!/usr/bin/env python3

import argparse
import concurrent.futures
import csv
import datetime
import json
import math
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from future_btc5m_fourhour_year_research import (PublicHttp, atomic_json, fee_rate, read_gzip_json, summarize,
                                                 write_gzip_json)

ET = ZoneInfo("America/New_York")
FETCH_START = datetime.date(2026, 1, 1)
FETCH_END = datetime.date(2026, 10, 19)
MODEL_START = int(datetime.datetime(2024, 10, 5, tzinfo=datetime.timezone.utc).timestamp())
MODEL_END = int(datetime.datetime(2026, 4, 4, tzinfo=datetime.timezone.utc).timestamp())
DATA_END = int(datetime.datetime(2026, 10, 19, tzinfo=datetime.timezone.utc).timestamp())
SELECTION_START = int(datetime.datetime(2026, 4, 1, tzinfo=datetime.timezone.utc).timestamp())
OOS_START = int(datetime.datetime(2026, 7, 1, tzinfo=datetime.timezone.utc).timestamp())
ROOT = Path(__file__).resolve().parents[1] / "artifacts/1d-research"
GAMMA = "https://gamma-api.polymarket.com/events/slug/"
TRADES = "https://data-api.polymarket.com/trades"
KLINES = "https://data-api.binance.vision/api/v3/klines"
BUCKETS = (15, 30, 60, 120, 240, 480, 720, 1500)


def slug_for(date):
    return f"bitcoin-up-or-down-on-{date.strftime('%B').lower()}-{date.day}-{date.year}"


def previous_noon(end):
    local = datetime.datetime.fromtimestamp(end, ET)
    previous = datetime.datetime.combine(local.date() - datetime.timedelta(days=1), datetime.time(12), ET)
    return int(previous.timestamp())


def fetch_metadata(root, limit=None):
    root.mkdir(parents=True, exist_ok=True)
    markets = {row["end"]: row for row in json.loads((root / "markets.json").read_text())} if (root / "markets.json").exists() else {}
    missing = set(json.loads((root / "missing.json").read_text())) if (root / "missing.json").exists() else set()
    dates = [FETCH_START + datetime.timedelta(days=i) for i in range((FETCH_END - FETCH_START).days + 1)]
    if limit:
        dates = dates[:limit]
    todo = [date for date in dates if int(datetime.datetime.combine(date, datetime.time(12), ET).timestamp()) not in markets and date.isoformat() not in missing]
    http = PublicHttp()

    def fetch(date):
        slug = slug_for(date)
        event = http.get(f"{GAMMA}{slug}", allow_404=True)
        if event is None:
            return date.isoformat(), None
        market = event["markets"][0]
        if not market.get("closed"):
            return date.isoformat(), {"pending": True}
        end = int(datetime.datetime.fromisoformat(market["endDate"].replace("Z", "+00:00")).timestamp())
        start = previous_noon(end)
        outcomes = json.loads(market["outcomes"])
        prices = [float(value) for value in json.loads(market["outcomePrices"])]
        if prices == [1, 0]:
            winner = "Up"
        elif prices == [0, 1]:
            winner = "Down"
        elif prices == [0.5, 0.5]:
            winner = "Tie"
        else:
            raise ValueError(f"Unresolved market: {slug}")
        metadata = event.get("eventMetadata") or {}
        opening = float(metadata["priceToBeat"]) if metadata.get("priceToBeat") is not None else None
        final = float(metadata["finalPrice"]) if metadata.get("finalPrice") is not None else None
        if opening is not None and final is not None:
            computed = "Up" if final > opening else "Down" if final < opening else "Tie"
            if computed != winner:
                raise ValueError(f"Settlement mismatch: {slug}")
        return date.isoformat(), {"start": start, "end": end, "slug": slug, "conditionId": market["conditionId"],
                                  "winner": winner, "priceToBeat": opening, "finalPrice": final,
                                  "volume": float(market.get("volume") or 0), "feesEnabled": bool(market.get("feesEnabled")),
                                  "feeType": market.get("feeType"), "feeSchedule": market.get("feeSchedule")}

    print(json.dumps({"stage": "metadata", "cached": len(markets), "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(fetch, date) for date in todo]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            key, row = future.result()
            if row is None:
                missing.add(key)
            elif not row.get("pending"):
                markets[row["end"]] = row
            if index % 25 == 0 or index == len(todo):
                atomic_json(root / "markets.json", sorted(markets.values(), key=lambda item: item["end"]))
                atomic_json(root / "missing.json", sorted(missing))
                print(json.dumps({"stage": "metadata", "done": index, "found": len(markets), "requests": http.requests}), flush=True)


def fetch_klines(root, limit=None):
    directory = root / "klines"
    directory.mkdir(parents=True, exist_ok=True)
    starts = list(range(MODEL_START, DATA_END, 60000))
    if limit:
        starts = starts[:limit]
    todo = [start for start in starts if not (directory / f"{start}.json.gz").exists()]
    http = PublicHttp(rate=12)

    def fetch(start):
        rows = http.get(KLINES, {"symbol": "BTCUSDT", "interval": "1m", "startTime": start * 1000,
                                 "endTime": min(start + 60000, DATA_END) * 1000 - 1, "limit": 1000})
        expected = list(range(start, min(start + 60000, DATA_END), 60))
        if not isinstance(rows, list) or [row[0] // 1000 for row in rows] != expected:
            raise ValueError(f"Incomplete klines: {start}")
        write_gzip_json(directory / f"{start}.json.gz", rows)

    print(json.dumps({"stage": "klines", "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, start) for start in todo]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            if index % 50 == 0 or index == len(todo):
                print(json.dumps({"stage": "klines", "done": index, "requests": http.requests}), flush=True)


def fetch_trades(root, limit=None):
    directory = root / "trades"
    directory.mkdir(parents=True, exist_ok=True)
    markets = json.loads((root / "markets.json").read_text())
    if limit:
        markets = markets[:limit]
    todo = [row for row in markets if not (directory / f"{row['end']}.json.gz").exists()]
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
        start, end = market["start"], market["end"]
        rows = page(market["conditionId"], start, end)
        buys = sorted([[row["timestamp"], int(row["outcome"] == "Up"), float(row["price"]), float(row["size"])]
                       for row in rows if row["side"] == "BUY" and row["outcome"] in ("Up", "Down")])
        write_gzip_json(directory / f"{end}.json.gz", {**market, "takerRows": len(rows), "buys": buys,
                                                      "completeRequestedInterval": True})

    print(json.dumps({"stage": "trades", "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(fetch, row): row for row in todo}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                future.result()
            except Exception as error:
                with (root / "trade-errors.jsonl").open("a") as stream:
                    stream.write(json.dumps({"end": futures[future]["end"], "error": str(error)[:400]}) + "\n")
            if index % 25 == 0 or index == len(todo):
                print(json.dumps({"stage": "trades", "done": index, "requests": http.requests}), flush=True)


def load_candles(root):
    candles = {}
    for path in sorted((root / "klines").glob("*.json.gz")):
        for row in read_gzip_json(path):
            candles[row[0] // 1000] = row
    return candles


def validate_settlements(markets, candles):
    for market in markets:
        opening_candidates = [float(candles[market["start"] - 60][4]), float(candles[market["start"]][4])]
        final_candidates = [float(candles[market["end"] - 60][4]), float(candles[market["end"]][4])]
        if market["priceToBeat"] is not None and not any(abs(value - market["priceToBeat"]) <= 0.01 for value in opening_candidates):
            raise ValueError(f"Opening candle mismatch: {market['slug']}")
        if market["finalPrice"] is not None and not any(abs(value - market["finalPrice"]) <= 0.01 for value in final_candidates):
            raise ValueError(f"Final candle mismatch: {market['slug']}")
        opening = market["priceToBeat"] if market["priceToBeat"] is not None else opening_candidates[-1]
        final = market["finalPrice"] if market["finalPrice"] is not None else final_candidates[-1]
        computed = "Up" if final > opening else "Down" if final < opening else "Tie"
        if computed != market["winner"]:
            raise ValueError(f"Binance settlement mismatch: {market['slug']}")


def noon(date):
    return int(datetime.datetime.combine(date, datetime.time(12), ET).timestamp())


def z_score(candles, start, checkpoint, end, opening_price=None):
    opening = opening_price if opening_price is not None else float(candles[start][4])
    window = [candles[checkpoint - 60 * (61 - i)] for i in range(61)]
    closes = [float(row[4]) for row in window]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, 61)]
    mean = sum(returns) / 60
    sigma = max(1e-5, math.sqrt(sum((value - mean) ** 2 for value in returns) / 59))
    minutes_left = int((end - checkpoint) // 60)
    z = math.log(closes[-1] / opening) / (sigma * math.sqrt(minutes_left))
    return z, minutes_left


def fit_model(candles):
    samples = {bucket: [] for bucket in BUCKETS}
    date = datetime.date(2024, 10, 5)
    end_date = datetime.date(2026, 4, 3)
    while date <= end_date:
        start = noon(date)
        end = noon(date + datetime.timedelta(days=1))
        for checkpoint in range(start + 900, end, 900):
            try:
                z, left = z_score(candles, start, checkpoint, end)
                final = float(candles[end][4])
                opening = float(candles[start][4])
                if final != opening:
                    bucket = next(bucket for bucket in BUCKETS if left <= bucket)
                    samples[bucket].append((z, int(final > opening)))
            except (KeyError, ValueError):
                pass
        date += datetime.timedelta(days=1)
    model = {}
    for bucket, rows in samples.items():
        z = np.clip(np.array([row[0] for row in rows]), -12, 12)
        y = np.array([row[1] for row in rows], dtype=float)
        x = np.column_stack([np.ones(len(z)), z])
        beta = np.zeros(2)
        for _ in range(60):
            p = 1 / (1 + np.exp(-x @ beta))
            w = np.maximum(p * (1 - p), 1e-8)
            h = x.T @ (x * w[:, None]) + np.eye(2) * 1e-4
            gradient = x.T @ (y - p) - beta * 1e-4
            delta = np.linalg.solve(h, gradient)
            beta += delta
            if np.max(np.abs(delta)) < 1e-8:
                break
        model[str(bucket)] = {"a": float(beta[0]), "b": float(beta[1]), "samples": len(rows)}
    return model


def probability(model, left, z):
    bucket = next(bucket for bucket in BUCKETS if left <= bucket)
    coefficients = model[str(bucket)]
    z = max(-12, min(12, z))
    return 1 / (1 + math.exp(-(coefficients["a"] + coefficients["b"] * z)))


def quote_at(buys, checkpoint):
    recent = [row for row in buys if checkpoint - 300 <= row[0] < checkpoint]
    implied = [100 * row[2] if row[1] else 100 * (1 - row[2]) for row in recent][-5:]
    if not implied:
        return None, None
    import statistics
    up = statistics.median(implied)
    return up, 100 - up


def execution_at(buys, checkpoint, side, end):
    is_up = int(side == "Up")
    after = [row for row in buys if checkpoint <= row[0] < min(checkpoint + 120, end) and row[1] == is_up]
    if not after:
        after = [row for row in buys if checkpoint <= row[0] < min(checkpoint + 300, end) and row[1] == is_up]
    size = sum(row[3] for row in after)
    price = sum(row[2] * row[3] for row in after) / size if size else None
    before = [row for row in buys if row[0] < checkpoint and row[1] == is_up]
    return price, before[-1][2] if before else None


def make_bet(market, checkpoint, side, price, previous):
    if price is None:
        return None
    conservative = max(price, previous or price) + 0.01
    won = market["winner"] == side
    outcome = 1 if won else 0.5 if market["winner"] == "Tie" else 0

    def pnl(entry):
        shares = 1 / entry
        return shares * outcome - 1 - fee_rate(market, entry) - 0.01

    local = datetime.datetime.fromtimestamp(market["start"], ET)
    return {"start": market["start"], "end": market["end"], "checkpoint": checkpoint, "side": side, "price": price,
            "previousPrice": previous, "conservativePrice": conservative, "winner": market["winner"], "won": won,
            "weekend": local.weekday() >= 5, "feesEnabled": market["feesEnabled"], "feeType": market["feeType"],
            "pnl": pnl(price), "conservativePnl": pnl(conservative)}


def summary_1d(bets):
    result = summarize(bets)
    ties = sum(row["winner"] == "Tie" for row in bets)
    decided = len(bets) - ties
    result["ties"] = ties
    result["winRate"] = result["wins"] / decided if decided else None
    return result


def checkpoints_for(market, candles, model):
    output = []
    for checkpoint in range(market["start"] + 300, market["end"], 300):
        try:
            z, left = z_score(candles, market["start"], checkpoint, market["end"], market["priceToBeat"])
            p_up = probability(model, left, z)
            up, down = quote_at(market["buys"], checkpoint)
            output.append({"checkpoint": checkpoint, "left": left, "pUp": p_up, "up": up, "down": down})
        except (KeyError, ValueError):
            continue
    return output


def model_rule(market, checkpoints, threshold, edge):
    for point in checkpoints:
        p_up = point["pUp"]
        side = "Up" if p_up >= 0.5 else "Down"
        confidence = p_up if side == "Up" else 1 - p_up
        ask = point["up"] if side == "Up" else point["down"]
        other = point["down"] if side == "Up" else point["up"]
        if confidence < threshold or ask is None or other is None or ask <= other or not 60 <= ask <= 97:
            continue
        if round(confidence * 100 - ask, 6) < edge:
            continue
        price, previous = execution_at(market["buys"], point["checkpoint"], side, market["end"])
        bet = make_bet(market, point["checkpoint"], side, price, previous)
        if bet:
            bet.update({"probability": confidence, "upAsk": point["up"], "downAsk": point["down"]})
            return bet
        return None
    return None


def favorite_rule(market, checkpoints, remaining, minimum):
    for point in checkpoints:
        if point["left"] != remaining:
            continue
        up, down = point["up"], point["down"]
        if up is None or down is None or up == down:
            return None
        side = "Up" if up > down else "Down"
        favorite = max(up, down)
        if not minimum <= favorite <= 97:
            return None
        price, previous = execution_at(market["buys"], point["checkpoint"], side, market["end"])
        bet = make_bet(market, point["checkpoint"], side, price, previous)
        if bet:
            bet.update({"upAsk": up, "downAsk": down})
            return bet
        return None
    return None


def analyze(root, limit=None):
    markets = json.loads((root / "markets.json").read_text())
    if limit:
        markets = markets[:limit]
    candles = load_candles(root)
    validate_settlements(markets, candles)
    model_path = root / "model.json"
    if model_path.exists():
        model = json.loads(model_path.read_text())
    else:
        model = fit_model(candles)
        atomic_json(model_path, model)
    enriched = []
    for market in markets:
        trade_path = root / "trades" / f"{market['end']}.json.gz"
        if not trade_path.exists():
            continue
        market = {**market, "buys": read_gzip_json(trade_path)["buys"]}
        checkpoints = checkpoints_for(market, candles, model)
        enriched.append((market, checkpoints))
    definitions = []
    for threshold in (0.85, 0.90, 0.93, 0.95, 0.97):
        for edge in (1, 2, 3, 5):
            definitions.append({"kind": "model", "threshold": threshold, "edge": edge,
                                "run": lambda market, points, t=threshold, e=edge: model_rule(market, points, t, e)})
    for remaining in (5, 15, 30, 60, 120, 240, 480, 720):
        for minimum in (60, 80, 85, 90, 93, 95):
            definitions.append({"kind": "favorite", "remaining": remaining, "minimum": minimum,
                                "run": lambda market, points, r=remaining, m=minimum: favorite_rule(market, points, r, m)})
    candidates = []
    all_bets = {}
    for definition in definitions:
        key = f"{definition['kind']}:{definition.get('threshold', definition.get('remaining'))}:{definition.get('edge', definition.get('minimum'))}"
        bets = []
        for market, checkpoints in enriched:
            bet = definition["run"](market, checkpoints)
            if bet:
                bet["rule"] = key
                bets.append(bet)
        all_bets[key] = bets
        periods = {"all": bets, "selection": [row for row in bets if SELECTION_START <= row["checkpoint"] < OOS_START],
                   "oos": [row for row in bets if row["checkpoint"] >= OOS_START],
                   "weekend": [row for row in bets if row["weekend"]],
                   "weekday": [row for row in bets if not row["weekend"]]}
        candidates.append({**{k: v for k, v in definition.items() if k != "run"}, "rule": key,
                           "groups": {name: summary_1d(rows) for name, rows in periods.items()}})
    atomic_json(root / "all-bets.json", all_bets)
    atomic_json(root / "candidates.json", candidates)
    with (root / "candidates.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["rule", "kind", "threshold", "edge", "remaining", "minimum", "bets", "winRate", "meanPnlPct", "t",
                  "selectionBets", "selectionPnlPct", "oosBets", "oosWinRate", "oosPnlPct", "oosT", "oosConservativePct"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in candidates:
            all_group, selection, oos = row["groups"]["all"], row["groups"]["selection"], row["groups"]["oos"]
            writer.writerow({**{k: v for k, v in row.items() if k in ("rule", "kind", "threshold", "edge", "remaining", "minimum")},
                             "bets": all_group["bets"], "winRate": all_group.get("winRate"), "meanPnlPct": all_group.get("meanPnlPct"),
                             "t": all_group.get("t"), "selectionBets": selection["bets"], "selectionPnlPct": selection.get("meanPnlPct"),
                             "oosBets": oos["bets"], "oosWinRate": oos.get("winRate"), "oosPnlPct": oos.get("meanPnlPct"),
                             "oosT": oos.get("t"), "oosConservativePct": oos.get("conservativeMeanPnlPct")})
    for kind in ("model", "favorite"):
        eligible = [row for row in candidates if row["kind"] == kind and row["groups"]["selection"]["bets"] >= 10]
        if eligible:
            best = max(eligible, key=lambda row: row["groups"]["selection"]["meanPnlPct"])
            atomic_json(root / f"best-{kind}.json", best)
            atomic_json(root / f"best-{kind}-bets.json", all_bets[best["rule"]])
    print(json.dumps({"markets": len(markets), "model": model,
                      "bestModel": json.loads((root / "best-model.json").read_text()) if (root / "best-model.json").exists() else None,
                      "bestFavorite": json.loads((root / "best-favorite.json").read_text()) if (root / "best-favorite.json").exists() else None},
                     ensure_ascii=False, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--metadata", action="store_true")
    parser.add_argument("--klines", action="store_true")
    parser.add_argument("--trades", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.all or args.metadata:
        fetch_metadata(args.root, args.limit)
    if args.all or args.klines:
        fetch_klines(args.root, args.limit)
    if args.all or args.trades:
        fetch_trades(args.root, args.limit)
    if args.all or args.analyze:
        analyze(args.root, args.limit)


if __name__ == "__main__":
    main()
