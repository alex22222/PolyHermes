#!/usr/bin/env python3
"""Causal historical-trade proxy replay of a BTC5m $1 entry / late reverse stake.

This research module never connects to a browser, an account, or an order endpoint.
Trade prints are not historical executable order books or Future fills.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def quote(buys, at):
    # Only prints strictly before the decision; all observations have second timestamps.
    recent = [trade for trade in buys if at - 15 <= trade[0] < at]
    if not recent or at - recent[-1][0] > 5:
        return None
    return statistics.median([p if side else 1 - p for _, side, p, _ in recent[-5:]])


def fill(buys, side, at, stake, fee_rate=0.07, slip=0, participation=0.1):
    """Proxy fills after one second latency, using at most 10% of subsequent prints.

    Completion must occur before at+6 and before market end. An incomplete proxy
    fill is treated as no fill, as with an FOK; this does not prove venue fillability.
    """
    remaining = stake
    shares = fees = 0.0
    last = None
    for second, direction, raw_price, size in buys:
        if direction != side or not at + 1 <= second < min(at + 6, 300):
            continue
        price = raw_price + slip
        if not 0 < price <= 0.99 or size <= 0:
            continue
        quantity = min(size * participation, remaining / price)
        cost = quantity * price
        shares += quantity
        fees += quantity * fee_rate * price * (1 - price)
        remaining -= cost
        last = second
        if remaining < 1e-8:
            return {"stake": stake, "shares": shares, "fee": fees, "price": stake / shares, "at": last}
    return None


def replay(round_data, reverse_stake=10, max_reverse_price=1, slip=0, extra_fee=0):
    buys = round_data["buys"]
    fee_rate = round_data.get("feeSchedule", {}).get("rate", 0.07)
    up = quote(buys, 60)
    if up is None:
        return {"skip": "ENTRY_QUOTE_UNAVAILABLE"}
    if up == 0.5:
        return {"skip": "ENTRY_TIED"}
    side = int(up > 0.5)
    initial_quote = up if side else 1 - up
    if not 0.60 <= initial_quote <= 0.97:
        return {"skip": "ENTRY_PRICE_OUTSIDE_60_97"}
    entry = fill(buys, side, 60, 1, fee_rate, slip)
    if not entry:
        return {"skip": "ENTRY_PROXY_LIQUIDITY_UNAVAILABLE"}
    if not 0.60 <= entry["price"] <= min(0.97, initial_quote + 0.02) + 1e-8:
        return {"skip": "ENTRY_FILL_PRICE_GUARD"}
    won = int(round_data["winner"] == "Up") == side
    entry_cost = 1 + entry["fee"] + extra_fee
    baseline = (entry["shares"] if won else 0) - entry_cost
    result = {"start": round_data["start"], "dateEt": datetime.fromtimestamp(round_data["start"], ET).date().isoformat(),
              "side": "Up" if side else "Down", "winner": round_data["winner"], "entryPrice": entry["price"],
              "entryFee": entry["fee"], "baselinePnl": baseline, "pnl": baseline, "principal": 1,
              "hedged": False, "hedgeWon": None, "triggerAt": None, "triggerQuote": None,
              "hedgePrice": None, "hedgeFee": None, "hedgeBlocked": None,
              "observableTailSeconds": 0}
    trigger = None
    for at in range(220, 300):
        up_at = quote(buys, at)
        if up_at is None:
            continue
        result["observableTailSeconds"] += 1
        original_mark = up_at if side else 1 - up_at
        reverse_quote = 1 - original_mark
        # Floating loss is an estimated mark, not known final settlement.
        if trigger is None and entry["shares"] * original_mark < entry_cost and reverse_quote > 0.80 + 1e-9:
            trigger = (at, reverse_quote)
    if trigger is None:
        return result
    at, reverse_quote = trigger
    result.update(triggerAt=at, triggerQuote=reverse_quote)
    if reverse_quote > max_reverse_price + 1e-9:
        result["hedgeBlocked"] = "PRICE_CAP_AT_FIRST_TRIGGER"
        return result
    hedge = fill(buys, 1 - side, at, reverse_stake, fee_rate, slip)
    if not hedge:
        result["hedgeBlocked"] = "HEDGE_PROXY_LIQUIDITY_UNAVAILABLE"
        return result
    if hedge["price"] <= 0.80 + 1e-9 or hedge["price"] > max_reverse_price + 1e-9:
        result["hedgeBlocked"] = "HEDGE_FILL_PRICE_GUARD"
        return result
    hedge_cost = reverse_stake + hedge["fee"] + reverse_stake * extra_fee
    delta = (0 if won else hedge["shares"]) - hedge_cost
    result.update(hedged=True, hedgeWon=not won, hedgePrice=hedge["price"], hedgeFee=hedge["fee"],
                  principal=1 + reverse_stake, pnl=baseline + delta)
    return result


def wilson(hits, count):
    if not count:
        return None
    z = 1.959963984540054
    p = hits / count
    scale = 1 + z * z / count
    center = (p + z * z / (2 * count)) / scale
    half = z * math.sqrt(p * (1 - p) / count + z * z / (4 * count * count)) / scale
    return [center - half, center + half]


def summarize(rows, field="pnl"):
    if not rows:
        return {"rounds": 0}
    values = [r[field] for r in rows]
    non_loss = sum(v >= -1e-9 for v in values)
    equity = peak = drawdown = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    principal = len(rows) if field == "baselinePnl" else sum(r["principal"] for r in rows)
    return {"rounds": len(rows), "nonLossRate": non_loss / len(rows), "nonLossCI95": wilson(non_loss, len(rows)),
            "totalPnlUsd": sum(values), "meanPnlUsd": statistics.mean(values), "deployedPrincipalUsd": principal,
            "roiOnDeployedPrincipal": sum(values) / principal, "maxDrawdownUsd": drawdown,
            "worstRoundUsd": min(values), "profitFactor": gains / losses if losses else None,
            "hedges": sum(r["hedged"] for r in rows),
            "unobservableTailRounds": sum(r["observableTailSeconds"] == 0 for r in rows)}


def paired_day_bootstrap(rows):
    by_day = defaultdict(list)
    for row in rows:
        by_day[row["dateEt"]].append(row["pnl"] - row["baselinePnl"])
    days = sorted(by_day)
    if len(days) < 2:
        return None
    groups = [(sum(by_day[day]), len(by_day[day])) for day in days]
    rng = random.Random(20261013)
    values = []
    for _ in range(3000):
        chosen = [rng.choice(groups) for _ in days]
        values.append(sum(v for v, _ in chosen) / sum(n for _, n in chosen))
    values.sort()
    return {"dayBlocks": len(days), "replications": len(values), "meanDeltaPerRoundUsd":
            statistics.mean(r["pnl"] - r["baselinePnl"] for r in rows),
            "ci95": [values[75], values[2924]], "note": "Few days; this is not independent out-of-sample validation."}


def analyze(directory):
    directory = Path(directory)
    input_bytes = (directory / "trades.jsonl").read_bytes()
    all_rounds = [json.loads(line) for line in input_bytes.decode().splitlines() if line.strip()]
    rounds = sorted({r["start"]: r for r in all_rounds}.values(), key=lambda r: r["start"])
    if len(rounds) != len(all_rounds):
        raise ValueError("Duplicate round cache")
    result = {"dataType": "CAUSAL_HISTORICAL_TAKER_TRADE_PROXY_NOT_FUTURE_FILLS", "rules": {
        "entry": "$1 favorite at +60, 60-97c and maximum quote increase 2c",
        "trigger": "First floating loss and opposite quote >80c in +220..299 seconds",
        "signal": "Median of latest five implied Up prices within preceding 15s; latest print age <=5s",
        "executionProxy": "1s latency, next 5s same-side BUY prints, maximum 10% participation, full amount required",
        "fees": "Actual cached market feeSchedule; extra Future fee sensitivity is hypothetical"},
        "cachedRounds": len(rounds), "sampleUtc": [datetime.fromtimestamp(rounds[0]["start"], ZoneInfo("UTC")).isoformat(),
                                                  datetime.fromtimestamp(rounds[-1]["start"], ZoneInfo("UTC")).isoformat()],
        "variants": {}}
    variants = [("reverse10", 10, 1, 0, 0), ("reverse10_cap90", 10, 0.90, 0, 0),
                ("reverse1", 1, 1, 0, 0), ("reverse10_slip1c", 10, 1, 0.01, 0),
                ("reverse10_future1pct", 10, 1, 0, 0.01)]
    for name, stake, cap, slip, extra_fee in variants:
        events = [replay(round_data, stake, cap, slip, extra_fee) for round_data in rounds]
        rows = [row for row in events if "skip" not in row]
        skipped = Counter(row["skip"] for row in events if "skip" in row)
        hedged = [row for row in rows if row["hedged"]]
        summary = {"all": summarize(rows), "pairedBaseline": summarize(rows, "baselinePnl"),
                   "entrySkips": dict(skipped), "triggered": sum(row["triggerAt"] is not None for row in rows),
                   "hedgeRefusals": dict(Counter(row["hedgeBlocked"] for row in rows if row["hedgeBlocked"])),
                   "hedgedSubset": summarize(hedged), "pairedBaselineOnHedged": summarize(hedged, "baselinePnl"),
                   "reverseWinRate": statistics.mean(row["hedgeWon"] for row in hedged) if hedged else None,
                   "reverseWinCI95": wilson(sum(row["hedgeWon"] for row in hedged), len(hedged)),
                   "avgHedgePrice": statistics.mean(row["hedgePrice"] for row in hedged) if hedged else None,
                   "pairedDayBootstrap": paired_day_bootstrap(rows), "priceBuckets": {}}
        for low, high in [(0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1)]:
            group = [row for row in hedged if low < row["hedgePrice"] <= high + 1e-9]
            summary["priceBuckets"][f"{low:.2f}-{high:.2f}"] = {
                **summarize(group), "reverseWinRate": statistics.mean(row["hedgeWon"] for row in group) if group else None}
        days = sorted({row["dateEt"] for row in rows})
        midpoint = days[len(days) // 2] if days else ""
        summary["chronologicalSplit"] = {"boundaryDateEt": midpoint,
            "earlier": summarize([row for row in rows if row["dateEt"] < midpoint]),
            "later": summarize([row for row in rows if row["dateEt"] >= midpoint])}
        summary["weekendEt"] = summarize([row for row in rows if datetime.fromtimestamp(row["start"], ET).weekday() >= 5])
        result["variants"][name] = summary
        with (directory / f"{name}-rounds.csv").open("w", newline="") as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    result["inputSha256"] = hashlib.sha256(input_bytes).hexdigest()
    (directory / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: {"all": val["all"], "hedged": val["hedgedSubset"], "reverseWinRate": val["reverseWinRate"]}
                      for key, val in result["variants"].items()}, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    analyze(parser.parse_args().directory)
