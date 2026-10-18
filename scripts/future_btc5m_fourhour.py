"""BTC 4-hour weekend rule: at a checkpoint, buy the side a price model is >=95% sure of when its
$1 ask is at least 3c below that probability.

Fitted and backtested in /Users/henry/projects/binance/scripts/run-4h-updown-research.mjs
(docs/btc-4h-high-winrate-research.md): Binance BTCUSDT 1m candles 2024-10..2026-03, z =
ln(price / open) / (sigma_1m * sqrt(minutes left)), sigma from the previous 60 one-minute
returns, P(Up) = logistic(a + b z) per minutes-left bucket.
"""

import math

from future_btc5m_series import CHECKPOINT_MINUTES, is_et_weekend


SOURCE = "binance_btcusdt_1m"
BINANCE_KLINES = "https://data-api.binance.vision/api/v3/klines"
# (minutes left upper bound, a, b), buckets (0,15], (15,30], (30,60], (60,120], (120,240].
MODEL = ((15, 0.060, 2.247), (30, -0.019, 1.968), (60, -0.040, 1.786), (120, -0.024, 1.780), (240, 0.033, 1.673))
MIN_PROBABILITY = 0.95
MIN_EDGE_CENTS = 3
MIN_ASK_CENTS = 60
MAX_ASK_CENTS = 97


def up_probability(open_price, closes, minutes_left):
    """Model P(Up). `closes` are the 61 one-minute closes ending at the checkpoint."""
    if len(closes) != 61 or not open_price > 0 or any(not close > 0 for close in closes) or not 0 < minutes_left < 240:
        raise ValueError("INVALID_MODEL_INPUT")
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, 61)]
    mean = sum(returns) / 60
    sigma = max(1e-5, math.sqrt(sum((value - mean) ** 2 for value in returns) / 59))
    z = math.log(closes[-1] / open_price) / (sigma * math.sqrt(minutes_left))
    a, b = next((a, b) for limit, a, b in MODEL if minutes_left <= limit)
    return 1 / (1 + math.exp(-(a + b * max(-12, min(12, z))))), z, sigma


def model_state(start, checkpoint, candles):
    """The model at `checkpoint` from Binance klines [[openTimeMs, open, high, low, close, ...], ...]:
    the round's first candle and the 61 candles before the checkpoint, all consecutive."""
    minute = (checkpoint - start) // 60
    if (checkpoint - start) % 60 or minute not in CHECKPOINT_MINUTES:
        raise ValueError("INVALID_CHECKPOINT")
    by_open = {}
    for row in candles:
        if not isinstance(row, list) or len(row) < 5:
            raise ValueError("INVALID_KLINE")
        by_open[int(row[0]) // 1000] = row
    first = by_open.get(start)
    window = [by_open.get(checkpoint - 60 * (61 - i)) for i in range(61)]
    if first is None or any(row is None for row in window):
        raise ValueError("KLINES_INCOMPLETE")
    open_price = float(first[1])
    closes = [float(row[4]) for row in window]
    probability, z, sigma = up_probability(open_price, closes, 240 - minute)
    return {"source": SOURCE, "periodStart": start, "checkpointAt": checkpoint, "minute": minute,
            "openPrice": open_price, "price": closes[-1], "sigma": sigma, "z": z, "pUp": probability}


def kline_urls(start, checkpoint):
    """The round's first candle and the 61 candles ending at the checkpoint (closed candles only)."""
    return [f"{BINANCE_KLINES}?symbol=BTCUSDT&interval=1m&startTime={start * 1000}&limit=1",
            f"{BINANCE_KLINES}?symbol=BTCUSDT&interval=1m&startTime={(checkpoint - 61 * 60) * 1000}"
            f"&endTime={(checkpoint - 1) * 1000}&limit=61"]


def evaluate(start, model, quote):
    """(decision, side, reason) for one checkpoint: decision is PREPARE or SKIP."""
    if not is_et_weekend(start):
        return "SKIP", None, "NOT_ET_WEEKEND"
    p_up = model["pUp"]
    side = "Up" if p_up >= 0.5 else "Down"
    probability = p_up if side == "Up" else 1 - p_up
    ask = quote["upAskCents"] if side == "Up" else quote["downAskCents"]
    other = quote["downAskCents"] if side == "Up" else quote["upAskCents"]
    if probability < MIN_PROBABILITY:
        return "SKIP", side, "MODEL_BELOW_THRESHOLD"
    if ask is None or other is None:
        return "SKIP", side, "ASK_UNAVAILABLE"
    if ask <= other:
        return "SKIP", side, "MODEL_SIDE_NOT_FAVORITE"
    if not MIN_ASK_CENTS <= ask <= MAX_ASK_CENTS:
        return "SKIP", side, "ASK_OUT_OF_RANGE"
    # Rounded so binary floating point cannot move an exact 3c edge across the threshold.
    if round(probability * 100 - ask, 6) < MIN_EDGE_CENTS:
        return "SKIP", side, "EDGE_TOO_SMALL"
    return "PREPARE", side, None
