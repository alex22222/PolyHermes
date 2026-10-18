"""Round series and strategies shared by the Future assistant and bridge.

`5m` is the original BTC 5-minute favorite strategy. `15m` buys the 15-minute favorite only
when the concurrent 1-hour market favors the other side (weekend backtest, 2026-10-15). `4h`
buys the side a price model is >=95% sure of on weekend 4-hour rounds (docs/btc-4h-high-winrate-research.md);
it only runs alongside 15m, in 2-minute windows that never overlap the 15m entry window.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo


SERIES = {
    "5m": {"period": 300, "entry": (60, 80), "variant": "fiveminute",
           "slug": "btc-updown-5m-", "id": "future-btc5m-prepare:",
           "open_source": "polymarket_crypto_price_fiveminute_twap60_openPrice"},
    "15m": {"period": 900, "entry": (150, 170), "variant": "fifteen",
            "slug": "btc-updown-15m-", "id": "future-btc15m-prepare:",
            "open_source": "polymarket_crypto_price_fifteen_twap60_openPrice"},
    # Entry is a 2-minute window at a decision checkpoint, see checkpoint_window().
    "4h": {"period": 14400, "entry": None, "variant": "fourhour",
           "slug": "btc-updown-4h-", "id": "future-btc4h-prepare:",
           "open_source": "polymarket_crypto_price_fourhour_twap60_openPrice"},
}
# Each strategy's series; the first is the default page, the others take over only in their windows.
STRATEGY_SERIES = {"btc5m_favorite": ("5m",), "btc15m_counter_1h": ("15m",), "btc15m_plus_4h": ("15m", "4h")}
STRATEGIES = {name: legs[0] for name, legs in STRATEGY_SERIES.items()}
DEFAULT_STRATEGY = "btc15m_counter_1h"
HOUR = 3600

# 4h decisions happen at minutes 5 and 10 of each quarter hour (never minute 0, so the 15m
# entry window at +150..170 s stays free); each opens a 2-minute preparation window.
CHECKPOINT_MINUTES = tuple(m for m in range(5, 240, 5) if m % 15)
CHECKPOINT_WINDOW = 120


def spec(series):
    return SERIES[series]


def round_start_of(timestamp, series):
    period = SERIES[series]["period"]
    return int(timestamp // period) * period


def checkpoint_window(start, at):
    """(first, last) of the 4h checkpoint window containing `at`, else None."""
    offset = at - start
    minute = int(offset // 300) * 5
    if minute not in CHECKPOINT_MINUTES or offset - minute * 60 >= CHECKPOINT_WINDOW:
        return None
    return start + minute * 60, start + minute * 60 + CHECKPOINT_WINDOW


def entry_bounds(start, series, at=None):
    """Absolute entry window of a round. The 4h window depends on the time it contains and is
    None outside a checkpoint window (or when `at` is not given)."""
    if series == "4h":
        return checkpoint_window(start, at) if at is not None else None
    first, last = SERIES[series]["entry"]
    return start + first, start + last


def slug_for(start, series):
    return f"{SERIES[series]['slug']}{start}"


def preparation_id(start, series):
    return f"{SERIES[series]['id']}{start}"


def series_of_slug(slug):
    """(series, start) for an exact round slug, else None."""
    if not isinstance(slug, str):
        return None
    for name, value in SERIES.items():
        match = re.fullmatch(re.escape(value["slug"]) + r"(0|[1-9][0-9]{0,14})", slug)
        if match and int(match[1]) % value["period"] == 0:
            return name, int(match[1])
    return None


def series_of_preparation_id(identifier):
    if not isinstance(identifier, str):
        return None
    for name, value in SERIES.items():
        match = re.fullmatch(re.escape(value["id"]) + r"(0|[1-9][0-9]{0,14})", identifier)
        if match and int(match[1]) % value["period"] == 0:
            return name, int(match[1])
    return None


def market_url_round(url):
    """(series, start) of a canonical Future round page URL, else None."""
    if not isinstance(url, str):
        return None
    match = re.fullmatch(r"https://future\.news/(?:zh/)?event/(btc-updown-(?:5m|15m|4h)-[0-9]{1,15})/?", url)
    return series_of_slug(match[1]) if match else None


def hourly_slug(start):
    """Polymarket's ET-hour slug, e.g. bitcoin-up-or-down-october-15-2026-12pm-et."""
    moment = datetime.fromtimestamp(start, ZoneInfo("America/New_York"))
    hour = moment.hour % 12 or 12
    return (f"bitcoin-up-or-down-{moment.strftime('%B').lower()}-{moment.day}-{moment.year}-"
            f"{hour}{'am' if moment.hour < 12 else 'pm'}-et")


def is_et_weekend(timestamp):
    return datetime.fromtimestamp(timestamp, ZoneInfo("America/New_York")).weekday() >= 5
