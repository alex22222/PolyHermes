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
from collections import Counter, defaultdict
from pathlib import Path

from future_btc5m_conditions import round_conditions
from future_btc5m_fourhour_year_research import (PublicHttp, atomic_json, fee_rate, read_gzip_json,
                                                  weighted_price, write_gzip_json)
from future_btc5m_series import hourly_slug

START = int(datetime.datetime(2025, 11, 2, tzinfo=datetime.timezone.utc).timestamp())
END = int(datetime.datetime(2026, 11, 2, tzinfo=datetime.timezone.utc).timestamp())
HALF_START = int(datetime.datetime(2026, 5, 2, tzinfo=datetime.timezone.utc).timestamp())
ROOT = Path(__file__).resolve().parents[1] / "artifacts/15m-dynamic-stake-research"
GAMMA_EVENTS = "https://gamma-api.polymarket.com/events"
TRADES = "https://data-api.polymarket.com/trades"
KLINES = "https://data-api.binance.vision/api/v3/klines"
SERIES = {"15m": (10192, 900), "1h": (10114, 3600)}


def event_start(event, series, expected):
    slug = event.get("slug")
    if series == "15m":
        prefix = "btc-updown-15m-"
        if not isinstance(slug, str) or not slug.startswith(prefix):
            return None
        try:
            start = int(slug[len(prefix):])
        except ValueError:
            return None
        return start if start in expected else None
    return expected.get(slug)


def market_row(event, series, start):
    if len(event.get("markets", [])) != 1:
        raise ValueError(f"Wrong markets: {event.get('slug')}")
    market = event["markets"][0]
    outcomes = json.loads(market["outcomes"])
    prices = json.loads(market["outcomePrices"])
    winners = [name for name, price in zip(outcomes, prices) if float(price) == 1]
    if market.get("closed") is not True or len(winners) != 1 or winners[0] not in ("Up", "Down"):
        raise ValueError(f"Unresolved market: {event.get('slug')}")
    return {"start": start, "series": series, "slug": event["slug"], "conditionId": market["conditionId"],
            "winner": winners[0], "feesEnabled": bool(market.get("feesEnabled")),
            "feeType": market.get("feeType"), "feeSchedule": market.get("feeSchedule")}


def fetch_metadata(root):
    http = PublicHttp(rate=12)
    for series, (series_id, period) in SERIES.items():
        expected = ({hourly_slug(start): start for start in range(START, END, period)} if series == "1h"
                    else set(range(START, END, period)))
        expected_starts = set(expected.values()) if isinstance(expected, dict) else set(expected)
        path = root / f"markets-{series}.json"
        markets = {row["start"]: row for row in json.loads(path.read_text())} if path.exists() else {}
        oldest = None
        pages = 0
        resume_end = min(markets) + period if markets else END
        end_date_max = datetime.datetime.fromtimestamp(resume_end, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
        print(json.dumps({"stage": "metadata", "series": series, "expected": len(expected_starts),
                          "cached": len(markets)}), flush=True)
        while True:
            events = http.get(GAMMA_EVENTS, {"series_id": series_id, "closed": "true", "limit": 100,
                                             "order": "endDate", "ascending": "false", "end_date_max": end_date_max})
            if not isinstance(events, list) or not events:
                break
            valid_oldest = None
            for event in events:
                start = event_start(event, series, expected)
                if start is None:
                    continue
                valid_oldest = start if valid_oldest is None else min(valid_oldest, start)
                markets[start] = market_row(event, series, start)
            atomic_json(path, sorted(markets.values(), key=lambda row: row["start"]))
            pages += 1
            oldest = valid_oldest if oldest is None else min(oldest, valid_oldest or oldest)
            print(json.dumps({"stage": "metadata", "series": series, "pages": pages, "found": len(markets),
                              "oldest": oldest}), flush=True)
            if len(events) < 100 or (valid_oldest is not None and valid_oldest <= START):
                break
            next_end = min(event["endDate"] for event in events)
            if next_end == end_date_max:
                raise ValueError("Metadata pagination did not advance")
            end_date_max = next_end
        missing = sorted(expected_starts - set(markets))
        atomic_json(root / f"coverage-{series}.json", {"start": START, "end": END, "expected": len(expected_starts),
                    "found": len(expected_starts & set(markets)), "missing": missing})


def fetch_klines(root):
    directory = root / "klines"
    directory.mkdir(parents=True, exist_ok=True)
    chunk_starts = list(range(START - 3600, END, 60000))
    old_directory = root.parent / "4h-year-research/klines"
    todo = []
    for start in chunk_starts:
        path = directory / f"{start}.json.gz"
        old = old_directory / path.name
        if not path.exists() and old.exists():
            os.link(old, path)
        if not path.exists():
            todo.append(start)
    http = PublicHttp(rate=12)

    def fetch(start):
        rows = http.get(KLINES, {"symbol": "BTCUSDT", "interval": "1m", "startTime": start * 1000,
                                 "endTime": min(start + 60000, END) * 1000 - 1, "limit": 1000})
        expected = list(range(start, min(start + 60000, END), 60))
        if not isinstance(rows, list) or [row[0] // 1000 for row in rows] != expected:
            raise ValueError(f"Incomplete klines: {start}")
        write_gzip_json(directory / f"{start}.json.gz", rows)

    print(json.dumps({"stage": "klines", "cached": len(chunk_starts) - len(todo), "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch, start) for start in todo]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            if index % 25 == 0 or index == len(todo):
                print(json.dumps({"stage": "klines", "done": index}), flush=True)


def fetch_trades(root, series):
    directory = root / ("trades-1h-full" if series == "1h" else f"trades-{series}")
    directory.mkdir(parents=True, exist_ok=True)
    markets = json.loads((root / f"markets-{series}.json").read_text())
    todo = [row for row in markets if not (directory / f"{row['start']}.json.gz").exists()]
    http = PublicHttp(rate=25)

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
        if series == "15m":
            lo, hi = start + 90, start + 169
            recent = http.get(TRADES, {"market": market["conditionId"], "takerOnly": "true", "limit": 100,
                                       "start": start + 90, "end": start + 149})
            if (not isinstance(recent, list) or any(row["conditionId"] != market["conditionId"] or
                    not start + 90 <= row["timestamp"] < start + 150 for row in recent)
                    or any(recent[i]["timestamp"] < recent[i + 1]["timestamp"] for i in range(len(recent) - 1))):
                raise ValueError("Invalid recent trade window")
            rows = recent + page(market["conditionId"], start + 150, start + 169)
        else:
            lo, hi = start - 300, start + 3599
            rows = page(market["conditionId"], lo, hi)
        buys = sorted([[row["timestamp"], int(row["outcome"] == "Up"), float(row["price"]), float(row["size"])]
                       for row in rows if row["side"] == "BUY" and row["outcome"] in ("Up", "Down")])
        write_gzip_json(directory / f"{start}.json.gz", {**market, "requestedInterval": [lo, hi],
                        "takerRows": len(rows), "buys": buys, "completeRequestedInterval": True})

    print(json.dumps({"stage": "trades", "series": series, "cached": len(markets) - len(todo),
                      "todo": len(todo)}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(fetch, row): row for row in todo}
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                future.result()
            except Exception as error:
                with (root / f"trade-errors-{series}.jsonl").open("a") as stream:
                    stream.write(json.dumps({"start": futures[future]["start"], "error": str(error)[:400]}) + "\n")
            if index % 100 == 0 or index == len(todo):
                print(json.dumps({"stage": "trades", "series": series, "done": index, "total": len(todo),
                                  "requests": http.requests}), flush=True)


def quote_at(buys, checkpoint, lookback):
    recent = [row for row in buys if checkpoint - lookback <= row[0] < checkpoint]
    implied = [100 * row[2] if row[1] else 100 * (1 - row[2]) for row in recent][-5:]
    up = statistics.median(implied) if implied else None
    return up, None if up is None else 100 - up


def execution_at(buys, checkpoint, side):
    is_up = int(side == "Up")
    after = [row for row in buys if checkpoint <= row[0] < checkpoint + 20 and row[1] == is_up]
    before = [row for row in buys if row[0] < checkpoint and row[1] == is_up]
    return weighted_price(after), before[-1][2] if before else None


def pnl(market, price, won):
    return (1 / price if won else 0) - 1 - fee_rate(market, price) - 0.01


def summarize(bets, dynamic=False, conservative=False):
    if not bets:
        return {"bets": 0}
    stakes = [(2 if dynamic and row["price"] > 0.75 else 1) for row in bets]
    key = "conservativePnl" if conservative else "pnl"
    profits = [stake * row[key] for stake, row in zip(stakes, bets)]
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    longest = 0
    streak = 0
    for row, profit in zip(bets, profits):
        cumulative += profit
        peak = max(peak, cumulative)
        drawdown = min(drawdown, cumulative - peak)
        streak = 0 if row["won"] else streak + 1
        longest = max(longest, streak)
    total_stake = sum(stakes)
    return {"bets": len(bets), "wins": sum(row["won"] for row in bets), "winRate": sum(row["won"] for row in bets) / len(bets),
            "avgPrice": statistics.mean(row["price"] for row in bets), "totalStakeUsd": total_stake,
            "meanPnlPct": 100 * sum(profits) / total_stake, "cumulativeUsd": sum(profits),
            "maxDrawdownUsd": drawdown, "longestLossStreak": longest,
            "over75Bets": sum(row["price"] > 0.75 for row in bets)}


def scenario_groups(bets):
    periods = {"year": bets, "half": [row for row in bets if row["start"] >= HALF_START]}
    result = {}
    for period, rows in periods.items():
        groups = {"all": rows, "over75": [row for row in rows if row["price"] > 0.75],
                  "upTo75": [row for row in rows if row["price"] <= 0.75]}
        result[period] = {name: {"fixed": summarize(group), "dynamic": summarize(group, dynamic=True),
                                 "fixedConservative": summarize(group, conservative=True),
                                 "dynamicConservative": summarize(group, dynamic=True, conservative=True)}
                          for name, group in groups.items()}
    return result


def analyze(root):
    markets = json.loads((root / "markets-15m.json").read_text())
    hours = {row["start"]: row for row in json.loads((root / "markets-1h.json").read_text())}
    candles = {}
    for path in sorted((root / "klines").glob("*.json.gz")):
        for row in read_gzip_json(path):
            candles[row[0] // 1000] = row
    bets = []
    skips = Counter()
    errors = []
    for index, market in enumerate(markets, 1):
        start = market["start"]
        try:
            trade_path = root / "trades-15m" / f"{start}.json.gz"
            hour_start = start // 3600 * 3600
            hour_path = root / "trades-1h-full" / f"{hour_start}.json.gz"
            if hour_start not in hours:
                skips["HOUR_MARKET_MISSING"] += 1
                continue
            if not trade_path.exists() or not hour_path.exists():
                skips["TRADES_MISSING"] += 1
                continue
            window = [candles[start - 3600 + 60 * i] for i in range(62)]
            conditions = round_conditions(start, window, start + 121)
            buys = read_gzip_json(trade_path)["buys"]
            hour_buys = read_gzip_json(hour_path)["buys"]
            up, down = quote_at(buys, start + 150, 60)
            hour_up, hour_down = quote_at(hour_buys, start + 150, 3900)
            if up is None or up == 50 or hour_up is None or hour_up == hour_down:
                skips["QUOTE_UNAVAILABLE"] += 1
                continue
            side = "Up" if up > 50 else "Down"
            hour_side = "Up" if hour_up > hour_down else "Down"
            if side == hour_side:
                skips["SAME_AS_1H"] += 1
                continue
            if conditions["volatilityBp"] > 4.16:
                skips["HIGH_VOLATILITY"] += 1
                continue
            ask = up if side == "Up" else down
            if not 60 <= ask <= 97:
                skips["QUOTE_OUT_OF_RANGE"] += 1
                continue
            price, previous = execution_at(buys, start + 150, side)
            if price is None:
                skips["EXECUTION_UNAVAILABLE"] += 1
                continue
            if not 0.60 <= price <= 0.97:
                skips["EXECUTION_OUT_OF_RANGE"] += 1
                continue
            conservative = max(price, previous or price) + 0.01
            won = market["winner"] == side
            bets.append({"start": start, "side": side, "hourSide": hour_side, "winner": market["winner"], "won": won,
                         "ask": ask / 100, "price": price, "previousPrice": previous, "conservativePrice": conservative,
                         "volatilityBp": conditions["volatilityBp"], "feesEnabled": market["feesEnabled"],
                         "pnl": pnl(market, price, won), "conservativePnl": pnl(market, conservative, won)})
        except (KeyError, ValueError, IndexError) as error:
            errors.append({"start": start, "error": str(error)})
        if index % 2500 == 0:
            print(json.dumps({"stage": "analyze", "done": index, "total": len(markets), "bets": len(bets)}), flush=True)
    write_gzip_json(root / "bets.json.gz", bets)
    with (root / "bets.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = ["start", "side", "hourSide", "winner", "won", "ask", "price", "previousPrice", "conservativePrice",
                  "volatilityBp", "feesEnabled", "pnl", "conservativePnl"]
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(bets)
    monthly = defaultdict(list)
    for row in bets:
        month = datetime.datetime.fromtimestamp(row["start"], datetime.timezone.utc).strftime("%Y-%m")
        monthly[month].append(row)
    report = {"sample": {"start": START, "end": END, "halfStart": HALF_START,
                         "resolved15m": len(markets), "resolved1h": len(hours), "bets": len(bets),
                         "skips": dict(skips), "errorCount": len(errors), "errors": errors[:100]},
              "groups": scenario_groups(bets),
              "monthly": {month: {"fixed": summarize(rows), "dynamic": summarize(rows, dynamic=True),
                                  "fixedConservative": summarize(rows, conservative=True),
                                  "dynamicConservative": summarize(rows, dynamic=True, conservative=True)}
                          for month, rows in sorted(monthly.items())}}
    atomic_json(root / "summary.json", report)
    write_report(root, report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


def money(value):
    return f"${value:+.2f}"


def pct(value):
    return f"{value:+.2f}%"


def write_report(root, report):
    lines = ["# BTC 15 分钟反 1 小时策略：>75¢ 加注到 $2 回测", "",
             f"样本：2025-11-02 至 2026-11-02 UTC；半年子样本自 2026-05-02 起。已结算 15 分钟市场 {report['sample']['resolved15m']} 轮，"
             f"形成下注 {report['sample']['bets']} 注。规则为第 150 秒买 15 分钟热门，仅当其与 1 小时热门相反，且 60 分钟波动率 ≤4.16 bp/分钟。", "",
             "收益已扣各市场实际 Polymarket taker 费和 Future 1%。动态仓位仅在实际成交价严格 >$0.75 时投入 $2，其余投入 $1。", ""]
    for period, title in (("year", "一年跨度"), ("half", "半年子样本")):
        lines += [f"## {title}", "", "口径 | 注数 | 胜率 | 总投入 | 每注投入加权收益 | 累计盈亏 | 最大回撤 | 最长连败",
                  "---|---:|---:|---:|---:|---:|---:|---:"]
        groups = report["groups"][period]["all"]
        for key, name in (("fixed", "固定 $1"), ("dynamic", ">75¢ 改 $2"),
                          ("fixedConservative", "固定 $1，保守价"), ("dynamicConservative", "动态 $1/$2，保守价")):
            row = groups[key]
            lines.append(f"{name} | {row['bets']} | {row['winRate']:.2%} | ${row['totalStakeUsd']:.0f} | "
                         f"{pct(row['meanPnlPct'])} | {money(row['cumulativeUsd'])} | {money(row['maxDrawdownUsd'])} | {row['longestLossStreak']}")
        lines += ["", "价格分组（实际成交口径）", "", "价格 | 注数 | 胜率 | 固定 $1 每注收益 | 固定 $1 累计 | 动态累计 | 动态最大回撤",
                  "---|---:|---:|---:|---:|---:|---:"]
        for key, name in (("over75", ">75¢"), ("upTo75", "≤75¢")):
            fixed = report["groups"][period][key]["fixed"]
            dynamic = report["groups"][period][key]["dynamic"]
            if not fixed["bets"]:
                continue
            lines.append(f"{name} | {fixed['bets']} | {fixed['winRate']:.2%} | {pct(fixed['meanPnlPct'])} | "
                         f"{money(fixed['cumulativeUsd'])} | {money(dynamic['cumulativeUsd'])} | {money(dynamic['maxDrawdownUsd'])}")
        lines.append("")
    lines += ["## 按月", "", "月份（UTC） | 注数 | 胜率 | 固定 $1 累计 | 动态累计 | 固定保守累计 | 动态保守累计",
              "---|---:|---:|---:|---:|---:|---:"]
    for month, groups in report["monthly"].items():
        lines.append(f"{month} | {groups['fixed']['bets']} | {groups['fixed']['winRate']:.2%} | "
                     f"{money(groups['fixed']['cumulativeUsd'])} | {money(groups['dynamic']['cumulativeUsd'])} | "
                     f"{money(groups['fixedConservative']['cumulativeUsd'])} | {money(groups['dynamicConservative']['cumulativeUsd'])}")
    lines += ["", "## 口径与限制", "",
              "- 15 分钟市场覆盖一年窗口的 34,996/35,040 轮；可匹配的 1 小时系列从 2026-03-15 开始，因此联合回测实际覆盖 2026-03-15 至 2026-11-02，不是连续 12 个月。",
              "- 15 分钟热门由入场前 60 秒最近 5 笔 taker 买单重建；1 小时方向由当时已发生的最近 5 笔 taker 买单重建，最长回看整个小时。它们是历史成交代理，不是 Future 按钮或 CLOB 卖一价的逐笔快照，较旧的 1 小时成交可能滞后于实时盘口。",
              "- 实际口径取第 150–170 秒同方向 taker 买入 VWAP，窗口内没有同方向成交则跳过；保守口径取实际均价与入场前最后成交价的较高者再加 1¢。",
              "- $2 与 $1 使用相同成交价，未模拟加量造成的盘口冲击，也无法还原页面与盘口 3¢ 偏差检查、点击延迟和 Future 最小下单限制。",
              "- 一年是时间跨度，不代表公开市场连续无缺；精确覆盖与跳过原因见 summary.json。此次仅研究，未改生产配置或提交订单。", "",
              f"分析跳过统计：`{json.dumps(report['sample']['skips'], ensure_ascii=False)}`；数据/计算错误 {report['sample']['errorCount']} 条。", ""]
    (root / "report.md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--metadata", action="store_true")
    parser.add_argument("--klines", action="store_true")
    parser.add_argument("--trades", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.all or args.metadata:
        fetch_metadata(args.root)
    if args.all or args.klines:
        fetch_klines(args.root)
    if args.all or args.trades:
        fetch_trades(args.root, "1h")
        fetch_trades(args.root, "15m")
    if args.all or args.analyze:
        analyze(args.root)


if __name__ == "__main__":
    main()
