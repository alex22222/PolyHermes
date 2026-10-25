"""Read-only per-round audit of the Future bridge ledgers: why a round was or was not bought.

For each round start it prints the 15m strategy decision, the ticket's state history, every buy
attempt (with the price-gate reason), whether a read-only preflight passed, and a one-line
verdict naming the step that stopped the round. Nothing is written.

Usage (from the repository root on the machine running the assistant):
    python3 scripts/future_btc5m_round_audit.py 1792704600 1792709100 ...
    python3 scripts/future_btc5m_round_audit.py --state-dir reports/future-btc5m-assistant/bridge <starts>
"""

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


STATE_DIR = Path(__file__).resolve().parents[1] / "reports/future-btc5m-assistant/bridge"
CST = timezone(timedelta(hours=8))


def records(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def at(value):
    return datetime.fromtimestamp(value, CST).strftime("%H:%M:%S") if isinstance(value, (int, float)) else "—"


def cents(value):
    return "—" if value is None else f"{value}¢"


def verdict(decision, tickets, attempts, preflight):
    if decision is None:
        return "未做判断：判断窗口里被前置条件拦下（浏览器未连接/页面不在当前盘/票据检查/按钮报价/1小时盘口/波动数据/开关），这些原因不写日志"
    if decision["decision"] == "SKIP_SAME_AS_1H":
        return f"与1小时同向跳过：实盘看到 15m 热门 {decision['buttonSide']}，1小时热门 {decision['hourSide']}"
    if decision["decision"] == "SKIP_HIGH_VOLATILITY":
        return f"R1 高波动跳过（波动 {decision.get('conditions', {}).get('volatilityBp', 0):.2f}）"
    states = [ticket.get("state") for ticket in tickets]
    if "READY" not in states:
        last = tickets[-1] if tickets else None
        return f"已决定买入但票据未就绪：{last.get('state')} / {last.get('reason')}" if last else "已决定买入但没有票据记录"
    if not attempts:
        return "票据就绪但扩展没有发起点击（页面/面板未运行或在等待价格门槛，未写买入记录）"
    clicked = [a for a in attempts if a.get("state") == "CLICK_ATTEMPTED"]
    if clicked:
        return "已点击买入（若钱包无成交，看平台结果）"
    return "价格门槛拦截：" + "、".join(sorted({a.get("reason") or "?" for a in attempts}))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("starts", nargs="+", type=int, help="15m round start timestamps (seconds)")
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    args = parser.parse_args()
    decisions = [r for r in records(args.state_dir / "strategy_decisions.jsonl") if r.get("series") == "15m"]
    tickets = records(args.state_dir / "preparations.jsonl")
    attempts = records(args.state_dir / "buy_attempts.jsonl")
    passes = records(args.state_dir / "preflight.jsonl")
    for start in args.starts:
        decision = next((r for r in decisions if r.get("periodStart") == start), None)
        round_tickets = sorted((r for r in tickets if r.get("id") == f"future-btc15m-prepare:{start}"),
                               key=lambda r: r.get("updatedAt") or 0)
        round_attempts = [r for r in attempts if r.get("periodStart") == start]
        preflight = any(r.get("periodStart") == start and "btc-updown-15m-" in (r.get("marketUrl") or "") for r in passes)
        print(f"\n=== {datetime.fromtimestamp(start, CST):%m-%d %H:%M} 北京时间（{start}）===")
        if decision:
            c = decision.get("conditions") or {}
            print(f"  判断 {at(decision.get('decidedAt'))}：{decision['decision']}  15m 涨{decision.get('upQuoteCents')}¢/跌{decision.get('downQuoteCents')}¢ → {decision.get('buttonSide')}"
                  f"  1h 卖价 涨{decision.get('hourUpAskCents')}¢/跌{decision.get('hourDownAskCents')}¢ → {decision.get('hourSide')}"
                  + (f"  波动 {c['volatilityBp']:.2f}" if "volatilityBp" in c else ""))
        else:
            print("  判断：无记录")
        for ticket in round_tickets:
            print(f"  票据 {at(ticket.get('updatedAt'))}：{ticket.get('state')} {ticket.get('side')} 涨{ticket.get('upQuoteCents')}¢/跌{ticket.get('downQuoteCents')}¢"
                  + (f"  原因 {ticket['reason']}" if ticket.get("reason") else ""))
        for attempt in round_attempts:
            print(f"  买入 {at(attempt.get('attemptedAt') or attempt.get('armedAt'))}：{attempt.get('state')} {attempt.get('reason') or ''}"
                  f"  页面 涨{attempt.get('upQuoteCents')}¢/跌{attempt.get('downQuoteCents')}¢"
                  f"  盘口 涨{cents(attempt.get('marketUpAskCents'))}/跌{cents(attempt.get('marketDownAskCents'))}  扩展 {attempt.get('extensionVersion')}")
        print(f"  预检通过：{'是' if preflight else '否'}")
        print(f"  结论：{verdict(decision, round_tickets, round_attempts, preflight)}")


if __name__ == "__main__":
    main()
