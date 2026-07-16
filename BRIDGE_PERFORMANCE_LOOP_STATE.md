# Bridge Performance Loop State

## Goal

Improve the local Polymtrade Bridge until all of these conditions hold:

- 5m/15m BUY latency: P50 6-10 seconds and P95 at most 15-20 seconds.
- SELL submission latency: 10-20 seconds; verification completes asynchronously.
- Webhook acceptance latency: P95 below 200 ms.
- No false health-check restart for seven consecutive days.

## Loop

Trigger: persistent Codex goal with iterative local implementation and Shadow verification.

Isolation: one worker in the current worktree, scoped to `polymtrade-bridge` and this state file.
Existing unrelated working-tree changes must not be modified.

Checker: Bridge tests, shell syntax checks, latency probes, database timing reports, and live
read-only runtime evidence. A change is not accepted from code review alone.

Verifier: `cd polymtrade-bridge && ./.venv/bin/python bridge_performance_report.py`.
Exit 0 means all sample and seven-day gates pass; exit 1 with `pending` means more evidence is needed.

## Baseline

Captured on 2026-07-15/16 before performance changes:

- 15m BUY signal-to-final: P50 25.36s, P95 33.23s (n=7).
- 15m SELL signal-to-final: P50 108.94s, P95 111.52s (n=4).
- 5m BUY record-to-final: P50 36.71s, P95 77.98s (n=7, last 24h).
- 5m SELL record-to-final: P50 58.08s, P95 98.80s (n=3, last 24h).
- Webhook acceptance for filtered 5m signals: P95 2.11s BUY / 2.66s SELL.
- 25 portfolio reads produced 1,582 measured Gamma requests.
- Bridge Chromium runtime used about 955 MB RSS across nine processes.
- The launchd supervisor recorded repeated single-probe health restarts during observation.

The 15m sample is small. It is sufficient to identify path overhead but not to certify the
final latency distribution.

## Open

- [x] Iteration 1: prevent single-probe false restarts and remove synchronous DB work from the webhook event loop.
- [x] Iteration 2: add a bounded signal queue and separate trade/portfolio page ownership.
- [x] Iteration 3: remove fixed waits and move BUY/SELL verification off the submission path.
- [x] Iteration 4: mark BUY/SELL submitted before asynchronous verification and persist stage metrics.
- [x] Iteration 5: collect last-mile quote and price-drift evidence in Shadow mode.
- [ ] Shadow verification reaches the latency targets with enough 5m/15m samples.
- [ ] Seven-day false-restart counter completes with zero false health restarts.
- [ ] Reduce the two-page Chromium footprint; the first live run reached about 1.08 GB RSS across 11 processes,
  run 30 was about 884.8 MB RSS across 11 Bridge-related processes, and run 32 is about 1.12 GB
  RSS across 11 Bridge-related processes with exactly two live pages.
- [x] Make planned restart admission retry-safe in code; the next safe/natural restart must load it before relying on it.
- [x] Validate planned restart admission state under live launchd after a quiet-window restart.
- [x] Add a quiet-window guarded restart runner so the first hot-load of drain code is not a manual guess.

## Done

- [x] Read-only baseline captured from runtime, logs, code, and `bridge_trade_record`.
- [x] Persistent goal and loop stop conditions created.
- [x] Supervisor now requires three consecutive failed probes; a successful probe resets the counter.
- [x] Recorder, config refresh/filtering, guard queries, and position-ledger calls in the signal path run off the event loop.
- [x] Iteration 1 verification: 52 Bridge tests passed, supervisor policy test passed,
  `bash -n start.sh supervisor_health.sh` passed, and `git diff --check` passed.
- [x] Signal ingestion now uses a bounded queue with four filter workers and retryable 503 backpressure.
- [x] Trade and portfolio work use task-local page scopes; portfolio reads no longer hold the trade lock.
- [x] Stable portfolio metadata and event resolution use TTL caches, concurrent singleflight, and a shared HTTP client.
- [x] Portfolio lazy loading now stops after two stable samples instead of always sleeping four seconds.
- [x] Iteration 2 verification: 59 unittest cases passed; page, BUY, SELL, event visibility,
  and enrichment async scripts passed. Pytest also passed 112 synchronous cases; 40 pre-existing
  top-level async cases require a missing pytest async plugin and were verified through their script entrypoints.
- [x] BUY and SELL now release the trade lock after UI submission; tracked background tasks verify
  live portfolio changes and preserve SUCCESS submission semantics with an audit warning when unconfirmed.
- [x] Fixed three-second post-navigation waits and the fixed one-second confirmation wait were removed;
  confirmation now returns immediately when the dialog closes and otherwise polls every 250 ms.
- [x] First-time 5m/15m event resolution queries Gamma markets before events and reuses a shared client.
- [x] `/metrics` now reports recent P50/P95 stage latency. A background writer persists timing and
  last-mile quote-drift events to `polymtrade-bridge/logs/bridge-performance.jsonl` without event-loop I/O.
- [x] Supervisor health failures, recoveries, threshold restarts, and service starts are persisted to
  `$LOG_DIR/polymtrade-health-events.jsonl` for the seven-day stability check.
- [x] Iteration 3-5 local verification: 70 unittest cases passed; BUY, SELL, event visibility,
  and enrichment async scripts passed; shell syntax and `git diff --check` passed.
- [x] Live code loaded at 2026-07-16 00:48 Asia/Shanghai; executor is ready/logged in with
  four signal workers. Launchd remained on run 29 after the 90-second startup grace.
- [x] Live webhook sample after restart: P50 7.071 ms, P95 21.877 ms (n=4).
  Isolated ASGI load check: P50 0.641 ms, P95 3.310 ms, max 101.373 ms (n=1,000).
- [x] First live SELL after restart submitted in 13.959 seconds end to end and 6.709 seconds
  inside the executor. Portfolio verification completed successfully 58.637 seconds later in the background.
- [x] First live portfolio enrichment issued 37 Gamma requests; subsequent reads used metadata cache hits.
- [x] Performance events are being appended to `polymtrade-bridge/logs/bridge-performance.jsonl`.
- [ ] No post-restart 5m/15m BUY sample has completed yet; BUY percentile targets remain unverified.
- [x] Added signal admission drain guard for planned restarts: `/admin/drain` is local-only, optional
  `BRIDGE_ADMIN_SECRET` aware, and makes `/signal` return retryable 503 with `Retry-After: 10`
  instead of enqueueing work into a shutting-down executor.
- [x] Iteration 6 local verification: `test_signal_queue.py` and supervisor policy tests passed,
  `bash -n start.sh supervisor_health.sh` passed, `git diff --check` passed, and full Bridge
  unittest discovery passed 73 tests before the final `start.sh` secret-header refinement.
- [x] Added `polymtrade-bridge/safe_restart_bridge.sh`. Default mode is check-only; `--execute`
  waits for a stable `signals_received` counter and empty signal queue before `launchctl kickstart -k`,
  then verifies the restarted process exposes `accepting_signals` in `/metrics`.
- [x] Iteration 7 local verification: `BRIDGE_RESTART_QUIET_SECONDS=3 bash ./safe_restart_bridge.sh`
  passed in check-only mode without restarting; 73 Bridge unittest cases passed; `git diff --check`
  passed; verifier remained `pending` because real 5m/15m samples and seven-day health evidence are
  still incomplete.
- [x] Iteration 8 loaded the admission-drain build into the launchd-managed service through
  `BRIDGE_RESTART_QUIET_SECONDS=45 bash ./safe_restart_bridge.sh --execute`. The quiet window passed,
  launchd advanced from run 29 to run 30, `/status` returned ready/logged_in with account id 2, and
  `/metrics` exposed `accepting_signals=true`, `signal_queue_depth=0`, and four signal workers.
- [x] After the restart, the health log recorded a new `service_start` at 1784134840 and `health_ok`
  at 1784134932 with zero `restart_threshold` events. A 100-request `/health` probe measured
  P50 0.922 ms, P95 4.473 ms, max 13.804 ms.
- [x] One real post-restart webhook was accepted: tx
  `0xf471c83cbe14012cb77fd858f1415a05d760c531d2ff25895af618998afbdb91`, webhook 4.455 ms,
  queue wait 14.694 ms. DB record 32219 was a controlled SELL skip with
  `Live portfolio insufficient position, skipped (available=0, required=1.0428)`, not an executor
  shutdown failure.
- [x] `safe_restart_bridge.sh` now performs a final pre-kick metrics check after attempting drain:
  it aborts if `signals_received` changed or the signal queue is non-empty immediately before restart.
  Check-only mode passed with `BRIDGE_RESTART_QUIET_SECONDS=3`; 73 Bridge unittest cases passed.
- [x] Iteration 9 added low-cost browser page diagnostics for resource work. `PolymtradeExecutor.browser_diagnostics()`
  reports context page count, default/portfolio page closed state, and per-page roles/URLs; `/metrics`
  includes this as `metrics.browser` after the next safe/natural restart. This does not navigate,
  screenshot, or read DOM, so it does not change live portfolio semantics.
- [x] Iteration 9 also changed `bridge_performance_report.py` so latency checks remain `pending`
  until the required sample floor is reached; early outliers set `would_fail_current_sample=true`
  instead of making the verifier hard-fail before enough evidence exists.
- [x] A real BUY webhook during local test load created tx
  `0x9634720448f4f94ac89bd6773c42b83310664be81c81a981ce9064fc0fb975e0`: webhook 475.525 ms,
  queue wait 1163.743 ms. It was skipped by the low-price tail-risk guard and DB record 32220 was
  `FAILED` with `Low-price tail-risk BUY skipped: price=0.004, min=0.10`. No executor failure.
- [x] Iteration 9 verification: 75 Bridge unittest cases passed; `git diff --check` passed;
  verifier returned `pending` with webhook `would_fail_current_sample=true` (n=7, P95 339.88 ms)
  because the sample floor is 100 and real 5m/15m trade samples remain incomplete.
- [x] Iteration 10 hot-loaded browser diagnostics through `safe_restart_bridge.sh --execute`. The first
  child after the restart exceeded the old 90-second startup grace while Playwright was recovering the
  persistent profile, causing one health `restart_threshold` at 1784135412. The following child recovered:
  `/status` is ready/logged_in, `/metrics.browser.page_count=2`, pages are `default` at
  `https://polym.trade/` and `portfolio` at `https://polym.trade/portfolio`, and queue depth is 0.
- [x] Iteration 10 fixed the recurrence cause in code: `start.sh` now uses
  `BRIDGE_STARTUP_GRACE_SECONDS` with a 240-second default before health probes can restart the child.
  This file change will be used by the next launchd-started supervisor process; the current parent
  shell was already running before the edit.
- [x] `bridge_performance_report.py` now measures seven consecutive health-stable days from the first
  `service_start` after the last `restart_threshold`. It keeps historical threshold count in
  `historical_threshold_restarts` but reports current-window `threshold_restarts=0` after recovery.
- [x] Iteration 10 verification: 76 Bridge unittest cases passed; `bash -n safe_restart_bridge.sh
  start.sh supervisor_health.sh` passed; `git diff --check` passed; verifier returned `pending`
  with `health_stability.observation_start=1784135451`, `threshold_restarts=0`,
  `historical_threshold_restarts=1`.
- [x] Iteration 11 aligned `safe_restart_bridge.sh` with the longer supervisor startup grace:
  `BRIDGE_RESTART_POST_START_TIMEOUT` now defaults to `BRIDGE_STARTUP_GRACE_SECONDS + 60`
  (300 seconds with the current 240-second grace), so a safe restart will not time out before
  the supervisor's own slow-start window has elapsed.
- [x] Iteration 11 verification: `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh`
  passed; 76 Bridge unittest cases passed; `git diff --check` passed; live `/health` and
  `/status` were ready/logged_in; verifier returned `pending` with seven-day health and real
  5m/15m trade samples still incomplete.
- [x] Iteration 12 added an idle portfolio-page close policy to reduce long-running Chromium
  footprint without returning portfolio reads to the trade page. `BRIDGE_PORTFOLIO_PAGE_IDLE_CLOSE_SECONDS`
  defaults to 120 seconds and can be set to 0 to disable. The page is reused during active portfolio
  reads, then closed after the idle window.
- [x] Iteration 12 verification: targeted browser diagnostics/idle-close tests passed (3 tests);
  full Bridge unittest discovery passed 78 tests; `bash -n safe_restart_bridge.sh start.sh
  supervisor_health.sh` passed; `git diff --check` passed; verifier returned `pending` with
  health and trade sample gates still incomplete. This change is not loaded into the live launchd
  process yet because no planned restart was performed.
- [x] Iteration 13 loaded the idle-close/startup-grace build through guarded restart after adding
  bounded `/metrics` retries to `safe_restart_bridge.sh`. The first execute attempt aborted before
  kickstart because a single metrics read timed out; the retrying version passed check-only mode and
  the second guarded execute restarted successfully with `/health` ok, `/status` ready/logged_in,
  `accepting_signals=true`, queue depth 0, and zero restart-threshold events in the new health window.
- [x] Live evidence after Iteration 13: webhook aggregate reached the sample floor and now passes
  (`count=698`, P50 0.126 ms, P95 9.89 ms). Health stability is still pending at about 0.54/7 days
  with `threshold_restarts=0` after observation start 1784135451. Browser diagnostics confirmed the
  idle portfolio page can close, but active portfolio polling can reopen it (`page_count=1` during
  idle, later `page_count=2` when `/portfolio` was requested).
- [x] Iteration 14 analyzed the slow real 5m samples. The first 5m BUY sample was 40.779 s
  signal-to-submit. The three real 5m SELL submissions were 43.142 s, 89.120 s, and 102.470 s
  signal-to-submit. The root cause was not webhook intake: the first XRP 5m SELL spent about
  40 s in UI work (event render timeout plus sell-dialog retries), and the next two queued behind
  `_trade_lock`, amplifying end-to-end latency.
- [x] Iteration 14 added a pre-portfolio/pre-UI stale gate for short-cycle 5m/15m BUY and SELL
  signals. `_short_cycle_market_stale_reason()` now supports BUY/SELL and `5m`/`15m` updown slugs;
  `handle_signal()` calls it immediately after quantity/amount calculation, before live portfolio
  scraping, portfolio-risk finalization, record submission, or `_trade_lock`. This prevents late
  short-cycle exits from consuming the single UI lane when they cannot meet the 10-20 s submit target.
- [x] Iteration 14 verification: targeted stale/SELL tests passed (9 tests); full Bridge unittest
  discovery passed 79 tests; `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed;
  `git diff --check` passed. `bridge_performance_report.py` remains `pending`: webhook passes, health
  needs seven days, and real 5m/15m BUY/SELL sample floors are not yet met. The Iteration 14 code is
  not hot-loaded into the live launchd process because no restart was performed in order to preserve
  the current health observation window.
- [x] Iteration 15 improved verifier sample-window visibility without changing runtime behavior.
  `bridge_performance_report.py` now supports `--since-ms` and `--since-health-window`, and reports
  `sample_window.performance_events_total` plus `sample_window.performance_events_evaluated`. Default
  behavior still evaluates all persisted performance events, so historical slow samples remain visible.
- [x] Iteration 15 live check: `bridge_performance_report.py --since-health-window` evaluated 1517
  of 1535 events from `since_ms=1784135451000`; webhook still passed, health remained pending at about
  0.545/7 days, and the same real 5m BUY/SELL slow samples remained in-window. This confirms the new
  window filter does not hide current-window failures.
- [x] Iteration 15 verification: report unit tests passed (5 tests); full Bridge unittest discovery
  passed 80 tests; `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed; `git diff
  --check` passed. No live restart was performed.
- [x] Iteration 16 added future code-load-window evidence. `start.sh` now exports
  `BRIDGE_CODE_SHA` and a deterministic `BRIDGE_CODE_FINGERPRINT` derived from Bridge `*.py` and
  `*.sh` files. `supervisor_health.sh` includes those fields in persisted health events when present.
  This means the next safe/natural restart will record which local Bridge code was actually loaded.
- [x] Iteration 16 extended `bridge_performance_report.py` with `--since-latest-code-fingerprint`.
  When health events contain code fingerprints, the verifier can automatically evaluate performance
  samples from the latest contiguous code-load window. If combined with `--since-health-window`, the
  later of the health window and code-load window is used. Current historical health events do not
  contain fingerprints, so this filter currently leaves all samples in scope, which is expected.
- [x] Iteration 16 verification: report/supervisor tests passed (8 tests); full Bridge unittest
  discovery passed 81 tests; `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed;
  `git diff --check` passed. Live Bridge remained ready/logged_in, queue depth 0, and webhook P95
  stayed below 200 ms. No live restart was performed.
- [x] Iteration 17 reduced short-cycle UI wait budgets for the next code load. `PolymtradeExecutor`
  now treats crypto up/down 5m/15m slugs as short-cycle markets and applies shorter configurable
  waits: `BRIDGE_SHORT_CYCLE_PAGE_READY_TIMEOUT_SECONDS=6`,
  `BRIDGE_SHORT_CYCLE_TARGET_VISIBLE_TIMEOUT_SECONDS=3`, and
  `BRIDGE_SHORT_CYCLE_EVENT_URL_TIMEOUT_SECONDS=2`. Non-short-cycle markets keep the existing 15/8/6
  second defaults.
- [x] Iteration 17 rationale: the slow real 5m submissions were dominated by UI waits before order
  submission. A 5m BUY spent 34.680 s in UI submit, and 5m SELLs spent about 39.502-46.878 s in UI
  submit. The prior generic waits allowed page-ready/event-url checks to consume 15+ seconds before
  the dialog logic even began, which is incompatible with the 6-20 s target for short-cycle markets.
- [x] Iteration 17 verification: navigation wait tests passed (5 tests); full Bridge unittest
  discovery passed 82 tests; `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed;
  `git diff --check` passed. Live verifier remains pending with webhook passing and health at about
  0.548/7 days. No live restart was performed, so this budget change is not hot-loaded yet.
- [x] Iteration 18 reduced short-cycle UI retry budgets for the next code load. Crypto up/down 5m/15m
  BUY attempts now default to 3 via `BRIDGE_SHORT_CYCLE_BUY_ATTEMPTS`; SELL dialog attempts now default
  to 2 via `BRIDGE_SHORT_CYCLE_SELL_DIALOG_ATTEMPTS`. Non-short-cycle markets keep the existing 6 BUY
  attempts and 5 SELL dialog attempts.
- [x] Iteration 18 rationale: shortening page-ready/event-url waits alone still left BUY/Sell loops
  capable of spending many seconds in repeated target-visible checks, re-navigation, and dialog-open
  retries. Short-cycle markets need to fail fast and release the single UI lane when target content or
  the sell dialog is not available quickly enough to meet the submit target.
- [x] Iteration 18 verification: navigation wait tests passed (7 tests); full Bridge unittest
  discovery passed 84 tests; `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed;
  `git diff --check` passed. Live verifier remains pending with webhook passing and health at about
  0.549/7 days. No live restart was performed, so this retry-budget change is not hot-loaded yet.
- [x] Iteration 19 tightened short-cycle dialog and submit-confirmation budgets for the next code load.
  Crypto up/down 5m/15m markets now default to `BRIDGE_SHORT_CYCLE_DIALOG_DETECT_TIMEOUT_SECONDS=1.25`
  and `BRIDGE_SHORT_CYCLE_CONFIRM_TIMEOUT_SECONDS=2`. Non-short-cycle markets keep the previous
  3-second dialog detection and 15-second confirmation window.
- [x] Iteration 19 rationale: after a submit button click, explicit UI confirmation is no longer the
  correctness gate because BUY/SELL verification is asynchronous. Letting a 5m/15m signal spend up to
  15 seconds waiting for a toast or dialog close can consume the whole target budget even after the
  order was already submitted.
- [x] Iteration 19 verification: navigation wait tests passed (8 tests); full Bridge unittest
  discovery passed 85 tests; `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed;
  `git diff --check -- polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_navigation_waits.py`
  passed. No live restart was performed, so this confirmation-budget change is not hot-loaded yet.
- [x] Iteration 20 added executor stage latency metrics for future real-sample diagnosis. BUY and SELL
  now record bucketed 5m/15m/other stage timings for navigation, page-ready, event visibility,
  dialog open/detect, baseline capture, amount entry, submit click, and submit confirmation.
- [x] Iteration 20 rationale: the target verifier intentionally scores only end-to-end submit latency,
  but tuning needs stage evidence when a future sample misses P50/P95. These metrics will show whether
  the next bottleneck is Polymtrade navigation/rendering, carousel/event matching, dialog detection,
  amount input, or post-click confirmation.
- [x] Iteration 20 verification: navigation wait tests passed (8 tests); full Bridge unittest
  discovery passed 85 tests; `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed;
  `git diff --check -- polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_navigation_waits.py
  BRIDGE_PERFORMANCE_LOOP_STATE.md` passed. No live restart was performed, so stage metrics are not
  hot-loaded yet.
- [x] Iteration 21 changed the planned-restart runner so `--execute` drains signal admission before
  waiting for a quiet window when the running Bridge exposes `accepting_signals`. Check-only mode
  remains read-only. This prevents continuous webhook traffic from permanently blocking a controlled
  restart.
- [x] Iteration 21 verification: the old check-only quiet-window path failed under live traffic because
  `signals_received` advanced from 1020 to 1034 during 45 seconds. A new fake-curl/launchctl test
  proves `safe_restart_bridge.sh --execute` requests `/admin/drain` before launchd restart; supervisor
  policy tests passed (3 tests), full Bridge unittest discovery passed 86 tests, shell syntax passed,
  and `git diff --check` passed for the restart runner and test.
- [x] Iteration 21 loaded the pending performance build with
  `BRIDGE_RESTART_DRAIN_TIMEOUT=30 BRIDGE_RESTART_POST_START_TIMEOUT=300 bash ./safe_restart_bridge.sh --execute`.
  The runner drained admission with `queue_depth=0 accepting_signals=False`, restarted launchd, and
  confirmed the new process exposes `accepting_signals=True`.
- [x] Post-load evidence: `/health` returned ok, `/status` was ready/logged_in with `last_error=null`,
  `/metrics` showed `signals_received=5`, `signals_filtered=5`, queue depth 0, four workers,
  `webhook_accept_ms` P50 0.042 ms and P95 0.104 ms, and one browser page. The health event log
  recorded `service_start` at 1784183402 with `code_sha=31fbc08` and
  `code_fingerprint=9ef12cf096f1ea372c6babcf44ff94529cb6f4ca`.
- [x] The post-load verifier
  `bridge_performance_report.py --since-health-window --since-latest-code-fingerprint` evaluated only
  the latest loaded code window (`since_ms=1784183402000`). It is correctly pending with 5 webhook
  samples, zero 5m/15m BUY/SELL submit samples, and no threshold restarts in the health window.
- [x] Iteration 22 captured the first real post-load BUY/SELL evidence. The first 5m BUY submitted in
  8.445 s signal-to-submit and 7.873 s UI-submit, with asynchronous portfolio verification confirming
  15.247 s later. The first 5m SELL submitted in 22.032 s signal-to-submit and 17.402 s UI-submit;
  SELL verification completed asynchronously. This proved the UI submit phase is now within the
  10-20 s target, while end-to-end SELL still had a small overrun.
- [x] Iteration 22 stage evidence identified the remaining SELL overrun: `sell_5m_dialog_detect_ms`
  was 2.993 s even though the short-cycle dialog-detect budget was 1.25 s, because the implementation
  waited up to 500 ms for each selector sequentially instead of enforcing the overall deadline. SELL
  also spent 2.209 s in submit confirmation under the previous loaded confirmation budget.
- [x] Iteration 22 fixed those recurrence causes for the next code window: short-cycle submit
  confirmation now defaults to 1.25 s, `_confirm_trade()` no longer sleeps past its deadline, and
  BUY/SELL dialog detection now bounds each selector wait by the remaining overall deadline.
- [x] Iteration 22 verification: navigation wait tests passed (9 tests), full Bridge unittest discovery
  passed 87 tests, `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed, and
  `git diff --check` passed for the executor/test changes.
- [x] Iteration 22 loaded the dialog-deadline/confirmation-budget fix with
  `BRIDGE_RESTART_DRAIN_TIMEOUT=30 BRIDGE_RESTART_POST_START_TIMEOUT=300 bash ./safe_restart_bridge.sh --execute`.
  The runner drained admission with `queue_depth=0 accepting_signals=False`, restarted launchd, and
  confirmed `accepting_signals=True`.
- [x] Post-load evidence after Iteration 22: `/health` returned ok, `/status` was ready/logged_in with
  `last_error=null`, `/metrics` showed queue depth 0, one browser page, and the health event log
  recorded `service_start` at 1784183685 with
  `code_fingerprint=e4205cc9238293f3e2f9f1b5d2dd517ff4908fda`. The latest-code verifier now starts at
  `since_ms=1784183685000` and is correctly pending with only two webhook samples and zero 5m/15m
  BUY/SELL submit samples in this newest code window.
- [x] Iteration 23 added `sample_window.metric_counts` to `bridge_performance_report.py`. This does
  not change pass/fail/pending logic; it makes each latest-code verifier run show whether the current
  window contains only webhook/queue events or actual BUY/SELL stage/submit samples.
- [x] Iteration 23 evidence before changing worker count: latest-code window since 1784183685000 had
  no submit/stage samples, only `webhook_accept_ms` and `signal_queue_wait_ms`. Under a 5m burst,
  `signal_queue_wait_ms` reached P95 about 1.3 s and max about 1.6 s while the queue depth eventually
  returned to 0.
- [x] Iteration 23 increased the default `SIGNAL_WORKER_COUNT` from 4 to 8 so bursts spend less time
  waiting for a filter worker. UI submission remains protected by `_trade_lock`, so this only widens
  the pre-trade filtering/recording lane.
- [x] Iteration 23 verification: report tests passed (7 tests), signal queue tests passed (5 tests),
  full Bridge unittest discovery passed 88 tests, shell syntax passed, and `git diff --check` passed.
- [x] Iteration 23 loaded the 8-worker build through
  `BRIDGE_RESTART_DRAIN_TIMEOUT=30 BRIDGE_RESTART_POST_START_TIMEOUT=300 bash ./safe_restart_bridge.sh --execute`.
  The runner drained admission with `queue_depth=0 accepting_signals=False`, restarted launchd, and
  confirmed `accepting_signals=True`.
- [x] Post-load evidence after Iteration 23: `/health` returned ok, `/status` was ready/logged_in with
  `last_error=null`, `/metrics` showed `signal_worker_count=8`, queue depth 0, one browser page,
  webhook P50 0.118 ms and P95 0.146 ms over the first 4 latest-code samples, and signal queue wait
  P95 0.795 ms over those first 4 samples. The health event log recorded `service_start` at
  1784183901 with `code_fingerprint=b4eeb91fe7d34e21efe09c90f3d6284089a7d1e5`. The latest-code
  verifier now starts at `since_ms=1784183901000` and is correctly pending with no 5m/15m submit
  samples yet.
- [x] Iteration 24 live observation: latest-code window `since_ms=1784183901000` still had no BUY/SELL
  submit or stage samples. The verifier's `metric_counts` showed only `webhook_accept_ms` and
  `signal_queue_wait_ms`. Over the first 8 samples after the 8-worker load, webhook P95 was about
  0.679 ms and signal queue wait max was about 2.965 ms. This confirms the prior second-level queue
  wait burst did not recur in the first post-load sample, but there is still no new trade-submit
  evidence to score BUY/SELL latency.
- [x] Iteration 25 live observation: the first 5m BUY after the 8-worker load confirmed successfully,
  but it was a bad latency and price-quality sample: `buy_5m_signal_to_submit_ms=33754.568`,
  `buy_5m_ui_submit_ms=30566.479`, and `buy_5m_quote_drift=0.1225` from signal price 0.5175 to
  submitted quote 0.64. The expensive stages were `page_ready=5561.757 ms`, `select_outcome=2588.825 ms`,
  `dialog_detect=2775.759 ms`, `enter_amount=4568.556 ms`, and `click_submit=7234.155 ms`.
- [x] Iteration 25 fixed the recurrence cause for late bad BUYs by passing signal price and the
  last-mile drift threshold into the executor. `_execute_buy_on_page()` now blocks a BUY immediately
  after selecting an outcome if the quoted page price exceeds signal price by more than the configured
  drift limit, before baseline capture, amount entry, or submit click.
- [x] Iteration 25 also records enforced pre-submit drift blocks in metrics with
  `buy_<window>_quote_drift`, `guard_mode=ENFORCED`, `last_mile_quote_observations`, and
  `last_mile_price_drift_would_block`, so future reports can separate fast failure from missing
  evidence.
- [x] Iteration 25 verification: navigation wait tests passed (10 tests), full Bridge unittest
  discovery passed 89 tests, `bash -n safe_restart_bridge.sh start.sh supervisor_health.sh` passed,
  and `git diff --check` passed for `main.py`, `polymtrade_executor.py`, and
  `test_navigation_waits.py`.
- [x] Iteration 25 loaded the final pre-submit drift guard build through
  `BRIDGE_RESTART_DRAIN_TIMEOUT=30 BRIDGE_RESTART_POST_START_TIMEOUT=300 bash ./safe_restart_bridge.sh --execute`.
  The runner drained admission with `queue_depth=0 accepting_signals=False`, restarted launchd, and
  confirmed `accepting_signals=True`.
- [x] Post-load evidence after Iteration 25: `/health` returned ok, `/status` was ready/logged_in with
  `last_error=null`, `/metrics` showed `signal_worker_count=8`, queue depth 0, webhook P50 0.175 ms
  and P95 6.582 ms over the first 8 latest-code samples, and signal queue wait P95 13.71 ms. The
  health event log recorded `service_start` at 1784184458 with
  `code_fingerprint=d55828650730233e314e86178f7855eea6d383ef`. The latest-code verifier now starts
  at `since_ms=1784184458000` and is correctly pending with no 5m/15m BUY/SELL submit samples yet.
- [x] Iteration 26 live observation: the latest-code window produced a good 5m BUY submit sample:
  `buy_5m_signal_to_submit_ms=9098.646`, `buy_5m_ui_submit_ms=8062.543`, and
  `buy_5m_quote_drift=0.002564`. Stage timings were within the intended shape:
  `page_ready=1610.48 ms`, `select_outcome=910.143 ms`, `enter_amount=919.214 ms`,
  `click_submit=66.218 ms`, and `submit_confirm=1251.014 ms`.
- [x] Iteration 26 added optional DB context to `bridge_performance_report.py` via
  `--include-db-records`. The verifier now can explain pending sample windows by summarizing
  `bridge_trade_record` statuses, market windows, and failure reasons without changing pass/fail logic.
  In the current window, the report showed one 5m BUY SUCCESS plus filtered failures dominated by
  `keyword whitelist not matched`, `price > max_price`, and `Insufficient position, skipped`.
- [x] Iteration 26 identified a BUY verification false-negative source. The successful XRP 5m BUY
  was marked `SUCCESS` but async verification was unconfirmed because the event-page baseline had
  captured `1.82 shares` before submit. Live portfolio later showed the same `1.82` quantity, meaning
  the baseline parser had likely treated a BUY dialog shares preview as existing position.
- [x] Iteration 26 tightened `_get_event_page_position_quantity()` so the broad
  `<outcome> - <shares>` fallback only applies inside holding/portfolio/position contexts. This
  preserves real holding-row parsing while ignoring BUY dialog preview rows such as
  `Up - 1.82 shares`.
- [x] Iteration 26 verification: `test_buy_verification.py` passed, report/navigation tests passed
  (19 tests), full Bridge unittest discovery passed 91 tests, shell syntax passed, and
  `git diff --check` passed for the changed Bridge files.
- [x] Iteration 26 loaded the executor/report build with a guarded restart. The first
  `safe_restart_bridge.sh --execute` post-start metrics probe hit the service before port 8080 was
  ready and exited with curl code 7, but launchd was running and `/health` recovered immediately.
  This was an operator-tool false negative, not a service failure or threshold restart. Health events
  recorded `service_start` at 1784184914 with
  `code_fingerprint=4560a94c80f385cdf70dbdc9bccee03a96624e67`.
- [x] Post-load evidence after Iteration 26: `/health` returned ok, `/status` was ready/logged_in with
  `last_error=null`, `/metrics` showed `signal_worker_count=8`, queue depth 0, one browser page,
  webhook P50 0.081 ms and P95 0.212 ms over the first 8 latest-code samples, and signal queue wait
  P95 1.018 ms. The latest-code verifier now starts at `since_ms=1784184914000`; it is pending with
  no submit samples yet, and `--include-db-records` explained the window as protective filters:
  seven `keyword whitelist not matched` SELLs and one BUY above max price.
- [x] Iteration 26 hardened `safe_restart_bridge.sh` after the observed false negative. The post-start
  loop now treats a transient `/metrics` curl failure as "not ready yet" and continues polling instead
  of exiting under `set -e`. `test_supervisor_health_policy.py` now covers this exact case.
- [x] Iteration 26 final verification after the restart-runner fix: supervisor policy tests passed
  (4 tests), full Bridge unittest discovery passed 92 tests, shell syntax passed, and
  `git diff --check` passed for all changed Bridge files.
- [x] Iteration 27 live observation: the post-Iteration-26 window produced another 5m BUY SUCCESS
  with confirmed async verification, so the dialog-preview baseline fix worked. The sample was still
  too slow for the end-to-end BUY target: `buy_5m_signal_to_submit_ms=21542.9`,
  `buy_5m_ui_submit_ms=16534.837`, and `buy_5m_quote_drift=-0.037436`.
- [x] Iteration 27 root cause for the slow pre-UI portion: logs for transaction
  `0x7906a031328540f964c6bdbbd182ecc2924e96c5fbd187043aed2d4bc263dade` showed both
  portfolio-risk precheck and final checks hit `ReadTimeout` in SHADOW mode. Each fail-open risk
  timeout consumed about 2 seconds before UI work started.
- [x] Iteration 27 added per-call timeout support to `PortfolioRiskClient.evaluate_buy()` and changed
  short-cycle 5m/15m BUY risk checks to use `SHORT_CYCLE_PORTFOLIO_RISK_TIMEOUT_SECONDS` in non-ENFORCED
  modes. Default is 0.75 seconds. ENFORCED mode keeps the normal risk timeout to preserve fail-closed
  behavior.
- [x] Iteration 27 also records portfolio-risk latency metrics:
  `portfolio_risk_<stage>_<window>_ms` with labels for transaction hash, enforcement mode, and
  availability. This makes future pre-UI latency regressions visible in the verifier metrics window.
- [x] Iteration 27 verification before load: portfolio-risk client/proportional-risk tests passed
  (15 tests), full Bridge unittest discovery passed 94 tests, and `git diff --check` passed for the
  changed risk-timeout files.
- [x] Iteration 27 loaded the short-cycle risk-timeout build with
  `BRIDGE_RESTART_DRAIN_TIMEOUT=30 BRIDGE_RESTART_POST_START_TIMEOUT=300 bash ./safe_restart_bridge.sh --execute`.
  The runner drained admission with `queue_depth=0 accepting_signals=False`, waited through a slow
  browser profile startup, and confirmed `accepting_signals=True` without the prior false-negative
  `/metrics` exit. Health events recorded `service_start` at 1784185239 with
  `code_fingerprint=dc719df8ddc827c2224ee005e02c55db63d4d622`.
- [x] Post-load evidence after Iteration 27: `/health` returned ok, `/status` was ready/logged_in with
  `last_error=null`, `/metrics` showed `signal_worker_count=8`, queue depth 0, one browser page,
  webhook P50 0.073 ms and P95 0.701 ms over the first 27 latest-code samples, and signal queue wait
  P95 376.723 ms. The latest-code verifier now starts at `since_ms=1784185239000`; it is pending
  with no submit samples yet, and `--include-db-records` explained the window as protective filters:
  23 SELL failures and 4 BUY failures, mostly keyword whitelist and max-price guards.
- [x] Iteration 28 investigated why the Bridge browser showed `https://docs.polym.trade/`.
  Code, launchd env, and startup logs point to `https://polym.trade`; `docs.polym.trade` appeared only
  as a browser diagnostics `role=other` tab inside the persistent Playwright profile. It is not the
  default trading page or portfolio page.
- [x] Iteration 28 added a narrow `close_known_unmanaged_pages()` guard that only closes
  `docs.polym.trade` tabs and preserves the default page, portfolio page, and any `polym.trade`
  trade/event pages. `/metrics` now invokes this cleanup before returning browser diagnostics.
- [x] Iteration 28 verification: `test_browser_diagnostics.py` passed 4 tests, including coverage
  that the docs tab closes while a `polym.trade/event/...` page remains open.
- [x] Iteration 28 load was deferred by the safe restart guard: `safe_restart_bridge.sh` observed
  signals arriving during the quiet window (`before=151 after=161`) and exited without restarting.
  Live `/metrics` still shows the old-process docs tab until a later safe restart loads the cleanup.
- [x] Iteration 29 live observation: a new 5m BUY SUCCESS
  (`0xe82d7fcdef183701142730838308e54ec43813ba49ed1e4efa09917c5f0e1280`) exposed a larger
  pre-navigation latency. The sample had `buy_5m_signal_to_submit_ms=36456.669` and
  `buy_5m_ui_submit_ms=34226.001`. Logs showed portfolio-risk final completed at `15:18:50.980`,
  but navigation did not start until `15:19:08.808`, so about 17.8 seconds were spent before UI
  navigation, primarily in event resolution.
- [x] Iteration 29 removed the short-cycle event-resolution network dependency. For `*-5m-*` and
  `*-15m-*` slugs, `_resolve_event_uncached()` now directly returns the market slug as the Polymtrade
  event slug without calling Gamma/CLOB. BUY and SELL now navigate with the `eventSlug` URL when
  `eventId` is empty, and SELL skips eventId URL waits in that mode.
- [x] Iteration 29 added `event_resolve_<window>_ms` metrics around `_resolve_event()` so the next
  5m/15m BUY/SELL submit sample can prove whether the former ~17.8 second gap has collapsed.
- [x] Iteration 29 verification: targeted pytest for metadata/navigation/sell async passed 17 tests,
  full Bridge unittest discovery passed 97 tests, and `git diff --check` passed for the changed
  executor/navigation files.
- [x] Iteration 30 live observation after loading the Iteration 29 shortcut: Bridge is healthy and
  logged in, with queue depth 0 and no pending DB records. The latest-code report window starts at
  `since_ms=1784187042000` from health event `service_start=1784187042` and
  `code_fingerprint=65af547538e23552f85937138663ceb62585ec3b`.
- [x] Iteration 30 did not get a real BUY/SELL submit sample to verify the event-resolution shortcut.
  The latest-code report evaluated 94 records and all were filtered before execution:
  55 SELL failures and 39 BUY failures. The dominant reasons were `keyword whitelist not matched`
  and `price > max_price 0.55000000`, matching active config 13 (`BTC 5mins-only XRP`, whitelist
  `["XRP"]`, `max_price=0.55`). Live metrics later showed 95 received / 95 filtered / 0 executed.
- [x] Iteration 30 webhook intake passed the latest-code verifier after the sample count reached
  105: webhook accept P50 `0.083 ms`, P95 `2.904 ms`, max `15.373 ms`, with no queue rejection.
  Signal queue P95 was about 31 ms. The overall report remains pending because BUY/SELL submit
  counts are still zero and the health-stability observation is only about 0.6 days into the
  required seven-day window.
- [x] Iteration 31 investigated a misleading live metric: after an XRP SELL was skipped by the
  local position ledger (`Insufficient position, skipped`), `/metrics` showed
  `signals_executed=1` and `trades_sell_total=1` even though no Polymtrade UI submit happened.
  This came from incrementing execution counters immediately after config match, before pre-submit
  guards such as stale-window, portfolio risk, and position checks.
- [x] Iteration 31 corrected the metric semantics. `signals_executed` and `trades_buy_total` /
  `trades_sell_total` now increment only immediately before the real `executor.execute_trade()`
  call, so pre-submit skips no longer look like submit attempts in runtime metrics.
- [x] Iteration 31 added regression coverage for the observed insufficient-position SELL path:
  matched non-proportional SELL with insufficient ledger position records a visible FAILED skip,
  does not call the executor, and leaves `signals_executed` / `trades_sell_total` at zero.
- [x] Iteration 31 verification: targeted pytest for proportional-risk, signal-queue, and metrics
  passed 18 tests; full Bridge unittest discovery passed 98 tests; `git diff --check` passed for
  the changed Bridge files.
- [x] Iteration 31 loaded the metric-semantics fix through `safe_restart_bridge.sh --execute`.
  The restart drained admission with queue depth 0 and recovered with `accepting_signals=True`.
  Health events recorded `service_start=1784187434` with
  `code_fingerprint=88597cad75bf5712b20127160dd609adbf7a7b76`.
- [x] Post-load evidence after Iteration 31: `/status` is ready/logged_in with `last_error=null`,
  `/metrics` shows 11 received / 11 filtered / 0 executed, queue depth 0, and no DB pending rows.
  The latest-code report starts at `since_ms=1784187434000`; it is pending with 11 webhook samples
  (P95 `4.181 ms`) and no BUY/SELL submit samples yet. All 11 latest-code DB records were filtered
  by max-price or whitelist guards before execution.
- [x] Iteration 32 live observation: the latest loaded code remains healthy and logged in with
  queue depth 0 and no pending DB rows. Runtime metrics showed 20 received / 20 filtered /
  0 executed, confirming the Iteration 31 metric semantics fix is active under live traffic.
- [x] Iteration 32 report evidence: latest-code report window remains
  `since_ms=1784187434000` and is pending because there are still no 5m/15m BUY or SELL submit
  latency events. Webhook remains comfortably below target in the partial sample
  (20 samples, P50 `0.191 ms`, P95 `4.009 ms`, max `6.0 ms`), but the verifier requires 100
  latest-code webhook samples before marking it pass again after the Iteration 31 restart.
- [x] Iteration 32 DB evidence: all latest-code records were pre-submit failures, currently
  19 SELL failures and 1 BUY failure since the latest code load. The visible reasons were
  max-price and whitelist guards, with zero SUCCESS/SUBMITTED samples and zero PENDING records.
  No code change was made because the report already exposes both the missing submit latency
  metrics and the DB reasons for the absence of samples.
- [x] Iteration 33 found a page-role drift that could add avoidable latency to the next real trade:
  `/account` wallet extraction still navigated the default execution page to `/portfolio`, so runtime
  browser diagnostics could show both the default and portfolio roles sitting on portfolio pages.
- [x] Iteration 33 moved `get_wallet_address()` into the existing portfolio-page scope. Wallet
  extraction now reuses/creates the dedicated portfolio page, keeps the default execution page on
  the trade entry URL, updates the wallet cache exactly as before, and schedules the existing
  portfolio idle-close path.
- [x] Iteration 33 added regression coverage that `get_wallet_address()` extracts the wallet from
  the portfolio page without changing `executor.page` away from the default page.
- [x] Iteration 33 verification before load: browser diagnostics/page-scope/portfolio-scroll pytest
  passed 7 tests; full Bridge unittest discovery passed 99 tests; `git diff --check` passed for the
  changed executor and browser diagnostic test files.
- [x] Iteration 33 loaded the page-role fix through `safe_restart_bridge.sh --execute`. The restart
  drained admission at queue depth 0 and recovered with `accepting_signals=True`. Health events
  recorded `service_start=1784187686` and
  `code_fingerprint=8574d435892613cbb2d56f2c9e404191ad41ffa0`.
- [x] Post-load evidence after Iteration 33: `/status` is ready/logged_in with `last_error=null`.
  Calling `/account` returned the wallet address and left `/metrics.browser` with the default page at
  `https://polym.trade/` and the portfolio page isolated at `https://polym.trade/portfolio`. Latest
  runtime metrics showed 26 received / 26 filtered / 0 executed, queue depth 0. Latest-code report
  starts at `since_ms=1784187686000`; it is pending with 26 webhook samples
  (P50 `0.145 ms`, P95 `31.228 ms`, max `103.449 ms`) and no BUY/SELL submit samples. DB evidence
  showed 17 SELL and 9 BUY pre-submit failures, all from max-price or whitelist guards.
- [x] Iteration 34 optimized the BUY amount-entry hot path. `_fill_input_safely()` now first fills
  native `input`/`textarea` controls in one browser-side operation using the native value setter and
  `input`/`change` events, then falls back to the existing Playwright click/fill/type ladder for
  contenteditable, custom spinbutton, and unusual controls. This targets the latest real 5m BUY
  sample where `buy_5m_enter_amount_ms` was `3358.199 ms`.
- [x] Iteration 34 verification: selector fixture passed and now asserts the fast native path emits
  both `input` and `change` events; navigation/browser/proportional-risk targeted unittest group
  passed 28 tests; full Bridge unittest discovery passed 99 tests.
- [x] Iteration 34 loaded the amount-entry optimization through `safe_restart_bridge.sh --execute`.
  The runner drained admission with queue depth 0 and recovered with `accepting_signals=True`.
  Post-load `/status` is ready/logged_in with `last_error=null`, default page remains
  `https://polym.trade/`, portfolio page remains isolated, and the latest-code report starts at
  `since_ms=1784188287000`.
- [x] Post-load evidence after Iteration 34: the latest-code verifier is still `pending` because no
  new BUY/SELL submit sample has arrived. The first 30 latest-code webhook samples are clean
  (P50 `0.065 ms`, P95 `0.183 ms`, max `0.222 ms`) and all 30 DB records were protective
  pre-submit filters: 22 SELL failures and 8 BUY failures, mainly `keyword whitelist not matched`
  and `price > max_price 0.55000000`.
- [x] Iteration 35 tightened the short-cycle portfolio-risk budget for non-ENFORCED modes. The
  default `SHORT_CYCLE_PORTFOLIO_RISK_TIMEOUT_SECONDS` changed from `0.75` to `0.35` seconds, while
  ENFORCED mode still keeps the normal default timeout. This targets the real 5m BUY sample where
  two unavailable SHADOW portfolio-risk calls consumed about 1.8 seconds before UI work.
- [x] Iteration 35 verification: portfolio-risk/proportional-risk tests passed 16 tests, including
  an assertion that short-cycle SHADOW risk now receives `timeout_seconds=0.35`; full Bridge unittest
  discovery passed 99 tests.
- [x] Iteration 35 loaded the risk-timeout budget through `safe_restart_bridge.sh --execute`. The
  runner drained admission with queue depth 0 and recovered with `accepting_signals=True`. Health
  events recorded `service_start=1784188422` with
  `code_fingerprint=60f5f145a5bd062199076c7f1e81af7ae06ff5ba`.
- [x] Post-load evidence after Iteration 35: `/health` is ok, `/status` is ready/logged_in with
  `last_error=null`, queue depth is 0, and the latest-code report starts at
  `since_ms=1784188422000`. The first 18 latest-code webhook samples are clean
  (P50 `0.157 ms`, P95 `7.58 ms`, max `34.614 ms`), and all 18 DB records were pre-submit SELL
  filters from whitelist/max-price guards, so no new BUY/SELL submit sample has yet exercised the
  tighter risk timeout.
- [x] Iteration 36 reduced portfolio-risk client overhead. `PortfolioRiskClient` now lazily reuses
  an owned `httpx.AsyncClient` with a small keepalive pool instead of creating a new client for each
  risk `evaluate` or `complete` call; externally injected clients are still not owned or closed.
  Bridge shutdown now calls `portfolio_risk_client.aclose()` after verification tasks and executor
  shutdown.
- [x] Iteration 36 verification: portfolio-risk/proportional-risk tests passed 18 tests, including
  owned-client reuse and injected-client close ownership; full Bridge unittest discovery passed
  101 tests.
- [x] Iteration 36 loaded the risk-client reuse build through `safe_restart_bridge.sh --execute`.
  The runner drained admission with queue depth 0 and recovered with `accepting_signals=True`.
  Health events recorded `service_start=1784188610` with
  `code_fingerprint=1af13861ab83adb7f198e63c76c919b7480463dd`.
- [x] Post-load evidence after Iteration 36: `/health` is ok, `/status` is ready/logged_in with
  `last_error=null`, queue depth is 0, and the latest-code report starts at
  `since_ms=1784188610000`. The first 13 latest-code webhook samples are clean
  (P50 `0.481 ms`, P95 `2.499 ms`, max `2.663 ms`), and all 13 DB records were protective
  pre-submit filters from whitelist/max-price guards. No new BUY/SELL submit sample has yet
  exercised the reused risk client.
- [x] Iteration 37 optimized binary Up/Down outcome selection for short-cycle markets.
  `_select_outcome_script()` now tries a `binary-fast` path before categorical row anchoring,
  matching only short Up/Down button labels with a single price and rejecting parent containers
  that include both sides. `_select_polymtrade_outcome()` also skips the first scroll/lazy-row
  discovery pass and the second Playwright text-confirmation wait for recognized binary up/down
  markets. This targets the real 5m BUY sample where `buy_5m_select_outcome_ms` was `2051.758 ms`.
- [x] Iteration 37 verification: selector fixture passed and now asserts BTC 5m Up/Down uses
  `strategy=binary-fast` while avoiding the `Up Or Down` container; full Bridge unittest discovery
  passed 101 tests.
- [x] Iteration 37 loaded the binary selector fast path through `safe_restart_bridge.sh --execute`.
  The runner drained admission with queue depth 0 and recovered with `accepting_signals=True`.
  Health events recorded `service_start=1784188897` with
  `code_fingerprint=fcb89fc8aeae5a39296a9c2cc07855276e2277fa`.
- [x] Post-load evidence after Iteration 37: `/health` is ok, `/status` is ready/logged_in with
  `last_error=null`, queue depth is 0, and the latest-code report starts at
  `since_ms=1784188897000`. The first 34 latest-code webhook samples are clean
  (P50 `0.092 ms`, P95 `2.562 ms`, max `27.072 ms`), browser diagnostics show the idle portfolio
  page closed (`page_count=1`), and all 34 DB records were protective pre-submit filters. No new
  BUY/SELL submit sample has yet exercised the binary selector fast path.
- [x] Iteration 38 optimized short-cycle page-ready detection for binary Up/Down markets.
  `_wait_for_page_ready()` now accepts `market_slug` and `outcome`, and for recognized binary
  up/down markets it directly treats a visible matching Up/Down trade button as ready. It rejects
  parent containers such as `Up Or Down` that include both sides. BUY and SELL now pass the current
  market slug and outcome into page-ready. This targets the real 5m BUY sample where
  `buy_5m_page_ready_ms` was `2708.203 ms`.
- [x] Iteration 38 verification: event-visibility fixture passed, including binary page-ready
  coverage that succeeds on real Up/Down trade buttons and fails on the `Up Or Down` container;
  navigation/browser diagnostics unittest group passed 17 tests; full Bridge unittest discovery
  passed 101 tests.
- [x] Iteration 38 loaded the page-ready binary fast check through `safe_restart_bridge.sh --execute`.
  The runner drained admission with queue depth 0 and recovered with `accepting_signals=True`.
  Health events recorded `service_start=1784189185` with
  `code_fingerprint=2a44de6593ed7f8f6dd8ddb923d1f25a5fcc348d`.
- [x] Post-load evidence after Iteration 38: `/health` is ok, `/status` is ready/logged_in with
  `last_error=null`, queue depth is 0, and the latest-code report starts at
  `since_ms=1784189185000`. After transient startup PENDING rows settled, latest-code DB records
  were 65/65 protective pre-submit failures. Webhook remains clean in the partial sample
  (P50 `0.113 ms`, P95 `7.018 ms`, max `67.749 ms`), but the latest-code webhook count is still
  below the verifier's 100-sample pass floor and no BUY/SELL submit sample has yet exercised the
  page-ready fast check.
- [x] Iteration 39 shortened short-cycle navigation waits. Crypto up/down 5m/15m BUY and SELL now
  call `_goto_with_retry(..., wait_until="commit")`, while non-short-cycle markets keep the default
  `domcontentloaded` wait. Page readiness is still checked immediately after navigation by the
  existing `_wait_for_page_ready()` guard. This targets the prior real 5m BUY sample where
  `buy_5m_navigate_ms` was `1399.959 ms`.
- [x] Iteration 39 verification: navigation/browser diagnostics unittest group passed 17 tests;
  full Bridge unittest discovery passed 101 tests; `git diff --check` passed for the changed executor
  and navigation tests.
- [x] Iteration 39 loaded the short-cycle navigation wait change through `safe_restart_bridge.sh
  --execute`. The runner drained admission with queue depth 0 and recovered with
  `accepting_signals=True`. Health events recorded `service_start=1784189590`; post-load `/health`
  is ok, `/status` is ready/logged_in with `last_error=null`, and queue depth is 0.
- [x] Post-load evidence after Iteration 39: the latest-code report starts at
  `since_ms=1784189590000` and is pending because the new code window initially had zero webhook or
  submit samples. This reset the latest-code sample floor as expected after the safe restart; it does
  not prove or disprove the navigation improvement until the next non-filtered 5m/15m submit sample.
- [x] Iteration 40 shortened the short-cycle submit-button search budget. Crypto up/down 5m/15m
  BUY and SELL now use `BRIDGE_SHORT_CYCLE_SUBMIT_BUTTON_TIMEOUT_SECONDS=2` by default when clicking
  the final submit button, while non-short-cycle markets keep the existing 10-second button search.
  BUY re-navigation retries also keep the short-cycle `commit` navigation wait instead of falling
  back to the default. This targets historical `buy_5m_click_submit_ms` outliers where the submit
  button search reached about `7234.155 ms`.
- [x] Iteration 40 verification: navigation/browser diagnostics unittest group passed 17 tests;
  full Bridge unittest discovery passed 101 tests; `git diff --check` passed for the changed executor
  and navigation tests.
- [x] Iteration 40 loaded the submit-button timeout change through `safe_restart_bridge.sh --execute`.
  The runner drained admission with queue depth 0 and recovered with `accepting_signals=True`.
  Health events recorded `service_start=1784189819` with
  `code_fingerprint=96de076914db94d132b8480e3c0f9d8ffeab037d`; post-load `/health` is ok,
  `/status` is ready/logged_in with `last_error=null`, queue depth is 0, and the default browser
  page remains on `https://polym.trade/`.
- [x] Post-load evidence after Iteration 40: the latest-code report starts at
  `since_ms=1784189819000`. The first 46 webhook samples are clean (P50 `0.111 ms`,
  P95 `3.386 ms`, max `73.78 ms`), but the count is still below the 100-sample pass floor.
  All 46 latest-code DB records were protective pre-submit failures from whitelist/max-price guards,
  so there are still no new BUY/SELL submit samples to exercise the shortened submit-button budget.
- [x] Iteration 41 waited for real latest-code evidence before changing code. The Iteration 40 window
  reached the webhook sample floor: 164 webhook samples passed with P50 `0.103 ms`, P95 `1.885 ms`,
  max `73.78 ms`. Three real 5m BUYs entered the UI path but were blocked before submit by
  last-mile quote drift. Stage evidence showed the earlier optimizations working: `buy_5m_navigate_ms`
  P50 `316.602 ms`, `buy_5m_select_outcome_ms` P50 `194.717 ms`, and target-visible P50
  `90.663 ms`. `buy_5m_page_ready_ms` remained around P50 `2370.212 ms`.
- [x] Iteration 41 shortened fixed short-cycle settle waits after outcome selection and retry
  navigation. Crypto up/down 5m/15m BUY now uses `BRIDGE_SHORT_CYCLE_POST_OUTCOME_SETTLE_SECONDS=0.15`,
  `BRIDGE_SHORT_CYCLE_RETRY_NAVIGATION_SETTLE_SECONDS=0.25`, and
  `BRIDGE_SHORT_CYCLE_PORTFOLIO_ROW_SETTLE_SECONDS=0.35`. Non-short-cycle markets keep the original
  0.8/1.0/1.5 second waits. This targets the next submit-eligible BUY path after outcome click;
  the three latest drift-blocked BUYs did not reach this sleep because drift protection fired first.
- [x] Iteration 41 verification: navigation/browser diagnostics unittest group passed 18 tests;
  full Bridge unittest discovery passed 102 tests; `git diff --check` passed for the changed executor
  and navigation tests.
- [x] Iteration 41 loaded the settle-wait change through `safe_restart_bridge.sh --execute`. The
  runner drained admission with queue depth 0 and recovered with `accepting_signals=True`. Health
  events recorded `service_start=1784190182` with
  `code_fingerprint=8fc3d88142c6b71a4961747d28bdf8ec692b38bc`; post-load `/health` is ok,
  `/status` is ready/logged_in with `last_error=null`, queue depth is 0, and the latest-code report
  starts at `since_ms=1784190182000`.
- [x] Post-load evidence after Iteration 41: the first 13 latest-code webhook samples were clean
  (P50 `0.091 ms`, P95 `0.387 ms`, max `0.623 ms`) but below the 100-sample pass floor. All 13
  DB records were protective pre-submit SELL filters. The single `buy_verification_ms` metric in
  this fresh window is an async tail from the previous code window, not a new submit sample.
- [x] Iteration 42 shortened short-cycle page-ready polling. `_wait_for_page_ready()` now uses
  `BRIDGE_SHORT_CYCLE_PAGE_READY_POLL_SECONDS=0.15` for crypto up/down 5m/15m markets while
  non-short-cycle markets keep the previous 0.5-second polling interval. This does not change the
  ready predicate; it only checks the existing predicate more frequently. It targets the latest real
  UI samples where `buy_5m_page_ready_ms` remained around P50 `2370.212 ms` after navigation and
  outcome selection were already reduced.
- [x] Iteration 42 verification: navigation/browser diagnostics unittest group passed 18 tests;
  `test_event_visibility.py` passed with real Playwright DOM fixtures; full Bridge unittest discovery
  passed 102 tests; `git diff --check` passed for the changed executor and navigation tests.
- [x] Iteration 42 loaded the page-ready poll interval through `safe_restart_bridge.sh --execute`.
  The runner drained admission with queue depth 0 and recovered with `accepting_signals=True`. Health
  events recorded `service_start=1784190444` with
  `code_fingerprint=1a95eec8e82715a03de89532c59c1e1bbbbb129b`; post-load `/health` is ok,
  `/status` is ready/logged_in with `last_error=null`, queue depth is 0, and the default browser
  page remains on `https://polym.trade/`.
- [x] Post-load evidence after Iteration 42: the first 9 latest-code webhook samples were clean
  (P50 `0.4 ms`, P95 `31.207 ms`, max `49.683 ms`) but below the 100-sample pass floor. All 9 DB
  records were protective pre-submit SELL filters, so no BUY/SELL submit or page-ready sample has yet
  exercised the faster poll interval.
- [x] Iteration 43 shortened the initial BUY page-ready budget for short-cycle markets. Crypto
  up/down 5m/15m BUY now uses `BRIDGE_SHORT_CYCLE_BUY_PAGE_READY_TIMEOUT_SECONDS=0.6`, while SELL
  keeps `BRIDGE_SHORT_CYCLE_PAGE_READY_TIMEOUT_SECONDS=6` and non-short-cycle BUY keeps 15 seconds.
  BUY still performs the stronger target-market/outcome visibility check immediately afterward with
  the existing short-cycle retry/re-navigation loop, so this reduces time spent in the weaker generic
  ready probe without removing content verification.
- [x] Iteration 43 verification: navigation/browser diagnostics unittest group passed 18 tests;
  `test_event_visibility.py` passed with real Playwright DOM fixtures; full Bridge unittest discovery
  passed 102 tests; `git diff --check` passed for the changed executor and navigation tests.
- [x] Iteration 43 loaded the BUY page-ready timeout through `safe_restart_bridge.sh --execute`.
  The runner drained admission with queue depth 0 and recovered with `accepting_signals=True`.
  Health events recorded `service_start=1784190639` with
  `code_fingerprint=e79b6a4b46f9459317dd2398bec98c6723fcb683`; post-load `/health` is ok,
  `/status` is ready/logged_in with `last_error=null`, queue depth is 0, and the latest-code report
  starts at `since_ms=1784190639000`.
- [x] Post-load evidence after Iteration 43: the first 34 latest-code webhook samples were clean
  (P50 `0.121 ms`, P95 `1.301 ms`, max `11.58 ms`) but below the 100-sample pass floor. All latest
  DB records were protective pre-submit filters, so no new BUY/SELL submit or page-ready sample has
  yet exercised the shorter BUY page-ready timeout.
- [x] Iteration 44 was evidence-only: no code change. The Iteration 43 latest-code window reached
  the webhook sample floor with 119 samples and passed comfortably: P50 `0.078 ms`, P95 `0.742 ms`,
  max `11.58 ms`. Runtime `/metrics` stayed healthy with `accepting_signals=true`, queue depth 0,
  default page on `https://polym.trade/`, and no `last_error`.
- [x] Iteration 44 DB evidence: there were zero `PENDING` bridge records. Latest-code records were
  all protective pre-submit filters, split across 5m/15m BUY/SELL, mostly `keyword whitelist not
  matched` and `price > max_price 0.55000000`. There were still no latest-code BUY/SELL submit or
  page-ready samples to validate the Iteration 43 BUY page-ready timeout change.
- [x] Iteration 45 was read-only Bridge health/idle investigation at 2026-07-16 16:36 CST. `/health`
  returned ok, `/status` was `ready=true`, `logged_in=true`, `last_error=null`, risk mode `SHADOW`,
  and `/metrics` showed queue depth 0 with `accepting_signals=true`. Runtime had 212 received signals
  in the latest-code window, 211 filtered, 0 failed executions, and webhook latency passed with P50
  `0.095 ms`, P95 `1.832 ms`, max `16.95 ms`.
- [x] Iteration 45 DB evidence: the bridge was not stuck. In the last 24 hours it recorded 27
  successful BUYs and 17 successful SELLs; the latest SUCCESS was BUY id 36201 at 2026-07-16
  16:22:09 CST. Records after that were still arriving through 16:36 CST but were protective
  pre-submit skips, mainly `keyword whitelist not matched` and `price > max_price 0.55000000`.
  There were zero `PENDING` bridge records, so no queued or hung execution was found.
- [x] Iteration 46 reduced DB work on protective pre-submit skips. `_record_failed_signal` now uses
  the existing one-shot `record_result(..., status="FAILED")` path instead of `record_pending`
  followed by `update_status`, and repeated skip branches for short-cycle BUY guards plus
  insufficient-position SELL skips now reuse `_record_failed_signal`. This halves DB writes for the
  dominant filtered-signal path observed in Iterations 44-45 and removes transient `PENDING` noise
  for skips without changing any trade eligibility, risk, or UI submission decision.
- [x] Iteration 46 verification: targeted tests passed 19/19 for proportional-risk Bridge behavior,
  signal queue, metrics, and async recorder behavior; full Bridge unittest discovery passed 102/102;
  `git diff --check` passed for `main.py`, `test_proportional_risk_bridge.py`, and this state file.
  The change was loaded through `safe_restart_bridge.sh --execute`; admission drained at queue depth 0
  and recovered with `accepting_signals=True`.
- [x] Iteration 46 post-load evidence: `/health` returned ok, `/status` was ready/logged in with
  `last_error=null`, and the latest-code report restarted at `since_ms=1784191195000`. The first 17
  post-load webhook samples had P50 `0.091 ms`, P95 `0.343 ms`, max `0.411 ms`; all execution records
  were still protective pre-submit filters, so BUY/SELL submit latency remains pending. DB spot-checks
  of new filtered rows showed `created_at == updated_at` (`update_delta_ms=0`) and global
  `PENDING` count 0, confirming one-shot FAILED inserts are live.
- [x] Iteration 47 captured the first real latest-code 5m BUY submit sample after the earlier
  executor optimizations. Runtime metrics showed one successful 5m BUY with `buy_5m_ui_submit_ms`
  `8308.260 ms` and `buy_5m_signal_to_submit_ms` `9362.842 ms`, both within the target envelope
  for a single sample. Stage breakdown showed the largest remaining contributors were
  `buy_5m_target_visible_ms=2175.653`, `buy_5m_click_submit_ms=1451.722`, and
  `buy_5m_submit_confirm_ms=1255.948`. The latest SUCCESS row was id 36786, XRP 5m BUY, created
  2026-07-16 16:41:24 CST, and global `PENDING` count remained 0.
- [x] Iteration 47 reduced short-cycle target-visible polling granularity. `_is_target_event_visible`
  now uses `_target_visible_poll_seconds_for_market`; 5m/15m markets poll at the existing short-cycle
  `0.15 s` cadence while non-short-cycle markets keep the previous `0.3 s` cadence. This leaves the
  strict active-target visibility check intact and only reduces wait granularity for the slowest
  observed 5m BUY stage.
- [x] Iteration 47 verification: navigation/browser diagnostics unittest group passed 18 tests,
  `test_selector_fixture.py` passed with Playwright DOM fixtures, full Bridge unittest discovery
  passed 102 tests, and `git diff --check` passed. The change was loaded with
  `safe_restart_bridge.sh --execute`; admission drained at queue depth 0 and recovered with
  `accepting_signals=True`. Post-load `/health` and `/status` were healthy, but no new signal arrived
  during a 45-second observation window, so this specific poll change still awaits the next real
  submit sample for measured effect.
- [x] Iteration 48 observed a real post-change slow 5m BUY submit: transaction
  `0xb8ffe68d8e885b2ee14cab92eee3f3894690a8d35001ac37026b68a70af06572`, DB id 39552,
  XRP 5m BUY, was marked SUCCESS but recorded `buy_5m_ui_submit_ms=58207.887` and
  `buy_5m_signal_to_submit_ms=61629.790`, outside the target envelope. Stage evidence showed
  `buy_5m_target_visible_ms` retries at `3912.812` and `3217.272`, `buy_5m_enter_amount_ms=2769.548`,
  and `buy_5m_click_submit_ms=8498.750`. The `click_submit` stage exceeded the configured 2-second
  short-cycle submit-button budget because each selector click could still wait up to 750 ms and
  cumulatively overrun the outer deadline.
- [x] Iteration 48 tightened submit-button deadline enforcement. `_click_buy_button` and
  `_click_sell_button` now clamp each selector click timeout and retry sleep to the remaining
  overall budget, so short-cycle BUY/SELL submit-button discovery cannot multiply a 2-second budget
  by the selector count. This directly targets the 8.5-second click-submit component from id 39552.
- [x] Iteration 48 also fixed health semantics for protective price-drift skips. A
  `LastMilePriceDriftError` is now logged as a warning and still bubbles to `main.py` for DB/metrics
  handling, but it no longer populates executor `last_error`; otherwise `/status` and health audits
  report a protective last-mile guard as a backend fault.
- [x] Iteration 48 verification: targeted tests for navigation waits, proportional-risk Bridge, and
  runtime-status audit passed 27 tests; `test_selector_fixture.py` passed with Playwright DOM
  fixtures; full Bridge unittest discovery passed 105 tests; `git diff --check` passed. The change
  was loaded through `safe_restart_bridge.sh --execute`; admission drained at queue depth 0 and
  recovered with `accepting_signals=True`. Post-load `/health` was ok, `/status` was ready/logged in
  with `last_error=null`, and the first 8 latest-code webhook samples had P50 `0.069 ms`, P95
  `0.112 ms`, max `0.130 ms`. No post-load submit sample has yet exercised the tightened
  submit-button deadline.
- [x] Iteration 49 reduced the short-cycle target-visible timeout from `3.0 s` to `1.2 s`.
  The preceding real slow 5m BUY sample id 39552 spent `3912.812 ms` and `3217.272 ms` in two
  target-visible retries before proceeding, so a missing or rotated-away active target could burn
  about seven seconds before re-navigation. The strict target-market/content check remains intact;
  5m/15m markets now fail that check faster and use the existing portfolio-row or re-navigation
  fallback sooner.
- [x] Iteration 49 verification: navigation/browser diagnostics tests passed 22 tests,
  `test_selector_fixture.py` passed, full Bridge unittest discovery passed 106 tests, and
  `git diff --check` passed. The change was loaded through `safe_restart_bridge.sh --execute`;
  admission drained at queue depth 0 and recovered with `accepting_signals=True`.
- [x] Iteration 49 post-load evidence: `/health` returned ok, `/status` was ready/logged in with
  `last_error=null`, `/metrics` had queue depth 0 and `accepting_signals=true`, and `/portfolio`
  returned live positions but took about `14.8 s`. The latest-code report restarted at
  `since_ms=1784210720000`; the first 23 post-load webhook samples had P50 `0.214 ms`, P95
  `6.764 ms`, max `11.165 ms`, below the target but below the 100-sample floor. All 23 execution
  records were protective FAILED filters (`keyword whitelist not matched`, `price > max_price
  0.55000000`, or insufficient position), and global `PENDING` count remained 0, so there is still
  no post-load BUY/SELL submit sample for the new target-visible budget.

## Blocked / Escalated

- Planned restart at 2026-07-16 00:48 overlapped signal record 32213. The old executor was
  already closing, so the record was marked FAILED with `Executor not ready` and no trade was submitted.
- Planned restart on 2026-07-16 01:08 loaded diagnostics but also exposed that the old 90-second
  startup grace was too short for a slow persistent-profile recovery. It recorded one
  `restart_threshold`; code now raises the default startup grace to 240 seconds and the verifier
  restarts the seven-day window after the recovered `service_start`. This does not yet prove seven-day
  health stability or trade latency targets.

## Next Iteration

Collect the next real 5m/15m BUY or SELL submit sample and seven consecutive days of health-event
evidence. Current traffic is being filtered by config 13, and pre-submit skips no longer increment
`signals_executed`, so do not infer submit latency from the absence of executions. Watch whether
the default browser page remains on `https://polym.trade/` between account/portfolio probes and
the next trade, whether `event_resolve_5m_ms`/`event_resolve_15m_ms` stays near zero,
short-cycle SHADOW portfolio-risk timeouts stay near <=0.35 seconds, available portfolio-risk calls
benefit from the reused client instead of per-call client setup, high-drift BUYs fail fast
before amount entry, `buy_5m_enter_amount_ms` drops materially below the prior `3358.199 ms` sample,
`buy_5m_select_outcome_ms` drops materially below the prior `2051.758 ms` sample through the
`binary-fast` path, `buy_5m_page_ready_ms` drops materially below the prior `2708.203 ms` sample
through binary Up/Down ready detection and the short-cycle 0.15-second page-ready polling interval,
short-cycle BUY initial page-ready waits cap around `0.6 s` before the stronger target-visible loop,
short-cycle missing-target checks cap around `1.2 s` per attempt before portfolio-row fallback or
re-navigation,
`buy_5m_navigate_ms` drops materially below the prior
`1399.959 ms` sample through the short-cycle `commit` navigation wait, `buy_5m_click_submit_ms`
drops materially below the prior `7234.155 ms` outlier through the short-cycle 2-second submit-button
budget, post-outcome fixed wait contributes about `0.15 s` instead of `0.8 s` on submit-eligible
short-cycle BUYs, submitted 5m/15m `*_ui_submit_ms` samples stay below the 10-20 s submission
target, and new BUY verifications stop producing false unconfirmed results from dialog share previews. Re-run the
latest-code report after either 100 post-restart webhook samples or the next
non-filtered submit attempt. If a latest-code window reaches 100 webhook samples but still has no
submit samples, record the webhook pass and DB reason summary without restarting; repeated restarts
reset the useful latest-code sample window. For fair post-load verification, run
`./.venv/bin/python bridge_performance_report.py --since-health-window --since-latest-code-fingerprint --include-db-records`.
Use `--since-ms <restart_epoch_ms>` only if a manual timestamp window is needed. If portfolio activity
becomes quiet for more than `BRIDGE_PORTFOLIO_PAGE_IDLE_CLOSE_SECONDS`, verify
`/metrics.browser.page_count=1` and capture a fresh Bridge-related RSS snapshot filtered to the Bridge
browser profile. Also keep tracking `/portfolio` latency separately because the post-load live read
took about `14.8 s`; this should not block SELL submission now that verification is asynchronous,
but it can still affect portfolio fallback and operator pages. Do not force restart while signal
traffic is active.
