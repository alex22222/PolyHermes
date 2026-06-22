## 1. 模态框主动选择网络/代币（迭代 1）

- [x] 1.1 在 `polymtrade_executor.py` 新增 `_select_network_and_token_in_modal(preferred_network, preferred_token)`，实现 Polygon/USDC 的自动选择。
- [x] 1.2 修改 `_dismiss_modal_dialogs()`，先尝试选择网络/代币，失败再回退到关闭。
- [x] 1.3 修改 `_execute_buy()` 的模态框重试循环，使用新的选择逻辑。

## 2. BUY 前余额检查（迭代 1）

- [x] 2.1 新增 `_get_usdc_balance()`，支持从页面 DOM 解析 USDC/pUSD 余额。
- [x] 2.2 在 `_execute_buy()` 开始阶段调用余额检查，余额不足时快速失败。

## 3. BUY 后成交校验（迭代 1）

- [x] 3.1 新增 `_verify_buy_executed()`，通过 portfolio/余额变化间接确认 BUY 成交。
- [x] 3.2 在 `execute_trade()` 返回结果中附加 `verified` 字段。

## 4. 日志与错误信息改进（迭代 1）

- [x] 4.1 修复 `_enrich_position()` 等路径的异常日志，确保原因完整输出。

## 5. 持仓 enrich 避免页面跳转 + 重试（迭代 2）

- [x] 5.1 分析 `_enrich_position()` 导致 `net::ERR_ABORTED` 的根因：点击 portfolio card 引发 pending navigation，`fetch_portfolio_positions` 的 `goto('/portfolio')` 被 abort。
- [x] 5.2 重写 `_enrich_position()`：优先使用 card 中的 `href`/`data-*`，其次用 Gamma markets/events title search，最后才回退到 card 点击。
- [x] 5.3 新增 `_gamma_request_with_retry()`、`_search_gamma_markets_by_title()`、`_search_gamma_events_by_title()`，带指数退避重试。
- [x] 5.4 `fetch_portfolio_positions()` 并发执行 enrichment（`asyncio.gather`），不再串行点击。
- [x] 5.5 `fetch_portfolio_positions()`  scraping 时额外提取 card 的 `href` 与 `data-*` 属性。

## 6. BUY 后成交精确校验（迭代 3）

- [x] 6.1 新增 `_capture_buy_baseline()`：在 `_execute_buy` 提交订单前捕获 USDC 余额与 event-page 持仓数量。
- [x] 6.2 新增 `_get_event_page_position_quantity()`：从 event page 解析 "You own X shares" / "持仓 X 份" 等文本。
- [x] 6.3 重写 `_verify_buy_executed()`：对比 pre/post 余额下降比例（≥50% 下单金额）与持仓数量增加。
- [x] 6.4 保留 success indicator 作为第三重兜底校验。
- [x] 6.5 `_execute_buy()` 返回结果中携带 `baseline`，`execute_trade()` 将其传给 `_verify_buy_executed()`。

## 7. 测试与验证

- [x] 7.1 新增静态 HTML 测试覆盖网络/代币模态框选择（`test_selector_fixture.py`）。
- [x] 7.2 新增静态 HTML 测试覆盖余额解析（`test_selector_fixture.py`）。
- [x] 7.3 新增 enrichment 单元测试与 Gamma API 重试测试（`test_enrichment.py`）。
- [x] 7.4 新增 BUY 校验单元测试（`test_buy_verification.py`）。
- [x] 7.5 运行 `test_selector_fixture.py`、`test_enrichment.py`、`test_buy_verification.py`、`test_copy_trading_config.py` 全部通过。
- [x] 7.6 运行 `python -m py_compile` 检查 `polymtrade_executor.py`、`main.py`、所有测试文件语法。
- [x] 7.7 本地启动 Bridge，验证 `/health` 和 `/portfolio` 正常响应，且 enrichment 不再触发 `ERR_ABORTED`。

## 8. 文档与记录

- [x] 8.1 更新 `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md` 记录需求。
- [x] 8.2 更新 `LOOP_STATE.md` 记录迭代 1、2、3 进展。
