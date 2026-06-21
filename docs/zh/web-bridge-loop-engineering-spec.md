# Web Bridge Loop Engineering Spec

## Goal

持续提高 PolyHermes Web Bridge 的 BUY 和 SELL 成功率，优先减少真实交易链路中的误点、漏点、卡单、误报成功、PENDING 悬挂和错误归因。

目标不是一次性重构，而是按 Loop Engineering 小步循环：从日志和数据库记录中发现最痛的失败模式，做最小可验证修复，重启/验证运行态，再把结果记录回本文件。

## Scope

### In Scope

- `polymtrade-bridge/` 中 Polymtrade 浏览器自动化逻辑。
- 后端向 Bridge 发送的 leader trade webhook 字段完整性和可追踪性。
- Bridge 执行记录、webhook 日志、持仓快照和真实 portfolio 的一致性。
- BUY/SELL 页面定位、市场行选择、结果按钮选择、金额/份额输入、确认状态识别。
- 失败原因分类、错误消息可读性、可复现日志上下文。

### Out of Scope

- 不自动追单补买历史错过的 leader 交易。
- 不自动平仓真实持仓，除非当前人工明确要求。
- 不改交易策略参数，如跟单比例、最大订单金额、leader 选择标准，除非某轮目标明确需要。
- 不绕过 Polymtrade 风控、认证、地区限制或资金限制。

## Operating Mode

每一轮循环都按以下步骤执行：

1. Discover
   - 读取 `backend/app.log`、`/tmp/polymtrade-bridge.log`、`polymtrade-bridge/bridge.log`。
   - 查询 MySQL 表：`bridge_trade_record`、`bridge_webhook_log`、`bridge_position_snapshot`、`copy_order_tracking`。
   - 从最新 FAILED、长时间 PENDING、SUCCESS 但 portfolio 不一致的记录中挑最高风险问题。

2. Classify
   - 将失败归类到一个明确 bucket：
     - `signal_not_received`
     - `bridge_not_ready`
     - `market_resolution_failed`
     - `wrong_market_selected`
     - `outcome_selection_failed`
     - `amount_input_failed`
     - `confirm_failed`
     - `network_deposit_modal`
     - `credential_decrypt_failed`
     - `success_but_position_mismatch`
     - `sell_precheck_ledger_drift`
     - `pending_timeout`

3. Fix
   - 每轮只做一个小修复，优先改最靠近故障点的代码。
   - 优先增强确定性匹配、状态校验和错误可观测性，再考虑较大结构调整。
   - 对浏览器自动化，禁止用“全局第一个 Yes/No”作为多市场页面 fallback。

4. Verify
   - Python 改动至少执行：
     - `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py`
   - Kotlin 改动至少执行：
     - `JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home ./gradlew compileKotlin`
   - 若需要进入运行态，重建后端：
     - `JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home ./gradlew bootJar`
   - 重启后验证：
     - `curl -sS http://127.0.0.1:8080/health`
     - `curl -sS http://127.0.0.1:8000/api/system/health`
   - 注意：后端健康接口若返回 `缺少认证令牌`，也说明服务已响应。

5. Record
   - 在本文件的 Loop State 中记录本轮发现、修改、验证结果和剩余风险。

## Metrics

优先跟踪这些指标：

- `bridge_success_rate`: Bridge `SUCCESS / (SUCCESS + FAILED)`，按最近 24 小时和最近 100 单统计。
- `pending_timeout_count`: `PENDING` 超过 2 分钟的记录数。
- `success_position_mismatch_count`: Bridge 记为 SUCCESS，但真实 portfolio 没有对应市场/方向/近似数量的记录数。
- `unexpected_portfolio_position_count`: 真实 portfolio 存在仓位，但 Bridge SUCCESS ledger 没有对应净持仓预期的记录数。
- `wrong_market_selected_count`: 真实 portfolio 出现非目标市场，且同时间目标市场未出现。
- `buy_execution_latency_ms`: webhook 创建到 Bridge 更新 SUCCESS/FAILED 的耗时。
- `sell_execution_latency_ms`: SELL 请求到 Bridge 更新 SUCCESS/FAILED 的耗时。
- `ambiguous_error_count`: `bridgeTradeRecord.errorType.other` 或无法归因错误数。

## Data Sources

### Runtime Logs

- `backend/app.log`
- `/tmp/polymtrade-bridge.log`
- `/tmp/polymtrade-bridge-supervisor.log`
- `polymtrade-bridge/bridge.log` legacy/local log

### Database Tables

- `bridge_trade_record`
- `bridge_webhook_log`
- `bridge_position_snapshot`
- `copy_order_tracking`
- `processed_trade`
- `copy_trading`
- `copy_trading_leaders`

### Live Checks

- Bridge health: `GET http://127.0.0.1:8080/health`
- Bridge portfolio: `GET http://127.0.0.1:8080/portfolio`
- Backend health: `GET http://127.0.0.1:8000/api/system/health`
- Bridge reliability audit:
  - `polymtrade-bridge/.venv/bin/python polymtrade-bridge/bridge_reliability_audit.py --limit 100 --ledger-limit 1000`

## Safety Rails

- Never place an after-the-fact replacement trade automatically.
- Never close a live position automatically unless the current user request explicitly asks for it.
- If a record says SUCCESS, verify against portfolio before treating it as truth when debugging selection code.
- When fixing market row selection, prefer failing closed over clicking an uncertain row.
- For multi-market event pages, a valid click must be tied to market-specific keywords or a precise row identity.
- Keep changes scoped; do not refactor unrelated backend, frontend, or strategy code during a reliability loop.

## Current Findings

### 2026-06-19

- `bridge_trade_record` id `209` failed before submit because Bridge JS returned `bestScore` without defining it.
- `bridge_trade_record` id `210` was marked SUCCESS for Curaçao `No`, but live portfolio showed Germany `No`; this indicates old fallback logic could click the wrong `No` row on multi-market pages.
- `bridge_trade_record` id `213` failed on Argentina `No` because World Cup final event row matching kept generic event keywords (`2026`, `fifa`, `world`, `cup`) and did not inspect div-based market rows specifically enough.
- Activity webhook payload originally sent `title = null`; this weakened Bridge row matching because it only had slug tokens.
- Account private API/decryption errors are noisy and affect backend direct order creation/order push, but Bridge browser execution can still succeed independently.

## Decisions

- Bridge row selection must use `title + slug` when available.
- If market-specific keywords exist and no row matches, Bridge should fail closed instead of falling back to global Yes/No.
- Backend Activity webhook should pass market `title` through to Bridge.
- SUCCESS records for browser trades should be periodically reconciled against live Bridge portfolio to detect wrong-market selections.

## Loop State

### Open

- [ ] Build a frontend/backend operator workflow for reviewing and applying durable audit reconciliation annotations.
- [ ] Add additional selector fixtures for World Cup group winner page variants if new regressions appear.
- [ ] Investigate account credential decrypt failures separately from Bridge browser reliability.

### Done

- [x] Fixed `bestScore is not defined` in Bridge outcome selection.
- [x] Backend Activity webhook now passes market title to Bridge.
- [x] Bridge keyword extraction now uses both market title and slug.
- [x] Bridge now fails closed on multi-market pages instead of globally clicking the first Yes/No when keywords exist.
- [x] Added `bridge_reliability_audit.py`, a read-only reconciliation helper that flags `PENDING` timeouts, `SUCCESS` records whose expected open positions do not match `/portfolio`, and unexpected real portfolio positions.
- [x] Added live `/portfolio` SELL pre-check in Bridge so stale `bridge_trade_record` ledger positions cannot trigger a browser SELL when the real Polymtrade holding is missing or too small.
- [x] Hardened multi-market BUY row selection by removing generic event keywords, adding common country aliases, including div-based market rows, and preferring the smallest row with the target Yes/No button.
- [x] Added `test_selector_fixture.py`, a deterministic Playwright fixture that exercises the same BUY selector JS against a World Cup multi-market page shape.
- [x] Added leader-signal SELL post-submit verification: after the browser SELL returns, Bridge re-reads live `/portfolio` and only marks SUCCESS when the position quantity decreases.
- [x] Improved Bridge trade record UI error classification so selector errors, live-position insufficiency, SELL post-submit verification failures, and portfolio mismatch audit buckets no longer fall through to `bridgeTradeRecord.errorType.other`.
- [x] Extended SELL live-position pre-check and post-submit verification to manual `/execute` SELL requests when conditionId/title matching is available; manual browser execution now also uses the shared trade lock.
- [x] Added per-record Bridge position mismatch visibility: backend trade DTOs include ledger net quantity, live snapshot quantity, snapshot sync time, and mismatch reason; frontend shows a `Position Drift`/`持仓漂移` tag on affected SUCCESS records.
- [x] Added a live read-only Bridge `/audit` endpoint that exposes aggregate reconciliation metrics and mismatch details using the same logic as `bridge_reliability_audit.py`.
- [x] Added fresh/stale classification for SUCCESS position mismatches so historical drift is separated from fresh wrong-market or missing-position risk.
- [x] Added Bridge-local durable audit reconciliation annotations backed by an ignored JSON file, plus read/write HTTP endpoints and audit support for reconciled vs active mismatch counts.

### Iterations

```text
Iteration: 2
Time: 2026-06-19 16:50 CST
Trigger: Continue loop engineering after fixing selector fail-closed behavior.
Observed records: id 209 FAILED bestScore; id 210 SUCCESS but target Curaçao No not in live portfolio; live portfolio contains Germany No and Belgium No.
Failure bucket: success_position_mismatch, unexpected_portfolio_position, pending_timeout
Root cause: Bridge SUCCESS records alone are not a reliable source of truth; wrong-market clicks and external/manual closes can make DB ledger drift from real Polymtrade holdings.
Change: Added polymtrade-bridge/bridge_reliability_audit.py to compare recent bridge_trade_record rows and SUCCESS ledger net quantities against live /portfolio.
Verification: py_compile passed; audit run checked 30 recent records with ledger limit 200 and found 14 SUCCESS ledger rows, 0 pending timeouts, 5 success_position_mismatch items, and 1 unexpected_portfolio_position for Germany No while current /portfolio had Germany No and Belgium No.
Runtime status: Bridge /portfolio responded successfully; backend was restarted in tmux session polyhermes-backend, Java PID 53546, port 8000 listening; health endpoint returned missing-token response.
Residual risk: The audit is read-only and local CLI only; mismatch data is not yet surfaced in the UI or backend alerting, and older manual closes can still look like ledger mismatch.
Next: Wire audit output into backend/operator visibility and refine mismatch handling for externally closed positions.
```

```text
Iteration: 3
Time: 2026-06-19 17:02 CST
Trigger: Audit still shows stale SUCCESS ledger drift and one unexpected Germany No real position.
Observed records: recent audit checked 50 records, found 0 pending timeouts, 5 success_position_mismatch items, and 1 unexpected_portfolio_position for Germany No.
Failure bucket: sell_precheck_ledger_drift, success_position_mismatch, unexpected_portfolio_position
Root cause: Bridge SELL gating used PositionLedger derived from bridge_trade_record SUCCESS rows; audit proves that ledger can drift from real /portfolio after wrong-market clicks or external/manual position changes.
Change: Added live /portfolio quantity check immediately before browser SELL execution. If available real quantity is less than required quantity, the record is marked FAILED with "Live portfolio insufficient position, skipped" and no sell click is attempted.
Verification: py_compile passed for main.py, polymtrade_executor.py, and bridge_reliability_audit.py; Bridge restarted and /health returned executor_ready=true; backend health returned missing-token response; audit still runs successfully.
Runtime status: Bridge running with new code as PID 90505 on port 8080; backend running on port 8000 in tmux session polyhermes-backend.
Residual risk: SELL post-submit success still needs reconciliation to confirm quantity decreased; there is a leftover tmux Bridge supervisor shell plus launchd-style supervisor, but only one Python Bridge process is listening on 8080.
Next: Add SELL post-submit verification or surface audit mismatch metrics in backend/UI.
```

```text
Iteration: 4
Time: 2026-06-19 17:10 CST
Trigger: Recent audit found id 213 FAILED for Argentina No with "Could not select outcome" while Spain/Mexico No on the same World Cup final event succeeded.
Observed records: id 213 Argentina No FAILED; id 212 Spain No SUCCESS; id 214 Mexico No SUCCESS; audit checked 60 records and found 0 pending timeouts, 5 success_position_mismatch items, and 1 unexpected_portfolio_position.
Failure bucket: market_resolution_failed, outcome_selection_failed
Root cause: Keyword extraction kept generic event words like 2026/fifa/world/cup, and the row selector only considered li/listitem/section. On the live event page, the specific Argentina row is a small div with "No 80c"; broad containers also contain Argentina and can outrank or obscure the true row.
Change: Removed generic event keywords, added common country aliases including Argentina/阿根廷, included div candidates, and sorted candidate rows by target side-button presence, score, then smallest text length.
Verification: py_compile passed for polymtrade_executor.py, main.py, and bridge_reliability_audit.py; keyword extraction now returns Argentina => [argentina, 阿根廷] and Germany => [germany, 德国]; live read-only DOM simulation on the World Cup final page chose the specific Argentina row with target "No 80c"; Bridge restarted and /health returned executor_ready=true; audit still runs successfully.
Runtime status: Bridge running with new code as PID 14525 on port 8080; backend running on port 8000 in tmux session polyhermes-backend.
Residual risk: The failed Argentina trade was not replayed; future similar signals should benefit from the selector fix. A deterministic selector fixture is still needed to prevent regressions.
Next: Add a fixture/test for multi-market row selection or continue with SELL post-submit verification.
```

```text
Iteration: 5
Time: 2026-06-19 17:17 CST
Trigger: Selector fix for id 213 needed deterministic regression coverage before further bridge selector changes.
Observed records: audit checked 80 records, found 0 pending timeouts, 5 success_position_mismatch items, 1 unexpected_portfolio_position, and no newer FAILED record after id 213.
Failure bucket: outcome_selection_failed, selector_regression_risk
Root cause: The live BUY selector was embedded inline in polymtrade_executor.py, so it could only be checked manually against a live page and was easy to regress.
Change: Extracted the browser-side BUY outcome selector JS into _select_outcome_script() and added polymtrade-bridge/test_selector_fixture.py. The fixture uses static HTML shaped like the World Cup nation-to-reach-final page and verifies Argentina No selects the small Argentina row, while missing market keywords fail closed instead of clicking a global No.
Verification: py_compile passed for polymtrade_executor.py, main.py, bridge_reliability_audit.py, and test_selector_fixture.py; polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_selector_fixture.py passed; Bridge restarted and /health returned executor_ready=true; backend health returned missing-token response; audit still runs successfully.
Runtime status: Bridge running with new code as PID 83684 on port 8080; backend running on port 8000 in tmux session polyhermes-backend.
Residual risk: Fixture currently covers the World Cup nation-to-reach-final row shape, not every group-winner variation; selector alias list is still manually curated.
Next: Continue with SELL post-submit verification or surface audit mismatch metrics in backend/UI.
```

```text
Iteration: 6
Time: 2026-06-19 17:22 CST
Trigger: Open item required SELL post-submit verification so Bridge does not mark a SELL SUCCESS solely because the trade dialog closed.
Observed records: audit checked 80 records, found 0 pending timeouts, 5 success_position_mismatch items, and 1 unexpected_portfolio_position. No newer FAILED record after id 213.
Failure bucket: sell_post_submit_unverified
Root cause: Leader SELL flow verified position existence before clicking SELL, but after executor.execute_trade returned, Bridge immediately marked the record SUCCESS without proving live portfolio quantity decreased.
Change: Added _wait_for_live_position_decrease() and wired it into leader-signal SELL execution. After SELL returns, Bridge polls live portfolio and marks SUCCESS only after quantity decreases by at least 0.01; otherwise it raises a clear "SELL post-submit verification failed" error and the record is marked FAILED.
Verification: py_compile passed for main.py, polymtrade_executor.py, bridge_reliability_audit.py, and test_selector_fixture.py; test_selector_fixture.py passed; a monkeypatched helper check verified both decrease-success and no-decrease failure paths; Bridge restarted and /health returned executor_ready=true; backend health returned missing-token response; audit still runs successfully.
Runtime status: Bridge running with new code as PID 11709 on port 8080; backend running on port 8000 in tmux session polyhermes-backend.
Residual risk: Manual /execute SELL still lacks post-submit verification when the request does not include reliable conditionId/title matching. Live portfolio polling can add a few seconds to SELL completion.
Next: Surface audit mismatch metrics in backend/UI or extend post-submit verification to manual SELL requests that include conditionId.
```

```text
Iteration: 7
Time: 2026-06-19 17:26 CST
Trigger: Earlier user-visible Bridge failures could display as bridgeTradeRecord.errorType.other even when the error text had a clear reliability bucket.
Observed records: audit checked 80 records, found 0 pending timeouts, 5 success_position_mismatch items, 1 unexpected_portfolio_position, and historical FAILED records id 209 selector JS error plus id 213 outcome selection failure.
Failure bucket: ambiguous_error_count, selector_error, sell_post_submit_unverified, success_position_mismatch, unexpected_portfolio_position
Root cause: The frontend BridgeTradeRecordList classifier only recognized a few legacy substrings. Newer Bridge reliability errors such as bestScore/ReferenceError, Live portfolio insufficient position, SELL post-submit verification failed, success_position_mismatch, and unexpected_portfolio_position could still fall through to errorType.other.
Change: Extended classifyError() with explicit buckets for selectorError, sellVerifyFailed, livePositionInsufficient, successPositionMismatch, and unexpectedPortfolioPosition. Added zh-CN/en/zh-TW locale labels for all Bridge errorType keys.
Verification: JSON locale parse passed for zh-CN/en/zh-TW; npm run build passed; py_compile and test_selector_fixture.py passed for Bridge-side files; Bridge /health returned executor_ready=true; backend health returned missing-token response; audit still runs successfully.
Runtime status: Bridge running as PID 11709 on port 8080; backend running on port 8000 in tmux session polyhermes-backend.
Residual risk: This improves operator visibility but does not yet expose audit mismatch metrics as first-class backend/UI rows.
Next: Surface audit mismatch metrics in backend/UI or extend manual SELL post-submit verification.
```

```text
Iteration: 8
Time: 2026-06-19 17:35 CST
Trigger: Open item required manual /execute SELL to receive the same live portfolio safeguards as leader-signal SELL when the request includes reliable conditionId/title matching.
Observed records: audit checked 80 records, found 0 pending timeouts, 5 success_position_mismatch items, 1 unexpected_portfolio_position, and no newer FAILED record after id 213.
Failure bucket: manual_sell_post_submit_unverified, browser_concurrency_risk, sell_precheck_ledger_drift
Root cause: Manual /execute updated bridge_trade_record to SUCCESS as soon as executor.execute_trade returned, without proving the live portfolio quantity decreased. It also did not use the shared _trade_lock, so a manual trade and a leader-signal trade could operate the same browser page concurrently.
Change: Wrapped manual _execute_and_record browser execution in _trade_lock. For manual SELL with conditionId or marketTitle, Bridge now reads live /portfolio before clicking, fails without clicking when the real quantity is insufficient, then polls /portfolio after submit and only marks SUCCESS when quantity decreases.
Verification: py_compile passed for main.py, polymtrade_executor.py, bridge_reliability_audit.py, and test_selector_fixture.py; test_selector_fixture.py passed; monkeypatched manual SELL helper check passed for decrease-success and insufficient-position failure paths; Bridge restarted with new code and /health returned executor_ready=true; backend health returned missing-token response; audit still runs successfully with 0 pending timeouts.
Runtime status: Bridge running as PID 80329 on port 8080; backend running on port 8000 in tmux session polyhermes-backend.
Residual risk: Manual SELL requests without conditionId or marketTitle still log that live verification was skipped because the position cannot be matched reliably. Existing historical ledger mismatch remains unresolved.
Next: Surface audit mismatch metrics in backend/UI and distinguish externally/manual-closed historical records from fresh mismatches.
```

```text
Iteration: 9
Time: 2026-06-19 17:41 CST
Trigger: Existing audit still found 5 success_position_mismatch items and 1 unexpected_portfolio_position, but operators could not see per-record drift directly in the Bridge trade list.
Observed records: audit checked 80 records, found 0 pending timeouts, 5 success_position_mismatch items, 1 unexpected_portfolio_position, and 72 historical failure rows.
Failure bucket: success_position_mismatch, operator_visibility_gap, stale_success_ledger
Root cause: BridgeTradeRecordList only showed DB trade status and error text. The backend already synced real /portfolio snapshots into bridge_position_snapshot, but Bridge trade DTOs did not expose ledger-vs-snapshot comparison fields, so old SUCCESS rows could still look trustworthy in the UI.
Change: BridgeTradeRecordService now enriches each trade record with ledgerNetQuantity, snapshotQuantity, snapshotSyncedAt, positionMismatch, and positionMismatchReason by comparing SUCCESS ledger net quantities with bridge_position_snapshot. The frontend Bridge trade list displays a Position Drift / 持仓漂移 tag with ledger, snapshot, and sync-time tooltip for affected records. Added zh-CN/en/zh-TW labels and TypeScript fields.
Verification: frontend npm run build passed; zh-CN/en/zh-TW locale JSON parse passed; Bridge py_compile and test_selector_fixture.py passed; Bridge /health returned executor_ready=true; bridge_reliability_audit.py still runs successfully with 0 pending timeouts. Backend compile could not be executed in this shell because no Java Runtime is available (`Unable to locate a Java Runtime`).
Runtime status: Bridge running on port 8080; backend running on port 8000 from the existing jar, but the new backend DTO/service code is not live until compiled and restarted in an environment with Java.
Residual risk: Aggregate audit metrics are still not first-class in the UI. Backend Kotlin changes need compile verification once a JDK is available.
Next: Install/restore a local JDK or use the backend build environment to compile and restart backend, then add aggregate reconciliation metrics.
```

```text
Iteration: 10
Time: 2026-06-19 17:49 CST
Trigger: Aggregate reconciliation metrics were still only available by running the local bridge_reliability_audit.py CLI, and backend/UI rollout is currently limited by the missing local Java Runtime.
Observed records: HTTP /audit and CLI audit both checked 80 records, found 0 pending timeouts, 5 success_position_mismatch items, 1 unexpected_portfolio_position, 4 live portfolio positions, and 72 historical failure rows.
Failure bucket: operator_visibility_gap, success_position_mismatch, unexpected_portfolio_position
Root cause: The audit logic already existed, but it was not exposed by a running service. Operators needed shell access to run the CLI, and the backend/UI path cannot be fully verified in this shell until Java is available.
Change: Added a read-only Bridge GET /audit endpoint. It reuses bridge_reliability_audit.audit(), runs it in a worker thread via asyncio.to_thread so the FastAPI event loop is not blocked, and exposes limit, ledger_limit, failure_limit, pending_timeout_ms, min_quantity_ratio, quantity_tolerance, and portfolio_timeout query parameters. It never places trades.
Verification: py_compile passed for main.py, bridge_reliability_audit.py, polymtrade_executor.py, and test_selector_fixture.py; test_selector_fixture.py passed; monkeypatched endpoint parameter-path check passed; Bridge restarted with the new endpoint and /health returned executor_ready=true; HTTP /audit returned metrics matching CLI audit: pending_timeout_count=0, success_position_mismatch_count=5, unexpected_portfolio_position_count=1; backend health returned missing-token response.
Runtime status: Bridge running on port 8080 with /audit live; backend running on port 8000 from the existing jar.
Residual risk: /audit is service-facing JSON, not yet a polished backend/UI dashboard. Historical mismatch rows still need reconciliation semantics so old manual/external closes can be separated from fresh wrong-market executions.
Next: Add stale/manual-close reconciliation semantics or complete backend/UI rollout after JDK is available.
```

```text
Iteration: 11
Time: 2026-06-19 17:56 CST
Trigger: /audit could expose mismatch counts, but old SUCCESS ledger drift still looked like current wrong-market risk because all mismatches used the same bucket.
Observed records: HTTP /audit checked 80 records and found 5 success_position_mismatch items. Their latest contributing records were older than the default 30 minute stale window; id 210 was updated around 2026-06-19 15:43 CST while the audit ran after 17:50 CST, and the others were older.
Failure bucket: stale_success_position_mismatch, success_position_mismatch, stale_success_ledger
Root cause: bridge_reliability_audit.py only compared expected vs actual quantities. It did not include latest contributing record time or age, so historical/external/manual-close drift could not be separated from fresh execution regressions.
Change: Added latest_record_updated_at, age_ms, is_stale, stale_after_ms, and mismatch_reason to success_position_mismatches. Added fresh_success_position_mismatch_count and stale_success_position_mismatch_count metrics. Added CLI --stale-mismatch-ms and Bridge /audit stale_mismatch_ms query parameter, defaulting to 30 minutes.
Verification: py_compile passed for main.py, bridge_reliability_audit.py, polymtrade_executor.py, and test_selector_fixture.py; test_selector_fixture.py passed; CLI audit returned fresh_success_position_mismatch_count=0 and stale_success_position_mismatch_count=5 with bucket=stale_success_position_mismatch; Bridge restarted and /health returned executor_ready=true; HTTP /audit returned the same stale metrics; HTTP /audit with stale_mismatch_ms=999999999 moved the same 5 items back to fresh bucket, proving the parameter path works; backend health returned missing-token response.
Runtime status: Bridge running on port 8080 with updated /audit; backend running on port 8000 from the existing jar.
Residual risk: The audit now classifies historical drift, but it does not yet persist an explicit reconciliation decision such as externally_closed or accepted_manual_close.
Next: Add durable reconciliation actions/annotations, or complete backend/UI rollout after JDK is available.
```

```text
Iteration: 12
Time: 2026-06-19 18:18 CST
Trigger: Stale SUCCESS drift could be classified as historical, but there was no durable way to mark an investigated mismatch as externally/manual closed or accepted stale.
Observed records: HTTP /audit checked 80 records and found active_success_position_mismatch_count=5, stale_success_position_mismatch_count=5, reconciled_success_position_mismatch_count=0, unexpected_portfolio_position_count=1. No real reconciliation annotations existed.
Failure bucket: stale_success_position_mismatch, reconciliation_annotation_gap, stale_success_ledger
Root cause: The audit classification was computed every run from ledger and portfolio state only. It could not remember an operator decision, so already-investigated historical drift would continue to appear as active drift forever.
Change: Added Bridge-local reconciliation annotations stored in polymtrade-bridge/audit_reconciliations.json, ignored by git. Added reconciliation_key(), load_reconciliations(), and save_reconciliations() helpers. Audit now reads annotations and moves matching mismatch items to bucket=reconciled_success_position_mismatch with mismatch_reason=operator_reconciled, while metrics split success_position_mismatch_count into active_success_position_mismatch_count and reconciled_success_position_mismatch_count. Added GET /audit/reconciliations and POST /audit/reconciliations endpoints with allowed statuses externally_closed, manual_closed, accepted_stale, and wrong_market_known.
Verification: py_compile passed for main.py, bridge_reliability_audit.py, polymtrade_executor.py, and test_selector_fixture.py; test_selector_fixture.py passed; CLI audit with a temporary annotation file moved one mismatch from active to reconciled (active=4, reconciled=1); offline HTTP endpoint test with a temporary BRIDGE_AUDIT_RECONCILIATION_FILE persisted and read back one annotation; Bridge restarted and /health returned executor_ready=true; live GET /audit/reconciliations returned count=0; live /audit returned active=5 and reconciled=0; audit_reconciliations.json is git-ignored and no real annotation file was created; backend health returned missing-token response.
Runtime status: Bridge running on port 8080 with reconciliation-aware /audit and /audit/reconciliations endpoints; backend running on port 8000 from the existing jar.
Residual risk: Reconciliation annotations are available at the Bridge API level but not yet exposed in the operator UI, and no real mismatch was marked reconciled automatically.
Next: Build frontend/backend workflow for reviewing and applying annotations, or apply manual annotations after human confirmation.
```

### Blocked

- None currently. Some checks require live Polymtrade UI state and may be flaky under network/proxy changes.

## Iteration Template

Use this template after each loop:

```text
Iteration:
Time:
Trigger:
Observed records:
Failure bucket:
Root cause:
Change:
Verification:
Runtime status:
Residual risk:
Next:
```
