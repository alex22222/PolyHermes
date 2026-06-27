import asyncio
import base64
import json
import logging
import os
import re
import time
import urllib.parse
from typing import Optional, Tuple

import httpx
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from bridge_metrics import metrics

logger = logging.getLogger(__name__)

_EVALUATE_ARG_MISSING = object()


class PolymtradeExecutor:
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.base_url = os.getenv("POLYMTRADE_URL", "https://polym.trade")
        self.proxy = os.getenv("BROWSER_PROXY")  # e.g. http://host.docker.internal:7890
        self.profile_dir = os.path.abspath(os.getenv("BROWSER_PROFILE_DIR", "./browser_profile"))
        self.headless = os.getenv("HEADLESS", "false").lower() == "true"
        self.last_error: Optional[str] = None
        self._ready = False
        self._logged_in = False

    async def start(self):
        """Start browser and load Polymtrade."""
        try:
            # Ensure profile directory exists
            os.makedirs(self.profile_dir, exist_ok=True)
            logger.info(f"Using browser profile: {self.profile_dir}")

            self.playwright = await async_playwright().start()

            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
            if self.proxy:
                browser_args.append(f"--proxy-server={self.proxy}")

            # Use persistent context to keep login session.
            # ignore_default_args removes Playwright's --enable-automation flag,
            # which often triggers OAuth "browser or app may not be secure" errors.
            self.context = await self.playwright.chromium.launch_persistent_context(
                self.profile_dir,
                headless=self.headless,
                args=browser_args,
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            self.page = await self.context.new_page()
            await self._goto_with_retry(self.base_url, max_retries=4, timeout_ms=60000)
            # Give dynamic content / websockets a moment to settle
            await asyncio.sleep(3)

            logger.info(f"Loaded {self.base_url}")

            # Check if already logged in (look for balance or wallet button)
            self._logged_in = await self._detect_login_state()
            if self._logged_in:
                logger.info("Already logged in to Polymtrade")
            else:
                logger.warning("Not logged in. Please login manually via the browser window.")

            self._ready = True

        except Exception as e:
            self.last_error = str(e)
            logger.exception(f"Failed to start executor: {e}")
            raise

    async def stop(self):
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                message = str(e).lower()
                if "target page" in message or "context or browser has been closed" in message:
                    logger.info(f"Browser context already closed during shutdown: {e}")
                else:
                    raise
            finally:
                self.context = None
                self.page = None
        if self.playwright:
            try:
                await self.playwright.stop()
            finally:
                self.playwright = None
        self._ready = False

    def is_ready(self) -> bool:
        return self._ready and self.page is not None

    def is_logged_in(self) -> bool:
        return self._logged_in

    async def _detect_login_state(self, timeout: int = 5000) -> bool:
        """Detect if user is logged in by looking for wallet/balance elements."""
        try:
            # Indicators of logged-in state on Polymtrade (English + Chinese UI)
            selectors = [
                "text=Portfolio",
                "text=Balance",
                "text=Deposit",
                "text=Withdraw",
                "text=Sign out",
                "text=Log out",
                "text=投资组合",   # Portfolio (zh)
                "text=余额",       # Balance (zh)
                "text=充值",       # Deposit (zh)
                "text=提现",       # Withdraw (zh)
                "[data-testid='wallet-button']",
                "[data-testid='balance']",
                ".balance-amount",
                "button:has-text('0x')",
            ]
            for selector in selectors:
                try:
                    await self.page.wait_for_selector(selector, timeout=timeout, state="visible")
                    return True
                except Exception:
                    continue

            # Fallback: look for wallet/balance markers in page text.
            # Polymtrade shows pUSD balance and an Ethereum address once logged in.
            try:
                body_text = await self.page.inner_text("body", timeout=timeout)
                markers = ["0x", "pUSD", "USDC", "Balance", "Portfolio", "Deposit", "Withdraw",
                           "余额", "投资组合", "充值", "提现"]
                if any(token in body_text for token in markers):
                    return True
            except Exception:
                pass

            return False
        except Exception as e:
            logger.warning(f"Login detection error: {e}")
            return False

    async def refresh_login_state(self):
        """Re-evaluate login state without restarting the browser."""
        if not self.page:
            self._logged_in = False
            return self._logged_in
        self._logged_in = await self._detect_login_state()
        if self._logged_in:
            logger.info("Login state refreshed: logged in")
        else:
            logger.warning("Login state refreshed: not logged in")
        return self._logged_in

    async def get_wallet_address(self) -> Optional[str]:
        """Extract the currently logged-in wallet address from the portfolio page."""
        if not self.page or not self._logged_in:
            return None
        try:
            await self._goto_with_retry(f"{self.base_url}/portfolio", max_retries=5, timeout_ms=30000)
            await asyncio.sleep(1)
            text = await self.page.inner_text("body", timeout=5000)
            ref_match = re.search(r'[?&]ref=(0x[a-fA-F0-9]{40})', text)
            if ref_match:
                return ref_match.group(1).lower()
            addresses = re.findall(r'0x[a-fA-F0-9]{40}', text)
            return addresses[0].lower() if addresses else None
        except Exception as e:
            logger.warning(f"Failed to extract wallet address: {e}")
            return None

    async def click_by_text(self, text: str) -> dict:
        """Click the first element containing the given text and return page info."""
        if not self.page:
            return {"error": "page not initialized"}
        try:
            selector = f"text={text}"
            await self.page.click(selector, timeout=5000)
            await asyncio.sleep(2)
            return await self.debug_info()
        except Exception as e:
            return {"error": str(e)}

    async def click_selector(self, selector: str) -> dict:
        """Click the first element matching a CSS selector and return page info."""
        if not self.page:
            return {"error": "page not initialized"}
        try:
            await self.page.click(selector, timeout=5000)
            await asyncio.sleep(2)
            return await self.debug_info()
        except Exception as e:
            return {"error": str(e)}

    async def navigate_to(self, url: str) -> dict:
        """Navigate to an arbitrary URL and return page info."""
        if not self.page:
            return {"error": "page not initialized"}
        try:
            await self._goto_with_retry(url, max_retries=4, timeout_ms=60000)
            await asyncio.sleep(2)
            return await self.debug_info()
        except Exception as e:
            return {"error": str(e)}

    async def eval_js(self, expression: str):
        """Evaluate an arbitrary JS expression in the page context."""
        if not self.page:
            return {"error": "page not initialized"}
        try:
            result = await self.page.evaluate(expression)
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _is_navigation_race_error(error: Exception) -> bool:
        text = str(error).lower()
        return (
            "execution context was destroyed" in text
            or "most likely because of a navigation" in text
            or "target page, context or browser has been closed" in text
            or "page closed during navigation" in text
        )

    async def _wait_after_navigation_race(self, label: str, attempt: int) -> None:
        """Give a page that is mid-navigation a short chance to settle."""
        if not self.page:
            raise RuntimeError(f"{label}: page not initialized during navigation retry")
        is_closed = getattr(self.page, "is_closed", None)
        if callable(is_closed) and is_closed():
            raise RuntimeError(f"{label}: page closed during navigation retry")
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception as e:
            logger.debug(f"{label}: wait_for_load_state after navigation race failed: {e}")
        await asyncio.sleep(0.25 + attempt * 0.25)

    async def _evaluate_with_navigation_retry(
        self,
        expression: str,
        arg=_EVALUATE_ARG_MISSING,
        *,
        max_retries: int = 3,
        label: str = "page.evaluate",
    ):
        """Evaluate JS and retry transient navigation context loss."""
        last_error = None
        for attempt in range(max_retries):
            try:
                if arg is _EVALUATE_ARG_MISSING:
                    return await self.page.evaluate(expression)
                return await self.page.evaluate(expression, arg)
            except Exception as e:
                last_error = e
                if not self._is_navigation_race_error(e):
                    raise
                if attempt >= max_retries - 1:
                    break
                logger.warning(
                    f"{label} hit navigation race (attempt {attempt + 1}/{max_retries}); retrying: {e}"
                )
                await self._wait_after_navigation_race(label, attempt)
        raise RuntimeError(
            f"{label}: navigation race persisted after {max_retries} attempts: {last_error}"
        ) from last_error

    async def _evaluate_handle_with_navigation_retry(
        self,
        expression: str,
        arg=_EVALUATE_ARG_MISSING,
        *,
        max_retries: int = 3,
        label: str = "page.evaluate_handle",
    ):
        """Evaluate JS handle and retry transient navigation context loss."""
        last_error = None
        for attempt in range(max_retries):
            try:
                if arg is _EVALUATE_ARG_MISSING:
                    return await self.page.evaluate_handle(expression)
                return await self.page.evaluate_handle(expression, arg)
            except Exception as e:
                last_error = e
                if not self._is_navigation_race_error(e):
                    raise
                if attempt >= max_retries - 1:
                    break
                logger.warning(
                    f"{label} hit navigation race (attempt {attempt + 1}/{max_retries}); retrying: {e}"
                )
                await self._wait_after_navigation_race(label, attempt)
        raise RuntimeError(
            f"{label}: navigation race persisted after {max_retries} attempts: {last_error}"
        ) from last_error

    async def fetch_portfolio_positions(self) -> dict:
        """Scrape current open positions from the Polymtrade portfolio page.

        Returns a dict with {"positions": [...], "synced_at": timestamp}.
        Each position contains: marketTitle, side, quantity, currentValue,
        pnl, percentPnl, marketIcon, marketSlug, conditionId, eventSlug.
        """
        if not self.page:
            return {"error": "page not initialized"}
        try:
            await self._goto_with_retry(f"{self.base_url}/portfolio", max_retries=6)
            rendered = await self._wait_for_portfolio_rows(timeout=12.0)
            if not rendered:
                logger.warning("Portfolio rows did not render before scrape; continuing with best effort")

            # 多次滚动页面到底部，触发 Polymtrade 的懒加载/分页，确保所有持仓都被渲染
            for _ in range(5):
                await self.page.evaluate("() => { window.scrollTo(0, document.body.scrollHeight); }")
                await asyncio.sleep(0.8)

            js = r"""
            () => {
                const parseMoney = (s) => {
                    if (!s) return null;
                    const clean = s.replace(/,/g, '').replace(/\$/g, '');
                    const m = clean.match(/(-?[0-9]+\.?[0-9]*)/);
                    return m ? parseFloat(m[1]) : null;
                };
                const parsePercent = (s) => {
                    if (!s) return null;
                    const m = s.match(/(-?[0-9]+\.?[0-9]*)%/);
                    return m ? parseFloat(m[1]) : null;
                };
                const lis = Array.from(document.querySelectorAll(
                    'li.flex.px-4.py-2.border-b.text-xs.items-center.cursor-pointer'
                )).filter(li => li.offsetParent !== null);

                const positions = [];
                for (const li of lis) {
                    const img = li.querySelector('img');
                    const lines = li.innerText.split(/\n/)
                        .map(t => t.trim())
                        .filter(t => t.length > 0);
                    if (lines.length < 3) continue;

                    const title = lines[0];
                    const currentValue = parseMoney(lines[1]);
                    const sideQtyLine = lines.find(l => l.includes('份'));
                    let side = '';
                    let quantity = null;
                    if (sideQtyLine) {
                        const parts = sideQtyLine.split('•').map(t => t.trim());
                        side = parts[0] || '';
                        const qm = (parts[1] || '').match(/([0-9]+\.?[0-9]*)/);
                        if (qm) quantity = parseFloat(qm[1]);
                    }
                    const pnlLine = lines.find(l => /^[+-]/.test(l));
                    const pnl = pnlLine ? parseMoney(pnlLine) : null;
                    const percentLine = lines.find(l => l.includes('%'));
                    let percentPnl = percentLine ? parsePercent(percentLine) : null;
                    if (percentPnl != null && pnl != null && pnl < 0 && percentPnl > 0) {
                        percentPnl = -percentPnl;
                    }

                    // Extract any link or data attributes that might contain market/event identifiers.
                    const link = li.querySelector('a[href]');
                    const href = link ? link.getAttribute('href') : null;
                    const allData = {};
                    for (const el of [li, link, img]) {
                        if (!el) continue;
                        for (const attr of el.attributes || []) {
                            if (attr.name.startsWith('data-') || attr.name.startsWith('dataTest')) {
                                allData[attr.name] = attr.value;
                            }
                        }
                    }

                    positions.push({
                        marketTitle: title,
                        side: side,
                        quantity: quantity,
                        currentValue: currentValue,
                        pnl: pnl,
                        percentPnl: percentPnl,
                        marketIcon: img ? img.src : null,
                        href: href,
                        cardData: allData,
                    });
                }
                return positions;
            }
            """
            positions = await self.page.evaluate(js)

            # Enrich with Gamma API metadata so the backend can map titles to
            # market/condition IDs and slugs without relying on its local cache.
            # Enrichments no longer navigate/click the page, so they can run concurrently.
            enrich_tasks = [self._enrich_position(pos) for pos in positions]
            enrichment_results = await asyncio.gather(*enrich_tasks, return_exceptions=True)
            for pos, meta in zip(positions, enrichment_results):
                if isinstance(meta, Exception):
                    logger.warning(f"Failed to enrich {pos.get('marketTitle')}: {type(meta).__name__}: {meta}")
                    continue
                pos.update(meta)

            return {
                "positions": positions,
                "synced_at": int(time.time() * 1000),
            }
        except Exception as e:
            logger.exception(f"Failed to fetch portfolio positions: {e}")
            return {"error": str(e)}

    async def _wait_for_portfolio_rows(self, timeout: float = 12.0) -> bool:
        """Wait until portfolio rows or an explicit empty state is rendered."""
        deadline = time.time() + timeout
        last_state = None
        js = """
        () => {
            const rowSelector = 'li.flex.px-4.py-2.border-b.text-xs.items-center.cursor-pointer';
            const rows = Array.from(document.querySelectorAll(rowSelector))
                .filter(li => li.offsetParent !== null || li.getClientRects().length);
            const text = document.body ? (document.body.innerText || document.body.textContent || '') : '';
            const empty = /暂无持仓|没有持仓|No positions|No open positions/i.test(text);
            const portfolioVisible = text.includes('持仓') || /positions/i.test(text);
            return {count: rows.length, empty, portfolioVisible, textLength: text.length};
        }
        """
        while time.time() < deadline:
            try:
                state = await self._evaluate_with_navigation_retry(
                    js,
                    label="portfolio_rows_wait",
                    max_retries=2,
                )
                last_state = state
                if state.get("count", 0) > 0 or state.get("empty"):
                    return True
                if not state.get("portfolioVisible") and state.get("textLength", 0) == 0:
                    await asyncio.sleep(0.5)
                    continue
            except Exception as e:
                last_state = {"error": str(e)}
            await asyncio.sleep(0.5)
        logger.warning(f"Timed out waiting for portfolio rows: {last_state}")
        return False

    async def _enrich_position(self, position: dict) -> dict:
        """Map a portfolio market title to conditionId/slugs.

        First tries to use identifiers already present in the scraped card
        (href, data attributes). Then searches Gamma markets/events by title.
        Enrichment is intentionally read-only; it never clicks portfolio cards,
        because the portfolio page carousel can reveal an unrelated event URL.
        """
        title = position.get("marketTitle")
        if not title:
            return {}

        # Strategy 0: use any slug/id extracted from the portfolio card.
        href = position.get("href") or ""
        event_slug = position.get("eventSlug")
        market_slug = position.get("marketSlug")
        condition_id = position.get("conditionId")

        if href:
            m = re.search(r"eventSlug=([^&]+)", href)
            if m:
                event_slug = urllib.parse.unquote(m.group(1))
            m = re.search(r"eventId=([0-9]+)", href)
            if m:
                position["eventId"] = m.group(1)

        if market_slug and not event_slug:
            try:
                markets = await self._search_gamma_markets_by_slug(market_slug)
                if markets:
                    market = self._find_market_by_title(markets, title)
                    if market:
                        event = (market.get("events") or [None])[0]
                        if event:
                            return {
                                "conditionId": market.get("conditionId"),
                                "marketSlug": market.get("slug"),
                                "eventSlug": event.get("slug"),
                            }
                    logger.info(
                        "Market slug search for %s did not contain a market matching portfolio title '%s'",
                        market_slug,
                        title,
                    )
            except Exception as e:
                logger.warning(f"Could not resolve market slug {market_slug}: {e}")

        if event_slug:
            try:
                events = await self._search_gamma_events_by_slug(event_slug)
                if events:
                    event = events[0]
                    market = self._find_event_market_by_title(event, title)
                    if market:
                        return {
                            "conditionId": market.get("conditionId"),
                            "marketSlug": market.get("slug"),
                            "eventSlug": event.get("slug"),
                        }
                    logger.info(
                        "Event slug %s did not contain a market matching portfolio title '%s'; "
                        "falling back to title search",
                        event_slug,
                        title,
                    )
            except Exception as e:
                logger.warning(f"Could not resolve event slug {event_slug}: {e}")

        for derived_event_slug in self._derive_portfolio_event_slugs(title):
            try:
                events = await self._search_gamma_events_by_slug(derived_event_slug)
                if not events:
                    continue
                event = events[0]
                market = self._find_event_market_by_title(event, title)
                if market:
                    logger.info(
                        "Enriched '%s' via derived event slug %s",
                        title,
                        derived_event_slug,
                    )
                    return {
                        "conditionId": market.get("conditionId"),
                        "marketSlug": market.get("slug"),
                        "eventSlug": event.get("slug"),
                    }
            except Exception as e:
                logger.warning(f"Could not resolve derived event slug {derived_event_slug}: {e}")

        for derived_market_slug in self._derive_portfolio_market_slugs(title):
            try:
                markets = await self._search_gamma_markets_by_slug(derived_market_slug)
                if not markets:
                    continue
                market = self._find_market_by_title(markets, title)
                if market:
                    event = (market.get("events") or [None])[0]
                    if event:
                        logger.info(
                            "Enriched '%s' via derived market slug %s",
                            title,
                            derived_market_slug,
                        )
                        return {
                            "conditionId": market.get("conditionId"),
                            "marketSlug": market.get("slug"),
                            "eventSlug": event.get("slug"),
                        }
            except Exception as e:
                logger.warning(f"Could not resolve derived market slug {derived_market_slug}: {e}")

        # Strategy 1: search Gamma markets API by title.
        try:
            markets = await self._search_gamma_markets_by_title(title)
            if markets:
                market = self._find_market_by_title(markets, title)
                if not market:
                    logger.warning(f"Gamma API did not return exact match for title: {title}")
                else:
                    event = (market.get("events") or [None])[0]
                    if event:
                        logger.info(f"Enriched '{title}' via Gamma markets title search")
                        return {
                            "conditionId": market.get("conditionId"),
                            "marketSlug": market.get("slug"),
                            "eventSlug": event.get("slug"),
                        }
        except Exception as e:
            logger.warning(f"Gamma markets title search failed for '{title}': {e}")

        # Strategy 2: search Gamma events API by title.
        try:
            events = await self._search_gamma_events_by_title(title)
            if events:
                event = next(
                    (e for e in events if e.get("title") == title),
                    events[0],
                )
                market = self._find_event_market_by_title(event, title)
                if market:
                    logger.info(f"Enriched '{title}' via Gamma events title search")
                    return {
                        "conditionId": market.get("conditionId"),
                        "marketSlug": market.get("slug"),
                        "eventSlug": event.get("slug"),
                    }
        except Exception as e:
            logger.warning(f"Gamma events title search failed for '{title}': {e}")

        logger.warning(f"Could not enrich position '{title}': exact metadata not found")
        return {}

    @staticmethod
    def _normalize_market_question(value: Optional[str]) -> str:
        if not value:
            return ""
        import unicodedata

        text = unicodedata.normalize("NFKD", str(value))
        text = "".join(char for char in text if not unicodedata.combining(char))
        text = text.lower().replace("&", " and ")
        text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _find_event_market_by_title(self, event: dict, title: Optional[str]) -> Optional[dict]:
        """Return an event market only when its question matches the portfolio title.

        Portfolio list hrefs can point at the current carousel event rather than
        the individual position. Falling back to the first market in that event
        contaminates every scraped position with the same conditionId/slug and
        breaks SELL live-position matching.
        """
        target = self._normalize_market_question(title)
        if not target:
            return None
        for market in event.get("markets") or []:
            if self._normalize_market_question(market.get("question")) == target:
                return market
        return None

    def _find_market_by_title(self, markets: list, title: Optional[str]) -> Optional[dict]:
        target = self._normalize_market_question(title)
        if not target:
            return None
        for market in markets or []:
            if self._normalize_market_question(market.get("question")) == target:
                return market
        return None

    @staticmethod
    def _derive_portfolio_event_slugs(title: Optional[str]) -> list[str]:
        if not title:
            return []
        normalized = PolymtradeExecutor._normalize_market_question(title)
        group_match = re.search(
            r"^will .+ win group ([a-z]) in the 2026 fifa world cup$",
            normalized,
        )
        if group_match:
            return [f"world-cup-group-{group_match.group(1)}-winner"]
        return []

    @staticmethod
    def _derive_portfolio_market_slugs(title: Optional[str]) -> list[str]:
        if not title:
            return []
        normalized = PolymtradeExecutor._normalize_market_question(title)
        if not normalized:
            return []
        return [normalized.replace(" ", "-")]

    async def debug_inputs(self) -> dict:
        """Return all input/textarea elements on the current page."""
        if not self.page:
            return {"error": "page not initialized"}
        try:
            elements = await self.page.query_selector_all("input, textarea")
            result = []
            for el in elements:
                try:
                    outer = await el.evaluate("e => e.outerHTML")
                    result.append(outer)
                except Exception:
                    pass
            return {"url": self.page.url, "count": len(result), "inputs": result[:50]}
        except Exception as e:
            return {"error": str(e)}

    async def debug_html(self, save_path: str = "/tmp/polymtrade_page.html") -> dict:
        """Return the current page HTML source for debugging.

        The full HTML is written to save_path; the response returns the path and a sample.
        """
        if not self.page:
            return {"error": "page not initialized"}
        try:
            html = await self.page.content()
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(html)
            return {
                "url": self.page.url,
                "title": await self.page.title(),
                "html_length": len(html),
                "html_path": save_path,
                "html_sample": html[:2000],
            }
        except Exception as e:
            return {"error": str(e)}

    async def debug_info(self, include_screenshot: bool = True) -> dict:
        """Return current page info and optional screenshot for debugging."""
        if not self.page:
            return {"error": "page not initialized"}
        try:
            title = await self.page.title()
            url = self.page.url
            body_text = await self.page.inner_text("body")
            result = {
                "title": title,
                "url": url,
                "text_sample": body_text[:3000],
                "text_length": len(body_text),
            }
            if include_screenshot:
                try:
                    screenshot_bytes = await self.page.screenshot(type="png", timeout=10000)
                    result["screenshot_png_base64"] = base64.b64encode(screenshot_bytes).decode("utf-8")
                except Exception as ss_err:
                    logger.warning(f"Screenshot failed: {ss_err}")
                    result["screenshot_error"] = str(ss_err)
            return result
        except Exception as e:
            logger.exception(f"Failed to collect debug info: {e}")
            return {"error": str(e)}

    async def search_markets(self, query: str) -> dict:
        """Use the Polymtrade search box to look for a market.

        Returns page info plus any market links found in the results.
        """
        if not self.page:
            return {"error": "page not initialized"}
        try:
            await self.page.goto(self.base_url, wait_until="load", timeout=60000)
            await asyncio.sleep(2)

            search_input = None

            # Strategy 1: direct visible search input
            search_selectors = [
                "input[placeholder='搜索市场']",
                "input[placeholder*='搜索']",
                "input[placeholder*='Search']",
                "input[type='search']",
                "[role='searchbox']",
            ]
            for sel in search_selectors:
                try:
                    search_input = await self.page.wait_for_selector(sel, timeout=2000)
                    if search_input:
                        logger.info(f"Found search input: {sel}")
                        break
                except Exception:
                    continue

            # Strategy 2: click the search trigger to open command palette
            if not search_input:
                trigger_selectors = [
                    "text=搜索市场",
                    "div:has-text('搜索市场')",
                    "button:has-text('搜索市场')",
                    "[cmdk-input]",
                ]
                for sel in trigger_selectors:
                    try:
                        await self.page.click(sel, timeout=2000)
                        logger.info(f"Clicked search trigger: {sel}")
                        await asyncio.sleep(1)
                        # Now look for an input in the opened dialog
                        for input_sel in search_selectors + ["input", "textarea", "[contenteditable='true']"]:
                            try:
                                search_input = await self.page.wait_for_selector(input_sel, timeout=2000)
                                if search_input:
                                    logger.info(f"Found input after trigger: {input_sel}")
                                    break
                            except Exception:
                                pass
                        if search_input:
                            break
                    except Exception:
                        continue

            # Strategy 3: use keyboard shortcut (Ctrl/Cmd + K)
            if not search_input:
                logger.info("Trying keyboard shortcut to open search")
                await self.page.keyboard.press("Meta+k")
                await asyncio.sleep(1)
                for input_sel in search_selectors + ["input", "textarea", "[contenteditable='true']"]:
                    try:
                        search_input = await self.page.wait_for_selector(input_sel, timeout=2000)
                        if search_input:
                            logger.info(f"Found input after Cmd+K: {input_sel}")
                            break
                    except Exception:
                        pass

            if not search_input:
                screenshot_path = "/tmp/polymtrade_search_error.png"
                try:
                    await self.page.screenshot(path=screenshot_path)
                except Exception:
                    pass
                return {
                    "error": "could not find search input",
                    "screenshot": screenshot_path,
                    "page": await self.debug_info(),
                }

            input_html = await search_input.evaluate("e => e.outerHTML")
            logger.info(f"Search input HTML: {input_html}")
            await search_input.click()
            await asyncio.sleep(0.5)
            try:
                await search_input.fill(query)
            except Exception:
                await search_input.type(query)
            # Wait for autocomplete results to render
            await asyncio.sleep(4)
            # If nothing changed, try pressing Enter as a fallback
            text_after_fill = await self.page.inner_text("body")
            if query.lower() not in text_after_fill.lower() and len(text_after_fill) < 300:
                await search_input.press("Enter")
                await asyncio.sleep(3)

            info = await self.debug_info()
            links = await self.page.eval_on_selector_all(
                "a[href*='/event/'], a[href*='/market/'], a[href*='/events/'], a[href*='/markets/']",
                "els => els.map(e => ({href: e.href, text: e.innerText.trim()}))",
            )
            info["market_links"] = links[:50]
            return info
        except Exception as e:
            logger.exception(f"Market search failed: {e}")
            return {"error": str(e)}

    async def _gamma_request_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> dict:
        """Make a Gamma API request with exponential backoff on transient errors."""
        last_error = None
        resp = None
        metrics.gamma_api_requests += 1
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, params=params, timeout=20.0)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_error = e
                err = str(e)
                is_transient = (
                    "ConnectError" in err
                    or "Timeout" in err
                    or "ReadError" in err
                    or (resp is not None and resp.status_code >= 500)
                )
                if is_transient and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Gamma request failed (attempt {attempt + 1}/{max_retries}): {e}; retrying in {delay}s")
                    metrics.gamma_api_failures += 1
                    await asyncio.sleep(delay)
                    continue
                metrics.gamma_api_failures += 1
                raise
        raise last_error

    async def _search_gamma_markets_by_title(
        self,
        title: str,
        max_retries: int = 3,
    ) -> list:
        """Search Gamma markets API by market title."""
        proxy_url = self.proxy
        transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
        async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
            return await self._gamma_request_with_retry(
                client,
                "https://gamma-api.polymarket.com/markets",
                {"title": title, "limit": "10"},
                max_retries=max_retries,
            )

    async def _search_gamma_markets_by_slug(
        self,
        slug: str,
        max_retries: int = 3,
    ) -> list:
        """Search Gamma markets API by exact market slug."""
        proxy_url = self.proxy
        transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
        async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
            return await self._gamma_request_with_retry(
                client,
                "https://gamma-api.polymarket.com/markets",
                {"slug": slug, "limit": "10"},
                max_retries=max_retries,
            )

    async def _search_gamma_events_by_title(
        self,
        title: str,
        max_retries: int = 3,
    ) -> list:
        """Search Gamma events API by event title."""
        proxy_url = self.proxy
        transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
        async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
            return await self._gamma_request_with_retry(
                client,
                "https://gamma-api.polymarket.com/events",
                {"title": title, "limit": "10"},
                max_retries=max_retries,
            )

    async def _search_gamma_events_by_slug(
        self,
        slug: str,
        max_retries: int = 3,
    ) -> list:
        """Search Gamma events API by event slug."""
        proxy_url = self.proxy
        transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
        async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
            return await self._gamma_request_with_retry(
                client,
                "https://gamma-api.polymarket.com/events",
                {"slug": slug, "limit": "10"},
                max_retries=max_retries,
            )

    async def _resolve_event(
        self,
        market_slug: Optional[str] = None,
        condition_id: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Resolve Polymtrade event id/slug from market slug or condition id."""
        proxy_url = self.proxy
        transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
        async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
            slug_to_use = market_slug

            # 1) Try treating the slug as a Gamma event slug
            if slug_to_use:
                try:
                    resp = await client.get(
                        "https://gamma-api.polymarket.com/events",
                        params={"slug": slug_to_use, "limit": 5},
                    )
                    resp.raise_for_status()
                    events = resp.json()
                    if events and events[0].get("id"):
                        event = events[0]
                        logger.info(f"Resolved event via Gamma events slug: {event['id']}")
                        return str(event["id"]), event["slug"]
                except Exception as e:
                    logger.warning(f"Failed to resolve event via Gamma events slug: {e}")

            # 2) Try treating the slug as a Gamma market slug
            if slug_to_use:
                try:
                    resp = await client.get(
                        "https://gamma-api.polymarket.com/markets",
                        params={"slug": slug_to_use, "limit": 5},
                    )
                    resp.raise_for_status()
                    markets = resp.json()
                    if markets and markets[0].get("events"):
                        event = markets[0]["events"][0]
                        logger.info(f"Resolved event via Gamma markets slug: {event['id']}")
                        return str(event["id"]), event["slug"]
                except Exception as e:
                    logger.warning(f"Failed to resolve event via Gamma markets slug: {e}")

            # 3) Fallback: condition_id -> CLOB market slug -> Gamma event.
            # Gamma's conditionId filters are unreliable (they often return
            # unrelated results), so we use CLOB to get the canonical market_slug
            # and then resolve the event from Gamma using that slug.
            if condition_id:
                try:
                    resp = await client.get(
                        f"https://clob.polymarket.com/markets/{condition_id}"
                    )
                    resp.raise_for_status()
                    clob_data = resp.json()
                    slug_to_use = clob_data.get("market_slug") or slug_to_use
                    logger.info(f"Resolved CLOB slug {slug_to_use} for condition {condition_id}")
                except Exception as e:
                    logger.warning(f"Failed to resolve conditionId via CLOB: {e}")

            if slug_to_use:
                for endpoint in ["events", "markets"]:
                    try:
                        resp = await client.get(
                            f"https://gamma-api.polymarket.com/{endpoint}",
                            params={"slug": slug_to_use, "limit": 5},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        event = None
                        if data:
                            if endpoint == "events":
                                event = data[0]
                            else:
                                event = data[0].get("events", [None])[0]
                        if event and event.get("id"):
                            logger.info(f"Resolved event via {endpoint} fallback: {event['id']}")
                            return str(event["id"]), event["slug"]
                    except Exception as e:
                        logger.warning(f"Failed to resolve event via {endpoint} fallback: {e}")

            raise RuntimeError(
                f"Could not resolve Polymtrade event for slug={market_slug}, condition_id={condition_id}"
            )

    async def execute_trade(
        self,
        market_slug: str,
        side: str,
        outcome: str,
        amount_usdc: float,
        condition_id: Optional[str] = None,
        size_shares: Optional[float] = None,
        market_title: Optional[str] = None,
    ):
        """Execute a trade on Polymtrade.

        Polymtrade's market page is `/portfolio?eventId=<id>&eventSlug=<slug>&eventSource=polymarket`.
        The outcome rows have a Yes (是) / No (否) button pair. We click the appropriate
        button to open the buy dialog, enter the amount, and submit.
        """
        if not self.is_ready():
            raise RuntimeError("Executor not ready")

        if not self._logged_in:
            logger.error("Cannot trade: not logged in to Polymtrade")
            raise RuntimeError("Not logged in")

        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Invalid side: {side}")

        try:
            event_id, event_slug = await self._resolve_event(
                market_slug=market_slug, condition_id=condition_id
            )

            if side == "BUY":
                result = await self._execute_buy(
                    event_id, event_slug, outcome, amount_usdc,
                    market_slug=market_slug, market_title=market_title
                )
                # Post-trade verification: confirm the buy actually affected the account.
                baseline = result.get("baseline") or {}
                verified = await self._verify_buy_executed(
                    outcome=outcome,
                    amount_usdc=amount_usdc,
                    baseline=baseline,
                    market_slug=market_slug,
                    market_title=market_title,
                )
                result["verified"] = verified
            else:
                result = await self._execute_sell(
                    event_id, event_slug, outcome, amount_usdc, size_shares,
                    market_slug=market_slug, market_title=market_title
                )
                # Post-trade verification: confirm the sell actually affected the account.
                baseline = result.get("baseline") or {}
                verified = await self._verify_sell_executed(
                    outcome=outcome,
                    size_shares=size_shares,
                    baseline=baseline,
                    market_slug=market_slug,
                    market_title=market_title,
                )
                result["verified"] = verified

            logger.info(f"Trade executed: {result}")
            return result

        except Exception as e:
            self.last_error = str(e)
            logger.exception(f"Trade execution failed: {e}")
            try:
                safe_slug = (market_slug or condition_id or "unknown").replace("/", "_")
                screenshot_path = f"/tmp/trade_error_{safe_slug}.png"
                await self.page.screenshot(path=screenshot_path)
                logger.info(f"Error screenshot saved: {screenshot_path}")
            except Exception:
                pass
            raise

    async def _wait_for_page_ready(
        self,
        timeout: float = 15.0,
        market_title: Optional[str] = None,
        event_id: Optional[str] = None,
    ):
        """Wait until the event page has rendered market rows.

        The portfolio page may auto-rotate through position events, so we no
        longer gate on the exact ``eventId`` appearing in the URL. Instead we
        wait until the market keywords and Yes/No side buttons are visible in
        the DOM. ``event_id`` is kept as a diagnostic argument only.
        """
        keywords = []
        if market_title:
            keywords = self._extract_market_keywords(market_title=market_title)
            # Keep only the shortest/most specific keywords for a quick check.
            keywords = [k for k in keywords if len(k) <= 20][:4]

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                has_content = await self._evaluate_with_navigation_retry(
                    """(args) => {
                        const keywords = args[0];
                        const sideLabels = ['是', '否', 'Yes', 'No', 'Buy Yes', 'Buy No', 'Long', 'Short', '买入', '卖出', 'Buy', 'Sell'];
                        const textOf = (el) => (el ? (el.innerText || el.textContent || "").trim() : "");
                        const norm = (s) => (s || "").toLowerCase().replace(/\\s+/g, " ").trim();
                        const bodyText = (document.body?.innerText || '').trim();
                        const hasMarkets = document.querySelectorAll('.market, [class*="market"], [class*="outcome"], li, [role="listitem"]').length > 0;
                        const isTradeAction = (el) => {
                            const t = norm(textOf(el));
                            if (t.length > 80) return false;
                            return sideLabels.some(l => {
                                const lnorm = l.toLowerCase();
                                return t === lnorm || t.startsWith(lnorm + " ") || t.endsWith(" " + lnorm) || t.includes(" " + lnorm + " ");
                            });
                        };
                        const hasSideButtons = Array.from(document.querySelectorAll('button, [role="button"], a, div[class*="button"], div[tabindex="0"]')).some(isTradeAction);
                        if (keywords.length > 0) {
                            const bodyLower = norm(bodyText);
                            const hasKeyword = keywords.some(kw => bodyLower.includes(kw.toLowerCase()));
                            const rows = Array.from(document.querySelectorAll('article, section, li, [role="listitem"], [class*="market"], [class*="outcome"], [class*="row"], div'));
                            const hasTargetTradeRow = rows.some(row => {
                                const rect = row.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0) return false;
                                const text = norm(textOf(row));
                                if (!text || text.length > 1400) return false;
                                if (!keywords.some(kw => text.includes(kw.toLowerCase()))) return false;
                                return Array.from(row.querySelectorAll('button, [role="button"], a, div[class*="button"], div[tabindex="0"], .cursor-pointer')).some(isTradeAction);
                            });
                            if (hasTargetTradeRow) return true;
                            return hasMarkets && hasKeyword && hasSideButtons;
                        }
                        return (hasMarkets || hasSideButtons) && bodyText.length > 200;
                    }""",
                    [keywords],
                    label="wait_for_page_ready.evaluate",
                )
                if has_content:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def _wait_for_event_url(self, event_id: str, timeout: float = 8.0) -> bool:
        """Wait until the portfolio carousel lands on the target event URL."""
        if not event_id:
            return True
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if event_id in self.page.url:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.2)
        return False

    async def _is_target_event_visible(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
        timeout: float = 8.0,
    ) -> bool:
        """Return True when the target market/outcome is rendered on the page.

        This is used for BUY attempts instead of hard-gating on ``eventId``
        appearing in the URL. The portfolio carousel can rotate away from an
        event where the Bridge account has no open position, leaving the page
        content correct but the URL pointing at a different event.
        """
        keywords = self._extract_market_keywords(market_slug, market_title)
        # Keep the most specific short keywords; avoid overly long phrases.
        keywords = [k for k in keywords if len(k) <= 25][:5]

        binary_updown = self._is_binary_updown_market(market_slug, market_title)
        side_labels = self._side_labels_for_outcome(outcome, market_slug, market_title)

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                result = await self._evaluate_with_navigation_retry(
                    """(args) => {
                        const [keywords, sideLabels, binaryOutcomeMode] = args;
                        const textOf = (el) => (el ? (el.innerText || el.textContent || "").trim() : "");
                        const norm = (s) => (s || "").toLowerCase().replace(/\\s+/g, " ").trim();
                        const bodyText = norm(textOf(document.body));

                        const keywordHits = keywords.filter(kw => bodyText.includes(kw.toLowerCase())).length;
                        const hasKeyword = keywords.length === 0 || keywordHits > 0;

                        const tradeLabels = binaryOutcomeMode
                            ? [...sideLabels]
                            : [...sideLabels, '买入', '卖出', 'buy', 'sell', 'Buy', 'Sell'];
                        const isTradeAction = (el) => {
                            const t = norm(textOf(el));
                            if (t.length > 80) return false;
                            return tradeLabels.some(l => {
                                const lnorm = l.toLowerCase();
                                return t === lnorm || t.startsWith(lnorm + " ") || t.endsWith(" " + lnorm) || t.includes(" " + lnorm + " ");
                            });
                        };

                        const hasSide = Array.from(document.querySelectorAll('button, [role="button"], a, div[class*="button"], div[tabindex="0"], .cursor-pointer')).some(isTradeAction);

                        const hasOutcome = sideLabels.some(l => bodyText.includes(l.toLowerCase()));
                        const rows = Array.from(document.querySelectorAll('article, section, li, [role="listitem"], [class*="market"], [class*="outcome"], [class*="row"], div'));
                        const hasTargetTradeRow = rows.some(row => {
                            const rect = row.getBoundingClientRect();
                            if (rect.width === 0 || rect.height === 0) return false;
                            const text = norm(textOf(row));
                            if (!text || text.length > 1400) return false;
                            if (keywords.length && !keywords.some(kw => text.includes(kw.toLowerCase()))) return false;
                            const actions = Array.from(row.querySelectorAll('button, [role="button"], a, div[class*="button"], div[tabindex="0"], .cursor-pointer'));
                            return actions.some(isTradeAction);
                        });
                        if (hasTargetTradeRow) {
                            return {
                                visible: true,
                                keywordHits,
                                hasSide,
                                hasOutcome,
                                hasTargetTradeRow,
                                bodyLength: bodyText.length,
                                url: window.location.href,
                            };
                        }
                        if (binaryOutcomeMode) {
                            return {
                                visible: false,
                                keywordHits,
                                hasSide,
                                hasOutcome,
                                hasTargetTradeRow,
                                bodyLength: bodyText.length,
                                url: window.location.href,
                            };
                        }
                        return {
                            visible: hasKeyword && hasSide && hasOutcome,
                            keywordHits,
                            hasSide,
                            hasOutcome,
                            hasTargetTradeRow,
                            bodyLength: bodyText.length,
                            url: window.location.href,
                        };
                    }""",
                    [keywords, side_labels, binary_updown],
                    label="target_event_visible.evaluate",
                )
                if result and result.get("visible"):
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.3)
        return False

    def _side_labels_for_outcome(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ) -> list[str]:
        outcome_norm = outcome.strip().lower()
        if self._is_binary_updown_market(market_slug, market_title) and outcome_norm in ("up", "down"):
            if outcome_norm == "up":
                return ["Up", "UP", "涨", "上涨"]
            return ["Down", "DOWN", "跌", "下跌"]
        if outcome_norm in ("yes", "是", "true"):
            return ["是", "Yes", "Buy Yes", "Long"]
        if outcome_norm in ("no", "否", "false"):
            return ["否", "No", "Buy No", "Short"]
        return ["是", "Yes", outcome]

    async def _open_target_market_from_portfolio_row(
        self,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ) -> bool:
        """Open a target market from the portfolio holdings list if we landed there.

        After a BUY succeeds, Polymtrade can leave the next trade on the portfolio
        dashboard. The holding row contains the market title and outcome text, but
        not the tradable Up/Down buttons. Clicking the row brings the event panel
        back before selection retries.
        """
        keywords = self._extract_market_keywords(market_slug, market_title)
        keywords = [k for k in keywords if len(k) <= 25][:6]
        try:
            result = await self._evaluate_with_navigation_retry(
                """(args) => {
                    const [marketTitle, keywords] = args;
                    const textOf = (el) => (el ? (el.innerText || el.textContent || "").trim() : "");
                    const norm = (s) => (s || "").toLowerCase().replace(/\\s+/g, " ").trim();
                    const titleNorm = norm(marketTitle || "");
                    const kws = (keywords || []).map(k => String(k).toLowerCase());
                    const isClickable = (el) => {
                        if (!el) return false;
                        const tag = el.tagName;
                        const role = el.getAttribute("role");
                        const cls = (el.getAttribute("class") || "").toLowerCase();
                        return tag === "BUTTON"
                            || tag === "A"
                            || role === "button"
                            || cls.includes("cursor-pointer")
                            || cls.includes("button")
                            || el.onclick
                            || el.getAttribute("tabindex") === "0";
                    };
                    const clickableAncestor = (el) => {
                        let cur = el;
                        for (let depth = 0; depth < 7 && cur; depth++, cur = cur.parentElement) {
                            if (isClickable(cur)) return cur;
                        }
                        return el;
                    };
                    const rows = Array.from(document.querySelectorAll('li, [role="listitem"], article, section, div'))
                        .map(row => ({row, text: textOf(row), lower: norm(textOf(row))}))
                        .filter(item => item.text && item.text.length < 700);
                    const portfolioHints = ["持仓", "历史", "份", "portfolio", "holdings"];
                    const candidates = rows.filter(item => {
                        const text = item.lower;
                        const titleHit = titleNorm && text.includes(titleNorm);
                        const kwHits = kws.filter(kw => text.includes(kw)).length;
                        const portfolioLike = portfolioHints.some(h => text.includes(h));
                        return (titleHit || kwHits >= Math.min(3, Math.max(1, kws.length))) && portfolioLike;
                    }).sort((a, b) => a.text.length - b.text.length);
                    for (const item of candidates) {
                        const target = clickableAncestor(item.row);
                        if (!target) continue;
                        target.scrollIntoView({block: "center", inline: "center"});
                        target.click();
                        return {clicked: true, label: textOf(target).slice(0, 120)};
                    }
                    return {clicked: false};
                }""",
                [market_title or "", keywords],
                label="open_portfolio_market.evaluate",
            )
            if result and result.get("clicked"):
                logger.info(f"Clicked portfolio market row: {result.get('label')}")
                return True
        except Exception as e:
            logger.warning(f"Failed to click portfolio market row: {e}")
        return False

    async def _is_buy_dialog_open(self, timeout: float = 3.0) -> bool:
        """Return True if a trade amount input is visible."""
        selectors = [
            "input[name='buyAmount']",
            "input[name*='amount' i]",
            "input[id*='amount' i]",
            "input[data-test*='amount' i]",
            "input[data-testid*='amount' i]",
            "input[inputmode='decimal']",
            "input[type='number']",
            "input[type='text']",
            "input[role='spinbutton']",
            "[role='spinbutton']",
            "input[placeholder*='Amount' i]",
            "input[placeholder*='amount' i]",
            "input[placeholder*='USDC' i]",
            "input[placeholder*='0.0' i]",
            "input[placeholder*='数量' i]",
            "input[placeholder*='金额' i]",
            "input[class*='amount' i]",
            "input[class*='trade-input' i]",
            "input[aria-label*='amount' i]",
            "input[aria-label*='USDC' i]",
            "input[aria-label*='数量' i]",
            "input[aria-label*='金额' i]",
            "textarea[placeholder*='Amount' i]",
            "textarea[placeholder*='amount' i]",
            "textarea[placeholder*='金额' i]",
            "[role='textbox'][aria-label*='amount' i]",
            "[role='textbox'][aria-label*='USDC' i]",
            "[role='textbox'][aria-label*='金额' i]",
            "[contenteditable='true'][aria-label*='amount' i]",
            "[contenteditable='true'][aria-label*='USDC' i]",
            "[contenteditable='true'][aria-label*='金额' i]",
            "[contenteditable='plaintext-only'][aria-label*='amount' i]",
            "[contenteditable='plaintext-only'][aria-label*='USDC' i]",
            "[contenteditable='plaintext-only'][aria-label*='金额' i]",
        ]
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                input_el = await self._find_trade_input(prefer_sell=False)
                if input_el and await input_el.is_visible():
                    return True
            except Exception:
                pass
            for selector in selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=500)
                    if el and await el.is_visible():
                        in_trade_form = await el.evaluate(
                            "el => !!el.closest('[role=\"dialog\"], .trade-dialog, [class*=\"trade\"], [class*=\"modal\"], [data-test*=\"trade\" i], [data-testid*=\"trade\" i]')"
                        )
                        if in_trade_form:
                            return True
                except Exception:
                    continue
            await asyncio.sleep(0.2)
        return False

    async def _is_sell_dialog_open(self, timeout: float = 3.0) -> bool:
        """Return True if a real sell form/dialog is open."""
        selectors = [
            "input[name='soldAmount']",
            "[role='dialog'] input[inputmode='decimal']",
            "[role='dialog'] input[type='number']",
            "[role='dialog'] input[placeholder*='Shares' i]",
            "[role='dialog'] input[placeholder*='shares' i]",
            "button#fullsell",
            "button#sellbtn",
            "[role='dialog'] button:has-text('卖出')",
            "[role='dialog'] button:has-text('确认')",
        ]
        deadline = time.time() + timeout
        while time.time() < deadline:
            for selector in selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=500)
                    if el and await el.is_visible():
                        return True
                except Exception:
                    continue
            await asyncio.sleep(0.2)
        return False

    @staticmethod
    def _is_transient_goto_error(error: Exception) -> bool:
        text = str(error).lower()
        return (
            "err_aborted" in text
            or "net::" in text
            or "err_connection" in text
            or "interrupted by another navigation" in text
            or ("timeout" in text and "goto" in text)
        )

    def _navigation_target_reached(self, url: str) -> bool:
        """Return True if the current page URL already represents the target."""
        try:
            current_url = self.page.url if self.page else ""
        except Exception:
            return False
        if not current_url:
            return False
        try:
            target = urllib.parse.urlparse(url)
            current = urllib.parse.urlparse(current_url)
            if target.netloc and current.netloc and target.netloc != current.netloc:
                return False
            target_qs = urllib.parse.parse_qs(target.query)
            current_qs = urllib.parse.parse_qs(current.query)
            for key in ("eventId", "eventSlug", "eventSource"):
                target_value = (target_qs.get(key) or [None])[0]
                if target_value and target_value != (current_qs.get(key) or [None])[0]:
                    return False
            target_path = target.path.rstrip("/")
            current_path = current.path.rstrip("/")
            if target_path and target_path != "/" and current_path != target_path:
                return False
            return True
        except Exception:
            return current_url.startswith(url)

    async def _goto_with_retry(
        self,
        url: str,
        max_retries: int = 4,
        *,
        wait_until: str = "domcontentloaded",
        timeout_ms: int = 45000,
        fallback_wait_until: str = "commit",
    ) -> None:
        """Navigate to a URL, retrying on transient network/navigation errors."""
        last_error = None
        for attempt in range(max_retries):
            try:
                await self.page.goto(url, wait_until=wait_until, timeout=timeout_ms)
                return
            except Exception as e:
                last_error = e
                if self._is_transient_goto_error(e):
                    if self._navigation_target_reached(url):
                        logger.warning(
                            f"Navigation reported transient error but target URL is reached; continuing: {e}"
                        )
                        return
                    logger.warning(f"Navigation transient failure (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(1.0 + attempt * 1.5, 5.0))
                        continue
                    break
                raise

        if fallback_wait_until and fallback_wait_until != wait_until:
            try:
                logger.warning(
                    f"Navigation failed after {max_retries} {wait_until} attempts; "
                    f"trying {fallback_wait_until} fallback for {url}: {last_error}"
                )
                await self.page.goto(
                    url,
                    wait_until=fallback_wait_until,
                    timeout=min(timeout_ms, 20000),
                )
                try:
                    await self.page.wait_for_load_state(wait_until, timeout=10000)
                except Exception as settle_error:
                    logger.warning(
                        f"Navigation reached {fallback_wait_until} but did not settle to "
                        f"{wait_until}: {settle_error}"
                    )
                return
            except Exception as fallback_error:
                last_error = fallback_error
                if self._is_transient_goto_error(fallback_error) and self._navigation_target_reached(url):
                    logger.warning(
                        f"Fallback navigation reported transient error but target URL is reached; "
                        f"continuing: {fallback_error}"
                    )
                    return
        raise RuntimeError(f"Navigation failed after {max_retries} attempts for {url}: {last_error}") from last_error

    async def _execute_buy(
        self,
        event_id: str,
        event_slug: str,
        outcome: str,
        amount_usdc: float,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ):
        """Execute a BUY order on the Polymtrade event page.

        We open a fresh page for each BUY. The persistent portfolio page can be
        in the middle of its position-event carousel; reusing it causes the
        carousel to rotate away from events where the Bridge account has no
        open position. A new page starts from a clean state and keeps the
        target event stable.
        """
        if not self.context:
            raise RuntimeError("Browser context not initialized")

        trade_page = await self.context.new_page()
        original_page = self.page
        self.page = trade_page
        try:
            return await self._execute_buy_on_page(
                event_id, event_slug, outcome, amount_usdc,
                market_slug=market_slug, market_title=market_title
            )
        finally:
            try:
                await trade_page.close()
            except Exception:
                pass
            self.page = original_page

    async def _execute_buy_on_page(
        self,
        event_id: str,
        event_slug: str,
        outcome: str,
        amount_usdc: float,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ):
        """Internal BUY implementation that operates on ``self.page``."""
        market_url = (
            f"{self.base_url}/portfolio?eventId={event_id}"
            f"&eventSlug={event_slug}&eventSource=polymarket"
        )
        # Fallback URL without eventId. Polymtrade redirects this to the canonical
        # event URL and it can be more reliable when the portfolio carousel would
        # otherwise rotate away from an event where we have no open position.
        fallback_url = (
            f"{self.base_url}/portfolio?eventSlug={event_slug}"
            f"&eventSource=polymarket"
        )
        logger.info(f"Navigating to {market_url}")
        await self._goto_with_retry(market_url)
        await asyncio.sleep(3)
        if not await self._wait_for_page_ready(timeout=15.0, market_title=market_title, event_id=event_id):
            logger.warning("Event page content did not render in time; proceeding anyway")

        # Pre-flight balance check: fail fast if we can read the balance and it
        # is clearly insufficient. This avoids entering the modal retry loop when
        # the account simply cannot afford the trade.
        balance = await self._get_usdc_balance()
        if balance is not None and balance < amount_usdc * 1.05:
            raise RuntimeError(
                f"Insufficient balance for BUY: available {balance:.4f} USDC, "
                f"required ~{amount_usdc * 1.05:.4f} USDC (including 5% buffer)"
            )

        # On Polymtrade a network/token selection modal may pop up when the user
        # first clicks an outcome. We try to actively select Polygon/USDC in the
        # modal; if that fails we fall back to dismissing it. If the modal keeps
        # coming back, the account likely lacks sufficient deposit balance.
        buy_dialog_open = False
        outcome_selected = False
        for attempt in range(6):
            # The portfolio page auto-rotates through the user's position events.
            # Instead of waiting for the exact eventId to appear in the URL, we
            # verify the target market/outcome content is actually rendered. If
            # the carousel rotated away, we re-navigate to bring it back.
            if not await self._is_target_event_visible(
                outcome, market_slug=market_slug, market_title=market_title, timeout=8.0
            ):
                current_url = self.page.url if self.page else ""
                logger.warning(
                    f"Target market content not visible (attempt {attempt + 1}); "
                    f"current URL: {current_url}"
                )
                if attempt < 5:
                    if await self._open_target_market_from_portfolio_row(
                        market_slug=market_slug, market_title=market_title
                    ):
                        await asyncio.sleep(1.5)
                        continue
                    target_url = fallback_url if attempt % 2 else market_url
                    logger.info(f"Re-navigating to {target_url}")
                    await self._goto_with_retry(target_url)
                    await asyncio.sleep(1.0)
                    continue
                raise RuntimeError(
                    f"Target market content never appeared for {market_title or market_slug}"
                )

            try:
                await self._select_polymtrade_outcome(
                    outcome, market_slug=market_slug, market_title=market_title
                )
                outcome_selected = True
            except RuntimeError as e:
                if "Could not select outcome" in str(e):
                    logger.warning(f"Outcome selection failed (attempt {attempt + 1}): {e}")
                    if attempt < 5:
                        # Categorical pages sometimes render rows lazily; wait
                        # a bit and try again without reloading first.
                        await asyncio.sleep(1.5)
                        continue
                    raise
                raise

            await asyncio.sleep(0.8)

            if await self._is_network_modal_open():
                logger.info(f"Network modal open after outcome click (attempt {attempt + 1}), handling")
                if await self._is_deposit_or_insufficient_modal_open():
                    raise RuntimeError(
                        "Insufficient balance for BUY: deposit modal is blocking the trade. "
                        "The Bridge account needs USDC balance or a deposit."
                    )
                # First try to actually select a network/token.
                handled = await self._select_network_and_token_in_modal()
                if not handled:
                    handled = await self._dismiss_modal_dialogs()
                if not handled:
                    raise RuntimeError("Could not handle network/deposit modal")
                await asyncio.sleep(0.5)
                continue

            if await self._is_buy_dialog_open(timeout=3.0):
                logger.info("Buy dialog detected after outcome click")
                buy_dialog_open = True
                break

            logger.warning(f"Buy dialog not detected after outcome click (attempt {attempt + 1}), retrying")
            # Page may have navigated; give it a moment to settle before retrying.
            await asyncio.sleep(1.0)

        if not buy_dialog_open:
            if await self._is_network_modal_open():
                if await self._is_deposit_or_insufficient_modal_open():
                    raise RuntimeError(
                        "Insufficient balance for BUY: deposit modal is blocking the trade. "
                        "The Bridge account needs USDC balance or a deposit."
                    )
                raise RuntimeError(
                    "Network/deposit modal keeps blocking the trade. "
                    "The Bridge account probably has insufficient USDC balance or needs a deposit."
                )
            if not outcome_selected:
                raise RuntimeError("Could not select outcome after retries")
            try:
                screenshot_path = "/tmp/trade_buy_dialog_open_error.png"
                await self.page.screenshot(path=screenshot_path)
                logger.warning(f"Buy dialog open error screenshot saved: {screenshot_path}")
            except Exception:
                pass
            raise RuntimeError("Could not open buy dialog after outcome click")

        # Final safety check before entering the amount.
        if await self._is_network_modal_open():
            if await self._is_deposit_or_insufficient_modal_open():
                raise RuntimeError(
                    "Insufficient balance for BUY: deposit modal is blocking the trade. "
                    "The Bridge account needs USDC balance or a deposit."
                )
            if not await self._select_network_and_token_in_modal():
                await self._dismiss_modal_dialogs()
            await asyncio.sleep(0.3)
            if await self._is_network_modal_open():
                raise RuntimeError("Network/deposit modal blocked trade")

        # Capture pre-trade baseline for post-execution verification.
        baseline = await self._capture_buy_baseline(
            outcome, market_slug=market_slug, market_title=market_title
        )

        # Enter amount in the buy dialog
        await self._enter_amount(amount_usdc)

        # Submit the buy order
        await self._click_buy_button()

        # Wait for confirmation
        await self._confirm_trade()

        return {
            "status": "executed",
            "side": "BUY",
            "outcome": outcome,
            "amount_usdc": amount_usdc,
            "event_id": event_id,
            "event_slug": event_slug,
            "baseline": baseline,
        }

    async def _execute_sell(
        self,
        event_id: str,
        event_slug: str,
        outcome: str,
        amount_usdc: float,
        size_shares: Optional[float] = None,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ):
        """Execute a SELL order on the Polymtrade event page.

        The position card on the event page exposes a sell button. Clicking it
        opens a dialog with input[name='soldAmount'] and #sellbtn. If size_shares
        is provided we sell that many shares; otherwise we sell the full position.
        """
        market_url = (
            f"{self.base_url}/portfolio?eventId={event_id}"
            f"&eventSlug={event_slug}&eventSource=polymarket"
        )
        logger.info(f"Navigating to event page for SELL: {market_url}")
        await self._goto_with_retry(market_url)
        await asyncio.sleep(3)
        if not await self._wait_for_page_ready(timeout=15.0, market_title=market_title, event_id=event_id):
            logger.warning("Event page content did not render in time for SELL; proceeding anyway")

        if not await self._wait_for_event_url(event_id, timeout=8.0):
            logger.warning(f"Target event {event_id} URL did not appear for SELL; proceeding anyway")

        # Dismiss any network/token modal before trying to open the sell dialog.
        if await self._is_network_modal_open():
            if await self._is_deposit_or_insufficient_modal_open():
                raise RuntimeError(
                    "Insufficient balance/deposit modal blocked SELL. "
                    "The Bridge account needs USDC balance or a deposit."
                )
            logger.info("Network modal open before SELL, handling")
            handled = await self._select_network_and_token_in_modal()
            if not handled:
                handled = await self._dismiss_modal_dialogs()
            if not handled:
                raise RuntimeError("Could not handle network/deposit modal before SELL")
            await asyncio.sleep(0.5)

        # Open the sell dialog for the position matching the outcome, retrying if
        # a modal or lazy rendering interferes.
        sell_dialog_open = False
        for attempt in range(5):
            if not await self._wait_for_event_url(event_id, timeout=6.0):
                logger.warning(f"Target event {event_id} did not appear in URL before SELL attempt {attempt + 1}")
                if attempt < 4:
                    await asyncio.sleep(1.0)
                    continue
                raise RuntimeError(f"Target event {event_id} URL never appeared for SELL")

            try:
                await self._open_sell_dialog(
                    outcome, market_slug=market_slug, market_title=market_title
                )
            except RuntimeError as e:
                logger.warning(f"Open sell dialog failed (attempt {attempt + 1}): {e}")
                if attempt < 4:
                    await asyncio.sleep(1.5)
                    continue
                raise

            await asyncio.sleep(0.8)

            if await self._is_network_modal_open():
                logger.info(f"Network modal open after SELL dialog attempt {attempt + 1}, handling")
                if await self._is_deposit_or_insufficient_modal_open():
                    raise RuntimeError(
                        "Insufficient balance/deposit modal blocked SELL. "
                        "The Bridge account needs USDC balance or a deposit."
                    )
                handled = await self._select_network_and_token_in_modal()
                if not handled:
                    handled = await self._dismiss_modal_dialogs()
                if not handled:
                    raise RuntimeError("Could not handle network/deposit modal during SELL")
                await asyncio.sleep(0.5)
                continue

            if await self._is_sell_dialog_open(timeout=3.0):
                logger.info("Sell dialog detected")
                sell_dialog_open = True
                break

            logger.warning(f"Sell dialog not detected after open attempt {attempt + 1}, retrying")
            await asyncio.sleep(1.0)

        if not sell_dialog_open:
            if await self._is_network_modal_open():
                if await self._is_deposit_or_insufficient_modal_open():
                    raise RuntimeError(
                        "Insufficient balance/deposit modal blocked SELL. "
                        "The Bridge account needs USDC balance or a deposit."
                    )
                raise RuntimeError(
                    "Network/deposit modal keeps blocking the SELL. "
                    "The Bridge account may need a network selection or deposit."
                )
            try:
                screenshot_path = "/tmp/trade_sell_dialog_open_error.png"
                await self.page.screenshot(path=screenshot_path)
                logger.warning(f"Sell dialog open error screenshot saved: {screenshot_path}")
            except Exception:
                pass
            raise RuntimeError("Could not open sell dialog after sell button click")

        # Final safety check before entering the amount.
        if await self._is_network_modal_open():
            if await self._is_deposit_or_insufficient_modal_open():
                raise RuntimeError(
                    "Insufficient balance/deposit modal blocked SELL. "
                    "The Bridge account needs USDC balance or a deposit."
                )
            if not await self._select_network_and_token_in_modal():
                await self._dismiss_modal_dialogs()
            await asyncio.sleep(0.3)
            if await self._is_network_modal_open():
                raise RuntimeError("Network/deposit modal blocked SELL")

        # Capture pre-trade baseline for post-execution verification.
        baseline = await self._capture_sell_baseline(
            outcome, market_slug=market_slug, market_title=market_title
        )
        live_position_qty = baseline.get("position_quantity")
        if (
            live_position_qty is not None
            and size_shares is not None
            and size_shares > live_position_qty
            and live_position_qty > 0
        ):
            logger.warning(
                f"Clamping SELL shares from {size_shares} to live position {live_position_qty}"
            )
            size_shares = live_position_qty

        # The sell dialog works in shares, not USDC.
        if size_shares is not None and size_shares > 0:
            entered = await self._enter_sell_shares(size_shares)
            if not entered:
                logger.warning("Could not enter sell shares, falling back to full")
                try:
                    await self.page.click("button#fullsell", timeout=3000)
                    logger.info("Selected full position sell (100%)")
                except Exception:
                    pass
        else:
            try:
                await self.page.click("button#fullsell", timeout=3000)
                logger.info("Selected full position sell (100%)")
            except Exception:
                logger.info("Full-sell button not found, using default amount")

        # Submit the sell order, retrying the button click if it is transiently stale.
        for attempt in range(3):
            try:
                await self._click_sell_button()
                break
            except RuntimeError as e:
                logger.warning(f"Click sell button failed (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    await asyncio.sleep(1.0)
                    continue
                raise

        # Wait for confirmation
        await self._confirm_trade()

        return {
            "status": "executed",
            "side": "SELL",
            "outcome": outcome,
            "amount_usdc": amount_usdc,
            "size_shares": size_shares,
            "event_id": event_id,
            "event_slug": event_slug,
            "baseline": baseline,
        }

    def _extract_market_keywords(self, market_slug: Optional[str] = None, market_title: Optional[str] = None) -> list:
        """Extract searchable keywords from a market slug or title.

        Long English titles/slugs are split and common stop-words are removed so
        we can match the short translated labels rendered by Polymtrade.
        """
        import unicodedata

        # FIFA / common 3-letter country codes that Polymarket embeds in slugs
        # such as "fifwc-bra-hai". Maps code -> (english forms, chinese forms).
        code_aliases = {
            "arg": (["argentina"], ["阿根廷"]),
            "bel": (["belgium"], ["比利时"]),
            "bra": (["brazil"], ["巴西"]),
            "can": (["canada"], ["加拿大"]),
            "col": (["colombia"], ["哥伦比亚"]),
            "cpv": (["cape verde"], ["佛得角"]),
            "cro": (["croatia"], ["克罗地亚"]),
            "cur": (["curacao", "curaçao"], ["库拉索"]),
            "den": (["denmark"], ["丹麦"]),
            "ecu": (["ecuador"], ["厄瓜多尔"]),
            "eng": (["england"], ["英格兰"]),
            "esp": (["spain"], ["西班牙"]),
            "fra": (["france"], ["法国"]),
            "ger": (["germany"], ["德国"]),
            "hai": (["haiti"], ["海地"]),
            "hti": (["haiti"], ["海地"]),
            "irn": (["iran"], ["伊朗"]),
            "ita": (["italy"], ["意大利"]),
            "jpn": (["japan"], ["日本"]),
            "ksa": (["saudi arabia"], ["沙特阿拉伯"]),
            "mar": (["morocco"], ["摩洛哥"]),
            "mex": (["mexico"], ["墨西哥"]),
            "ned": (["netherlands"], ["荷兰"]),
            "por": (["portugal"], ["葡萄牙"]),
            "sco": (["scotland"], ["苏格兰"]),
            "sui": (["switzerland"], ["瑞士"]),
            "swe": (["sweden"], ["瑞典"]),
            "tun": (["tunisia"], ["突尼斯"]),
            "uru": (["uruguay"], ["乌拉圭"]),
            "usa": (["usa"], ["美国"]),
        }

        country_aliases = {
            "argentina": ["阿根廷"],
            "belgium": ["比利时"],
            "brazil": ["巴西"],
            "canada": ["加拿大"],
            "cape verde": ["佛得角"],
            "colombia": ["哥伦比亚"],
            "croatia": ["克罗地亚"],
            "curacao": ["库拉索"],
            "curaçao": ["库拉索"],
            "denmark": ["丹麦"],
            "ecuador": ["厄瓜多尔"],
            "england": ["英格兰"],
            "france": ["法国"],
            "germany": ["德国"],
            "haiti": ["海地"],
            "iran": ["伊朗"],
            "italy": ["意大利"],
            "japan": ["日本"],
            "mexico": ["墨西哥"],
            "morocco": ["摩洛哥"],
            "netherlands": ["荷兰"],
            "portugal": ["葡萄牙"],
            "saudi arabia": ["沙特阿拉伯"],
            "scotland": ["苏格兰"],
            "spain": ["西班牙"],
            "sweden": ["瑞典"],
            "switzerland": ["瑞士"],
            "tunisia": ["突尼斯"],
            "uruguay": ["乌拉圭"],
            "usa": ["美国"],
        }

        stop_words = {
            "will", "the", "a", "an", "be", "at", "in", "of", "for", "to", "by",
            "and", "or", "is", "are", "on", "vs", "with", "from", "as", "it",
            "their", "there", "this", "that", "these", "those", "i", "you", "he",
            "she", "we", "they", "my", "your", "his", "her", "our", "their",
            "score", "win", "lose", "reach", "final", "market", "event", "more",
            "than", "points", "matchup", "game", "winner", "top", "can", "qat",
            "draw", "world", "cup", "fifa", "fifwc", "2026", "nation", "national", "group",
            # Generic political terms that appear in many unrelated market titles.
            "presidential", "president", "election", "elections", "candidate",
            "candidates", "vote", "voting", "primary", "primaries", "general",
            "runoff", "ballot", "poll", "campaign", "debate", "nomination",
            # Esports/event-level words that should not anchor team rows.
            "team", "esports", "iem", "cologne", "major", "counter", "strike",
            "cs2", "bo3", "playoffs", "map", "handicap", "game1", "away",
            "home", "1pt5", "vit", "fal2", "ts7",
        }

        raw = " ".join(part for part in [market_title, market_slug] if part)
        # Normalize unicode (ç -> c) and drop combining marks so that the
        # following ASCII split keeps multi-byte characters intact.
        raw = unicodedata.normalize("NFKD", raw)
        raw = "".join(c for c in raw if not unicodedata.combining(c)).lower()
        # Remove dates like 2026-06-19 or 06/19/2026
        raw = re.sub(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", " ", raw)
        raw = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b", " ", raw)

        tokens = re.split(r"[^a-z0-9]+", raw)
        keywords = []
        seen = set()
        title_country_hits = set()
        if market_title:
            title_norm_for_codes = unicodedata.normalize("NFKD", market_title).lower()
            title_norm_for_codes = "".join(c for c in title_norm_for_codes if not unicodedata.combining(c))
            for en in country_aliases:
                if en in title_norm_for_codes:
                    title_country_hits.add(en)

        def add(k: str):
            k = k.strip()
            if not k or k in seen:
                return
            seen.add(k)
            keywords.append(k)

        # Extract tokens; expand known country codes and country names.
        for t in tokens:
            t = t.strip()
            if not t or t in stop_words or len(t) <= 1:
                continue
            # 3-letter country code -> expand to full country name + Chinese
            if t in code_aliases:
                if title_country_hits and not any(en in title_country_hits for en in code_aliases[t][0]):
                    continue
                for en in code_aliases[t][0]:
                    add(en)
                for zh in code_aliases[t][1]:
                    add(zh)
                continue
            # Drop generic 2-letter alphabetic tokens, but keep esports/team
            # names like "g2" that carry a digit and are meaningful outcomes.
            if len(t) == 2 and t.isalpha() and t != "us":
                continue
            add(t)
            if t in country_aliases:
                for zh in country_aliases[t]:
                    add(zh)

        # Add full country names/phrases that appear in the title (handles
        # multi-word names like "Cape Verde" or "Saudi Arabia").
        if market_title:
            title_norm = unicodedata.normalize("NFKD", market_title).lower()
            title_norm = re.sub(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", " ", title_norm)
            title_norm = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b", " ", title_norm)
            for en, zh_list in country_aliases.items():
                if en in title_norm:
                    add(en)
                    for zh in zh_list:
                        add(zh)

        # For non-country markets (WNBA team names, etc.) keep significant
        # phrases from the title so "Toronto Tempo" can match as a phrase.
        if market_title:
            title_norm = unicodedata.normalize("NFKD", market_title).lower()
            title_norm = re.sub(r"[^\w\s]", " ", title_norm)
            title_norm = re.sub(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", " ", title_norm)
            title_norm = re.sub(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b", " ", title_norm)
            title_tokens = [
                w for w in title_norm.split()
                if w and w not in stop_words and len(w) > 2
            ]
            for i in range(len(title_tokens)):
                for j in range(i + 1, min(i + 4, len(title_tokens) + 1)):
                    phrase = " ".join(title_tokens[i:j])
                    if len(phrase) >= 6:
                        add(phrase)

        return keywords

    @staticmethod
    def _select_outcome_script() -> str:
        """Return the browser-side outcome selector script.

        Polymtrade renders categorical event pages as a list of outcome rows
        (e.g. "荷兰  是 77¢ / 否 25¢"). We first try to anchor on the small
        text element that contains the market keyword (country/team name), then
        walk up to the nearest row that exposes the Yes/No side buttons. This
        avoids clicking the large outer event card that also contains the
        keyword somewhere in its body.
        """
        return """
        (args) => {
            const [outcome, sideLabels, keywords, binaryOutcomeMode] = args;
            const textOf = (el) => (el ? (el.innerText || el.textContent || "").trim() : "");
            const norm = (s) => (s || "").toLowerCase().replace(/\\s+/g, " ").trim();

            function matchesSideLabel(text) {
                const t = norm(text);
                // Side buttons are short labels like "是 77¢" or "否 25¢".
                // Long texts belong to event cards, not side buttons.
                if (t.length > 40) return false;
                for (const label of sideLabels) {
                    const l = label.toLowerCase();
                    if (t === l || t.startsWith(l + " ") || t.endsWith(" " + l) || t.includes(" " + l + " ")) {
                        return true;
                    }
                }
                return false;
            }

            function isClickable(el) {
                if (!el) return false;
                const tag = el.tagName;
                const role = el.getAttribute("role");
                const cls = (el.getAttribute("class") || "").toLowerCase();
                // Polymtrade side buttons use the class "button ... cursor-pointer".
                // We intentionally do NOT treat every cursor-pointer element as a
                // button to avoid matching large event cards.
                return tag === "BUTTON"
                    || tag === "A"
                    || role === "button"
                    || cls.includes("button")
                    || el.onclick
                    || el.getAttribute("tabindex") === "0";
            }

            function clickableAncestor(el) {
                let cur = el;
                for (let depth = 0; depth < 5 && cur; depth++, cur = cur.parentElement) {
                    if (isClickable(cur)) return cur;
                }
                return el;
            }

            function clickTarget(el) {
                const target = clickableAncestor(el);
                target.scrollIntoView({block: "center", inline: "center"});
                target.click();
                return target;
            }

            function isInsideComments(el) {
                while (el) {
                    const cls = (el.getAttribute("class") || "").toLowerCase();
                    if (cls.includes("comment") || cls.includes("review")) return true;
                    el = el.parentElement;
                }
                return false;
            }

            function isInNoise(el) {
                // Ignore anchors inside navigation, sidebar, header, footer, or
                // modal overlays to avoid clicking top-bar language/search items.
                // We match whole class tokens so that Tailwind utilities like
                // "bg-sidebar" or "sidebar-wrapper" do not mask the main content.
                function hasClassToken(cls, token) {
                    const re = new RegExp("(^|\\s)" + token + "($|\\s)");
                    return re.test(cls);
                }
                while (el) {
                    const tag = el.tagName;
                    const cls = (el.getAttribute("class") || "").toLowerCase();
                    if (
                        tag === "HEADER" ||
                        tag === "NAV" ||
                        tag === "ASIDE" ||
                        tag === "FOOTER" ||
                        hasClassToken(cls, "sidebar") ||
                        hasClassToken(cls, "header") ||
                        hasClassToken(cls, "breadcrumb") ||
                        hasClassToken(cls, "dialog") ||
                        hasClassToken(cls, "modal") ||
                        hasClassToken(cls, "overlay")
                    ) {
                        return true;
                    }
                    el = el.parentElement;
                }
                return false;
            }

            function findSideButtons(container) {
                const buttons = [];
                const candidates = Array.from(container.querySelectorAll("*"));
                for (const c of candidates) {
                    if (isClickable(c) && matchesSideLabel(textOf(c))) {
                        buttons.push(clickableAncestor(c));
                    }
                }
                return buttons;
            }

            function scoreText(text) {
                const t = norm(text);
                let s = 0;
                for (const kw of keywords) {
                    if (t.includes(kw.toLowerCase())) s += 1;
                }
                return s;
            }

            // Strategy 1: anchor on the smallest visible text element that
            // contains a keyword, then walk up to the nearest row with side
            // buttons. This is the primary path for categorical pages.
            const leafSelectors = "span, div, p, h1, h2, h3, h4, h5, h6, a, button, li";
            const anchors = [];
            for (const leaf of document.querySelectorAll(leafSelectors)) {
                const t = textOf(leaf);
                if (!t || t.length > 80) continue;
                if (isInsideComments(leaf) || isInNoise(leaf)) continue;
                const s = scoreText(t);
                if (s > 0) anchors.push({ el: leaf, text: t, score: s });
            }
            // Prefer the most specific anchor (shortest exact text), then
            // highest keyword score.
            anchors.sort((a, b) => a.text.length - b.text.length || b.score - a.score);

            for (const anchor of anchors) {
                let el = anchor.el;
                for (let depth = 0; depth < 8 && el; depth++) {
                    const btns = findSideButtons(el);
                    if (btns.length >= 1) {
                        for (const sideLabel of sideLabels) {
                            const l = sideLabel.toLowerCase();
                            const target = btns.find(b => {
                                const t = norm(textOf(b));
                                return t === l || t.startsWith(l + " ") || t.endsWith(" " + l) || t.includes(" " + l + " ");
                            });
                            if (target) {
                                const clicked = clickTarget(target);
                                return {clicked: true, label: textOf(clicked), rowScore: anchor.score, rowText: textOf(el).slice(0, 80), strategy: "anchor"};
                            }
                        }
                        // Fallback: click the first side button we found.
                        const clicked = clickTarget(btns[0]);
                        return {clicked: true, label: textOf(clicked), rowScore: anchor.score, rowText: textOf(el).slice(0, 80), strategy: "anchor-fallback"};
                    }
                    el = el.parentElement;
                }
            }

            // Strategy 2: score candidate rows and pick the smallest row that
            // contains side buttons and the most keywords.
            const rows = Array.from(document.querySelectorAll('li, [role="listitem"], section, article, div'))
                .filter(row => !isInNoise(row));
            const scoredRows = rows
                .map(row => {
                    const rowText = textOf(row);
                    const titleEl = row.querySelector("h1,h2,h3,h4,h5,h6");
                    const titleScore = titleEl ? scoreText(textOf(titleEl)) : 0;
                    const fullScore = scoreText(rowText);
                    const btns = findSideButtons(row);
                    return {
                        row,
                        fullScore,
                        titleScore,
                        score: fullScore + titleScore * 2,
                        textLength: rowText.length,
                        btns,
                        rowText: rowText.slice(0, 80),
                    };
                })
                .filter(item => item.score > 0 && item.btns.length > 0)
                .sort((a, b) => {
                    if (b.score !== a.score) return b.score - a.score;
                    return a.textLength - b.textLength;
                });
            const bestScore = scoredRows.length > 0 ? scoredRows[0].score : 0;

            for (const { row, score, btns } of scoredRows) {
                for (const sideLabel of sideLabels) {
                    const l = sideLabel.toLowerCase();
                    const target = btns.find(b => {
                        const t = norm(textOf(b));
                        return t === l || t.startsWith(l + " ") || t.endsWith(" " + l) || t.includes(" " + l + " ");
                    });
                    if (target) {
                        const clicked = clickTarget(target);
                        return {clicked: true, label: textOf(clicked), rowScore: score, rowText: textOf(row).slice(0, 80), strategy: "row-score"};
                    }
                }
            }

            // Binary Up/Down pages have one market on the event page and the
            // actionable labels are the outcomes themselves. Market keywords
            // may only appear in the page title, so row scoring can be 0 even
            // while the correct short "Up"/"Down" button is visible.
            if (binaryOutcomeMode) {
                const allButtons = Array.from(document.querySelectorAll("button, [role='button'], a, div, span"))
                    .filter(el => isClickable(el) && !isInNoise(el));
                for (const sideLabel of sideLabels) {
                    const l = sideLabel.toLowerCase();
                    const target = allButtons.find(b => {
                        const t = norm(textOf(b));
                        if (t.length > 40) return false;
                        return t === l || t.startsWith(l + " ") || t.endsWith(" " + l) || t.includes(" " + l + " ");
                    });
                    if (target) {
                        const clicked = clickTarget(target);
                        return {
                            clicked: true,
                            label: textOf(clicked),
                            rowScore: bestScore,
                            rowText: textOf(clicked).slice(0, 80),
                            strategy: "binary-global"
                        };
                    }
                }
            }

            // Fallback: search globally only when we have no market-specific
            // keywords. On multi-market event pages, a global Yes/No fallback
            // can click the wrong row.
            if (keywords.length > 0) {
                return {clicked: false, bestScore: bestScore, keywords: keywords, skippedGlobalFallback: true};
            }

            const xpath = "//*[contains(text(), '" + outcome.replace(/'/g, "\\'") + "')]";
            const iter = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
            let node;
            while ((node = iter.iterateNext())) {
                let el = node;
                for (let i = 0; i < 10; i++) {
                    if (!el) break;
                    const btns = findSideButtons(el);
                    for (const sideLabel of sideLabels) {
                        const l = sideLabel.toLowerCase();
                        const target = btns.find(b => {
                            const t = norm(textOf(b));
                            return t === l || t.startsWith(l + " ") || t.endsWith(" " + l) || t.includes(" " + l + " ");
                        });
                        if (target) {
                            const clicked = clickTarget(target);
                            return {clicked: true, label: textOf(clicked), fallback: true};
                        }
                    }
                    el = el.parentElement;
                }
            }
            return {clicked: false, bestScore: bestScore, keywords: keywords};
        }
        """

    @staticmethod
    def _is_binary_updown_market(
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ) -> bool:
        raw = " ".join(part for part in [market_slug, market_title] if part).lower()
        return (
            "updown" in raw
            or "up-or-down" in raw
            or "up or down" in raw
            or ("bitcoin" in raw and "up" in raw and "down" in raw)
            or ("btc" in raw and "up" in raw and "down" in raw)
        )

    async def _select_polymtrade_outcome(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
        max_attempts: int = 4,
    ):
        """Click the Yes/No button for the chosen outcome on the event page.

        For categorical event pages (e.g. World Cup golden boot) Polymtrade lists
        several sub-markets. We use `market_slug`/`market_title` keywords to find
        the correct row, then click the side (Yes/No) button inside that row.

        This method retries with short waits to give lazy-rendered rows time to
        appear, and scrolls the target element into view before clicking to
        improve reliability.
        """
        outcome_norm = outcome.strip().lower()
        binary_updown = self._is_binary_updown_market(market_slug, market_title)
        if binary_updown and outcome_norm in ("up", "down"):
            if outcome_norm == "up":
                side_labels = ["Up", "UP", "涨", "上涨"]
            else:
                side_labels = ["Down", "DOWN", "跌", "下跌"]
        elif outcome_norm in ("yes", "是", "true"):
            side_labels = ["是", "Yes", "Buy Yes", "Long"]
        elif outcome_norm in ("no", "否", "false"):
            side_labels = ["否", "No", "Buy No", "Short"]
        else:
            # For custom outcome names (e.g. "France") default to Yes/是 side.
            side_labels = ["是", "Yes", outcome]

        keywords = self._extract_market_keywords(market_slug, market_title)
        if outcome_norm not in ("yes", "是", "true", "no", "否", "false"):
            outcome_keywords = self._extract_market_keywords(None, outcome)
            merged_keywords = []
            seen_keywords = set()
            for keyword in [*outcome_keywords, *keywords]:
                if keyword not in seen_keywords:
                    seen_keywords.add(keyword)
                    merged_keywords.append(keyword)
            keywords = merged_keywords
        last_result = None

        for attempt in range(max_attempts):
            # Lazy rows may need a moment; scroll the page to trigger rendering.
            try:
                await self._evaluate_with_navigation_retry(
                    "() => { window.scrollTo(0, 0); }",
                    label="select_outcome.scroll_top",
                )
                await asyncio.sleep(0.2)
                await self._evaluate_with_navigation_retry(
                    "() => { window.scrollTo(0, document.body.scrollHeight); }",
                    label="select_outcome.scroll_bottom",
                )
                await asyncio.sleep(0.2)
            except Exception:
                pass

            result = await self._evaluate_with_navigation_retry(
                self._select_outcome_script(),
                [outcome, side_labels, keywords, binary_updown],
                label="select_outcome.evaluate",
            )
            last_result = result

            if result and result.get("clicked"):
                # Scroll the clicked element into view and use Playwright click
                # as a second confirmation. If the element is gone, the JS click
                # already fired, so we still treat it as success.
                try:
                    # Try to find the button that was clicked by its label text.
                    label = result.get("label", "")
                    if label:
                        clicked_el = await self.page.wait_for_selector(
                            f"text={label}", timeout=1000
                        )
                        if clicked_el:
                            await clicked_el.scroll_into_view_if_needed()
                            await asyncio.sleep(0.1)
                except Exception:
                    pass
                logger.info(
                    f"Selected outcome: {outcome} -> {result.get('label')} "
                    f"(rowScore={result.get('rowScore')}, strategy={result.get('strategy')}, "
                    f"keywords={keywords}, attempt={attempt + 1})"
                )
                return

            logger.warning(
                f"Outcome selection failed (attempt {attempt + 1}/{max_attempts}): "
                f"outcome={outcome}, keywords={keywords}, rowScore={result.get('bestScore') if result else None}"
            )
            if attempt < max_attempts - 1:
                # On the first failure, try revealing low-liquidity markets before
                # waiting and retrying.
                if attempt == 0:
                    await self._show_low_liquidity_markets()
                await asyncio.sleep(1.5)

        raise RuntimeError(
            f"Could not select outcome: {outcome} ({side_labels}), keywords={keywords}, "
            f"rowScore={last_result.get('bestScore') if last_result else None}"
        )

    async def _show_low_liquidity_markets(self) -> bool:
        """Click the 'show low-liquidity markets' toggle if it is currently hiding them.

        On categorical event pages Polymtrade hides low-liquidity markets by default.
        If the target market row is not visible, flipping this switch reveals it.
        """
        try:
            toggle = await self.page.query_selector('button[role="switch"][aria-checked="true"]')
            if not toggle:
                return False
            label = await toggle.get_attribute("aria-label") or ""
            label_lower = label.lower()
            # Match Chinese or English liquidity labels.
            if "低流动性" in label or "liquidity" in label_lower:
                logger.info(f"Clicking low-liquidity toggle to reveal hidden markets: {label}")
                await toggle.click()
                await asyncio.sleep(1.5)
                return True
        except Exception as e:
            logger.debug(f"Failed to toggle low-liquidity markets: {e}")
        return False

    async def _is_network_modal_open(self) -> bool:
        """Return True if the network/token selection modal is visible."""
        try:
            return await self.page.evaluate(
                """() => {
                    const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
                    const all = Array.from(document.querySelectorAll('*[role="dialog"], div, section'));
                    return all.some(d => {
                        if (!modalTexts.some(mt => (d.innerText || '').includes(mt))) return false;
                        // Ignore hidden elements; display:none can still report innerText in some browsers.
                        const rect = d.getBoundingClientRect();
                        const visible = rect.width > 0 && rect.height > 0 && d.style.display !== 'none';
                        return visible;
                    });
                }"""
            )
        except Exception as e:
            logger.warning(f"Failed to check modal state: {e}")
            return False

    async def _is_deposit_or_insufficient_modal_open(self) -> bool:
        """Return True if the visible network/token modal is actually a funding block."""
        try:
            return await self.page.evaluate(
                """() => {
                    const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
                    const fundingPattern = /deposit|充值|insufficient|余额不足|not enough/i;
                    const all = Array.from(document.querySelectorAll('*[role="dialog"], div, section, aside, [class*="modal"], [class*="chakra-modal"]'));
                    return all.some(d => {
                        const text = (d.innerText || '').trim();
                        if (!text || !modalTexts.some(mt => text.includes(mt))) return false;
                        if (!fundingPattern.test(text)) return false;
                        const rect = d.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 && d.style.display !== 'none';
                    });
                }"""
            )
        except Exception as e:
            logger.warning(f"Failed to check deposit modal state: {e}")
            return False

    async def _select_network_and_token_in_modal(
        self,
        preferred_network: str = "Polygon",
        preferred_token: str = "USDC",
    ) -> bool:
        """Try to actively select a network and token in the modal instead of just closing it.

        Returns True if a selection was made and the modal appears to be gone.
        """
        js = """
        (args) => {
            const [preferredNetwork, preferredToken] = args;
            const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
            const all = Array.from(document.querySelectorAll('div, section, aside, [role="dialog"], [class*="modal"], [class*="chakra-modal"]'));
            let modal = null;
            for (const dialog of all) {
                const rect = dialog.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0 || dialog.style.display === 'none') continue;
                const text = (dialog.innerText || '').trim();
                if (modalTexts.some(mt => text.includes(mt))) {
                    modal = dialog;
                    break;
                }
            }
            if (!modal) return {selected: false, reason: 'no_modal'};

            const modalText = (modal.innerText || '').trim();
            const isDepositModal = /deposit|充值|insufficient|余额不足|not enough/i.test(modalText);
            if (isDepositModal) return {selected: false, reason: 'deposit_modal'};

            // Helper: click an element whose text matches one of the candidates.
            function clickByText(candidates, context) {
                const elements = Array.from(context.querySelectorAll('button, [role="button"], div, li, span'));
                for (const el of elements) {
                    const text = (el.innerText || el.textContent || '').trim();
                    const lower = text.toLowerCase();
                    if (candidates.some(c => lower === c.toLowerCase())) {
                        el.click();
                        return {clicked: true, text: text};
                    }
                }
                // Fallback: substring match.
                for (const el of elements) {
                    const text = (el.innerText || el.textContent || '').trim();
                    const lower = text.toLowerCase();
                    if (candidates.some(c => lower.includes(c.toLowerCase()))) {
                        el.click();
                        return {clicked: true, text: text};
                    }
                }
                return {clicked: false};
            }

            // 1) Select network.
            const networkResult = clickByText([preferredNetwork, 'Polygon', 'Polygon Mainnet', '137'], modal);
            if (!networkResult.clicked) return {selected: false, reason: 'network_not_found'};

            // 2) Select token.
            const tokenResult = clickByText([preferredToken, 'USDC', 'pUSD', 'USDC.e'], modal);
            if (!tokenResult.clicked) return {selected: false, reason: 'token_not_found'};

            // 3) Confirm if a confirm button exists.
            const confirmResult = clickByText(['Confirm', '确认', 'Done', '完成'], modal);

            return {
                selected: true,
                network: networkResult.text,
                token: tokenResult.text,
                confirmed: confirmResult.clicked,
            };
        }
        """
        try:
            result = await self.page.evaluate(js, [preferred_network, preferred_token])
            if result and result.get("selected"):
                metrics.modal_blocks += 1
                metrics.modal_dismissals += 1
                logger.info(
                    f"Selected network/token in modal: {result.get('network')} / {result.get('token')}"
                )
                await asyncio.sleep(0.8)
                if not await self._is_network_modal_open():
                    return True
                logger.warning("Modal still visible after network/token selection")
                return False
            logger.warning(f"Could not select network/token in modal: {result}")
            return False
        except Exception as e:
            logger.warning(f"Failed to select network/token in modal: {e}")
            return False

    async def _get_usdc_balance(self) -> Optional[float]:
        """Try to read the USDC/pUSD balance from the page DOM.

        Returns the balance as a float, or None if it cannot be parsed.
        """
        js = """
        () => {
            const balanceTexts = ['USDC', 'pUSD', 'USD Coin'];
            const all = Array.from(document.querySelectorAll('div, span, p, button, [data-testid]'));
            for (const el of all) {
                const text = (el.innerText || el.textContent || '').trim();
                if (!balanceTexts.some(bt => text.includes(bt))) continue;
                const m = text.match(/([0-9,]+\\.?[0-9]*)\\s*(USDC|pUSD)/i);
                if (m) {
                    return {text: text, value: parseFloat(m[1].replace(/,/g, ''))};
                }
            }
            // Broader regex for any balance-looking text near the element.
            for (const el of all) {
                const text = (el.innerText || el.textContent || '').trim();
                if (!/balance|余额|wallet|钱包/i.test(text) && !balanceTexts.some(bt => text.includes(bt))) continue;
                const m = text.match(/\\$?\\s*([0-9,]+\\.?[0-9]*)/);
                if (m) {
                    return {text: text, value: parseFloat(m[1].replace(/,/g, '')), approx: true};
                }
            }
            return null;
        }
        """
        try:
            result = await self.page.evaluate(js)
            if result and result.get("value") is not None:
                logger.info(f"Detected balance: {result.get('value')} from '{result.get('text')}'")
                return float(result.get("value"))
        except Exception as e:
            logger.warning(f"Failed to read balance from page: {e}")
        return None

    async def _get_event_page_position_quantity(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ) -> Optional[float]:
        """Try to read the current position quantity for an outcome from the event page.

        Polymtrade sometimes shows 'You own X shares' or '持仓 X 份' near the
        selected outcome row. Returns the quantity as a float, or None.
        """
        outcome_norm = outcome.strip().lower()
        keywords = self._extract_market_keywords(market_slug, market_title)
        keywords = [k.lower() for k in keywords if len(k) <= 25][:5]
        js = """
        (args) => {
            const [outcomeNorm, keywords] = args;
            const bodyText = (document.body?.innerText || '');
            const norm = (s) => (s || '').toLowerCase().replace(/\\s+/g, ' ').trim();
            const parse = (text) => {
                const patterns = [
                    /(?:You own|持仓|持有|Position|pos)\\s*[:：]?\\s*([0-9,]+\\.?[0-9]*)\\s*(?:shares?|份|shares?)/i,
                    /([0-9,]+\\.?[0-9]*)\\s*(?:shares?|份)\\s*(?:owned|held|持仓)/i,
                    /(?:own|hold|持仓)\\s+([0-9,]+\\.?[0-9]*)\\s*(?:shares?|份)/i,
                    /(?:剩余|Remaining|Available)\\s*[:：]?\\s*([0-9,]+\\.?[0-9]*)/i,
                ];
                for (const re of patterns) {
                    const m = text.match(re);
                    if (m) return {text: m[0], value: parseFloat(m[1].replace(/,/g, ''))};
                }
                return null;
            };
            const score = (text) => {
                const lower = norm(text);
                let s = 0;
                for (const kw of keywords) {
                    if (lower.includes(kw)) s += 1;
                }
                return s;
            };

            const hasMarketContext = keywords.length > 0;
            const rows = Array.from(document.querySelectorAll('li, [role="listitem"], section, article, div'))
                .map(row => {
                    const text = (row.innerText || '').trim();
                    return {row, text, lower: norm(text), score: score(text), len: text.length};
                })
                .filter(item => item.text && item.len < (hasMarketContext ? 520 : 1200))
                .sort((a, b) => b.score - a.score || a.len - b.len);

            for (const item of rows) {
                if (keywords.length && item.score <= 0) continue;
                if (outcomeNorm && !item.lower.includes(outcomeNorm)) continue;
                const parsed = parse(item.text);
                if (parsed) return parsed;
            }

            // Patterns ordered from most specific to least specific.
            const patterns = [
                /(?:You own|持仓|持有|Position|pos)\\s*[:：]?\\s*([0-9,]+\\.?[0-9]*)\\s*(?:shares?|份|shares?)/i,
                /([0-9,]+\\.?[0-9]*)\\s*(?:shares?|份)\\s*(?:owned|held|持仓)/i,
                /(?:own|hold|持仓)\\s+([0-9,]+\\.?[0-9]*)\\s*(?:shares?|份)/i,
                /(?:剩余|Remaining|Available)\\s*[:：]?\\s*([0-9,]+\\.?[0-9]*)/i,
            ];
            if (!keywords.length) {
                for (const re of patterns) {
                    const m = bodyText.match(re);
                    if (m) return {text: m[0], value: parseFloat(m[1].replace(/,/g, ''))};
                }
            }
            // Outcome-specific: look near the outcome row for quantity text.
            for (const row of rows) {
                const text = row.text;
                const lower = row.lower;
                if (keywords.length && row.score <= 0) continue;
                if (!lower.includes(outcomeNorm)) continue;
                const m = text.match(/([0-9,]+\\.?[0-9]*)\\s*(?:shares?|份)/i);
                if (m) return {text: m[0], value: parseFloat(m[1].replace(/,/g, ''))};
            }
            return null;
        }
        """
        try:
            result = await self.page.evaluate(js, [outcome_norm, keywords])
            if result and result.get("value") is not None:
                logger.info(f"Detected position quantity: {result.get('value')} from '{result.get('text')}'")
                return float(result.get("value"))
        except Exception as e:
            logger.warning(f"Failed to read position quantity from page: {e}")
        return None

    async def _capture_buy_baseline(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ) -> dict:
        """Capture pre-trade state for later verification.

        Returns a dict with balance and position quantity (both may be None).
        """
        balance = await self._get_usdc_balance()
        quantity = await self._get_event_page_position_quantity(
            outcome, market_slug=market_slug, market_title=market_title
        )
        baseline = {
            "balance": balance,
            "position_quantity": quantity,
            "captured_at": int(time.time() * 1000),
        }
        logger.info(f"Captured BUY baseline: balance={balance}, qty={quantity}")
        return baseline

    async def _capture_sell_baseline(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ) -> dict:
        """Capture pre-SELL state for later verification.

        Returns a dict with balance and position quantity (both may be None).
        """
        balance = await self._get_usdc_balance()
        quantity = await self._get_event_page_position_quantity(
            outcome, market_slug=market_slug, market_title=market_title
        )
        baseline = {
            "balance": balance,
            "position_quantity": quantity,
            "captured_at": int(time.time() * 1000),
        }
        logger.info(f"Captured SELL baseline: balance={balance}, qty={quantity}")
        return baseline

    async def _dismiss_modal_dialogs(self) -> bool:
        """Dismiss the network/token selection modal that blocks the buy dialog.

        First tries to actively select Polygon/USDC in the modal. If that fails,
        falls back to closing the modal. We only act if the modal title text is
        present, to avoid closing the actual trade dialog.
        """
        if await self._select_network_and_token_in_modal():
            return True

        js = """
        () => {
            const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
            // Broad search: any element whose text contains the modal title
            const all = Array.from(document.querySelectorAll('div, section, aside, [role="dialog"], [class*="modal"], [class*="chakra-modal"]'));
            for (const dialog of all) {
                const rect = dialog.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0 || dialog.style.display === 'none') continue;
                const text = (dialog.innerText || '').trim();
                if (modalTexts.some(mt => text.includes(mt))) {
                    // Try to find the close button inside this modal (must be a clickable element, not an svg)
                    let closeBtn = dialog.querySelector('button[aria-label="Close"], button[class*="close"], [class*="close-btn"]');
                    if (!closeBtn) {
                        // Look for a button whose text is exactly a close label
                        const closeLabels = ['Close', '关闭', '×', 'X'];
                        const btns = Array.from(dialog.querySelectorAll('button'));
                        closeBtn = btns.find(b => {
                            const t = b.textContent.trim();
                            return closeLabels.includes(t) || closeLabels.some(l => b.getAttribute('aria-label') === l);
                        });
                    }
                    if (!closeBtn) {
                        // Some modals put the svg directly inside a button; look for a button containing an svg
                        const btns = Array.from(dialog.querySelectorAll('button'));
                        closeBtn = btns.find(b => b.querySelector('svg') && b.getAttribute('aria-label') === 'Close');
                    }
                    if (!closeBtn) {
                        // Last resort: any button in the top-right area of the modal
                        const rect = dialog.getBoundingClientRect();
                        const btns = Array.from(dialog.querySelectorAll('button'));
                        closeBtn = btns.find(b => {
                            const br = b.getBoundingClientRect();
                            return br.top < rect.top + 60 && br.right > rect.right - 60;
                        });
                    }
                    if (closeBtn) {
                        closeBtn.click();
                        return {dismissed: true, text: text.slice(0, 50)};
                    }
                    // Fallback: hide the modal so we can interact with the page
                    dialog.style.display = 'none';
                    return {dismissed: true, text: text.slice(0, 50), method: 'hidden'};
                }
            }
            return {dismissed: false};
        }
        """
        try:
            result = await self.page.evaluate(js)
            if result and result.get("dismissed"):
                metrics.modal_blocks += 1
                metrics.modal_dismissals += 1
                logger.info(f"Dismissed network selection modal: {result.get('text')}")
                await asyncio.sleep(0.5)
                # Verify the modal is really gone; if not, force-hide it.
                still_visible = await self.page.evaluate(
                    """() => {
                        const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
                        const all = Array.from(document.querySelectorAll('*[role="dialog"], div, section'));
                        return all.some(d => {
                            if (!modalTexts.some(mt => (d.innerText || '').includes(mt))) return false;
                            const rect = d.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0 && d.style.display !== 'none';
                        });
                    }"""
                )
                if still_visible:
                    logger.warning("Modal still visible after close attempt, forcing hide")
                    await self.page.evaluate(
                        """() => {
                            const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
                            const all = Array.from(document.querySelectorAll('*[role="dialog"], div, section'));
                            for (const d of all) {
                                if (!modalTexts.some(mt => (d.innerText || '').includes(mt))) continue;
                                const rect = d.getBoundingClientRect();
                                if (rect.width === 0 || rect.height === 0 || d.style.display === 'none') continue;
                                d.style.display = 'none';
                                    const overlay = d.parentElement;
                                    if (overlay && overlay.getAttribute('data-state') === 'open') overlay.style.display = 'none';
                                }
                            }
                        }"""
                    )
                    await asyncio.sleep(0.3)
                return True
        except Exception as e:
            logger.warning(f"Failed to evaluate modal dismiss script: {e}")

        # Fallback: press Escape to close any open modal (safe before outcome is clicked)
        try:
            await self.page.keyboard.press('Escape')
            logger.info("Pressed Escape to dismiss modal dialog")
            await asyncio.sleep(0.5)
            return True
        except Exception:
            return False

    async def _fill_input_safely(self, input_el, value: str):
        """Focus, clear and fill a Playwright input element robustly."""
        tag_name = ""
        is_custom_editable = False
        try:
            await input_el.scroll_into_view_if_needed()
            await input_el.click(timeout=3000)
            tag_name = await input_el.evaluate("el => el.tagName")
            is_text_editable = await input_el.evaluate(
                "el => el.isContentEditable || el.getAttribute('role') === 'textbox'"
            )
            is_custom_editable = await input_el.evaluate(
                "el => el.isContentEditable || ['textbox', 'spinbutton'].includes(el.getAttribute('role'))"
            )
            if tag_name not in ("INPUT", "TEXTAREA") and is_text_editable:
                await input_el.evaluate(
                    """el => {
                        if (el.isContentEditable) {
                            el.textContent = '';
                            el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'deleteContent'}));
                        }
                    }"""
                )
                await input_el.press("Control+a")
                await input_el.press("Backspace")
                await input_el.type(value, timeout=3000)
                return True
        except Exception as e:
            logger.debug(f"editable type failed: {e}")
        try:
            tag_name = await input_el.evaluate("el => el.tagName")
            if tag_name not in ("INPUT", "TEXTAREA") and is_custom_editable:
                await input_el.scroll_into_view_if_needed()
                await input_el.click(timeout=3000)
                await input_el.press("Control+a")
                await input_el.press("Backspace")
                await input_el.type(value, timeout=3000)
                typed_value = await input_el.evaluate(
                    "el => (el.value || el.textContent || el.getAttribute('aria-valuenow') || '').trim()"
                )
                if value in typed_value:
                    return True
                await input_el.evaluate(
                    """(el, value) => {
                        el.textContent = value;
                        el.setAttribute('aria-valuenow', value);
                        el.setAttribute('data-bridge-filled-value', value);
                        el.dispatchEvent(new InputEvent('input', {bubbles: true, data: value, inputType: 'insertText'}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    }""",
                    value,
                )
                return True
        except Exception as e:
            logger.debug(f"custom editable fill failed: {e}")
        try:
            await input_el.scroll_into_view_if_needed()
            await input_el.click(timeout=3000)
            await input_el.fill(value, timeout=3000)
            return True
        except Exception as e:
            logger.debug(f"fill failed: {e}")
        try:
            await input_el.click(timeout=3000)
            await input_el.press("Control+a")
            await input_el.press("Backspace")
            await input_el.type(value, timeout=3000)
            return True
        except Exception as e:
            logger.debug(f"type fallback failed: {e}")
        return False

    async def _enter_amount(self, amount_usdc: float):
        """Enter the trade amount in the buy dialog with retries and fallbacks."""
        selectors = [
            "input[name='buyAmount']",
            "input[name*='amount' i]",
            "input[id*='amount' i]",
            "input[data-test*='amount' i]",
            "input[data-testid*='amount' i]",
            "input[inputmode='decimal']",
            "input[type='number']",
            "input[type='text']",
            "input[role='spinbutton']",
            "[role='spinbutton']",
            "input[placeholder*='Amount' i]",
            "input[placeholder*='amount' i]",
            "input[placeholder*='USDC' i]",
            "input[placeholder*='0.0' i]",
            "input[placeholder*='0' i]",
            "input[placeholder*='数量' i]",
            "input[placeholder*='金额' i]",
            "input[class*='amount' i]",
            "input[class*='trade-input' i]",
            "input[aria-label*='amount' i]",
            "input[aria-label*='USDC' i]",
            "input[aria-label*='数量' i]",
            "input[aria-label*='金额' i]",
            "[data-test='trade-amount-input']",
            "textarea[placeholder*='Amount' i]",
            "textarea[placeholder*='amount' i]",
            "textarea[placeholder*='金额' i]",
            "[role='textbox'][aria-label*='amount' i]",
            "[role='textbox'][aria-label*='USDC' i]",
            "[role='textbox'][aria-label*='金额' i]",
            "[contenteditable='true'][aria-label*='amount' i]",
            "[contenteditable='true'][aria-label*='USDC' i]",
            "[contenteditable='true'][aria-label*='金额' i]",
            "[contenteditable='plaintext-only'][aria-label*='amount' i]",
            "[contenteditable='plaintext-only'][aria-label*='USDC' i]",
            "[contenteditable='plaintext-only'][aria-label*='金额' i]",
        ]
        deadline = time.time() + 18.0
        last_error = None
        while time.time() < deadline:
            try:
                input_el = await self._find_trade_input(prefer_sell=False)
                if input_el and await self._fill_input_safely(input_el, str(amount_usdc)):
                    logger.info(f"Entered amount via trade-input scan: {amount_usdc}")
                    return
            except Exception as e:
                last_error = e

            # Prefer a visible input that is inside a dialog or trade area.
            for selector in selectors:
                try:
                    input_el = await self.page.wait_for_selector(selector, timeout=1500)
                    if input_el and await input_el.is_visible() and await input_el.is_enabled():
                        # Restrict to elements inside a dialog/trade panel to avoid
                        # filling unrelated search inputs on the page.
                        in_dialog = await input_el.evaluate(
                            "el => !!el.closest('[role=\"dialog\"], .trade-dialog, [class*=\"trade\"], [class*=\"modal\"]')"
                        )
                        if not in_dialog:
                            continue
                        if await self._fill_input_safely(input_el, str(amount_usdc)):
                            logger.info(f"Entered amount: {amount_usdc}")
                            return
                except Exception as e:
                    last_error = e
                    continue

            # Fallback: try any visible decimal/number input inside a dialog.
            try:
                input_el = await self.page.wait_for_selector(
                    "[role='dialog'] input[inputmode='decimal'], "
                    "[role='dialog'] input[type='number'], "
                    "[role='dialog'] input[type='text'], "
                    "[role='dialog'] input[role='spinbutton'], "
                    "[role='dialog'] [role='spinbutton'], "
                    ".trade-dialog input, "
                    "[class*='trade'] input[type='text'], "
                    "[class*='trade'] [role='spinbutton'], "
                    "[class*='dialog'] input[inputmode='decimal']",
                    timeout=1500
                )
                if input_el and await input_el.is_visible() and await input_el.is_enabled():
                    if await self._fill_input_safely(input_el, str(amount_usdc)):
                        logger.info(f"Entered amount via fallback: {amount_usdc}")
                        return
            except Exception as e:
                last_error = e
                pass

            await asyncio.sleep(0.5)

        # Screenshot and DOM candidate snapshot help diagnose why the input
        # could not be found on the next loop iteration.
        try:
            screenshot_path = "/tmp/trade_amount_input_error.png"
            await self.page.screenshot(path=screenshot_path)
            logger.warning(f"Amount input error screenshot saved: {screenshot_path}")
        except Exception:
            pass
        await self._capture_trade_input_diagnostics(
            "/tmp/trade_amount_input_candidates.json",
            prefer_sell=False,
        )
        raise RuntimeError(f"Could not enter trade amount: {last_error}")

    async def _capture_trade_input_diagnostics(self, path: str, prefer_sell: bool = False) -> None:
        """Write a compact DOM snapshot of possible trade inputs for debugging."""
        try:
            payload = await self.page.evaluate(
                """
                (preferSell) => {
                    const textOf = (el) => (el ? (el.innerText || el.textContent || '').trim() : '');
                    const isVisible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    const selector = [
                        "input",
                        "textarea",
                        "[role='textbox']",
                        "[role='spinbutton']",
                        "[contenteditable='true']",
                        "[contenteditable='plaintext-only']",
                        "[contenteditable]:not([contenteditable='false'])"
                    ].join(',');
                    return Array.from(document.querySelectorAll(selector)).slice(0, 80).map((el) => {
                        const rect = el.getBoundingClientRect();
                        let ancestor = el;
                        const ancestors = [];
                        for (let i = 0; i < 5 && ancestor; i++, ancestor = ancestor.parentElement) {
                            ancestors.push({
                                tag: ancestor.tagName,
                                role: ancestor.getAttribute('role'),
                                className: ancestor.getAttribute('class'),
                                text: textOf(ancestor).slice(0, 160),
                            });
                        }
                        return {
                            tag: el.tagName,
                            type: el.getAttribute('type'),
                            role: el.getAttribute('role'),
                            name: el.getAttribute('name'),
                            id: el.getAttribute('id'),
                            className: el.getAttribute('class'),
                            placeholder: el.getAttribute('placeholder'),
                            ariaLabel: el.getAttribute('aria-label'),
                            dataTest: el.getAttribute('data-test') || el.getAttribute('data-testid'),
                            value: el.value || el.getAttribute('aria-valuenow') || textOf(el).slice(0, 120),
                            visible: isVisible(el),
                            disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
                            rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                            ancestors,
                        };
                    });
                }
                """,
                prefer_sell,
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.warning(f"Trade input diagnostics saved: {path}")
        except Exception as e:
            logger.debug(f"Failed to capture trade input diagnostics: {e}")

    async def _find_trade_input(self, prefer_sell: bool = False):
        """Find the most likely active trade amount/shares input."""
        js = """
        (preferSell) => {
            const textOf = (el) => (el ? (el.innerText || el.textContent || '').trim() : '');
            const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const isNoise = (el) => {
                let cur = el;
                for (let i = 0; i < 8 && cur; i++, cur = cur.parentElement) {
                    const tag = cur.tagName;
                    const cls = (cur.getAttribute('class') || '').toLowerCase();
                    const role = cur.getAttribute('role');
                    if (tag === 'ASIDE' || tag === 'NAV' || tag === 'HEADER' || tag === 'FOOTER') return true;
                    if (role === 'search') return true;
                    if (/(sidebar|navigation|header|footer|search)/.test(cls)) return true;
                }
                return false;
            };
            const inputs = Array.from(document.querySelectorAll(
                "input[name='buyAmount'], input[name='soldAmount'], input[name*='amount' i], input[name*='quantity' i], input[name*='shares' i], input[id*='amount' i], input[id*='quantity' i], input[id*='shares' i], input[data-test*='amount' i], input[data-testid*='amount' i], input[data-test*='usdc' i], input[data-testid*='usdc' i], input[inputmode='decimal'], input[inputmode='numeric'], input[type='number'], input[type='text'], input[role='spinbutton'], input[placeholder*='Amount' i], input[placeholder*='amount' i], input[placeholder*='USDC' i], input[placeholder*='Shares' i], input[placeholder*='数量' i], input[placeholder*='金额' i], input[aria-label*='Amount' i], input[aria-label*='amount' i], input[aria-label*='USDC' i], input[aria-label*='Shares' i], input[aria-label*='数量' i], input[aria-label*='金额' i], textarea[placeholder*='Amount' i], textarea[placeholder*='amount' i], textarea[placeholder*='金额' i], textarea[aria-label*='金额' i], [role='textbox'], [role='spinbutton'], [contenteditable='true'], [contenteditable='plaintext-only'], [contenteditable]:not([contenteditable='false'])"
            ));
            const scored = [];
            for (const input of inputs) {
                if (!isVisible(input) || input.disabled || input.readOnly || isNoise(input)) continue;
                if (input.hasAttribute('contenteditable') && input.getAttribute('contenteditable') === 'false') continue;
                const attrs = [
                    input.name || '',
                    input.id || '',
                    input.placeholder || '',
                    input.getAttribute('aria-label') || '',
                    input.getAttribute('data-test') || '',
                    input.getAttribute('data-testid') || '',
                    input.getAttribute('class') || '',
                    input.getAttribute('role') || '',
                ].join(' ').toLowerCase();
                if (/search|filter|邮箱|email|address|wallet/.test(attrs)) continue;
                let score = 0;
                let cur = input;
                for (let depth = 0; depth < 8 && cur; depth++, cur = cur.parentElement) {
                    const text = textOf(cur).toLowerCase();
                    const cls = (cur.getAttribute('class') || '').toLowerCase();
                    const role = cur.getAttribute('role') || '';
                    if (role === 'dialog' || cls.includes('dialog') || cls.includes('modal')) score += 10;
                    if (cls.includes('trade') || cls.includes('order') || cls.includes('amount')) score += 4;
                    if (/买入|buy|卖出|sell|amount|shares|份|数量|金额|usdc|pusd/.test(text)) score += 3;
                    if (preferSell && /卖出|sell|shares|份|sold/.test(text + ' ' + attrs)) score += 5;
                    if (!preferSell && /买入|buy|amount|usdc|pusd|金额|数量/.test(text + ' ' + attrs)) score += 5;
                    if (/搜索市场|search market|你的推荐链接|solana钱包地址/.test(text)) score -= 10;
                }
                scored.push({input, score});
            }
            scored.sort((a, b) => b.score - a.score);
            if (!scored.length || scored[0].score < 3) return null;
            return scored[0].input;
        }
        """
        handle = await self._evaluate_handle_with_navigation_retry(
            js,
            prefer_sell,
            label="find_trade_input.evaluate_handle",
        )
        if not handle:
            return None
        return handle.as_element()

    async def _enter_sell_shares(self, size_shares: float) -> bool:
        """Enter the sell shares amount in the sell dialog."""
        selectors = [
            "input[name='soldAmount']",
            "input[inputmode='decimal']",
            "input[type='number']",
            "input[placeholder*='Shares' i]",
            "input[placeholder*='shares' i]",
            "input[placeholder*='Amount' i]",
            "input[placeholder*='amount' i]",
            "input[class*='amount' i]",
            "[role='dialog'] input",
            ".trade-dialog input",
        ]
        deadline = time.time() + 10.0
        while time.time() < deadline:
            try:
                input_el = await self._find_trade_input(prefer_sell=True)
                if input_el and await self._fill_input_safely(input_el, str(size_shares)):
                    logger.info(f"Entered sell shares via trade-input scan: {size_shares}")
                    return True
            except Exception:
                pass
            for selector in selectors:
                try:
                    input_el = await self.page.wait_for_selector(selector, timeout=2000)
                    if input_el and await input_el.is_visible() and await input_el.is_enabled():
                        if await self._fill_input_safely(input_el, str(size_shares)):
                            logger.info(f"Entered sell shares: {size_shares}")
                            return True
                except Exception:
                    continue
            await asyncio.sleep(0.5)
        return False

    async def _click_buy_button(self):
        """Click the buy button in the trade dialog."""
        selectors = [
            "button[data-test='trade-buy-button']",
            "button#buybtn",
            "[role='dialog'] button:has-text('确认买入')",
            "button:has-text('买入')",
            "[role='dialog'] button:has-text('买入')",
            "[role='dialog'] button:has-text('确认')",
            "[role='dialog'] button:has-text('下单')",
            "[role='dialog'] button:has-text('Review')",
            "[role='dialog'] button:has-text('Place')",
        ]
        deadline = time.time() + 10.0
        while time.time() < deadline:
            for selector in selectors:
                try:
                    await self.page.click(selector, timeout=750)
                    logger.info("Clicked buy button")
                    return
                except Exception:
                    continue
            if await self._click_trade_submit_button("BUY"):
                return
            await asyncio.sleep(0.35)
        try:
            screenshot_path = "/tmp/trade_buy_submit_button_error.png"
            await self.page.screenshot(path=screenshot_path)
            logger.warning(f"Buy submit button error screenshot saved: {screenshot_path}")
        except Exception:
            pass
        await self._capture_trade_submit_diagnostics(
            "/tmp/trade_buy_submit_button_candidates.json",
            "BUY",
        )
        raise RuntimeError("Could not click buy button")

    async def _open_sell_dialog(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ):
        """Click the sell button for the position matching the outcome.

        On the event page the position card has a sell button. When there are
        multiple positions we use market_slug/market_title keywords to find the
        right card, then click its sell button.
        """
        outcome_norm = outcome.strip().lower()
        side_labels = []
        if outcome_norm in ("yes", "是", "true"):
            side_labels = ["Yes", "是"]
        elif outcome_norm in ("no", "否", "false"):
            side_labels = ["No", "否"]
        else:
            side_labels = [outcome]

        keywords = self._extract_market_keywords(market_slug, market_title)

        js = """
        (args) => {
            const [outcome, sideLabels, keywords] = args;
            const textOf = (el) => (el.innerText || el.textContent || "").trim();
            const isVisible = (el) => !!(el.offsetParent || el.getClientRects().length);

            function isSellButton(b) {
                const t = textOf(b).toLowerCase();
                return t === '卖出' || t.includes('卖出') || t === 'sell' || t.includes('sell');
            }

            function isWalletPmSellButton(b) {
                const ownText = textOf(b).toLowerCase();
                if (ownText.includes('$pm') || ownText.match(/\\bpm\\b/)) return true;
                let el = b;
                for (let i = 0; i < 5 && el; i++, el = el.parentElement) {
                    const text = textOf(el).toLowerCase();
                    if (
                        text.includes('持仓') ||
                        text.includes('剩余') ||
                        text.includes('position') ||
                        text.includes('remaining')
                    ) {
                        return false;
                    }
                    if (text.length > 350) {
                        el = el.parentElement;
                        continue;
                    }
                    if (
                        text.includes('solana钱包地址') ||
                        text.includes('solana wallet') ||
                        text.includes('买入 $pm') ||
                        text.includes('sell $pm') ||
                        text.includes('0 pm')
                    ) {
                        return true;
                    }
                }
                return false;
            }

            function hasPositionContext(card) {
                const text = textOf(card).toLowerCase();
                return text.includes('持仓') ||
                    text.includes('剩余') ||
                    text.includes('remaining') ||
                    text.includes('position') ||
                    text.includes('pnl') ||
                    text.includes('market') ||
                    text.includes('市场');
            }

            function clickableAncestor(el) {
                let cur = el;
                for (let depth = 0; depth < 5 && cur; depth++, cur = cur.parentElement) {
                    const tag = cur.tagName;
                    const role = cur.getAttribute('role');
                    const cls = (cur.getAttribute('class') || '').toLowerCase();
                    if (tag === 'BUTTON' || role === 'button' || cls.includes('button') || cur.onclick || cur.getAttribute('tabindex') === '0') {
                        return cur;
                    }
                }
                return el;
            }

            function clickTarget(el) {
                const target = clickableAncestor(el);
                target.scrollIntoView({block: 'center', inline: 'center'});
                target.click();
                return target;
            }

            function scoreCard(card) {
                const text = textOf(card).toLowerCase();
                let s = 0;
                for (const kw of keywords) {
                    if (text.includes(kw)) s += 1;
                }
                return s;
            }

            function bestAncestorFor(btn) {
                let best = btn;
                let bestScore = -1;
                let bestTextLen = 0;
                let el = btn;
                for (let i = 0; i < 14 && el; i++, el = el.parentElement) {
                    const text = textOf(el);
                    if (!text) continue;
                    if (text.length > 1200) continue;
                    if (isWalletPmSellButton(btn) || text.includes('买入 $pm') || text.includes('sell $pm')) continue;
                    const score = scoreCard(el);
                    if (keywords.length && score <= 0) continue;
                    if (!hasPositionContext(el)) continue;
                    const textLen = text.length;
                    if (score > bestScore || (score === bestScore && (bestTextLen === 0 || textLen < bestTextLen))) {
                        best = el;
                        bestScore = score;
                        bestTextLen = textLen;
                    }
                }
                return {card: best, keywordScore: Math.max(bestScore, 0)};
            }

            // Strategy 1: find all sell buttons and score their ancestor cards.
            // The old nearest-div grouping could score only a tiny wrapper whose
            // text was just "卖出", causing multi-market event pages to click the
            // current unrelated position. Require a keyword hit when keywords are
            // available.
            const allSellBtns = Array.from(document.querySelectorAll('button, [role="button"], .cursor-pointer, [class*="button"]'))
                .filter(b => isVisible(b) && isSellButton(b) && !isWalletPmSellButton(b));

            let bestBtn = null;
            let bestScore = -1;
            let bestKeywordScore = 0;
            for (const btn of allSellBtns) {
                const candidate = bestAncestorFor(btn);
                const card = candidate.card;
                const s = candidate.keywordScore;
                if (keywords.length && s <= 0) continue;
                // Tie-break: prefer a card whose text also contains the side label/outcome
                const cardText = textOf(card).toLowerCase();
                const sideMatch = sideLabels.some(l => cardText.includes(l.toLowerCase()));
                const outcomeMatch = cardText.includes(outcome.toLowerCase());
                const positionMatch = hasPositionContext(card);
                if (!positionMatch) continue;
                const finalScore = s * 10 + (sideMatch ? 5 : 0) + (outcomeMatch ? 5 : 0);
                if (finalScore > bestScore) {
                    bestScore = finalScore;
                    bestKeywordScore = s;
                    bestBtn = btn;
                }
            }

            if (bestBtn && (!keywords.length || bestKeywordScore > 0)) {
                const clicked = clickTarget(bestBtn);
                return {clicked: true, label: textOf(clicked), score: bestScore, keywordScore: bestKeywordScore};
            }

            // Strategy 2: walk up from any element containing the outcome/side label
            // and look for a sell button.
            const searchTerms = [...sideLabels, outcome];
            for (const term of searchTerms) {
                if (!term) continue;
                const iter = document.evaluate(
                    "//*[contains(text(), '" + term + "')]",
                    document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null
                );
                let node;
                while ((node = iter.iterateNext())) {
                    let el = node;
                    for (let i = 0; i < 10 && el; i++) {
                        const text = textOf(el).toLowerCase();
                        if (keywords.length && !keywords.some(kw => text.includes(kw))) {
                            el = el.parentElement;
                            continue;
                        }
                        if (!hasPositionContext(el)) {
                            el = el.parentElement;
                            continue;
                        }
                        const sell = el.querySelector
                            ? Array.from(el.querySelectorAll('button, [role="button"], .cursor-pointer'))
                                .find(b => isSellButton(b) && !isWalletPmSellButton(b))
                            : null;
                        if (sell) {
                            const clicked = clickTarget(sell);
                            return {clicked: true, label: textOf(clicked), fallback: true};
                        }
                        el = el.parentElement;
                    }
                }
            }

            // Strategy 3: global #sell button
            const sell = keywords.length ? null : document.querySelector('#sell');
            if (sell && isVisible(sell) && !isWalletPmSellButton(sell)) {
                const clicked = clickTarget(sell);
                return {clicked: true, label: textOf(sell), fallback: true};
            }
            return {clicked: false, keywords, sellButtons: allSellBtns.length};
        }
        """
        result = await self._evaluate_with_navigation_retry(
            js,
            [outcome, side_labels, keywords],
            label="open_sell_dialog.evaluate",
        )
        if not result or not result.get("clicked"):
            raise RuntimeError(f"Could not open sell dialog for outcome: {outcome} (keywords={keywords}, sellButtons={result.get('sellButtons') if result else None})")
        logger.info(f"Opened sell dialog for outcome: {outcome} -> {result.get('label')} (score={result.get('score')})")

    async def _click_sell_button(self):
        """Click the sell button in the sell dialog."""
        if not await self._is_sell_dialog_open(timeout=0.75):
            try:
                screenshot_path = "/tmp/trade_sell_submit_context_missing.png"
                await self.page.screenshot(path=screenshot_path)
                logger.warning(f"Sell submit context missing screenshot saved: {screenshot_path}")
            except Exception:
                pass
            await self._capture_trade_submit_diagnostics(
                "/tmp/trade_sell_submit_button_candidates.json",
                "SELL",
            )
            raise RuntimeError("Sell dialog disappeared before submit")
        selectors = [
            "button#sellbtn",
            "[role='dialog'] button:has-text('确认卖出')",
            "[role='dialog'] button:has-text('卖出')",
            "[role='dialog'] button:has-text('确认')",
            "[role='dialog'] button:has-text('下单')",
            "[role='dialog'] button:has-text('Review')",
            "[role='dialog'] button:has-text('Place')",
        ]
        deadline = time.time() + 10.0
        while time.time() < deadline:
            for selector in selectors:
                try:
                    await self.page.click(selector, timeout=750)
                    logger.info("Clicked sell button")
                    return
                except Exception:
                    continue
            if await self._click_trade_submit_button("SELL"):
                return
            await asyncio.sleep(0.35)
        try:
            screenshot_path = "/tmp/trade_sell_submit_button_error.png"
            await self.page.screenshot(path=screenshot_path)
            logger.warning(f"Sell submit button error screenshot saved: {screenshot_path}")
        except Exception:
            pass
        await self._capture_trade_submit_diagnostics(
            "/tmp/trade_sell_submit_button_candidates.json",
            "SELL",
        )
        raise RuntimeError("Could not click sell button")

    async def _click_trade_submit_button(self, side: str) -> bool:
        """Click the active submit button inside the current trade dialog/form."""
        js = """
        (side) => {
            const sideLower = side.toLowerCase();
            const textOf = (el) => {
                if (!el) return '';
                const visibleText = (el.innerText || el.textContent || '').trim();
                const attrs = [
                    el.getAttribute('aria-label') || '',
                    el.getAttribute('title') || '',
                    el.getAttribute('value') || '',
                    el.getAttribute('data-testid') || '',
                    el.getAttribute('data-test') || '',
                    el.getAttribute('id') || '',
                    el.getAttribute('name') || '',
                    el.getAttribute('type') || '',
                ].filter(Boolean).join(' ');
                return (visibleText + ' ' + attrs).trim();
            };
            const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const containers = Array.from(document.querySelectorAll('[role="dialog"], form, [class*="dialog"], [class*="modal"], [class*="trade"], [class*="order"]'))
                .filter(isVisible);
            if (!containers.length) return {clicked: false, bestScore: -1, reason: 'no_trade_container'};
            const positive = sideLower === 'sell'
                ? ['确认卖出', '卖出', 'sell', 'place sell', 'submit sell', 'submit', 'confirm sell', 'confirm', '确认', '确认订单', '提交订单', '提交', '下单', 'review', 'review order', 'place order']
                : ['确认买入', '买入', 'buy', 'place buy', 'submit buy', 'submit', 'confirm buy', 'confirm', '确认', '确认订单', '提交订单', '提交', '下单', 'review', 'review order', 'place order'];
            const negative = ['取消', 'cancel', '关闭', 'close', 'max', '最大', 'full', '100%', '充值', '提现', 'deposit', 'withdraw', 'wallet', '钱包'];
            let best = null;
            let bestScore = -1;
            let bestText = '';
            for (const container of containers) {
                const buttons = Array.from(container.querySelectorAll(
                    'button, [role="button"], input[type="submit"], input[type="button"], div[class*="button"], [tabindex="0"], .cursor-pointer, [data-testid*="submit" i], [data-test*="submit" i], [data-testid*="sell" i], [data-test*="sell" i], [data-testid*="buy" i], [data-test*="buy" i], [id*="submit" i], [id*="sell" i], [id*="buy" i]'
                ));
                for (const btn of buttons) {
                    const cls = (btn.getAttribute('class') || '').toLowerCase();
                    if (
                        !isVisible(btn) ||
                        btn.disabled ||
                        btn.getAttribute('aria-disabled') === 'true' ||
                        btn.getAttribute('data-disabled') === 'true' ||
                        cls.includes('disabled') ||
                        window.getComputedStyle(btn).pointerEvents === 'none'
                    ) continue;
                    const text = textOf(btn).toLowerCase();
                    if (negative.some(word => text.includes(word))) continue;
                    let score = 0;
                    for (const word of positive) {
                        if (text === word.toLowerCase()) score += 10;
                        else if (text.includes(word.toLowerCase())) score += 5;
                    }
                    const tag = btn.tagName;
                    const type = (btn.getAttribute('type') || '').toLowerCase();
                    const idAttrs = [
                        btn.getAttribute('id') || '',
                        btn.getAttribute('name') || '',
                        btn.getAttribute('data-testid') || '',
                        btn.getAttribute('data-test') || '',
                    ].join(' ').toLowerCase();
                    if (tag === 'INPUT' && type === 'submit') score += 5;
                    if (tag === 'BUTTON' && type === 'submit') score += 5;
                    if (idAttrs.includes('submit')) score += 4;
                    if (sideLower === 'sell' && idAttrs.includes('sell')) score += 5;
                    if (sideLower === 'buy' && idAttrs.includes('buy')) score += 5;
                    if (container.getAttribute('role') === 'dialog') score += 4;
                    if (/(order|trade|dialog|modal)/i.test(container.getAttribute('class') || '')) score += 2;
                    if (score > bestScore) {
                        best = btn;
                        bestScore = score;
                        bestText = text;
                    }
                }
            }
            if (!best || bestScore < 4) return {clicked: false, bestScore};
            best.scrollIntoView({block: 'center', inline: 'center'});
            best.click();
            return {clicked: true, text: bestText || textOf(best), bestScore};
        }
        """
        try:
            result = await self.page.evaluate(js, side)
            if result and result.get("clicked"):
                logger.info(
                    f"Clicked {side} submit button via fallback: "
                    f"{result.get('text')} (score={result.get('bestScore')})"
                )
                return True
        except Exception as e:
            logger.debug(f"Trade submit fallback failed: {e}")
        return False

    async def _capture_trade_submit_diagnostics(self, path: str, side: str) -> None:
        """Write candidate submit buttons for the current trade context."""
        try:
            payload = await self._evaluate_with_navigation_retry(
                """
                (side) => {
                    const textOf = (el) => {
                        if (!el) return '';
                        const visibleText = (el.innerText || el.textContent || '').trim();
                        const attrs = [
                            el.getAttribute('aria-label') || '',
                            el.getAttribute('title') || '',
                            el.getAttribute('value') || '',
                            el.getAttribute('data-testid') || '',
                            el.getAttribute('data-test') || '',
                            el.getAttribute('id') || '',
                            el.getAttribute('name') || '',
                            el.getAttribute('type') || '',
                        ].filter(Boolean).join(' ');
                        return (visibleText + ' ' + attrs).trim();
                    };
                    const isVisible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    const buttons = Array.from(document.querySelectorAll(
                        'button, [role="button"], input[type="submit"], input[type="button"], div[class*="button"], [tabindex="0"], .cursor-pointer, [data-testid], [data-test], [id]'
                    )).slice(0, 100);
                    return {
                        side,
                        url: window.location.href,
                        hasDialog: !!document.querySelector('[role="dialog"], [class*="dialog"], [class*="modal"]'),
                        buttons: buttons.map((btn) => {
                            const rect = btn.getBoundingClientRect();
                            const container = btn.closest('[role="dialog"], form, [class*="dialog"], [class*="modal"], [class*="trade"], [class*="order"]');
                            return {
                                tag: btn.tagName,
                                text: textOf(btn).slice(0, 160),
                                id: btn.getAttribute('id'),
                                className: btn.getAttribute('class'),
                                role: btn.getAttribute('role'),
                                type: btn.getAttribute('type'),
                                ariaDisabled: btn.getAttribute('aria-disabled'),
                                disabled: !!btn.disabled,
                                visible: isVisible(btn),
                                rect: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
                                containerRole: container ? container.getAttribute('role') : null,
                                containerClass: container ? container.getAttribute('class') : null,
                                containerText: container ? (container.innerText || container.textContent || '').trim().slice(0, 240) : null,
                            };
                        }),
                    };
                }
                """,
                side,
                label="submit_diagnostics.evaluate",
            )
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.warning(f"Trade submit diagnostics saved: {path}")
        except Exception as e:
            logger.debug(f"Failed to capture trade submit diagnostics: {e}")

    async def _confirm_trade(self):
        """Wait for trade confirmation.

        Polymtrade shows a brief toast and/or closes the dialog. We wait for
        either the dialog to disappear or a success/toast text to appear.
        """
        await asyncio.sleep(1)

        success_selectors = [
            "text=Order submitted",
            "text=Success",
            "text=Confirmed",
            "text=Order placed",
            "text=订单已提交",
            "text=成功",
            "text=卖出成功",
            "text=买入成功",
        ]

        # Wait up to 15 seconds for the dialog to close or a success marker.
        for _ in range(30):
            try:
                dialog = await self.page.query_selector("[role='dialog']")
            except Exception as e:
                message = str(e).lower()
                if self._is_navigation_race_error(e) or "target page" in message or "context or browser has been closed" in message:
                    logger.warning(
                        "Trade confirmation page changed after submit; treating as submitted "
                        f"and deferring to post-trade verification: {e}"
                    )
                    return
                raise
            if not dialog:
                logger.info("Trade dialog closed; trade likely confirmed")
                return

            for selector in success_selectors:
                try:
                    el = await self.page.wait_for_selector(selector, timeout=200, state="visible")
                    if el:
                        logger.info("Trade confirmed")
                        return
                except Exception:
                    continue

            await asyncio.sleep(0.5)

        logger.warning("Could not detect explicit confirmation, but trade may have been submitted")


    async def _verify_buy_executed(
        self,
        outcome: str,
        amount_usdc: float,
        baseline: dict,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
        timeout: float = 15.0,
    ) -> bool:
        """Best-effort verification that a BUY order actually affected the account.

        Compares USDC/pUSD balance and event-page position quantity before and after
        the trade. If balance dropped by at least 50% of the intended amount, or the
        position quantity increased, the buy is considered verified.

        If verification fails, the trade is still considered executed, but
        `verified=False` is returned for audit follow-up.
        """
        try:
            pre_balance = baseline.get("balance")
            pre_quantity = baseline.get("position_quantity")

            # Give the page a moment to reflect the new balance/order state.
            await asyncio.sleep(3)

            post_balance = await self._get_usdc_balance()
            post_quantity = await self._get_event_page_position_quantity(
                outcome, market_slug=market_slug, market_title=market_title
            )

            logger.info(
                f"BUY verification: pre_balance={pre_balance}, post_balance={post_balance}, "
                f"pre_qty={pre_quantity}, post_qty={post_quantity}, amount={amount_usdc}"
            )

            # Check 1: balance decreased by a meaningful portion of the trade amount.
            if (
                pre_balance is not None
                and post_balance is not None
                and amount_usdc > 0
                and (pre_balance - post_balance) >= amount_usdc * 0.5
            ):
                logger.info("BUY verified: balance decreased")
                return True

            # Check 2: position quantity increased.
            if post_quantity is not None:
                if pre_quantity is None:
                    # We didn't have a pre-trade quantity, but we now see a position.
                    logger.info("BUY verified: new position detected after trade")
                    return True
                if post_quantity > pre_quantity:
                    logger.info("BUY verified: position quantity increased")
                    return True

            # Check 3: success indicator still visible on the page.
            has_success_text = await self.page.evaluate(
                """
                () => {
                    const body = document.body.innerText || '';
                    const successTexts = ['Order submitted', '订单已提交', 'Success', '成功', '买入成功'];
                    return successTexts.some(t => body.includes(t));
                }
                """
            )
            if has_success_text:
                logger.info("BUY verified: success indicator detected")
                return True

            logger.warning("BUY verification could not confirm account change")
            return False
        except Exception as e:
            logger.warning(f"BUY verification failed with exception: {e}")
            return False

    async def _verify_sell_executed(
        self,
        outcome: str,
        size_shares: Optional[float],
        baseline: dict,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
        timeout: float = 15.0,
    ) -> bool:
        """Best-effort verification that a SELL order actually affected the account.

        Compares USDC/pUSD balance and event-page position quantity before and after
        the trade. If the position quantity decreased, or the balance increased by a
        meaningful amount, the sell is considered verified.

        If verification fails, the trade is still considered executed, but
        `verified=False` is returned for audit follow-up.
        """
        try:
            pre_balance = baseline.get("balance")
            pre_quantity = baseline.get("position_quantity")

            # Give the page a moment to reflect the new balance/order state.
            await asyncio.sleep(3)

            post_balance = await self._get_usdc_balance()
            post_quantity = await self._get_event_page_position_quantity(
                outcome, market_slug=market_slug, market_title=market_title
            )

            logger.info(
                f"SELL verification: pre_balance={pre_balance}, post_balance={post_balance}, "
                f"pre_qty={pre_quantity}, post_qty={post_quantity}, size={size_shares}"
            )

            # Check 1: position quantity decreased.
            if pre_quantity is not None and post_quantity is not None:
                delta = pre_quantity - post_quantity
                if delta > 0.001:
                    logger.info(f"SELL verified: position quantity decreased by {delta}")
                    return True

            # Check 2: balance increased by a meaningful portion of the trade value.
            # SELL releases USDC/pUSD, so a balance bump is a strong signal.
            if (
                pre_balance is not None
                and post_balance is not None
                and post_balance > pre_balance + 0.01
            ):
                logger.info("SELL verified: balance increased")
                return True

            # Check 3: success indicator still visible on the page.
            has_success_text = await self.page.evaluate(
                """
                () => {
                    const body = document.body.innerText || '';
                    const successTexts = ['Order submitted', '订单已提交', 'Success', '成功', '卖出成功', 'Order placed'];
                    return successTexts.some(t => body.includes(t));
                }
                """
            )
            if has_success_text:
                logger.info("SELL verified: success indicator detected")
                return True

            logger.warning("SELL verification could not confirm account change")
            return False
        except Exception as e:
            logger.warning(f"SELL verification failed with exception: {e}")
            return False
