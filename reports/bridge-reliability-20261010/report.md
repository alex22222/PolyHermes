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
- First broad run: 265 passed plus 2 subtests. Narrow browser/parser/verification run: 65 passed.
- Second broad run: 266 passed plus 2 subtests. The subsequent SELL precheck-recording regression was first reproduced, fixed, and verified with 21 focused tests.
- Final full suite: **267 passed, 2 subtests passed**, 77.38 seconds. `py_compile` and final diff whitespace checks passed.

## Sources

- https://docs.polymarket.com/api-reference/search/search-markets-events-and-profiles
- https://docs.polymarket.com/api-reference/markets/list-markets

## Deployment

- Code commit `b0c3cb6`; pre-deployment evidence commit `b7d8d63`; both pushed to `origin/main`.
- Two drain checks, separated by more than one minute, reported admission false, queue 0, verification tasks 0; recent PENDING database count 0. No orders replayed.
- Only `main.py` and `polymtrade_executor.py` updated. Bridge restarted at **2026-10-10 16:07:08 UTC / 2026-10-11 00:07:08 Beijing**. App and MySQL start times remained 2026-10-02 and 2026-07-12 respectively.
- Runtime/source SHA-256 matches local committed files:
  - main.py: `7c4c66a25084d5e80e45f0cb7ade25df380fa4c00279b0a3fce7fdf387778615`
  - polymtrade_executor.py: `8201636582e115514669613d0377dd4deaabe786cef04886965dad839a9eee05`
- Ready true, logged_in true, last_error null, account 1, four configurations, risk ENFORCED. Portfolio complete with 86 positions and balance $41. Admission true and queue 0. Public HTTPS `/health` returns healthy.
- Initial probes overlapping startup saw connection resets and one portfolio HTTP 500; subsequent completed-startup health/status/portfolio checks passed. These were not hidden as successful probes.
- Same quoted-title search through deployed executor returned 15 candidate markets and an exact Rand Paul match. At acceptance, 126 Gamma request attempts and two failures across cold-cache enrichment; those counters include unrelated markets, not just this query.
- Browser volume retained: `polymtrade-bridge_polymtrade-browser-profile`. Production `.env` SHA-256 unchanged: `14556aebd1c81779f941eba03c5354a7ff2db957ef058310fe515d6024415a8b`.
- Image persisted as `polyhermes-bridge:reliability-b7d8d63`, ID `sha256:f127955de86fb88b5b8ca8b84661c85a2327c7ca7a73883cccfc3c59a7310565`; existing runtime/gui/linux-amd64/browser-upgrade aliases updated. Old image retained as `polyhermes-bridge:before-b7d8d63`; old source files retained under `/opt/polyhermes/backups/bridge-reliability-b7d8d63/`.
- Unrelated dirty Jev/research files and LOOP_STATE.md preserved. No database/profile/config changes or test trades.

## Remaining limitations

This repairs query storms and stale/unknown holding evidence, not every market UI failure. Holdings changes remain portfolio-based verification, not independently attributed on-chain order fills. Historical SUBMITTED_UNVERIFIED records were not rewritten or resubmitted. Realized execution-rate improvements require new production observations; no success-rate claim is made.
