"""Paper shadow evaluation of regime filter G1 for the btc15m_counter_1h strategy.

Rule G1 (pre-registered 2026-11-09; research: btc-15m-research/round5.py on the
2026-10-17..11-07 live decisions and three years of 15m klines): a 15m PREPARE round
qualifies only when |trend60Bp| >= 15 at decision time. Real trading rules are
unchanged; this module shadows every 15m PREPARE decision with a $1 paper trade at
the decision-time button quote and resolves it from Binance 15m klines (open vs close
of the round), so the page can compare baseline vs filtered paper results live.

Paper P&L per $1 staked at price p cents: win -> (100 - p) / p dollars, loss -> -1.
The platform settles on the Chainlink TWAP, so a Binance-resolved outcome is an
estimate and is labelled as such on the page.
"""

import json
import os

from future_btc5m_conditions import BINANCE_KLINES

LEDGER_NAME = "paper_regime.jsonl"
RULE = "G1 |trend60|>=15bp"
MIN_TREND60_BP = 15.0
ROUND_SECONDS = 900
# Binance's final 15m close is published within seconds of round end; 60s is conservative.
RESOLVE_AFTER_END = 60


def _path(state_dir):
    return state_dir / LEDGER_NAME


def _load(state_dir):
    try:
        with _path(state_dir).open(encoding="utf-8") as ledger:
            rows = [json.loads(line) for line in ledger if line.strip()]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as error:
        raise OSError("PAPER_LEDGER_INVALID") from error
    if any(not isinstance(row, dict) or type(row.get("periodStart")) is not int for row in rows):
        raise OSError("PAPER_LEDGER_INVALID")
    return rows


def _save(state_dir, rows):
    tmp = _path(state_dir).with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as ledger:
        for row in rows:
            ledger.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        ledger.flush()
        os.fsync(ledger.fileno())
    os.replace(tmp, _path(state_dir))


def record(state_dir, *, period_start, side, price_cents, trend60_bp, volatility_bp, now):
    """Shadow one 15m PREPARE decision with a pending $1 paper trade; idempotent per round."""
    rows = _load(state_dir)
    if any(row["periodStart"] == period_start for row in rows):
        return
    rows.append({"schemaVersion": 1, "rule": RULE, "periodStart": period_start, "side": side,
                 "priceCents": price_cents, "trend60Bp": trend60_bp, "volatilityBp": volatility_bp,
                 "g1Eligible": abs(trend60_bp) >= MIN_TREND60_BP, "state": "PENDING", "createdAt": now,
                 "outcome": None, "win": None, "roi": None, "binanceOpen": None, "binanceClose": None,
                 "resolvedAt": None})
    _save(state_dir, rows)


def _kline_url(start, end):
    return (f"{BINANCE_KLINES}?symbol=BTCUSDT&interval=15m"
            f"&startTime={start * 1000}&endTime={end * 1000}&limit=1000")


def resolve(state_dir, fetch_json, now):
    """Resolve every pending paper trade whose round ended RESOLVE_AFTER_END seconds ago.

    fetch_json(url) -> parsed JSON (the assistant's curl_json). Returns the number resolved."""
    rows = _load(state_dir)
    due = [row for row in rows
           if row["state"] == "PENDING" and row["periodStart"] + ROUND_SECONDS + RESOLVE_AFTER_END <= now]
    if not due:
        return 0
    start = min(row["periodStart"] for row in due)
    end = max(row["periodStart"] for row in due) + ROUND_SECONDS
    candles = fetch_json(_kline_url(start, end))
    by_open = {int(row[0]) // 1000: (float(row[1]), float(row[4])) for row in candles}
    resolved = 0
    for row in due:
        kline = by_open.get(row["periodStart"])
        if kline is None:
            continue
        open_, close = kline
        outcome = "Up" if close > open_ else "Down" if close < open_ else "Flat"
        win = outcome == row["side"] if outcome != "Flat" else None
        price = row["priceCents"]
        row.update(state="RESOLVED", outcome=outcome, win=win,
                   roi=(100 - price) / price if win else (-1.0 if win is False else 0.0),
                   binanceOpen=open_, binanceClose=close, resolvedAt=now)
        resolved += 1
    if resolved:
        _save(state_dir, rows)
    return resolved


def _stats(rows):
    settled = [row for row in rows if row["state"] == "RESOLVED" and row["win"] is not None]
    wins = sum(1 for row in settled if row["win"])
    total = sum(row["roi"] for row in settled)
    return {"trades": len(rows), "settled": len(settled), "wins": wins,
            "winRate": wins / len(settled) if settled else None,
            "roiPerDollar": total / len(settled) if settled else None,
            "totalUsd": round(total, 4)}


def summary(state_dir, now):
    """The status payload: baseline (all paper trades) vs the G1-filtered subset."""
    rows = _load(state_dir)
    if not rows:
        return None
    resolved = [row for row in rows if row["state"] == "RESOLVED"]
    recent = sorted(resolved, key=lambda row: row["periodStart"], reverse=True)[:10]
    return {"rule": RULE, "minTrend60Bp": MIN_TREND60_BP, "resolutionSource": "binance_15m_estimate",
            "baseline": _stats(rows), "filtered": _stats([row for row in rows if row["g1Eligible"]]),
            "recent": [{"periodStart": row["periodStart"], "side": row["side"], "priceCents": row["priceCents"],
                        "trend60Bp": row["trend60Bp"], "g1Eligible": row["g1Eligible"], "win": row["win"],
                        "roi": row["roi"]} for row in recent],
            "updatedAt": now}
