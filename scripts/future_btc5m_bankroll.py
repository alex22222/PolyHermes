#!/usr/bin/env python3
"""Replay a finite USD bankroll using public historical BTC5m trade proxies.

No network, browser, account, or order capabilities. Cash is separate from resolved
receivables; only credited proceeds can fund subsequent bets.
"""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime
import hashlib
import heapq
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from future_btc5m_late_hedge_backtest import replay

START = 1788192000
END = 1790784000
BJ = ZoneInfo("Asia/Shanghai")


class Bankroll:
    def __init__(self, initial, hedge, extra_fee=0, settlement_delay=0):
        self.initial = initial
        self.cash = initial
        self.hedge = hedge
        self.extra_fee = extra_fee
        self.settlement_delay = settlement_delay
        self.pending = []

    def _release(self, now):
        while self.pending and self.pending[0][0] <= now:
            _, _, amount = heapq.heappop(self.pending)
            self.cash += amount

    def advance(self, start, candidate):
        self._release(start + 60)
        before = self.cash
        row = {"start": start, "roundBj": datetime.fromtimestamp(start, BJ).isoformat(),
               "entered": False, "hedged": False, "cashBeforeEntry": before, "minCashInRound": before,
               "entryCost": 0, "hedgeCost": 0, "fees": 0, "payout": 0, "pnl": 0,
               "cashBlock": None, "strategySkip": candidate.get("skip"), "triggerAt": candidate.get("triggerAt")}
        if "skip" not in candidate:
            entry_cost = 1 + candidate["entryFee"] + self.extra_fee
            if self.cash + 1e-10 < entry_cost:
                row["cashBlock"] = "INSUFFICIENT_ENTRY_FUNDS"
            else:
                self.cash -= entry_cost
                payout = max(0, candidate["baselinePnl"] + 1 + candidate["entryFee"])
                row.update(entered=True, entryCost=entry_cost, fees=candidate["entryFee"] + self.extra_fee,
                           payout=payout, minCashInRound=self.cash)
                if self.hedge and candidate["hedged"]:
                    self._release(start + candidate["triggerAt"])
                    hedge_cost = 10 + candidate["hedgeFee"] + 10 * self.extra_fee
                    if self.cash + 1e-10 < hedge_cost:
                        row["cashBlock"] = "INSUFFICIENT_HEDGE_FUNDS"
                    else:
                        self.cash -= hedge_cost
                        hedge_payout = max(0, candidate["pnl"] - candidate["baselinePnl"] + 10 + candidate["hedgeFee"])
                        row.update(hedged=True, hedgeCost=hedge_cost,
                                   fees=row["fees"] + candidate["hedgeFee"] + 10 * self.extra_fee,
                                   payout=payout + hedge_payout,
                                   minCashInRound=min(row["minCashInRound"], self.cash))
                row["pnl"] = row["payout"] - row["entryCost"] - row["hedgeCost"]
                heapq.heappush(self.pending, (start + 300 + self.settlement_delay, start, row["payout"]))
        self._release(start + 300)
        receivable = sum(amount for _, _, amount in self.pending)
        row.update(cashEnd=self.cash, resolvedReceivable=receivable, equityEnd=self.cash + receivable)
        if self.cash < -1e-8 or row["minCashInRound"] < -1e-8:
            raise ValueError("Cash accounting borrowed funds")
        return row


def statistics(rows, initial):
    entered = [row for row in rows if row["entered"]]
    hedged = [row for row in entered if row["hedged"]]
    peak = initial
    drawdown = drawdown_pct = 0
    for row in rows:
        peak = max(peak, row["equityEnd"])
        drawdown = max(drawdown, peak - row["equityEnd"])
        drawdown_pct = max(drawdown_pct, (peak - row["equityEnd"]) / peak)
    last = rows[-1]
    first_entry_block = next((row["roundBj"] for row in rows if row["cashBlock"] == "INSUFFICIENT_ENTRY_FUNDS"), None)
    first_hedge_block = next((row["roundBj"] for row in rows if row["cashBlock"] == "INSUFFICIENT_HEDGE_FUNDS"), None)
    return {"initialUsd": initial, "monthEndEquityUsd": last["equityEnd"], "monthEndCashUsd": last["cashEnd"],
            "monthEndReceivableUsd": last["resolvedReceivable"], "netPnlUsd": last["equityEnd"] - initial,
            "returnOnInitialCapital": (last["equityEnd"] - initial) / initial, "marketRounds": len(rows),
            "entries": len(entered), "hedges": len(hedged), "totalFeesUsd": sum(row["fees"] for row in rows),
            "principalTurnoverUsd": len(entered) + 10 * len(hedged),
            "combinedNonLossRate": sum(row["pnl"] >= -1e-9 for row in entered) / len(entered) if entered else None,
            "hedgedNonLossRate": sum(row["pnl"] >= -1e-9 for row in hedged) / len(hedged) if hedged else None,
            "maxDrawdownUsd": drawdown, "maxDrawdownFraction": drawdown_pct,
            "minClosedRoundEquityUsd": min(row["equityEnd"] for row in rows),
            "minAvailableCashUsd": min(row["minCashInRound"] for row in rows),
            "worstRoundUsd": min(row["pnl"] for row in entered) if entered else None,
            "insufficientEntryFunds": sum(row["cashBlock"] == "INSUFFICIENT_ENTRY_FUNDS" for row in rows),
            "insufficientHedgeFunds": sum(row["cashBlock"] == "INSUFFICIENT_HEDGE_FUNDS" for row in rows),
            "firstInsufficientEntryBj": first_entry_block, "firstInsufficientHedgeBj": first_hedge_block,
            "lastEntryBj": entered[-1]["roundBj"] if entered else None,
            "firstClosedEquityBelow10Bj": next((row["roundBj"] for row in rows if row["equityEnd"] < 10), None),
            "firstClosedEquityBelow1Bj": next((row["roundBj"] for row in rows if row["equityEnd"] < 1), None)}


def run(directory):
    directory = Path(directory)
    cache = directory / "trades.jsonl"
    offsets = {}
    digest = hashlib.sha256()
    with cache.open("rb") as stream:
        while True:
            offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            digest.update(line)
            item = json.loads(line)
            start = item["start"]
            if start in offsets or start not in range(START, END, 300) or item.get("completeRequestedIntervals") is not True:
                raise ValueError("Duplicate, outside-month, or incomplete historical cache")
            offsets[start] = offset
    expected = set(range(START, END, 300))
    if set(offsets) != expected:
        raise ValueError(f"Full month unavailable: {len(expected - set(offsets))} rounds missing")
    accounts = {"baseline": Bankroll(100, hedge=False), "reverse10": Bankroll(100, hedge=True),
                "reverse10_extra1pct": Bankroll(100, hedge=True, extra_fee=0.01),
                "reverse10_creditDelay5m": Bankroll(100, hedge=True, settlement_delay=300)}
    rows = {name: [] for name in accounts}
    eligibility = Counter()
    input_checks = Counter()
    with cache.open("rb") as stream:
        for number, start in enumerate(sorted(offsets), 1):
            stream.seek(offsets[start])
            item = json.loads(stream.readline())
            candidate = replay(item)
            if "skip" not in candidate and item.get("lateFetched") is False:
                raise ValueError("An eligible entry lacks its late interval")
            eligibility[candidate.get("skip", "ELIGIBLE_ENTRY")] += 1
            input_checks["lateIntervals" if item.get("lateFetched", True) else "earlyOnlySkippedEntry"] += 1
            for name, account in accounts.items():
                rows[name].append(account.advance(start, candidate))
            if number % 1000 == 0:
                print(json.dumps({"analyzed": number, "reverseEquity": rows["reverse10"][-1]["equityEnd"]}), flush=True)
    result = {"periodBeijing": ["2026-09-01T00:00:00+08:00", "2026-10-01T00:00:00+08:00"],
              "dataType": "CAUSAL_HISTORICAL_TAKER_TRADE_PROXY_NOT_FUTURE_FILLS", "markets": len(offsets),
              "initialFundsUsd": 100, "inputSha256": digest.hexdigest(), "eligibility": dict(eligibility),
              "inputChecks": dict(input_checks), "scenarios": {},
              "assumptions": ["Fixed $1 entry and $10 reverse stake; no borrowing, deposits, or resizing",
                              "Only credited cash can fund bets; insufficient cash skips that leg",
                              "Payouts from historical market winner; all open outcomes resolved at round end in the model",
                              "Primary credit delay zero; 5-minute credit-delay scenario is separate",
                              "Closing equity includes resolved receivables, not yet available cash",
                              "Quotes/fills reuse the previous causal trade proxy; not executable books",
                              "Extra 1% fee is hypothetical, not a verified Future fee"]}
    for name, account in accounts.items():
        data = rows[name]
        summary = statistics(data, account.initial)
        if abs(sum(row["pnl"] for row in data) - summary["netPnlUsd"]) > 1e-6:
            raise ValueError("Equity does not reconcile to funded-leg profit and loss")
        daily = defaultdict(list)
        for row in data:
            daily[row["roundBj"][:10]].append(row)
        summary["daily"] = [{"dateBj": date, "endEquityUsd": day[-1]["equityEnd"],
                             "endCashUsd": day[-1]["cashEnd"], "pnlUsd": sum(row["pnl"] for row in day),
                             "entries": sum(row["entered"] for row in day), "hedges": sum(row["hedged"] for row in day)}
                            for date, day in sorted(daily.items())]
        result["scenarios"][name] = summary
        with (directory / f"{name}-bankroll.csv").open("w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    (directory / "bankroll-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    labels = {"baseline": "只买 $1", "reverse10": "叠加尾盘反向 $10", "reverse10_extra1pct": "叠加策略 + 假设额外 1% 费用",
              "reverse10_creditDelay5m": "叠加策略 + 结算到账延迟 5 分钟"}
    report = ["2026 年 9 月 BTC 五分钟盘：初始 $100 账户回放", "日期按北京时间：9 月 1 日 00:00 至 10 月 1 日 00:00。",
              "全部 8640 轮市场元数据与结算已核实；逐笔资料为历史成交代理，不能认作历史可执行订单簿或 Future 真实成交。",
              "入场：每轮第 60 秒，较高方向 60–97¢，成交代理价不高于准备报价 2¢；固定买入本金 $1。",
              "叠加：到期前最后 80 秒，首次浮亏且反方向报价严格高于 80¢，固定反向买入 $10，一次尝试，不补单。",
              "报价只用决策前成交；模拟 1 秒延迟、随后 5 秒成交量的最多 10%，完整金额不足视为未成交。",
              "余额足够支付本金及手续费才扣款；无追加本金、借款、缩单或比例复投。反向资金不足时保留原 $1 仓位。",
              "手续费使用各市场 feeSchedule。主口径假设每轮结束即可获得结算款；仅可用现金能支付新仓。",
              "额外 1% 费用仅为压力情景，Future 附加费用尚未核实。到账延迟 5 分钟单独计算；月末权益包含已结算应收款。",
              "", "策略 | 月末权益 USD | 月末现金 USD | 净盈亏 USD | 本金收益率 | 入场次数 | 反向次数 | 最大回撤 USD | 手续费 USD"]
    for name, values in result["scenarios"].items():
        report.append(f"{labels[name]} | {values['monthEndEquityUsd']:.4f} | {values['monthEndCashUsd']:.4f} | "
                      f"{values['netPnlUsd']:.4f} | {values['returnOnInitialCapital']:.2%} | {values['entries']} | "
                      f"{values['hedges']} | {values['maxDrawdownUsd']:.4f} | {values['totalFeesUsd']:.4f}")
        report.append(f"  入场资金不足 {values['insufficientEntryFunds']} 次；反向资金不足 {values['insufficientHedgeFunds']} 次；"
                      f"最后入场 {values['lastEntryBj']}；首次收盘权益低于 $1 {values['firstClosedEquityBelow1Bj']}。")
    report += ["", "资格过滤统计：" + json.dumps(result["eligibility"], ensure_ascii=False),
               "实际入场后的不亏比例不包含任何跳过轮次；不能把资金不足未交易计作成功保本。",
               "结算赢家在回放中只影响到期付款，不决定是否入场/加仓；应收款到账之前不能用于下一笔本金。",
               "该月历史回放不代表未来月收益；模型未还原 Future 的真实盘口、按钮延迟、额外费用和资金到账记录。",
               "此次没有改动实盘策略或提交订单。",
               "官方手续费公式：https://docs.polymarket.com/trading/fees",
               "复算：python3 scripts/future_btc5m_bankroll.py reports/future-btc5m-assistant/month-202609-bankroll100",
               "逐轮资金表：各 *-bankroll.csv；完整统计/每日余额：bankroll-report.json；图表：bankroll-equity.png/pdf。"]
    (directory / "bankroll-report.txt").write_text("\n".join(report) + "\n")
    print(json.dumps({name: {key: value for key, value in stats.items() if key != "daily"}
                      for name, stats in result["scenarios"].items()}, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    run(parser.parse_args().directory)
