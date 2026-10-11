#!/usr/bin/env python3
"""Export one row per Future BTC5m round for backtesting.

Joins the bridge preparation ledger, the extension Buy attempt audit, Polymarket's public
resolution and, when present, reconciled platform fills. `estPnlUsdAtQuote` prices a $1
stake at the button quote shown at preparation time: it is not a fill and excludes fees,
slippage and the platform's minimum order size. Only `fills.jsonl` rows are fill facts.
"""
from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STATE_DIR = Path(__file__).resolve().parents[1] / "reports/future-btc5m-assistant/bridge"
GAMMA_EVENTS = "https://gamma-api.polymarket.com/events?slug="
FILL_FIELDS = ("platformOrderId", "filledShares", "avgFillPrice", "feeUsd", "source")
COLUMNS = ["periodStart", "roundStartEt", "slug", "preparationState", "preparationReason", "side",
           "upQuoteCents", "downQuoteCents", "sideQuoteCents", "quoteObservedAt", "openPrice", "priceAt60s",
           "chainlinkSide", "readyAt", "buyState", "buyReason", "buyAttempts", "clickedAt",
           "clickUpQuoteCents", "clickDownQuoteCents", "clickSelectedSide", "extensionVersion",
           "resolvedOutcome", "won", "estSharesAtQuote", "estPnlUsdAtQuote",
           "platformOrderId", "filledShares", "avgFillPrice", "feeUsd", "realizedPnlUsd", "fillSource"]


def read_jsonl(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def ssl_context():
    context = ssl.create_default_context()
    # Same as the assistant: framework Python on macOS may ship without a CA bundle.
    if context.cert_store_stats()["x509_ca"] == 0 and Path("/etc/ssl/cert.pem").is_file():
        context.load_verify_locations(cafile="/etc/ssl/cert.pem")
    return context


def fetch_resolution(slug):
    # The public API rejects urllib's default User-Agent.
    request = urllib.request.Request(GAMMA_EVENTS + urllib.parse.quote(slug),
                                     headers={"User-Agent": "polyhermes-backtest-export/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15, context=ssl_context()) as response:
        events = json.load(response)
    markets = events[0].get("markets", []) if events else []
    if len(markets) != 1 or not markets[0].get("closed"):
        return None
    outcomes = json.loads(markets[0]["outcomes"])
    prices = json.loads(markets[0]["outcomePrices"])
    winners = [name for name, price in zip(outcomes, prices) if price == "1"]
    return winners[0] if len(winners) == 1 and winners[0] in ("Up", "Down") else None


def build_rows(state_dir, resolve=fetch_resolution):
    state_dir = Path(state_dir)
    rounds = {}
    for record in read_jsonl(state_dir / "preparations.jsonl"):
        # The ledger appends each transition; keep the original PENDING evidence and the final state.
        entry = rounds.setdefault(record["periodStart"], {"first": record})
        entry["last"] = record
        if record["state"] == "READY":
            entry["readyAt"] = record["updatedAt"]
    audits = {}
    for audit in read_jsonl(state_dir / "buy_attempts.jsonl"):
        audits.setdefault(audit["periodStart"], []).append(audit)
    fills = {fill["periodStart"]: fill for fill in read_jsonl(state_dir / "fills.jsonl")}
    cache_path = state_dir / "resolutions.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows = []
    for start in sorted(rounds):
        first, last = rounds[start]["first"], rounds[start]["last"]
        side = first["side"]
        side_quote = first.get("upQuoteCents" if side == "Up" else "downQuoteCents")
        attempts = sorted(audits.get(start, []), key=lambda item: item["attemptedAt"])
        clicks = [item for item in attempts if item["state"] == "CLICK_ATTEMPTED"]
        shown = clicks[0] if clicks else attempts[-1] if attempts else None
        if clicks:
            buy_state = "CLICK_ATTEMPTED"
        elif attempts:
            buy_state = "BLOCKED"
        else:
            # READY without an audit: before audits existed, or the extension did not report.
            buy_state = "NO_AUDIT" if last["state"] == "READY" else "NOT_READY"
        slug = first["slug"]
        outcome = cache.get(slug)
        if outcome is None and resolve is not None:
            try:
                outcome = resolve(slug)
            except (OSError, ValueError, KeyError, IndexError):
                outcome = None
            if outcome is not None:
                cache[slug] = outcome
        won = None if outcome is None else outcome == side
        shares = 100 / side_quote if side_quote else None
        fill = fills.get(start)
        realized = None
        if fill and outcome is not None:
            cost = fill["filledShares"] * fill["avgFillPrice"] + (fill.get("feeUsd") or 0)
            realized = round((fill["filledShares"] if won else 0) - cost, 6)
        opening, current = first.get("openPrice"), first.get("currentPrice")
        rows.append({
            "periodStart": start,
            "roundStartEt": datetime.fromtimestamp(start, ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M"),
            "slug": slug, "preparationState": last["state"], "preparationReason": last.get("reason"),
            "side": side, "upQuoteCents": first.get("upQuoteCents"), "downQuoteCents": first.get("downQuoteCents"),
            "sideQuoteCents": side_quote, "quoteObservedAt": first.get("quoteObservedAt"),
            "openPrice": opening, "priceAt60s": current,
            "chainlinkSide": None if opening is None or current is None else
                "Up" if current > opening else "Down" if current < opening else "Flat",
            "readyAt": rounds[start].get("readyAt"), "buyState": buy_state,
            "buyReason": shown["reason"] if shown else None, "buyAttempts": len(clicks),
            "clickedAt": clicks[0]["attemptedAt"] if clicks else None,
            "clickUpQuoteCents": shown["upQuoteCents"] if shown else None,
            "clickDownQuoteCents": shown["downQuoteCents"] if shown else None,
            "clickSelectedSide": shown["selectedSide"] if shown else None,
            "extensionVersion": shown["extensionVersion"] if shown else None,
            "resolvedOutcome": outcome, "won": won,
            "estSharesAtQuote": round(shares, 6) if shares else None,
            "estPnlUsdAtQuote": None if won is None or shares is None else round(shares - 1 if won else -1, 6),
            "platformOrderId": fill.get("platformOrderId") if fill else None,
            "filledShares": fill.get("filledShares") if fill else None,
            "avgFillPrice": fill.get("avgFillPrice") if fill else None,
            "feeUsd": fill.get("feeUsd") if fill else None,
            "realizedPnlUsd": realized, "fillSource": fill.get("source") if fill else None,
        })
    if resolve is not None:
        cache_path.write_text(json.dumps(cache, indent=1, sort_keys=True) + "\n")
    return rows


def summary(rows):
    ready = [row for row in rows if row["preparationState"] == "READY"]
    resolved = [row for row in ready if row["won"] is not None]
    priced = [row for row in resolved if row["estPnlUsdAtQuote"] is not None]
    clicked = [row for row in rows if row["buyState"] == "CLICK_ATTEMPTED"]
    filled = [row for row in rows if row["realizedPnlUsd"] is not None]
    return {
        "rounds": len(rows), "ready": len(ready), "clickAttempts": len(clicked),
        "blocked": sum(row["buyState"] == "BLOCKED" for row in rows),
        "readyWithoutAudit": sum(row["buyState"] == "NO_AUDIT" for row in rows),
        "resolvedReady": len(resolved), "readyWins": sum(bool(row["won"]) for row in resolved),
        # Early schema1 rounds recorded no button quote, so they cannot be priced.
        "pricedReady": len(priced),
        "estPnlUsdAtQuoteReady": round(sum(row["estPnlUsdAtQuote"] for row in priced), 4),
        "filledRounds": len(filled), "realizedPnlUsd": round(sum(row["realizedPnlUsd"] for row in filled), 4),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    parser.add_argument("--out", type=Path, help="CSV path (default: <state-dir>/backtest_rounds.csv)")
    parser.add_argument("--no-resolve", action="store_true", help="skip Polymarket resolution lookups")
    args = parser.parse_args(argv)
    rows = build_rows(args.state_dir, None if args.no_resolve else fetch_resolution)
    out = args.out or args.state_dir / "backtest_rounds.csv"
    with out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    with out.with_suffix(".jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"csv": str(out), **summary(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
