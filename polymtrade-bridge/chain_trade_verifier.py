"""On-chain trade confirmation and market availability via Polymarket public APIs.

polym.trade is a third-party UI: its portfolio scrape lags real fills and its
market pages sometimes fail to render. Polymarket's own data-api (v2) exposes
the wallet's executed trades, and gamma-api exposes market lifecycle state.
Both endpoints are read-only and need no authentication, so they are safe
fallbacks for post-submit confirmation and failure classification.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

DATA_API_TRADES_URL = "https://data-api.polymarket.com/v2/trades"
GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"

HTTP_TIMEOUT_SECONDS = 6.0

AVAILABILITY_ACTIVE = "active"
AVAILABILITY_CLOSED = "closed"
AVAILABILITY_NOT_FOUND = "not_found"
AVAILABILITY_UNKNOWN = "unknown"

_availability_cache: dict[str, tuple[str, float]] = {}
_AVAILABILITY_TTL_SECONDS = {
    AVAILABILITY_ACTIVE: 15 * 60,
    AVAILABILITY_CLOSED: 6 * 3600,
    AVAILABILITY_NOT_FOUND: 6 * 3600,
    AVAILABILITY_UNKNOWN: 60,
}


async def fetch_wallet_trades(
    wallet: str,
    *,
    limit: int = 100,
    client: Optional[httpx.AsyncClient] = None,
) -> list[dict[str, Any]]:
    """Fetch recent executed trades for a wallet from Polymarket data-api v2."""
    if not wallet:
        return []
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, trust_env=False)
    try:
        response = await client.get(
            DATA_API_TRADES_URL, params={"user": wallet, "limit": limit}
        )
        if response.status_code != 200:
            logger.warning("data-api trades fetch HTTP %s", response.status_code)
            return []
        payload = response.json()
    except Exception as e:
        logger.warning("data-api trades fetch failed: %s: %s", type(e).__name__, e)
        return []
    finally:
        if owns_client:
            await client.aclose()
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    return [trade for trade in data if isinstance(trade, dict)]


def find_matching_fill(
    trades: list[dict[str, Any]],
    *,
    condition_id: str,
    side: str,
    outcome: Optional[str] = None,
    since_epoch_s: float,
    skew_s: float = 180.0,
) -> Optional[dict[str, Any]]:
    """Return the earliest trade matching market/side/outcome at or after since-skew."""
    target_condition = (condition_id or "").strip().lower()
    target_side = (side or "").strip().upper()
    target_outcome = (outcome or "").strip().lower()
    if not target_condition or not target_side:
        return None
    cutoff = since_epoch_s - max(0.0, skew_s)
    match: Optional[dict[str, Any]] = None
    match_ts = float("inf")
    for trade in trades:
        if str(trade.get("condition_id") or "").strip().lower() != target_condition:
            continue
        if str(trade.get("side") or "").strip().upper() != target_side:
            continue
        if target_outcome and str(trade.get("outcome") or "").strip().lower() != target_outcome:
            continue
        try:
            ts = float(trade.get("timestamp") or 0)
        except (TypeError, ValueError):
            continue
        if ts < cutoff:
            continue
        if ts < match_ts:
            match = trade
            match_ts = ts
    return match


async def get_market_availability(
    condition_id: str,
    *,
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """Classify a market via gamma-api: active / closed / not_found / unknown (cached)."""
    key = (condition_id or "").strip().lower()
    if not key:
        return AVAILABILITY_UNKNOWN
    cached = _availability_cache.get(key)
    now = time.monotonic()
    if cached and now < cached[1]:
        return cached[0]
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS, trust_env=False)
    try:
        response = await client.get(
            GAMMA_MARKETS_URL, params={"condition_ids": condition_id}
        )
        if response.status_code != 200:
            status = AVAILABILITY_UNKNOWN
            logger.warning("gamma-api availability HTTP %s", response.status_code)
        else:
            payload = response.json()
            if isinstance(payload, list):
                markets = payload
            elif isinstance(payload, dict):
                markets = payload.get("data") or []
            else:
                markets = []
            if not markets:
                status = AVAILABILITY_NOT_FOUND
            elif any(isinstance(m, dict) and not m.get("closed") for m in markets):
                status = AVAILABILITY_ACTIVE
            else:
                status = AVAILABILITY_CLOSED
    except Exception as e:
        logger.warning(
            "gamma-api availability check failed for %s: %s: %s",
            condition_id,
            type(e).__name__,
            e,
        )
        status = AVAILABILITY_UNKNOWN
    finally:
        if owns_client:
            await client.aclose()
    _availability_cache[key] = (status, now + _AVAILABILITY_TTL_SECONDS[status])
    return status


def reset_availability_cache() -> None:
    _availability_cache.clear()
