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

## 7. SELL 路径加固（迭代 4）

- [x] 7.1 新增 `_is_sell_dialog_open()`：检测 SELL 弹窗是否真正打开。
- [x] 7.2 新增 `_capture_sell_baseline()`：在提交 SELL 前捕获余额与 event-page 持仓数量。
- [x] 7.3 新增 `_verify_sell_executed()`：通过持仓数量下降、余额增加、success indicator 三重校验确认 SELL 成交。
- [x] 7.4 重写 `_execute_sell()`：增加事件 URL 等待、网络/代币模态框处理、SELL 弹窗打开重试、卖出按钮点击重试。
- [x] 7.5 `execute_trade()` 对 SELL 调用 `_verify_sell_executed()` 并返回 `verified` 字段。
- [x] 7.6 `main.py` 不再因 live portfolio 校验未立即通过而将 SELL 标为 FAILED；改为记录警告并保持 SUCCESS，避免假阴性。
- [x] 7.7 提高 `_wait_for_live_position_decrease()` 轮询次数与间隔（8 次 × 2.5 秒）。

## 8. BUY outcome/amount 与 SELL 持仓匹配加固（迭代 5）

- [x] 8.1 优化 `_select_polymtrade_outcome()`：增加重试、页面滚动、更多 side label、点击后滚动到视图。
- [x] 8.2 优化 `_enter_amount()`：扩大 selector 范围、限制在 dialog/trade 区域内、失败时截图。
- [x] 8.3 优化 SELL live portfolio 匹配：同时匹配 `marketSlug`/`eventSlug` 与标题子串。
- [x] 8.4 SELL 实际持仓不足时自动降级为卖出全部可用数量，而非直接 FAILED。
- [x] 8.5 新增 `bridge_metrics.py` 与 `/metrics` 接口，统计信号、交易、Gamma API、模态框、Portfolio 请求等指标。
- [x] 8.6 在 `main.py` 与 `polymtrade_executor.py` 关键路径埋点更新指标。

## 9. 测试与验证

- [x] 9.1 新增静态 HTML 测试覆盖网络/代币模态框选择（`test_selector_fixture.py`）。
- [x] 9.2 新增静态 HTML 测试覆盖余额解析（`test_selector_fixture.py`）。
- [x] 9.3 新增 enrichment 单元测试与 Gamma API 重试测试（`test_enrichment.py`）。
- [x] 9.4 新增 BUY 校验单元测试（`test_buy_verification.py`）。
- [x] 9.5 新增 SELL 校验单元测试（`test_sell_verification.py`）。
- [x] 9.6 运行 `test_selector_fixture.py`、`test_enrichment.py`、`test_buy_verification.py`、`test_sell_verification.py`、`test_copy_trading_config.py` 全部通过。
- [x] 9.7 运行 `python -m py_compile` 检查 `polymtrade_executor.py`、`main.py`、所有测试文件语法。
- [x] 9.8 重启 launchd 服务，验证 `/health`、`/portfolio`、`/metrics` 正常响应。

## 10. 文档与记录

- [x] 10.1 更新 `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md` 记录需求。
- [x] 10.2 更新 `LOOP_STATE.md` 记录迭代 1、2、3、4、5 进展。
