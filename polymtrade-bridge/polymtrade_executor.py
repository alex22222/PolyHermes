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

logger = logging.getLogger(__name__)


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
            await self.page.goto(self.base_url, wait_until="load", timeout=60000)
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
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

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
            await self.page.goto(url, wait_until="load", timeout=60000)
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

    async def fetch_portfolio_positions(self) -> dict:
        """Scrape current open positions from the Polymtrade portfolio page.

        Returns a dict with {"positions": [...], "synced_at": timestamp}.
        Each position contains: marketTitle, side, quantity, currentValue,
        pnl, percentPnl, marketIcon, marketSlug, conditionId, eventSlug.
        """
        if not self.page:
            return {"error": "page not initialized"}
        try:
            await self.page.goto(
                f"{self.base_url}/portfolio", wait_until="load", timeout=60000
            )
            await asyncio.sleep(3)

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

                    positions.push({
                        marketTitle: title,
                        side: side,
                        quantity: quantity,
                        currentValue: currentValue,
                        pnl: pnl,
                        percentPnl: percentPnl,
                        marketIcon: img ? img.src : null,
                    });
                }
                return positions;
            }
            """
            positions = await self.page.evaluate(js)

            # Enrich with Gamma API metadata so the backend can map titles to
            # market/condition IDs and slugs without relying on its local cache.
            # Performed serially because each enrichment navigates/clicks the page.
            for pos in positions:
                try:
                    meta = await self._enrich_position(pos)
                    pos.update(meta)
                except Exception as e:
                    logger.warning(f"Failed to enrich {pos.get('marketTitle')}: {e}")

            return {
                "positions": positions,
                "synced_at": int(time.time() * 1000),
            }
        except Exception as e:
            logger.exception(f"Failed to fetch portfolio positions: {e}")
            return {"error": str(e)}

    async def _enrich_position(self, position: dict) -> dict:
        """Map a portfolio market title to conditionId/slugs.

        Polymtrade's portfolio cards do not expose slugs in the DOM. Clicking a
        card updates the page URL with `eventId` and `eventSlug`, which we then
        use to resolve the exact market via Gamma's events API.
        """
        title = position.get("marketTitle")
        if not title:
            return {}
        try:
            clicked = await self.page.eval_on_selector_all(
                "li.flex.px-4.py-2.border-b.text-xs.items-center.cursor-pointer",
                """(lis, title) => {
                    const li = Array.from(lis).find(l => (l.innerText || "").includes(title));
                    if (li) { li.click(); return true; }
                    return false;
                }""",
                title,
            )
            if not clicked:
                logger.warning(f"Could not find portfolio card to click for: {title}")
                return {}

            # Wait for the overlay to update the URL with eventSlug.
            await asyncio.sleep(1.5)
            url = self.page.url
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            event_slug = qs.get("eventSlug", [None])[0]
            if not event_slug:
                logger.warning(f"Portfolio click did not reveal eventSlug for: {title}, url={url}")
                return {}

            proxy_url = self.proxy
            transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
            async with httpx.AsyncClient(transport=transport, timeout=20.0) as client:
                resp = await client.get(
                    "https://gamma-api.polymarket.com/events",
                    params={"slug": event_slug, "limit": "5"},
                )
                resp.raise_for_status()
                events = resp.json()
                if not events:
                    logger.warning(f"Gamma events API returned empty for slug: {event_slug}")
                    return {}

                event = events[0]
                market = next(
                    (m for m in event.get("markets", []) if m.get("question") == title),
                    None,
                )
                if not market:
                    logger.warning(f"Event {event_slug} does not contain market titled: {title}")
                    return {}

                return {
                    "conditionId": market.get("conditionId"),
                    "marketSlug": market.get("slug"),
                    "eventSlug": event.get("slug"),
                }
        except Exception as e:
            logger.warning(f"Failed to enrich position {title}: {e}")
            return {}

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

        Polymtrade's market page is `/?eventId=<id>&eventSlug=<slug>&eventSource=polymarket`.
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
            else:
                result = await self._execute_sell(
                    event_id, event_slug, outcome, amount_usdc, size_shares,
                    market_slug=market_slug, market_title=market_title
                )

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

    async def _execute_buy(
        self,
        event_id: str,
        event_slug: str,
        outcome: str,
        amount_usdc: float,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ):
        """Execute a BUY order on the Polymtrade event page."""
        market_url = (
            f"{self.base_url}/?eventId={event_id}"
            f"&eventSlug={event_slug}&eventSource=polymarket"
        )
        logger.info(f"Navigating to {market_url}")
        await self.page.goto(market_url, wait_until="load", timeout=60000)
        await asyncio.sleep(3)

        # On Polymtrade a network/deposit modal may pop up when the user first
        # clicks an outcome. We try to click the outcome, dismiss the modal, and
        # retry a few times. If the modal keeps coming back the account likely
        # lacks sufficient deposit balance.
        buy_dialog_open = False
        for attempt in range(3):
            await self._select_polymtrade_outcome(
                outcome, market_slug=market_slug, market_title=market_title
            )
            await asyncio.sleep(0.8)
            if not await self._is_network_modal_open():
                logger.info("No network modal after outcome click")
                buy_dialog_open = True
                break
            logger.info(f"Network modal open after outcome click (attempt {attempt + 1}), dismissing")
            dismissed = await self._dismiss_modal_dialogs()
            if not dismissed:
                raise RuntimeError("Could not dismiss network/deposit modal")
            await asyncio.sleep(0.5)
        else:
            # Loop exhausted: the modal was dismissed each time. Try one final
            # outcome click to open the actual buy dialog.
            if not await self._is_network_modal_open():
                await self._select_polymtrade_outcome(
                    outcome, market_slug=market_slug, market_title=market_title
                )
                await asyncio.sleep(0.8)
                if not await self._is_network_modal_open():
                    buy_dialog_open = True

        if not buy_dialog_open:
            if await self._is_network_modal_open():
                raise RuntimeError(
                    "Network/deposit modal keeps blocking the trade. "
                    "The Bridge account probably has insufficient USDC balance or needs a deposit."
                )
            # Modal is gone but no buy dialog either; fall through to _enter_amount
            # which will report if the amount input cannot be found.

        # Final safety check before entering the amount.
        if await self._is_network_modal_open():
            await self._dismiss_modal_dialogs()
            await asyncio.sleep(0.3)
            if await self._is_network_modal_open():
                raise RuntimeError("Network/deposit modal blocked trade")

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

        The position card on the event page exposes a #sell button. Clicking it
        opens a dialog with input[name='soldAmount'] and #sellbtn. If size_shares
        is provided we sell that many shares; otherwise we sell the full position.
        """
        market_url = (
            f"{self.base_url}/?eventId={event_id}"
            f"&eventSlug={event_slug}&eventSource=polymarket"
        )
        logger.info(f"Navigating to event page for SELL: {market_url}")
        await self.page.goto(market_url, wait_until="load", timeout=60000)
        await asyncio.sleep(3)

        # Open the sell dialog for the position matching the outcome
        await self._open_sell_dialog(
            outcome, market_slug=market_slug, market_title=market_title
        )
        await asyncio.sleep(1)

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

        # Submit the sell order
        await self._click_sell_button()

        # Wait for confirmation
        await self._confirm_trade()

        return {
            "status": "executed",
            "side": "SELL",
            "outcome": outcome,
            "amount_usdc": amount_usdc,
            "event_id": event_id,
            "event_slug": event_slug,
        }

    def _extract_market_keywords(self, market_slug: Optional[str] = None, market_title: Optional[str] = None) -> list:
        """Extract searchable keywords from a market slug or title.

        Long English titles/slugs are split and common stop-words are removed so
        we can match the short translated labels rendered by Polymtrade.
        """
        stop_words = {
            "will", "the", "a", "an", "be", "at", "in", "of", "for", "to", "by",
            "and", "or", "is", "are", "on", "vs", "with", "from", "as", "it",
            "their", "there", "this", "that", "these", "those", "i", "you", "he",
            "she", "we", "they", "my", "your", "his", "her", "our", "their", "score",
            "win", "lose", "reach", "final", "market", "event", "more", "than", "by",
            "points", "matchup", "game", "winner", "top", "can", "qat", "draw",
        }
        raw = (market_slug or market_title or "").lower()
        tokens = re.split(r"[^a-z0-9]+", raw)
        keywords = []
        for t in tokens:
            t = t.strip()
            if not t or t in stop_words or len(t) <= 1:
                continue
            # Keep short numeric tokens (years) but drop very generic 2-letter words
            if len(t) == 2 and not t.isdigit():
                continue
            keywords.append(t)
        # Deduplicate while preserving order
        seen = set()
        result = []
        for k in keywords:
            if k not in seen:
                seen.add(k)
                result.append(k)
        return result

    async def _select_polymtrade_outcome(
        self,
        outcome: str,
        market_slug: Optional[str] = None,
        market_title: Optional[str] = None,
    ):
        """Click the Yes/No button for the chosen outcome on the event page.

        For categorical event pages (e.g. World Cup golden boot) Polymtrade lists
        several sub-markets. We use `market_slug`/`market_title` keywords to find
        the correct row, then click the side (Yes/No) button inside that row.
        """
        outcome_norm = outcome.strip().lower()
        if outcome_norm in ("yes", "是", "true"):
            side_labels = ["是", "Yes"]
        elif outcome_norm in ("no", "否", "false"):
            side_labels = ["否", "No"]
        else:
            # For custom outcome names (e.g. "France") default to Yes/是 side.
            side_labels = ["是", "Yes"]

        keywords = self._extract_market_keywords(market_slug, market_title)

        js = """
        (args) => {
            const [outcome, sideLabels, keywords] = args;
            const textOf = (el) => (el.innerText || el.textContent || "").trim();

            // Helper: score a candidate element by how many keywords it contains.
            function score(el) {
                const text = textOf(el).toLowerCase();
                let s = 0;
                for (const kw of keywords) {
                    if (text.includes(kw)) s += 1;
                }
                return s;
            }

            // Find all candidate rows (li or section items). Prefer the highest-
            // scoring row that actually contains a matching side label.
            const rows = Array.from(document.querySelectorAll('li, [role="listitem"], section'));
            const scoredRows = rows
                .map(row => ({ row, s: score(row) }))
                .filter(item => item.s > 0)
                .sort((a, b) => b.s - a.s);

            for (const { row, s } of scoredRows) {
                const buttons = Array.from(row.querySelectorAll('button, [role="button"], div[class*="button"], .cursor-pointer'));
                for (const sideLabel of sideLabels) {
                    const target = buttons.find(b => {
                        const t = textOf(b);
                        return t === sideLabel || t.toLowerCase() === sideLabel.toLowerCase() || t.startsWith(sideLabel);
                    });
                    if (target) {
                        target.click();
                        return {clicked: true, label: textOf(target), rowScore: s, rowText: textOf(row).slice(0, 80)};
                    }
                }
            }

            // Fallback: search globally for any element containing the outcome text,
            // walk up to find a clickable side label.
            const xpath = "//*[contains(text(), '" + outcome + "')]";
            const iter = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
            let node;
            while ((node = iter.iterateNext())) {
                let el = node;
                for (let i = 0; i < 10; i++) {
                    if (!el) break;
                    const btns = Array.from(el.querySelectorAll('button, [role="button"], div[class*="button"], .cursor-pointer'));
                    for (const sideLabel of sideLabels) {
                        const target = btns.find(b => {
                            const t = textOf(b);
                            return t === sideLabel || t.toLowerCase() === sideLabel.toLowerCase() || t.startsWith(sideLabel);
                        });
                        if (target) {
                            target.click();
                            return {clicked: true, label: textOf(target), fallback: true};
                        }
                    }
                    el = el.parentElement;
                }
            }
            return {clicked: false, bestScore, keywords};
        }
        """
        result = await self.page.evaluate(js, [outcome, side_labels, keywords])
        if not result or not result.get("clicked"):
            raise RuntimeError(f"Could not select outcome: {outcome} ({side_labels}), keywords={keywords}, rowScore={result.get('bestScore') if result else None}")
        logger.info(f"Selected outcome: {outcome} -> {result.get('label')} (rowScore={result.get('rowScore')}, keywords={keywords})")

    async def _is_network_modal_open(self) -> bool:
        """Return True if the network/token selection modal is visible."""
        try:
            return await self.page.evaluate(
                """() => {
                    const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
                    const all = Array.from(document.querySelectorAll('*[role="dialog"], div, section'));
                    return all.some(d => modalTexts.some(mt => (d.innerText || '').includes(mt)));
                }"""
            )
        except Exception as e:
            logger.warning(f"Failed to check modal state: {e}")
            return False

    async def _dismiss_modal_dialogs(self) -> bool:
        """Dismiss the network/token selection modal that blocks the buy dialog.

        Polymtrade sometimes shows a '选择网络和代币' modal before the first trade.
        We only close it if its title text is present, to avoid closing the actual
        trade dialog.
        """
        js = """
        () => {
            const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
            // Broad search: any element whose text contains the modal title
            const all = Array.from(document.querySelectorAll('div, section, aside, [role="dialog"], [class*="modal"], [class*="chakra-modal"]'));
            for (const dialog of all) {
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
                logger.info(f"Dismissed network selection modal: {result.get('text')}")
                await asyncio.sleep(0.5)
                # Verify the modal is really gone; if not, force-hide it.
                still_visible = await self.page.evaluate(
                    """() => {
                        const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
                        const all = Array.from(document.querySelectorAll('*[role="dialog"], div, section'));
                        return all.some(d => modalTexts.some(mt => (d.innerText || '').includes(mt)));
                    }"""
                )
                if still_visible:
                    logger.warning("Modal still visible after close attempt, forcing hide")
                    await self.page.evaluate(
                        """() => {
                            const modalTexts = ['选择网络和代币', '选择网络', '选择币种', 'Select Network', 'Select Token'];
                            const all = Array.from(document.querySelectorAll('*[role="dialog"], div, section'));
                            for (const d of all) {
                                if (modalTexts.some(mt => (d.innerText || '').includes(mt))) {
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

    async def _enter_amount(self, amount_usdc: float):
        """Enter the trade amount in the buy dialog."""
        selectors = [
            "input[name='buyAmount']",
            "input[inputmode='decimal']",
            "input[type='number']",
            "input[placeholder*='Amount' i]",
            "input[placeholder*='amount' i]",
            "input[placeholder*='USDC' i]",
            "input[placeholder*='0.0' i]",
            "input[placeholder*='数量' i]",
            "input[placeholder*='金额' i]",
            "input[class*='amount' i]",
            "input[class*='trade-input' i]",
        ]
        for selector in selectors:
            try:
                input_el = await self.page.wait_for_selector(selector, timeout=2000)
                if input_el:
                    await input_el.fill(str(amount_usdc))
                    logger.info(f"Entered amount: {amount_usdc}")
                    return
            except Exception:
                continue

        # Fallback: try any visible input inside a trade dialog.
        try:
            input_el = await self.page.wait_for_selector(
                "[role='dialog'] input, .trade-dialog input, [class*='dialog'] input[inputmode='decimal']",
                timeout=2000
            )
            if input_el:
                await input_el.fill(str(amount_usdc))
                logger.info(f"Entered amount via fallback: {amount_usdc}")
                return
        except Exception:
            pass

        raise RuntimeError("Could not enter trade amount")

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
        for selector in selectors:
            try:
                input_el = await self.page.wait_for_selector(selector, timeout=2000)
                if input_el:
                    await input_el.fill(str(size_shares))
                    logger.info(f"Entered sell shares: {size_shares}")
                    return True
            except Exception:
                continue
        return False

    async def _click_buy_button(self):
        """Click the buy button in the trade dialog."""
        selectors = [
            "button[data-test='trade-buy-button']",
            "button#buybtn",
            "button:has-text('买入')",
            "[role='dialog'] button:has-text('买入')",
        ]
        for selector in selectors:
            try:
                await self.page.click(selector, timeout=3000)
                logger.info("Clicked buy button")
                return
            except Exception:
                continue
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

            function scoreCard(card) {
                const text = textOf(card).toLowerCase();
                let s = 0;
                for (const kw of keywords) {
                    if (text.includes(kw)) s += 1;
                }
                return s;
            }

            // Strategy 1: find all sell buttons and group them by their card.
            // Pick the card with the highest keyword score.
            const allSellBtns = Array.from(document.querySelectorAll('button, [role="button"], .cursor-pointer, [class*="button"]'))
                .filter(b => isVisible(b) && isSellButton(b));

            let bestBtn = null;
            let bestScore = 0;
            for (const btn of allSellBtns) {
                let card = btn.closest('[class*="card"], [class*="position"], [class*="portfolio"], li, div');
                if (!card) card = btn.parentElement;
                const s = scoreCard(card);
                // Tie-break: prefer a card whose text also contains the side label/outcome
                const cardText = textOf(card).toLowerCase();
                const sideMatch = sideLabels.some(l => cardText.includes(l.toLowerCase()));
                const outcomeMatch = cardText.includes(outcome.toLowerCase());
                const finalScore = s + (sideMatch ? 5 : 0) + (outcomeMatch ? 5 : 0);
                if (finalScore > bestScore) {
                    bestScore = finalScore;
                    bestBtn = btn;
                }
            }

            if (bestBtn) {
                bestBtn.click();
                return {clicked: true, label: textOf(bestBtn), score: bestScore};
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
                        const sell = el.querySelector ? Array.from(el.querySelectorAll('button, [role="button"], .cursor-pointer')).find(isSellButton) : null;
                        if (sell) {
                            sell.click();
                            return {clicked: true, label: textOf(sell), fallback: true};
                        }
                        el = el.parentElement;
                    }
                }
            }

            // Strategy 3: global #sell button
            const sell = document.querySelector('#sell');
            if (sell && isVisible(sell)) {
                sell.click();
                return {clicked: true, label: textOf(sell), fallback: true};
            }
            return {clicked: false, keywords, sellButtons: allSellBtns.length};
        }
        """
        result = await self.page.evaluate(js, [outcome, side_labels, keywords])
        if not result or not result.get("clicked"):
            raise RuntimeError(f"Could not open sell dialog for outcome: {outcome} (keywords={keywords}, sellButtons={result.get('sellButtons') if result else None})")
        logger.info(f"Opened sell dialog for outcome: {outcome} -> {result.get('label')} (score={result.get('score')})")

    async def _click_sell_button(self):
        """Click the sell button in the sell dialog."""
        selectors = [
            "button#sellbtn",
            "button:has-text('卖出')",
            "[role='dialog'] button:has-text('卖出')",
        ]
        for selector in selectors:
            try:
                await self.page.click(selector, timeout=3000)
                logger.info("Clicked sell button")
                return
            except Exception:
                continue
        raise RuntimeError("Could not click sell button")

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
            dialog = await self.page.query_selector("[role='dialog']")
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
