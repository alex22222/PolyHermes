"""BTC conditions for the 15m decision, from Binance BTCUSDT 1m candles.

Rule R1 (/Users/henry/projects/binance/scripts/evaluate-15m-condition-rules.mjs, 2026-10-22): skip a
15m round when the 60-minute volatility is above 4.16 bp per minute, the training-period upper
tercile. It improved per-bet results in training, validation and live trades, for the counter-1h
bets and for every 15m favorite. Volatility is the sample standard deviation of ln(close / open)
over the 60 one-minute candles closed before the decision; the last opens at round start + 60.

trend15Bp, trend60Bp and takerFlow are recorded for observation only (Up-positive, unsigned by side).
"""

import math


SOURCE = "binance_btcusdt_1m"
BINANCE_KLINES = "https://data-api.binance.vision/api/v3/klines"
VOLATILITY_MAX_BP = 4.16
FIRST_FETCH_OFFSET = 121  # the candle opening at start + 60 has closed


def kline_url(start):
    """The 62 candles opening at start - 3600 .. start + 60."""
    return (f"{BINANCE_KLINES}?symbol=BTCUSDT&interval=1m&startTime={(start - 3600) * 1000}"
            f"&endTime={(start + 60) * 1000}&limit=62")


def round_conditions(start, candles, fetched_at):
    """Conditions for the 15m round at `start` from Binance klines
    [[openTimeMs, open, high, low, close, volume, closeTimeMs, quote, trades, takerBuyBase, ...], ...]."""
    by_open = {}
    for row in candles:
        if not isinstance(row, list) or len(row) < 10:
            raise ValueError("INVALID_KLINE")
        by_open[int(row[0]) // 1000] = row
    rows = [by_open.get(start - 3600 + 60 * i) for i in range(62)]
    if any(row is None for row in rows) or int(rows[-1][6]) >= fetched_at * 1000:
        raise ValueError("KLINES_INCOMPLETE")
    opens, closes = [float(row[1]) for row in rows], [float(row[4]) for row in rows]
    volumes, taker_buys = [float(row[5]) for row in rows[-15:]], [float(row[9]) for row in rows[-15:]]
    if any(not math.isfinite(value) or value <= 0 for value in opens + closes) or not sum(volumes) > 0:
        raise ValueError("INVALID_KLINE")
    returns = [math.log(close / open_) for open_, close in zip(opens[-60:], closes[-60:])]
    mean = sum(returns) / 60
    volatility = math.sqrt(sum((value - mean) ** 2 for value in returns) / 59) * 1e4
    round_open = opens[60]
    values = {"volatilityBp": volatility, "trend15Bp": math.log(round_open / opens[45]) * 1e4,
              "trend60Bp": math.log(round_open / opens[0]) * 1e4, "takerFlow": 2 * sum(taker_buys) / sum(volumes) - 1}
    if not all(math.isfinite(value) for value in values.values()) or not -1 <= values["takerFlow"] <= 1:
        raise ValueError("INVALID_KLINE")
    return {"source": SOURCE, "periodStart": start, "lastCandleOpen": start + 60, "observedAt": fetched_at,
            "volatilityMaxBp": VOLATILITY_MAX_BP, **values}
