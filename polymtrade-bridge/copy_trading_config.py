import asyncio
import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Optional, Tuple

import pymysql
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class CopyTradingConfig:
    id: int
    account_id: int
    leader_id: int
    leader_address: str
    leader_category: Optional[str]
    copy_mode: str
    copy_ratio: Decimal
    fixed_amount: Optional[Decimal]
    max_order_size: Decimal
    min_order_size: Decimal
    max_daily_loss: Optional[Decimal]
    max_daily_orders: int
    price_tolerance: Decimal
    delay_seconds: int
    support_sell: bool
    min_order_depth: Optional[Decimal]
    max_spread: Optional[Decimal]
    min_price: Optional[Decimal]
    max_price: Optional[Decimal]
    max_position_value: Optional[Decimal]
    max_price_deviation: Optional[Decimal]
    max_delay_seconds: Optional[int]
    keyword_filter_mode: str
    keywords: Optional[List[str]]
    max_market_end_date: Optional[int]
    push_failed_orders: bool


class CopyTradingRuleEngine:
    """Load copy-trading rules from PolyHermes MySQL and apply them to signals."""

    def __init__(self, refresh_interval: int = 30):
        self.host = os.getenv("COPY_TRADING_DB_HOST", "127.0.0.1")
        self.port = int(os.getenv("COPY_TRADING_DB_PORT", "3307"))
        self.user = os.getenv("COPY_TRADING_DB_USER", "root")
        self.password = os.getenv("COPY_TRADING_DB_PASSWORD", "")
        self.database = os.getenv("COPY_TRADING_DB_NAME", "polyhermes")
        self.account_id = os.getenv("COPY_TRADING_ACCOUNT_ID")
        self.refresh_interval = refresh_interval
        self._configs: List[CopyTradingConfig] = []
        self._last_refresh = 0.0

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    def refresh_if_needed(self):
        now = time.time()
        if now - self._last_refresh > self.refresh_interval:
            try:
                self._load_configs()
                self._last_refresh = now
            except Exception:
                logger.exception("Failed to refresh copy-trading configs")

    def set_account_id(self, account_id: Optional[int]):
        """Override the account id used to filter configs and force a reload."""
        if account_id != self.account_id:
            logger.info(f"Copy-trading account_id overridden: {self.account_id} -> {account_id}")
            self.account_id = account_id
            self._last_refresh = 0.0

    def resolve_account_id_by_wallet(self, wallet_address: str) -> Optional[int]:
        """Look up the wallet_accounts id for the given address (case-insensitive)."""
        if not wallet_address:
            return None
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id FROM wallet_accounts WHERE LOWER(wallet_address) = LOWER(%s) LIMIT 1",
                        (wallet_address,),
                    )
                    row = cur.fetchone()
                    return row["id"] if row else None
        except Exception:
            logger.exception("Failed to resolve account id by wallet address")
            return None

    def _load_configs(self):
        account_filter = ""
        params = []
        if self.account_id:
            account_filter = "AND ct.account_id = %s"
            params.append(int(self.account_id))

        sql = f"""
        SELECT
            ct.id, ct.account_id, ct.leader_id, ctl.leader_address, ctl.category AS leader_category,
            ct.copy_mode, ct.copy_ratio, ct.fixed_amount,
            ct.max_order_size, ct.min_order_size, ct.max_daily_loss,
            ct.max_daily_orders, ct.price_tolerance, ct.delay_seconds,
            ct.support_sell, ct.min_order_depth, ct.max_spread,
            ct.min_price, ct.max_price, ct.max_position_value,
            ct.max_price_deviation, ct.max_delay_seconds,
            ct.keyword_filter_mode, ct.keywords, ct.max_market_end_date,
            ct.push_failed_orders
        FROM copy_trading ct
        JOIN copy_trading_leaders ctl ON ct.leader_id = ctl.id
        WHERE ct.enabled = 1 {account_filter}
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        configs = []
        for row in rows:
            keywords = None
            if row.get("keywords"):
                try:
                    import json

                    keywords = json.loads(row["keywords"])
                    if not isinstance(keywords, list):
                        keywords = [str(keywords)]
                except Exception:
                    keywords = [str(row["keywords"])]
            configs.append(
                CopyTradingConfig(
                    id=row["id"],
                    account_id=row["account_id"],
                    leader_id=row["leader_id"],
                    leader_address=(row["leader_address"] or "").lower(),
                    leader_category=(row["leader_category"] or "").lower() or None,
                    copy_mode=(row["copy_mode"] or "RATIO").upper(),
                    copy_ratio=Decimal(row["copy_ratio"] or 1),
                    fixed_amount=Decimal(row["fixed_amount"]) if row["fixed_amount"] is not None else None,
                    max_order_size=Decimal(row["max_order_size"] or 0),
                    min_order_size=Decimal(row["min_order_size"] or 0),
                    max_daily_loss=Decimal(row["max_daily_loss"]) if row["max_daily_loss"] is not None else None,
                    max_daily_orders=int(row["max_daily_orders"] or 0),
                    price_tolerance=Decimal(row["price_tolerance"] or 0),
                    delay_seconds=int(row["delay_seconds"] or 0),
                    support_sell=bool(row["support_sell"]),
                    min_order_depth=Decimal(row["min_order_depth"]) if row["min_order_depth"] is not None else None,
                    max_spread=Decimal(row["max_spread"]) if row["max_spread"] is not None else None,
                    min_price=Decimal(row["min_price"]) if row["min_price"] is not None else None,
                    max_price=Decimal(row["max_price"]) if row["max_price"] is not None else None,
                    max_position_value=Decimal(row["max_position_value"]) if row["max_position_value"] is not None else None,
                    max_price_deviation=Decimal(row["max_price_deviation"]) if row["max_price_deviation"] is not None else None,
                    max_delay_seconds=int(row["max_delay_seconds"]) if row["max_delay_seconds"] is not None else None,
                    keyword_filter_mode=(row["keyword_filter_mode"] or "DISABLED").upper(),
                    keywords=keywords,
                    max_market_end_date=int(row["max_market_end_date"]) if row["max_market_end_date"] is not None else None,
                    push_failed_orders=bool(row["push_failed_orders"]),
                )
            )
        self._configs = configs
        logger.info(f"Loaded {len(configs)} copy-trading configs")

    def get_matching_configs(
        self,
        trader_address: str,
        side: str,
        title: str,
        price: Decimal,
        market_end_date_ms: Optional[int] = None,
        signal_timestamp_ms: Optional[int] = None,
    ) -> List[Tuple[CopyTradingConfig, Optional[str]]]:
        """Return (config, filter_reason) tuples. filter_reason is None when passed."""
        self.refresh_if_needed()
        address = (trader_address or "").lower()
        side = side.upper()
        market_category = infer_market_category(title)
        results = []
        for cfg in self._configs:
            if cfg.leader_address != address:
                continue
            reason = self._check_filters(
                cfg,
                side,
                title,
                price,
                market_end_date_ms,
                signal_timestamp_ms,
                market_category,
            )
            results.append((cfg, reason))
        return results

    def _check_filters(
        self,
        cfg: CopyTradingConfig,
        side: str,
        title: str,
        price: Decimal,
        market_end_date_ms: Optional[int],
        signal_timestamp_ms: Optional[int],
        market_category: Optional[str],
    ) -> Optional[str]:
        if side == "SELL" and not cfg.support_sell:
            return "support_sell=false"

        # 分类匹配检查：Leader 只能跟单其擅长领域的市场
        if cfg.leader_category is not None and market_category is not None:
            if cfg.leader_category != market_category:
                return f"category mismatch: leader={cfg.leader_category}, market={market_category}"

        if cfg.min_price is not None and price < cfg.min_price:
            return f"price {price} < min_price {cfg.min_price}"
        if cfg.max_price is not None and price > cfg.max_price:
            return f"price {price} > max_price {cfg.max_price}"

        if cfg.max_market_end_date is not None and market_end_date_ms is not None:
            if market_end_date_ms > cfg.max_market_end_date:
                return "market_end_date exceeds limit"

        if cfg.keyword_filter_mode != "DISABLED" and cfg.keywords:
            title_lower = (title or "").lower()
            matched = any(k.lower() in title_lower for k in cfg.keywords if k)
            if cfg.keyword_filter_mode == "WHITELIST" and not matched:
                return "keyword whitelist not matched"
            if cfg.keyword_filter_mode == "BLACKLIST" and matched:
                return "keyword blacklist matched"

        # 信号延迟检查
        if cfg.max_delay_seconds is not None and signal_timestamp_ms is not None:
            delay_seconds = (time.time() * 1000 - signal_timestamp_ms) / 1000
            if delay_seconds > cfg.max_delay_seconds:
                return f"signal delay {delay_seconds:.1f}s > max_delay_seconds {cfg.max_delay_seconds}"

        if side == "BUY" and cfg.max_daily_orders > 0:
            today_count = self._count_today_buy_orders(cfg.id)
            if today_count >= cfg.max_daily_orders:
                return f"max_daily_orders reached ({today_count})"

        return None

    def _count_today_buy_orders(self, copy_trading_id: int) -> int:
        try:
            now = int(time.time() * 1000)
            start_of_day = now - (now % 86400000)
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) AS cnt FROM copy_order_tracking
                        WHERE copy_trading_id = %s AND side = 'BUY' AND created_at >= %s
                        """,
                        (copy_trading_id, start_of_day),
                    )
                    row = cur.fetchone()
                    return row["cnt"] if row else 0
        except Exception:
            logger.exception("Failed to count today buy orders")
            return 0

    def compute_buy_quantity(
        self, cfg: CopyTradingConfig, leader_price: Decimal, leader_size: Decimal
    ) -> Optional[Decimal]:
        """Return USDC amount to buy. None if filtered by min/max size."""
        if cfg.copy_mode == "RATIO":
            leader_value = leader_price * leader_size
            value = leader_value * cfg.copy_ratio
        elif cfg.copy_mode == "FIXED" and cfg.fixed_amount is not None:
            value = cfg.fixed_amount
        else:
            return None

        if cfg.min_order_size and value < cfg.min_order_size:
            logger.info(f"Config {cfg.id}: value {value} below min_order_size, skipping")
            return None
        if cfg.max_order_size and value > cfg.max_order_size:
            value = cfg.max_order_size

        return value.quantize(Decimal("0.01"))

    def compute_sell_shares(
        self, cfg: CopyTradingConfig, leader_price: Decimal, leader_size: Decimal
    ) -> Optional[Decimal]:
        """Return number of shares to sell. None if filtered by min/max size."""
        if cfg.copy_mode == "RATIO":
            shares = leader_size * cfg.copy_ratio
        elif cfg.copy_mode == "FIXED" and cfg.fixed_amount is not None:
            shares = cfg.fixed_amount / leader_price
        else:
            return None

        value = shares * leader_price
        if cfg.min_order_size and value < cfg.min_order_size:
            logger.info(f"Config {cfg.id}: sell value {value} below min_order_size, skipping")
            return None
        if cfg.max_order_size and value > cfg.max_order_size:
            shares = cfg.max_order_size / leader_price

        return shares.quantize(Decimal("0.0001"))

    async def sleep_delay(self, cfg: CopyTradingConfig):
        if cfg.delay_seconds > 0:
            logger.info(f"Delaying {cfg.delay_seconds}s per config {cfg.id}")
            await asyncio.sleep(cfg.delay_seconds)


def infer_market_category(title: Optional[str]) -> Optional[str]:
    """Infer market category from title keywords (matches backend CategoryValidator logic).

    Priority:
    1. politics keywords
    2. sports keywords
    3. crypto keywords
    4. finance keywords
    """
    if not title:
        return None
    text = title.lower()
    text = text.replace("-", " ").replace("_", " ")

    politics_keywords = (
        "trump", "biden", "election", "president", "congress", "senate",
        "supreme court", "tariff", "taiwan", "china", "israel", "iran",
        "ukraine", "russia", "putin", "weinstein", "prison", "sentenced",
        "sentence", "court", "trial", "judge", "verdict", "lawsuit",
        "attorney", "prosecutor", "defendant", "guilty", "convicted",
        "criminal", "justice", "senators", "representatives", "house", "bill"
    )
    if any(k in text for k in politics_keywords):
        return "politics"

    sports_keywords = (
        "world cup", "fifa", "nba", "nfl", "mlb", "nhl", "ufc", "tennis",
        "soccer", "football", "baseball", "basketball", "golf", "championship",
        "premier league", "esports", "e sports", "电竞", "电子竞技",
        "counter strike", "cs2", "csgo", "valorant", "dota", "league of legends",
        " lol ", "overwatch", "starcraft", "bo3", "bo5", "iem ", "major stage",
        "natus vincere", " navi ", " g2 ", "faze", "vitality", "over/under", " o/u ",
        "spread", "exact score", "halftime", "draw", "win on", "btts",
        "team total", "leading at", "clean sheet", "first goal",
        "red card", "penalty", "overtime", "full time", "match winner",
        "moneyline", "points", "score", "winner"
    )
    if any(k in text for k in sports_keywords):
        return "sports"

    crypto_keywords = (
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "doge",
        "dogecoin", "airdrop", "stablecoin", "crypto", "blockchain", "defi",
        "nft", "altcoin", "memecoin", "layer2", "rollup", "token", "tokens"
    )
    if any(k in text for k in crypto_keywords):
        return "crypto"

    finance_keywords = (
        "fed", "interest rate", "inflation", "cpi", "recession", "nasdaq",
        "s&p", "stock", "ipo", "gdp", "treasury", "oil price", "unemployment",
        "payroll", "nfp", "earnings", "revenue", "quarter", "q1", "q2", "q3",
        "q4", "gross domestic product", "spx"
    )
    if any(k in text for k in finance_keywords):
        return "finance"
    return None
