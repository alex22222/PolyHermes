#!/usr/bin/env python3
"""Audit BTC proxy paths and causal reverse-bet filters. No network or orders."""
import argparse
from collections import Counter
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics as stats
from zoneinfo import ZoneInfo

from future_btc5m_bankroll import Bankroll, statistics
from future_btc5m_late_hedge_backtest import fill, replay, summarize

BJ = ZoneInfo("Asia/Shanghai")
VALIDATION_START = int(datetime(2026, 9, 16, tzinfo=BJ).timestamp())
POLICIES = ("baseline", "original", "volatility10bp", "cap90", "agreement", "sustained10", "distance", "combined")


def features(candles, at, direction):
    # A candle at second s closes at s+1. Neither the trigger's candle nor any
    # future candle may participate in a decision at integer second at.
    past = {row[0]: row for row in candles if row[0] < at}
    opening = stats.mean(past[second][4] for second in range(-60, 0))
    closes = [past[second][4] for second in range(at - 61, at)]
    deltas = [right - left for left, right in zip(closes, closes[1:])]
    noise = stats.stdev(deltas) * math.sqrt(300 - at)
    spot_gap = direction * (closes[-1] - opening)
    twap_gap = direction * (stats.mean(closes[-60:]) - opening)
    last_trade = max((second for second, row in past.items() if row[6] > 0), default=None)
    def agrees(second):
        spot = direction * (past[second - 1][4] - opening)
        twap = direction * (stats.mean(past[t][4] for t in range(second - 60, second)) - opening)
        return spot > 0 and twap > 0
    last_minute = [past[second] for second in range(at - 60, at)]
    return {"observedSecond": at - 1, "proxyOpeningTwap60": opening,
            "rawSpot": closes[-1], "rawTwap60": stats.mean(closes[-60:]),
            "spotGapUsd": spot_gap, "twapGapUsd": twap_gap,
            "remainingSeconds": 300 - at, "noiseBudgetUsd": noise,
            "requiredSpotGapUsd": max(20, 1.5 * noise),
            "normalizedSpotGap": spot_gap / noise if noise > 1e-8 else None,
            "pre60RangeBps": (max(r[2] for r in last_minute) - min(r[3] for r in last_minute)) / opening * 10000,
            "momentum15Usd": direction * (closes[-1] - closes[-16]),
            "lastTradedSecond": last_trade,
            "lastTradeAgeSeconds": at - last_trade if last_trade is not None else None,
            "sustainedAgreement10s": all(agrees(second) for second in range(at - 9, at + 1))}


def unhedged(original, reason):
    return {**original, "hedged": False, "hedgeWon": None, "hedgePrice": None,
            "hedgeFee": None, "hedgeBlocked": reason, "principal": 1, "pnl": original["baselinePnl"]}


def policy_candidate(round_data, original, path, policy):
    if "skip" in original or policy == "original":
        return original, None
    if policy == "baseline" or original["triggerAt"] is None:
        return unhedged(original, None), None
    cap = .90 if policy in ("cap90", "combined") else 1
    if original["triggerQuote"] > cap + 1e-9:
        reason = "TRIGGER_QUOTE_ABOVE_CAP"
        return unhedged(original, reason), reason
    if policy not in ("cap90", "baseline"):
        direction = -1 if original["side"] == "Up" else 1
        value = features(path["BTCUSDT"], original["triggerAt"], direction)
        if policy == "volatility10bp" and value["pre60RangeBps"] > 10:
            reason = "PRE60_VOLATILITY_ABOVE_10BP"
            return unhedged(original, reason), reason
        if policy != "volatility10bp" and (value["spotGapUsd"] <= 0 or value["twapGapUsd"] <= 0):
            reason = "BTC_DIRECTION_OR_TWAP_MISMATCH"
            return unhedged(original, reason), reason
        if policy == "sustained10" and not value["sustainedAgreement10s"]:
            reason = "BTC_AGREEMENT_NOT_SUSTAINED_10S"
            return unhedged(original, reason), reason
        if policy in ("distance", "combined") and (value["spotGapUsd"] < value["requiredSpotGapUsd"] or value["twapGapUsd"] < 10):
            reason = "BTC_MARGIN_TOO_SMALL_FOR_RECENT_NOISE"
            return unhedged(original, reason), reason
    # A cap is implemented on each simulated print, not only its average. This
    # represents a bounded FOK proxy; no actual historical order book is known.
    eligible = [trade for trade in round_data["buys"] if trade[2] <= cap + 1e-9]
    hedge = fill(eligible, int(original["side"] == "Down"), original["triggerAt"],
                 10, round_data.get("feeSchedule", {}).get("rate", .07))
    if hedge is None:
        reason = "CAPPED_PROXY_FILL_UNAVAILABLE" if cap == .90 else "PROXY_FILL_UNAVAILABLE"
        return unhedged(original, reason), reason
    if hedge["price"] <= .80 + 1e-9:
        reason = "HEDGE_FILL_PRICE_GUARD"
        return unhedged(original, reason), reason
    # The settled winner is used only here for payment, never for filter inputs.
    reverse_won = original["side"] != original["winner"]
    pnl = original["baselinePnl"] + (hedge["shares"] if reverse_won else 0) - 10 - hedge["fee"]
    return {**original, "hedged": True, "hedgeWon": reverse_won, "hedgePrice": hedge["price"],
            "hedgeFee": hedge["fee"], "hedgeBlocked": None, "principal": 11, "pnl": pnl}, None


def tail_metrics(candles, at, reverse_direction):
    by_second = {row[0]: row for row in candles}
    value = features(candles, at, reverse_direction)
    opening = value["proxyOpeningTwap60"]
    tail = [by_second[second] for second in range(at, 300)]
    raw_end_twap = stats.mean(by_second[second][4] for second in range(240, 300))
    spot_cross = next((second + 1 for second in range(at, 300)
                       if reverse_direction * (by_second[second][4] - opening) <= 0), None)
    return {**value, "tailRangeUsd": max(row[2] for row in tail) - min(row[3] for row in tail),
            "tailRangeBps": (max(row[2] for row in tail) - min(row[3] for row in tail)) / opening * 10000,
            "maxFiveSecondMoveUsd": max((abs(by_second[second][4] - by_second[second - 5][4]) for second in range(at + 4, 300)), default=None),
            "tailSecondsWithTrades": sum(row[6] > 0 for row in tail),
            "rawEndSpot": by_second[299][4], "rawEndTwap60": raw_end_twap,
            "proxyTwapWinner": "Up" if raw_end_twap >= opening else "Down",
            "firstSpotCrossAfterTrigger": spot_cross}


def path_category(value, winner):
    if value["proxyTwapWinner"] != winner:
        category = "PROXY_SETTLEMENT_DISAGREEMENT"
    elif value["spotGapUsd"] <= 0:
        category = "BTC_ALREADY_AGAINST_HEDGE_AT_TRIGGER"
    elif value["twapGapUsd"] <= 0:
        category = "SPOT_REVERSE_TWAP_STILL_ORIGINAL"
    elif value["tailRangeBps"] >= 10:
        category = "LARGE_PROXY_REVERSAL"
    elif value["tailRangeBps"] < 5:
        category = "SMALL_PROXY_CROSSING"
    else:
        category = "MODERATE_PROXY_CROSSING"
    return category


def loss_audit(candidate, path):
    direction = -1 if candidate["side"] == "Up" else 1
    value = tail_metrics(path["BTCUSDT"], candidate["triggerAt"], direction)
    cross_check = tail_metrics(path["BTCUSDC"], candidate["triggerAt"], direction)
    actual = path["boundaries"]
    both_settle = value["proxyTwapWinner"] == cross_check["proxyTwapWinner"] == candidate["winner"]
    spot_agrees = (value["spotGapUsd"] > 0) == (cross_check["spotGapUsd"] > 0)
    twap_agrees = (value["twapGapUsd"] > 0) == (cross_check["twapGapUsd"] > 0)
    category = path_category(value, candidate["winner"]) if both_settle and spot_agrees and twap_agrees else "PRICE_SOURCE_UNCERTAINTY"
    actual_gap = actual["finalPrice"] - actual["priceToBeat"]
    offset = actual["priceToBeat"] - value["proxyOpeningTwap60"]
    return {"start": candidate["start"], "roundBj": datetime.fromtimestamp(candidate["start"], BJ).isoformat(),
            "triggerBj": datetime.fromtimestamp(candidate["start"] + candidate["triggerAt"], BJ).isoformat(),
            "reverseSide": "Down" if direction == -1 else "Up", "winner": candidate["winner"],
            "reverseFillPriceCents": candidate["hedgePrice"] * 100,
            "combinedPnlUsd": candidate["pnl"], "originalLegPnlUsd": candidate["baselinePnl"],
            "chainlinkOpeningUsd": actual["priceToBeat"], "chainlinkFinalUsd": actual["finalPrice"],
            "chainlinkFinalGapUsd": actual_gap, "category": category,
            "usdtCategory": path_category(value, candidate["winner"]),
            "usdcCategory": path_category(cross_check, candidate["winner"]), **value,
            "endTwapAnchorErrorUsd": value["rawEndTwap60"] + offset - actual["finalPrice"],
            "usdcSpotGapUsd": cross_check["spotGapUsd"], "usdcTwapGapUsd": cross_check["twapGapUsd"],
            "usdcTailRangeBps": cross_check["tailRangeBps"], "usdcProxyWinner": cross_check["proxyTwapWinner"],
            "bothPairsMatchSettlement": both_settle,
            "bothPairsTriggerDirectionAgree": spot_agrees,
            "bothPairsTriggerTwapAgree": twap_agrees}


def write_csv(path, rows):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(source, directory):
    source, directory = Path(source), Path(directory)
    candidates = {r["start"]: r for r in json.loads((directory / "candidates.json").read_text())}
    path_cache = directory / "btc-seconds.jsonl"
    paths = {}
    with path_cache.open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["start"] in paths or row.get("completeSeconds") is not True:
                raise ValueError("Duplicate or incomplete BTC seconds")
            paths[row["start"]] = row
    if set(paths) != set(candidates):
        raise ValueError("All trigger candidates need second-level data")
    losses = [loss_audit(candidate, paths[start]) for start, candidate in sorted(candidates.items())
              if candidate["fundedOriginalHedge"] and candidate["hedged"] and not candidate["hedgeWon"]]
    if len(losses) != 27:
        raise ValueError("Original funded reversal cohort changed")
    accounts = {policy: Bankroll(100, hedge=policy != "baseline") for policy in POLICIES}
    validation_accounts = {policy: Bankroll(100, hedge=policy != "baseline") for policy in POLICIES}
    ledger, validation_ledger, planned = ({policy: [] for policy in POLICIES} for _ in range(3))
    vetoes = {policy: Counter() for policy in POLICIES}
    paired = {policy: [] for policy in POLICIES}
    digest = hashlib.sha256()
    with (source / "trades.jsonl").open("rb") as stream:
        offsets = {}
        while True:
            offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            digest.update(line)
            start = json.loads(line)["start"]
            if start in offsets:
                raise ValueError("Duplicate trade round")
            offsets[start] = offset
        expected_hash = json.loads((source / "bankroll-report.json").read_text())["inputSha256"]
        if digest.hexdigest() != expected_hash or len(offsets) != 8640:
            raise ValueError("Original complete-month input changed")
        for number, start in enumerate(sorted(offsets), 1):
            stream.seek(offsets[start])
            raw = json.loads(stream.readline())
            original = replay(raw)
            path = paths.get(start)
            for policy in POLICIES:
                result, reason = policy_candidate(raw, original, path, policy)
                ledger[policy].append(accounts[policy].advance(start, result))
                if start >= VALIDATION_START:
                    validation_ledger[policy].append(validation_accounts[policy].advance(start, result))
                if "skip" not in result:
                    planned[policy].append(result)
                    if reason:
                        vetoes[policy][reason] += 1
                    if candidates.get(start, {}).get("fundedOriginalHedge"):
                        paired[policy].append({"start": start, "kept": result["hedged"],
                                               "originalReverseLost": not original["hedgeWon"],
                                               "originalCombinedProfitable": original["pnl"] >= 0,
                                               "deltaPnlUsd": result["pnl"] - original["pnl"]})
            if number % 2000 == 0:
                print(json.dumps({"analyzed": number}), flush=True)
    old = json.loads((source / "bankroll-report.json").read_text())["scenarios"]
    for policy, old_name in (("baseline", "baseline"), ("original", "reverse10")):
        if abs(ledger[policy][-1]["equityEnd"] - old[old_name]["monthEndEquityUsd"]) > 1e-7:
            raise ValueError("Unfiltered bankroll failed independent reconciliation")
    result = {"dataType": "BINANCE_1S_PROXY_NOT_EXACT_CHAINLINK_TICK_ATTRIBUTION",
              "inputSha256": digest.hexdigest(), "pathSha256": hashlib.sha256(path_cache.read_bytes()).hexdigest(),
              "marketRounds": 8640, "triggerCandidates": len(candidates), "fundedLossCohort": len(losses),
              "categoryCounts": dict(Counter(row["category"] for row in losses)),
              "bothPairsMatchSettlement": sum(row["bothPairsMatchSettlement"] for row in losses),
              "bothPairsTriggerDirectionAgree": sum(row["bothPairsTriggerDirectionAgree"] for row in losses),
              "tailRangeThresholdCounts": {str(bp): sum(row["tailRangeBps"] >= bp for row in losses) for bp in (5, 10, 20)},
              "medianTailRangeBps": stats.median(row["tailRangeBps"] for row in losses),
              "medianFinalAbsoluteGapUsd": stats.median(abs(row["chainlinkFinalGapUsd"]) for row in losses),
              "losses": losses, "policies": {},
              "limits": ["Exact Chainlink historical second-level reports unavailable; published boundaries are verified",
                         "Binance USDT and USDC are exchange proxies; opening basis anchored to preceding 60s average",
                         "Filter uses only candles completed before the first trigger; no later trigger retry",
                         "10bp large / 5bp small are descriptive thresholds, not market-provided labels",
                         "All rules are exploratory; September 16-30 is a chronological check, not independent untouched validation",
                         "Fills are bounded trade-print proxies; Future books, extra fees and real receipts unavailable",
                         "Main $100 simulation has no deposits or borrowing; validation starts a separate $100 on September 16",
                         "Live strategy unchanged; no order submitted"]}
    for policy in POLICIES:
        rows = ledger[policy]
        full = statistics(rows, 100)
        if abs(sum(r["pnl"] for r in rows) - full["netPnlUsd"]) > 1e-6:
            raise ValueError("Filtered bankroll did not reconcile")
        comparisons = paired[policy]
        result["policies"][policy] = {"bankroll": full, "plannedAllMonth": summarize(planned[policy]),
            "earlyPlanned": summarize([r for r in planned[policy] if r["start"] < VALIDATION_START]),
            "validationPlanned": summarize([r for r in planned[policy] if r["start"] >= VALIDATION_START]),
            "validationSeparate100Bankroll": statistics(validation_ledger[policy], 100),
            "vetoes": dict(vetoes[policy]),
            "originalFundedSubset": {"rounds": len(comparisons),
                "original27ReversalsPrevented": sum(r["originalReverseLost"] and not r["kept"] for r in comparisons),
                "original27ReversalsRetained": sum(r["originalReverseLost"] and r["kept"] for r in comparisons),
                "originalProfitableHedgesMissed": sum(r["originalCombinedProfitable"] and not r["kept"] for r in comparisons),
                "deltaPnlUsd": sum(r["deltaPnlUsd"] for r in comparisons)}}
        write_csv(directory / f"{policy}-bankroll.csv", rows)
    (directory / "path-filter-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    write_csv(directory / "27-reversals-btc-paths.csv", losses)
    print(json.dumps({"categories": result["categoryCounts"], "pairAgreement": result["bothPairsMatchSettlement"],
                      "policies": {key: {"cash": val["bankroll"]["monthEndEquityUsd"],
                        "caught27": val["originalFundedSubset"]["original27ReversalsPrevented"],
                        "missedProfits": val["originalFundedSubset"]["originalProfitableHedgesMissed"],
                        "validationPnl": val["validationPlanned"]["totalPnlUsd"]}
                        for key, val in result["policies"].items()}}, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    run(args.source, args.directory)
