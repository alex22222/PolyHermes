import asyncio
import os
from playwright.async_api import async_playwright

QUERY = "Ethereum 1900"
PROXY = os.getenv("BROWSER_PROXY")


async def main():
    async with async_playwright() as p:
        args = ["--disable-blink-features=AutomationControlled"]
        if PROXY:
            args.append(f"--proxy-server={PROXY}")
        browser = await p.chromium.launch(
            headless=True,
            args=args,
            ignore_default_args=["--enable-automation"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        await page.goto("https://polym.trade", wait_until="networkidle", timeout=60000)
        print("loaded", page.url)

        # Try common search selectors
        search_selectors = [
            "input[placeholder*='搜索']",
            "input[placeholder*='Search']",
            "input[type='search']",
            "input[placeholder*='市场']",
            "input[placeholder*='market']",
        ]
        search_input = None
        for sel in search_selectors:
            try:
                search_input = await page.wait_for_selector(sel, timeout=3000)
                if search_input:
                    print("found search input", sel)
                    break
            except Exception:
                pass

        if not search_input:
            # dump page text to debug
            text = await page.inner_text("body")
            print("no search input found; page text sample:")
            print(text[:2000])
            await browser.close()
            return

        await search_input.fill(QUERY)
        await asyncio.sleep(2)
        # maybe press enter
        await search_input.press("Enter")
        await asyncio.sleep(3)

        # capture results and screenshot
        text = await page.inner_text("body")
        print("=" * 40)
        print(text[:3000])
        print("=" * 40)
        await page.screenshot(path="/tmp/polymtrade_search.png")
        print("screenshot saved to /tmp/polymtrade_search.png")

        # try to extract market links
        links = await page.eval_on_selector_all("a[href*='/event/']", "els => els.map(e => ({href: e.href, text: e.innerText}))")
        print("market links:", links[:20])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
