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
- [x] 8.7 扩展 `bridge_reliability_audit.py` 与 `/audit`，输出 FAILED error bucket、actionability 和 next action candidates，支持每轮自动挖掘下一类修复对象。

## 9. BUY eventId URL 误判失败修复（迭代 6）

- [x] 9.1 分析 trade id 583 失败日志：`Target event 34584 URL never appeared`。
- [x] 9.2 确认根因：Bridge 账户在哥伦比亚大选事件上无持仓，portfolio 轮播离开目标事件导致 `eventId` 未出现在 URL。
- [x] 9.3 修改 `_wait_for_page_ready()`：移除 `eventId` URL 硬依赖，改为验证目标市场关键词与 Yes/No 按钮。
- [x] 9.4 新增 `_is_target_event_visible()`：基于关键词、side label、outcome 文本判断目标市场是否渲染。
- [x] 9.5 修改 `_execute_buy()`：用内容可见性替代 URL 等待，主 URL 失败时回退到 `eventSlug` 兜底 URL 并重新导航。
- [x] 9.6 在 `_extract_market_keywords()` stop words 中补充 `presidential`/`election` 等通用政治词汇，降低跨事件误匹配。

## 10. 测试与验证

- [x] 10.1 新增静态 HTML 测试覆盖网络/代币模态框选择（`test_selector_fixture.py`）。
- [x] 10.2 新增静态 HTML 测试覆盖余额解析（`test_selector_fixture.py`）。
- [x] 10.3 新增 enrichment 单元测试与 Gamma API 重试测试（`test_enrichment.py`）。
- [x] 10.4 新增 BUY 校验单元测试（`test_buy_verification.py`）。
- [x] 10.5 新增 SELL 校验单元测试（`test_sell_verification.py`）。
- [x] 10.6 新增事件可见性测试（`test_event_visibility.py`）。
- [x] 10.7 运行 `python -m pytest -q --asyncio-mode=auto`：37 tests 全部通过。
- [x] 10.8 运行 `python -m py_compile` 检查 `polymtrade_executor.py`、`main.py`、所有测试文件语法。
- [x] 10.9 重启 launchd 服务，验证 `/health`、`/portfolio`、`/metrics` 正常响应。
- [x] 10.10 新增政治候选型市场 outcome 选择回归测试，覆盖 `Will Abelardo de la Espriella win the 2026 Colombian presidential election?` 这类候选行选择。
- [x] 10.11 新增 `test_bridge_reliability_audit.py`，覆盖 Bridge FAILED 错误分类、failure bucket 汇总和 next action candidates。
- [x] 10.12 新增电竞队伍型市场 outcome 选择回归测试，覆盖 `Will Team Spirit win IEM Cologne Major 2026?`，并过滤 `team/iem/major` 等事件泛词。
- [x] 10.13 扩展 BUY 金额输入识别与回归测试，覆盖 `contenteditable`/`role=textbox` 自定义金额框，降低 `Could not enter trade amount` 失败。
- [x] 10.14 扩展 BUY/SELL 提交按钮点击逻辑与回归测试，覆盖延迟启用的 `role=button` 确认卖出控件，降低 `Could not click sell button` 失败。
- [x] 10.15 扩展 Bridge audit 输出 `coverage_hint`、covered/uncovered 计数和 coverage ids，避免已被 exact fixture 覆盖的历史失败继续挤占下一步修复队列。
- [x] 10.16 新增世界杯 group 多国家 selector fixture 与 coverage 规则，覆盖 Uruguay/Ecuador/Belgium/Spain 中文国家行的 Yes/No 选择。
- [x] 10.17 新增剩余世界杯国家 selector fixture、alias 修复与 coverage 规则，覆盖 Haiti/Curaçao/Cape Verde/Scotland/USA，并避免 Haiti slug 中的 Brazil 对手码污染目标关键词。
- [x] 10.18 新增电竞队伍 outcome 强锚点与 coverage 规则，覆盖 Vitality/Falcons、Map 1、Spirit/G2、Map Handicap，并保留 `G2` 这类短 alphanumeric 队名。
- [x] 10.19 新增 `select_outcome` 收尾 fixture 与 coverage 规则，覆盖 USA Group D 和 Mexico reach final 两个剩余未覆盖样本。
- [x] 10.20 扩展 BUY 表单打开守卫与金额输入识别，覆盖 `type=text`/`aria-label=USDC`/`role=spinbutton` 控件，并将未打开 BUY 表单从 `amount_input` 中拆分为 `buy_dialog_open`。
- [x] 10.21 扩展目标市场可见性判断，支持目标行内 `买入/卖出` 中文交易动作，并将 Abelardo `target_market_missing` 历史失败标记为 exact covered。
- [x] 10.22 拆分 SELL 弹窗未打开与提交后无效果失败桶，禁止 SELL 弹窗未检测到时继续输入份额，并补齐 Germany Group E / Argentina final 的 selector coverage。
- [x] 10.23 SELL 无 live 持仓时记录可见 FAILED skip 而非进入 UI 卖出，audit 将历史测试/缺元数据记录降级为非行动队列，并用 live precheck 覆盖 Ludvig Aberg `sell_dialog_open` 历史失败。
- [x] 10.24 增强 BUY/SELL 提交按钮识别与诊断，支持 `type=submit`、`aria-label`、`data-testid/data-test/id`、图标型确认按钮，并在提交按钮点击失败时保存截图。
- [x] 10.25 扩展 audit row-level 降级规则到 `amount_input` 等 UI code bucket，并修正 `/audit` 汇总使用最终 row-level bucket 与 coverage，避免缺元数据/零金额测试记录挤占真实修复队列。
- [x] 10.26 扩展 BUY 金额输入执行链路，支持中文 `aria-label=金额/数量` 与非原生 `role=spinbutton` 控件，并在金额输入失败时保存候选输入 DOM 诊断 JSON。
- [x] 10.27 为 BUY/SELL 页面 evaluate/evaluate_handle 增加 navigation race 重试封装，覆盖 page-ready、target-visible、outcome select、trade input scan 和 sell dialog open 路径。
- [x] 10.28 增强 BUY/SELL submit 失败诊断，SELL 提交前确认弹窗消失时不再误点 portfolio 卖出按钮，并保存 submit 候选按钮 DOM JSON。
- [x] 10.29 拆分 `other` 历史失败，新增/扩展 `navigation_race`、`read_only_account`、`executor_js_error` 与缺元数据降级规则，使 `/audit` 不再保留未知 other 队列。
- [x] 10.30 加固 Polymtrade 页面导航网络重试，portfolio 抓取和交易页跳转统一走 `_goto_with_retry()`，使用 `domcontentloaded`、更长 backoff，并在 transient 错误后目标 URL 已到达时继续执行。
- [x] 10.31 收口 `amount_input` 历史截图噪音：零金额 UI 失败降级为 `test_or_incomplete_record`，并用 record-id exact coverage 标记 BUY 弹窗未打开的历史截图记录。
- [x] 10.32 收口 `click_submit` 历史 SELL submit 样本：id 597 标记为 robust submit fixture exact covered，确保已修复旧失败不再阻塞下一步行动队列。
- [x] 10.33 收口 `navigation_race` 历史样本：evaluate context-loss 与 goto interrupted 样本标记为 exact covered，手工零金额 page-closed SELL 降级为 `test_or_incomplete_record`。
- [x] 10.34 收口 `navigation_network` 历史样本：ERR_ABORTED BUY 跳转失败标记为 `_goto_with_retry()` exact covered，手工零金额 ERR_CONNECTION_RESET 降级为 `test_or_incomplete_record`。
- [x] 10.35 为 Bridge `/audit` 和 CLI 增加 `since_ms` / `--since-ms` 过滤，支持只观察修复后新增 PENDING/FAILED 队列。
- [x] 10.36 扩展 `/audit` metrics 水位，输出 raw/filtered 最新记录时间、最新失败时间与 actionable bucket 数，便于 post-fix loop 监控。
- [x] 10.37 为 `/audit` 和 CLI 增加 `monitor_status`，直接输出 `clear` / `actionable` / `no_recent_records` 状态与下一步 bucket 列表。
- [x] 10.38 后端新增正式 Bridge audit 代理接口，并在统计信息页展示 `monitor_status`、可处理失败桶、最近失败数、Pending 超时和下一步 bucket。
- [x] 10.39 新增优化点日报页面 `/optimization-daily`，集中展示 live audit、最近 24 小时 post-fix 窗口和近期 Bridge 优化项。
- [x] 10.40 加固 portfolio/通用导航：启动、钱包地址提取、手动导航和持仓抓取统一使用 `_goto_with_retry()`，连续 transient 网络错误后启用 `commit` fallback，并提高 portfolio 抓取重试次数。
- [x] 10.41 规范 Bridge 跟单账号解析：空/0/非法 `COPY_TRADING_ACCOUNT_ID` 不再作为有效过滤条件，优先使用钱包检测账号，并在 `/status` 暴露实际 account id 与配置数量。
- [x] 10.42 优化点日报接入 Bridge runtime status，显示执行器 ready、登录状态、实际跟单 account id 与有效配置数。
- [x] 10.43 后端新增正式 Bridge runtime status 代理接口 `/api/bridge/trades/status`，优化点日报优先使用正式 API，开发环境保留 `/bridge-runtime/status` 兜底。
- [x] 10.44 使用项目内 JDK17 补跑后端 `compileKotlin`，验证 Bridge audit/status 正式代理 Kotlin 编译通过。
- [x] 10.45 Bridge `/audit` 顶层合并 `runtime_status`，后端/前端 audit 类型贯通，优化点日报优先使用 audit 内 runtime status，减少额外 status 请求。
- [x] 10.46 Bridge 在线 `/audit` 增加 runtime gate：未 ready、未登录、缺 account id、配置数为 0 或 last_error 存在时，`monitor_status.status=runtime_blocked`。
- [x] 10.47 优化点日报将 `runtime_block_reasons` 映射为中文标签，runtime_blocked 时可直接看到执行器未就绪、未登录、账号缺失、配置为空等原因。
- [x] 10.48 统计信息页同步展示 `runtime_blocked` 为执行受阻，并将 `runtime_block_reasons` 映射为中文原因标签。
- [x] 10.49 修复 portfolio enrichment 的错 metadata 污染：eventSlug 和 title search 都必须找到同标题 market，找不到时不再回退到第一个 market，降低 SELL live portfolio 匹配漂移。
- [x] 10.50 移除 portfolio enrichment 的并发卡片点击 fallback，确保 `/portfolio` 元数据补全保持只读，不再扰动当前 portfolio carousel。
- [x] 10.51 `/portfolio` 抓取前等待持仓行或明确空状态渲染，避免刚导航/刚重启时把未渲染列表误判为 0 持仓。
- [x] 10.52 为 2026 世界杯小组冠军持仓增加只读高置信 enrichment：从标题推导 `world-cup-group-<letter>-winner`，再 exact match market question，恢复正确 metadata 且不污染其它持仓。
- [x] 10.53 当钱包账号检测暂时失败但已加载配置全部属于同一 account 时，runtime status 推断该 account id，避免误报 `copy_trading_account_missing`；若配置跨多个 account 仍保持阻断。
- [x] 10.54 修复 portfolio marketSlug 查询参数，并从持仓标题推导 exact market slug 反查 Gamma，补齐 Abelardo/Argentina 这类现有持仓 metadata，提升 SELL live precheck 匹配质量。
- [x] 10.55 收敛 audit success mismatch 指标：stale 历史错配保留展示但不计入 active/strict actionable，fresh mismatch 才触发可行动状态，避免历史或外部平仓噪音干扰 SELL 可靠性监控。
- [x] 10.56 为 stale success mismatch 增加只读 reconciliation suggestions，输出可人工确认的 annotation payload，降低历史账本噪音复盘成本且不自动掩盖真实 SELL 风险。
- [x] 10.57 后端正式 audit DTO 与优化点日报接入 reconciliation suggestions，展示历史错配、当前错配、复盘建议和可行动问题，并列出前 8 条建议供人工复盘。

## 11. 文档与记录

- [x] 11.1 更新 `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md` 记录需求。
- [x] 11.2 更新 `LOOP_STATE.md` 记录迭代 6 进展。
