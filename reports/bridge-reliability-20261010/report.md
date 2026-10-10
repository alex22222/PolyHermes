# Bridge Gamma search and execution verification repair

## Scope and acceptance criteria

- Fix repeated Gamma title lookup failures without changing region, proxy, wallet, trading configuration, or replaying orders.
- Use the documented public-search API, exact market matching, singleflight and bounded query-local failure cooldown.
- Confirm trades against fresh complete holdings before and after submission. Unknown holdings must never become zero.
- Regression tests, scoped commit/push, Bridge-only deployment, preserved login and production data, verified served hashes and readiness.
- Stop deployment if queue/verification work cannot drain, login is unavailable, or protected state changes unexpectedly.

## Evidence

- Existing title calls sent `title` to list `/markets` and `/events`; the documented search API is `/public-search?q=...`.
- Read-only request from the same VPS with original curly-quoted `Will Rand Paul vote “Yea” on the Clarity Act?` returned HTTP 200 and the exact straight-quoted market on 2026-10-10 16:00 UTC approximately. Quotes triggering a WAF remains unproven; no region/network bypass was used.
- Existing position metadata had a five-minute negative cache, keyed partly by changing card hrefs. There was no cross-scrape HTTP query cooldown. Thus “no negative cache at all” is not accurate.
- Portfolio snapshot cache defaults to 55 seconds; post-submit verification polls eight times with 2.5-second intervals. A cached pre-submit snapshot can cover the whole polling window.
- Failed/incomplete reads were treated as zero. Missing event-page BUY baseline was also coerced to zero. Partially parsed portfolio rows could be flagged complete.
- Read-only rolling-24h database snapshot around 2026-10-10 15:56 UTC: 109 FAILED, 20 SUBMITTED_UNVERIFIED, 1 SUCCESS. These differ from the earlier user window. Failures include 26 insufficient-position skips, 21 insufficient-balance skips, 14 repeat-market guards, and target-content errors. This is not an on-chain PnL/fill analysis.
- A streaming read-only log aggregation found 999 Gamma 403-related log lines, 960 mentioning Rand Paul. These are log lines, not unique request counts. Of 20 logged BUY baselines, seven had `qty=None`.

## Implementation

- Public-search results are shared between market/event title lookups; exact identity matching is retained.
- Identical HTTP metadata requests coalesce. Successful/empty results cache for five minutes. HTTP 403 cooldown starts at 30 minutes and doubles to six hours; other exhausted failures start at one minute and cap at 15 minutes; numeric 429 Retry-After is respected. Query cache is capped at 2,048 entries. Cooldowns reset on process restart.
- BUY captures fresh complete pre-submit holdings under the trade lock. Both BUY and SELL confirmation force fresh holdings reads, bypassing the UI snapshot cache. This adds one portfolio read before BUY and can increase latency; unavailable holdings fail closed.
- Incomplete/error/login-missing reads cannot confirm SELL or fabricate zero BUY baselines. Partial parse marks a snapshot incomplete. SELL precheck errors are recorded without submission.
- No historical status rewriting, retrying submitted orders, funds movement, leader/config changes, or new dependencies.

## Verification

- Initial baseline: 37 unit tests passed; one browser-launch test failed inside the sandbox. Re-running with browser permission resolved the environment limitation.
- Ten initial regression cases failed before implementation, then passed. Additional pre-BUY baseline and partial-parse cases also reproduced before their fixes.
- First broad run: 265 passed plus 2 subtests. Narrow browser/parser/verification run: 65 passed. Final run and deployment evidence will be appended after completion.
- Second broad run: 266 passed plus 2 subtests. The subsequent SELL precheck-recording regression was first reproduced, fixed, and verified with 21 focused tests.

## Sources

- https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles
- https://docs.polymarket.com/api-reference/markets/list-markets

## Deployment

Pending final verification. Preserve unrelated dirty Jev/OpenSpec/research files and LOOP_STATE.md. Deploy only `main.py` and `polymtrade_executor.py`; production database and browser profile remain untouched.
