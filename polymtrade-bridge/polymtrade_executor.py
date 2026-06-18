import asyncio
import base64
import json
import logging
import os
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

            # 3) Fallback: conditionId -> CLOB market slug -> Gamma event
            if not slug_to_use and condition_id:
                try:
                    resp = await client.get(
                        f"https://clob.polymarket.com/markets/{condition_id}"
                    )
                    resp.raise_for_status()
                    clob_data = resp.json()
                    slug_to_use = clob_data.get("market_slug")
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
                result = await self._execute_buy(event_id, event_slug, outcome, amount_usdc)
            else:
                result = await self._execute_sell(event_id, event_slug, outcome, amount_usdc, size_shares)

            logger.info(f"Trade executed: {result}")
            return result

        except Exception as e:
            self.last_error = str(e)
            logger.exception(f"Trade execution failed: {e}")
            try:
                safe_slug = (market_slug or "unknown").replace("/", "_")
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
    ):
        """Execute a BUY order on the Polymtrade event page."""
        market_url = (
            f"{self.base_url}/?eventId={event_id}"
            f"&eventSlug={event_slug}&eventSource=polymarket"
        )
        logger.info(f"Navigating to {market_url}")
        await self.page.goto(market_url, wait_until="load", timeout=60000)
        await asyncio.sleep(3)

        # Click the Yes/No button for the chosen outcome
        await self._select_polymtrade_outcome(outcome)
        await asyncio.sleep(1)

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
        await self._open_sell_dialog(outcome)
        await asyncio.sleep(1)

        # The sell dialog works in shares, not USDC.
        if size_shares is not None and size_shares > 0:
            try:
                input_el = await self.page.wait_for_selector("input[name='soldAmount']", timeout=5000)
                await input_el.fill(str(size_shares))
                logger.info(f"Entered sell shares: {size_shares}")
            except Exception as e:
                logger.warning(f"Could not enter sell shares, falling back to full: {e}")
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

    async def _select_polymtrade_outcome(self, outcome: str):
        """Click the Yes/No button in the outcome row matching the outcome name."""
        # Normalize common Yes/No labels to the Chinese UI text
        outcome_norm = outcome.strip().lower()
        if outcome_norm in ("yes", "是", "true"):
            side_label = "是"
        elif outcome_norm in ("no", "否", "false"):
            side_label = "否"
        else:
            # For custom outcome names, the signal usually carries the outcome name
            # (e.g., "法国"). In Polymtrade's grouped market view, each row has the
            # outcome name and Yes/No buttons; we default to Yes (buy) for the named outcome.
            side_label = "是"

        # Use JS to find the row containing the outcome text and click the Yes/No button.
        js = """
        (args) => {
            const [outcome, sideLabel] = args;
            const xpath = "//*[contains(text(), '" + outcome + "')]";
            const iter = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_ITERATOR_TYPE, null);
            let node;
            while ((node = iter.iterateNext())) {
                let el = node;
                for (let i = 0; i < 8; i++) {
                    if (!el) break;
                    const btns = Array.from(el.querySelectorAll('button, [role="button"], div.button, .cursor-pointer'));
                    const target = btns.find(b => {
                        const t = b.textContent.trim();
                        return t === sideLabel || t.startsWith(sideLabel + ' ') || t.startsWith(sideLabel);
                    });
                    if (target) {
                        target.click();
                        return {clicked: true, label: target.textContent.trim()};
                    }
                    el = el.parentElement;
                }
            }
            return {clicked: false};
        }
        """
        result = await self.page.evaluate(js, [outcome, side_label])
        if not result or not result.get("clicked"):
            raise RuntimeError(f"Could not select outcome: {outcome} ({side_label})")
        logger.info(f"Selected outcome: {outcome} -> {result.get('label')}")

    async def _enter_amount(self, amount_usdc: float):
        """Enter the trade amount in the buy dialog."""
        selectors = [
            "input[name='buyAmount']",
            "input[inputmode='decimal']",
            "input[type='number']",
        ]
        for selector in selectors:
            try:
                input_el = await self.page.wait_for_selector(selector, timeout=3000)
                if input_el:
                    await input_el.fill(str(amount_usdc))
                    logger.info(f"Entered amount: {amount_usdc}")
                    return
            except Exception:
                continue
        raise RuntimeError("Could not enter trade amount")

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

    async def _open_sell_dialog(self, outcome: str):
        """Click the sell button for the position matching the outcome.

        On the event page the position card has a #sell button. When there are
        multiple positions we try to click the sell button inside the card whose
        text contains the outcome / side label.
        """
        outcome_norm = outcome.strip().lower()
        side_label = None
        if outcome_norm in ("yes", "是", "true"):
            side_label = "Yes"
        elif outcome_norm in ("no", "否", "false"):
            side_label = "No"

        js = """
        (args) => {
            const [outcome, sideLabel] = args;
            const candidates = Array.from(document.querySelectorAll('button, [role="button"]'))
                .filter(b => {
                    const t = b.textContent.trim();
                    return t === '卖出' || t.includes('卖出');
                });

            // Prefer a sell button whose ancestor card contains the side label
            // or the outcome name.
            for (const btn of candidates) {
                let text = '';
                let el = btn.parentElement;
                for (let i = 0; i < 6 && el; i++) {
                    text += ' ' + (el.innerText || '');
                    el = el.parentElement;
                }
                text = text.toLowerCase();
                if (sideLabel && text.includes(sideLabel.toLowerCase())) {
                    btn.click();
                    return {clicked: true, label: btn.textContent.trim()};
                }
                if (text.includes(outcome.toLowerCase())) {
                    btn.click();
                    return {clicked: true, label: btn.textContent.trim()};
                }
            }

            // Fallback to the global #sell button on the event page.
            const sell = document.querySelector('#sell');
            if (sell) {
                sell.click();
                return {clicked: true, label: sell.textContent.trim()};
            }
            return {clicked: false};
        }
        """
        result = await self.page.evaluate(js, [outcome, side_label])
        if not result or not result.get("clicked"):
            raise RuntimeError(f"Could not open sell dialog for outcome: {outcome}")
        logger.info(f"Opened sell dialog for outcome: {outcome} -> {result.get('label')}")

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
