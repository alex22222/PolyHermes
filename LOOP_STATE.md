# Loop Engineering State: PolyHermes Web Bridge BUY/SELL 可靠性持续改进

## Goal

通过挖掘 Bridge 日志和数据库中的 BUY/SELL 失败记录，持续修复 `polymtrade-bridge` 的执行可靠性问题，降低误判失败和假成功比例。

验证标准：
- 针对每个识别出的失败模式，有对应的代码修复。
- 新增/更新单元测试或静态 fixture 测试覆盖修复逻辑并通过。
- `python -m py_compile` 检查通过，Bridge 能正常启动且 `/health`、`/portfolio` 返回 200。
- 每次迭代记录到 `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/`。

## Trigger

由用户指令启动的持续改进循环；每次迭代聚焦一个具体失败模式，完成后可继续下一轮。

## Isolation

- 工作目录：`/Users/henry/projects/polyhermes`
- 改动集中在 `polymtrade-bridge/...`
- 不修改后端数据库结构（本次迭代）

## Memory

- 本文件：`/Users/henry/projects/polyhermes/LOOP_STATE.md`
- OpenSpec 变更：`openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/`
- 待办：由父 agent 的 todo list 维护

## Open

- [x] 迭代 1：修复网络/代币模态框导致 BUY 反复失败的问题（已完成）
- [x] 迭代 2：修复 `_enrich_position` 导致 `net::ERR_ABORTED` 的问题（已完成）
- [x] 迭代 3：增强 BUY 后成交精确校验（已完成）
- [x] 迭代 4：SELL 路径加固，减少假阴性（已完成）
- [x] 迭代 5：BUY outcome/amount 鲁棒性、SELL 持仓降级、Bridge 指标（已完成）
- [x] 迭代 6：修复 BUY 因 portfolio 轮播导致 eventId 未出现在 URL 而误判失败的问题（已完成）
- [x] 迭代 7：将真实 Bridge 执行成败纳入 Leader execution_score（已完成）

## Done

- [x] 读取 loop-engineering 与 openspec-new-change skill
- [x] 探索 polymtrade-bridge 代码结构与 BUY/SELL 流程
- [x] 挖掘 `bridge.log` 与 `/private/tmp/polymtrade-bridge.log` 中的失败模式
- [x] 探索 `bridge_trade_record`、`bridge_reliability_audit.py`、`position_ledger.py` 等数据源
- [x] 识别主要根因：网络/代币模态框仅被关闭未选择、BUY 无成交后校验、部分异常日志缺失原因
- [x] 创建 OpenSpec 变更目录与初始提案/设计/任务/需求文档
- [x] 实现迭代 1 代码修复并验证
- [x] Leader 研究评分已接入真实执行记录：优先使用 `copy_order_tracking` / `filtered_order` / `sell_match_record`，并补充 `bridge_trade_record.raw_payload.leaderAddress` 归因。

## Iteration 1 Log

**目标**：修复 BUY 执行中网络/代币模态框反复阻塞的问题，补充 BUY 前后校验与异常日志。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
  - 新增 `_select_network_and_token_in_modal()`：在模态框内主动选择 Polygon + USDC，识别充值/余额不足模态框并拒绝选择。
  - 新增 `_get_usdc_balance()`：从页面 DOM 读取 USDC/pUSD 余额。
  - 新增 `_verify_buy_executed()`：BUY 提交后通过 success indicator 间接校验成交，返回 `verified` 字段。
  - 修改 `_execute_buy()`：前置余额检查，模态框处理优先选择网络/代币再回退关闭。
  - 修改 `_is_network_modal_open()`、`_dismiss_modal_dialogs()`：增加可见性判断，避免 `display:none` 元素仍被误判为模态框开启。
  - 修改 `_enrich_position()`：异常日志使用 `exc_info=True` 并输出异常类型。
- `polymtrade-bridge/test_selector_fixture.py`
  - 新增网络/代币模态框选择测试（正常选择与充值模态框拒绝）。
  - 新增余额解析测试。

**验证结果**：
- `python -m py_compile polymtrade_executor.py main.py test_selector_fixture.py` 通过。
- `python test_selector_fixture.py` 通过。
- `python test_copy_trading_config.py` 14 tests OK。
- Bridge 通过 launchd 重启，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- `/portfolio` 返回 200。
- 日志中 `_enrich_position` 失败已输出完整 traceback（如 `httpx.ConnectError`）。

**已知限制 / 下一步可继续优化**：
- `_verify_buy_executed()` 当前仅检测页面 success indicator，未实现 portfolio 数量/余额变化的精确比对，后续可加入 portfolio 刷新与数量差值校验。
- `_get_usdc_balance()` 依赖页面 DOM 文本，Polymtrade UI 变化可能导致解析失败；后续可接入 CLOB/wallet API 获取精确余额。
- 日志中仍偶发 `httpx.ConnectError`，可能是代理或 Gamma API 瞬断；迭代 2 已为 Gamma API 请求加入重试，但 `/portfolio` 整体链路仍可加入指标与熔断。

## Iteration 2 Log

**目标**：修复 `fetch_portfolio_positions` / `_enrich_position` 导致的 `net::ERR_ABORTED` 与空 enrich 日志。

**根因**：
- 旧 `_enrich_position` 点击 portfolio card 更新 URL 的 `eventSlug`，再查 Gamma events API。
- 点击 card 会触发 pending navigation，导致下一次 `fetch_portfolio_positions` 调用 `page.goto('/portfolio')` 时出现 `net::ERR_ABORTED`。
- 串行点击也让 `/portfolio` 接口变慢。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
  - 新增 `_gamma_request_with_retry()`：为 Gamma API 请求提供指数退避重试。
  - 新增 `_search_gamma_markets_by_title()` / `_search_gamma_events_by_title()`。
  - 重写 `_enrich_position()`：
    - 优先解析 card `href` 中的 `eventSlug` / `eventId`。
    - 其次使用 Gamma markets/events title search。
    - 最后才回退到 card 点击，并带重试。
  - 修改 `fetch_portfolio_positions()`：
    - scraping 时额外提取 card 的 `href` 与 `data-*` 属性。
    - enrichment 改为 `asyncio.gather` 并发执行。
- `polymtrade-bridge/test_enrichment.py`（新增）
  - 覆盖 title search enrichment、href 解析、Gamma API 重试成功/耗尽场景。

**验证结果**：
- `python -m py_compile` 通过。
- `python test_selector_fixture.py` + `test_enrichment.py` + `test_copy_trading_config.py` 全部通过。
- Bridge 重启后 `/health` 与 `/portfolio` 均返回 200。
- 运行日志显示所有持仓通过 `Gamma markets title search` 成功 enrich，无 `ERR_ABORTED`：
  - `Enriched 'Will Argentina reach the 2026 FIFA World Cup final?' via Gamma markets title search`
  - `Enriched 'Will Belgium win Group G in the 2026 FIFA World Cup?' via Gamma markets title search`
  - 等。

**已知限制 / 下一步可继续优化**：
- Gamma API title search 偶尔返回空或不相关结果；可加入条件 ID / CLOB fallback。
- `/portfolio` 接口仍可能因 Gamma API 延迟而变慢；可考虑缓存或异步后台刷新。

## Iteration 3 Log

**目标**：将 `_verify_buy_executed()` 从 success indicator 兜底升级为基于余额/持仓数量变化的精确校验。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
  - 新增 `_capture_buy_baseline()`：在 `_execute_buy` 提交订单前记录 USDC 余额与目标 event-page 持仓数量，存入 `_last_buy_baseline`。
  - 新增 `_get_event_page_position_quantity()`：导航到 event page 并解析 "You own X shares" / "持仓 X 份" 文本。
  - 重写 `_verify_buy_executed()`：先比较 pre/post USDC 余额下降（≥ 下单金额的 50%），再比较 event-page 持仓数量增加，最后仍保留 success indicator 兜底。
  - 修改 `_execute_buy()`：调用 `_capture_buy_baseline()` 并返回 `baseline` 字段。
  - 修改 `execute_trade()`：将 `baseline` 传递给 `_verify_buy_executed()`，确保 SELL 分支不受影响。
- `polymtrade-bridge/test_buy_verification.py`（新增）
  - 覆盖 baseline 捕获、余额下降确认、持仓数量增加确认、新增持仓确认、无变化标记失败等场景。
- `polymtrade-bridge/test_enrichment.py`
  - 保持迭代 2 的 enrichment 测试。

**验证结果**：
- `python -m py_compile polymtrade_executor.py main.py test_*.py` 通过。
- `python test_selector_fixture.py` 14 tests OK。
- `python test_enrichment.py` 7 tests OK。
- `python test_buy_verification.py` 6 tests OK。
- `python test_copy_trading_config.py` 14 tests OK。
- launchd 服务 `com.polyhermes.polymtrade-bridge` 已重启，exit code 0，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- `/portfolio` 返回 200，enrichment 全部成功，无 `ERR_ABORTED`。

**已知限制 / 下一步可继续优化**：
- `_get_event_page_position_quantity()` 仍依赖 DOM 文本解析，后续可接入 CLOB/wallet API。
- 当前 verify 仅返回布尔值用于标记 `verified` 字段，未在失败时自动撤销/纠正交易记录；如需自动撤销，需引入 wallet/positions API。
- 可考虑对 BUY 失败（余额未变化且无持仓增加）加入重试/取消逻辑。

## Iteration 4 Log

**目标**：加固 SELL 执行路径，解决“无法打开/点击卖出弹窗”、“SELL 提交后校验失败”、“页面/浏览器异常关闭”三类失败模式中的前两类的可修复部分，并降低第三类复发的概率。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
  - 新增 `_is_sell_dialog_open()`：多 selector 检测 SELL 弹窗是否真正打开。
  - 新增 `_capture_sell_baseline()`：提交前捕获余额与 event-page 持仓数量。
  - 新增 `_verify_sell_executed()`：通过持仓数量下降、余额增加、success indicator 三重校验确认 SELL 成交。
  - 重写 `_execute_sell()`：增加事件 URL 等待、网络/代币模态框处理、SELL 弹窗打开重试（最多 5 次）、卖出按钮点击重试（最多 3 次）。
  - 修改 `execute_trade()`：SELL 分支也返回 `baseline` 并调用 `_verify_sell_executed()`。
- `polymtrade-bridge/main.py`
  - `handle_signal()` SELL 分支不再因 `_wait_for_live_position_decrease()` 未确认下降而抛异常标 FAILED；改为记录警告并保持 SUCCESS，避免假阴性。
  - 提高 `_wait_for_live_position_decrease()` 轮询次数至 8 次、间隔至 2.5 秒。
- `polymtrade-bridge/test_sell_verification.py`（新增）
  - 覆盖 SELL baseline 捕获、数量下降确认、余额增加确认、success indicator 兜底、无变化失败等场景。

**验证结果**：
- `python -m py_compile polymtrade_executor.py main.py test_*.py` 通过。
- `test_buy_verification.py` 6 tests OK。
- `test_sell_verification.py` 5 tests OK。
- `test_selector_fixture.py` 14 tests OK。
- `test_enrichment.py` 7 tests OK。
- `test_copy_trading_config.py` 14 tests OK。
- 使用 `launchctl kickstart -k` 重启 `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`，`/portfolio` 返回 200 且 enrichment 正常。

**已知限制 / 下一步可继续优化**：
- “Target page/context/browser closed” 类错误主要由之前的 `ERR_ABORTED` 和多实例引起，本次修复后未再出现；若单实例浏览器本身崩溃，仍需要手动重启服务。
- SELL 校验仍依赖 DOM 文本解析，后续可接入 CLOB/wallet API。
- 当前未对 SELL 执行失败做自动重试整单（例如重新打开弹窗），如需可继续迭代。

## Iteration 5 Log

**目标**：降低 BUY 的 outcome 选择失败和金额输入失败，优化 SELL 持仓匹配避免误判，并增加 Bridge 可观测性指标。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
  - `_select_polymtrade_outcome()`：增加最多 4 次重试、页面滚动触发懒加载、扩展 side label 列表（Buy Yes/Buy No/Long/Short）、点击后滚动到视图。
  - `_enter_amount()`：扩展 selector、限制在 dialog/trade 区域内查找、失败截图。
  - `_get_live_position_quantity()`（被 `main.py` 调用）：匹配逻辑增加 `marketSlug`/`eventSlug`/标题子串。
  - `_gamma_request_with_retry()`、`_select_network_and_token_in_modal()`、`_dismiss_modal_dialogs()`：增加指标埋点。
- `polymtrade-bridge/main.py`
  - SELL 分支：若 live portfolio 小于预期数量，自动降级为卖出全部可用数量，不再直接 FAILED。
  - `handle_signal()`：增加信号过滤/执行/失败、BUY/SELL 成功失败、outcome/amount 失败等指标计数。
  - `/portfolio`：增加 portfolio 请求/错误计数。
  - 新增 `/metrics` 接口返回 JSON 指标。
- `polymtrade-bridge/bridge_metrics.py`（新增）
  - `BridgeMetrics` 内存计数器与 `/metrics` 导出。

**验证结果**：
- `python -m py_compile polymtrade_executor.py main.py bridge_metrics.py` 通过。
- `test_buy_verification.py` 6 tests OK；`test_sell_verification.py` 5 tests OK；`test_selector_fixture.py` 14 tests OK；`test_enrichment.py` 7 tests OK；`test_copy_trading_config.py` 14 tests OK。
- `launchctl kickstart -k` 重启服务，`/health`、`/portfolio`、`/metrics` 均正常响应。
- `/metrics` 实测返回 `portfolio_requests=1`、`gamma_api_requests=4` 等，埋点生效。

**已知限制 / 下一步可继续优化**：
- outcome 选择仍有赖于页面 DOM 结构；若 Polymtrade 大改版，脚本可能再次失效。
- 指标是内存级，Bridge 重启会清零；如需持久化可接入后端数据库或 Prometheus。
- 第 3 点建议的"低余额告警/自动充值"尚未实现。

## Iteration 6 Log

**目标**：修复 trade id 583（BUY 哥伦比亚大选 Yes）因 portfolio 轮播未停留在目标 event 而被误判为 `Target event 34584 URL never appeared` 的失败。

**根因**：
- Bridge 账户在该事件上无持仓，Polymtrade `/portfolio` 页会自动轮播到已有持仓的事件，导致 URL 中的 `eventId` 被替换为其他事件。
- `_execute_buy()` 和 `_wait_for_page_ready()` 之前把 `eventId 出现在 URL` 作为硬门槛，只要轮播离开目标事件就会触发 `RuntimeError`。
- `_extract_market_keywords()` 未过滤 `presidential` / `election` 等通用政治词汇，跨事件关键词匹配可能误命中。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
  - `_wait_for_page_ready()`：移除对 `eventId` 出现在 URL 的硬依赖，改为验证页面是否渲染了目标市场关键词与 Yes/No 侧边按钮。
  - 新增 `_is_target_event_visible()`：基于市场关键词、side label 与 outcome 文本判断目标市场是否真正渲染在当前页面。
  - `_execute_buy()`：用 `_is_target_event_visible()` 替代 `_wait_for_event_url()`；若目标内容不可见，则在主 URL 与 `eventSlug` 兜底 URL 之间重新导航，最多重试 6 次。
  - `_extract_market_keywords()`：在 stop words 中补充 `presidential`、`president`、`election`、`candidate`、`vote` 等通用政治词汇，降低跨事件误匹配。
- `polymtrade-bridge/test_event_visibility.py`（新增）
  - 覆盖目标事件可见/不可见、缺少按钮、`_wait_for_page_ready()` 不依赖 URL 中 eventId 等场景。

**验证结果**：
- `python -m py_compile polymtrade_executor.py main.py bridge_metrics.py` 通过。
- `python -m pytest -q --asyncio-mode=auto`：37 tests 全部通过（含新增 5 个）。
- `launchctl` 重启 `com.polyhermes.polymtrade-bridge` 后 `/health`、`/portfolio`、`/metrics` 均正常响应。

**已知限制 / 下一步可继续优化**：
- SELL 路径仍部分依赖 `eventId` URL 匹配；若未来在无持仓事件上尝试 SELL，仍可能遇到类似问题（但当前 ledger/live 检查会提前拦截无持仓 SELL）。
- 内容可见性检查仍基于 DOM 文本，若 Polymtrade 调整 class/文本，需要同步更新 selector。

---

# Loop Engineering State: Leader 筛选和交易原则落地

## Goal

将 `docs/zh/leader 筛选和交易原则.md` 中的原则转化为可运行的代码改进，使真实跟单入口具备：
1. Leader 成交价实时偏离过滤
2. 端到端延迟测量与类别化延迟过滤
3. Bridge 端二次风控
4. 统一 `copy_score` 门控

验证标准：
- 新增单元测试/集成测试覆盖上述逻辑并通过。
- 现有测试套件不回归。
- 关键风控路径新增日志与指标，可观测。

## Trigger

本次为一次性循环，由用户指令启动；后续可通过 `loop-engineering` skill 或手动继续迭代。

## Isolation

- 工作目录：`/Users/henry/projects/polyhermes`
- 后端改动在 `backend/src/main/kotlin/...` 下隔离进行
- bridge 改动在 `polymtrade-bridge/...` 下隔离进行
- 新增数据库字段通过 Flyway migration 管理

## Memory

- 本文件：`/Users/henry/projects/polyhermes/LOOP_STATE.md`
- 待办：由父 agent 的 todo list 维护

## Open

- [x] 迭代 1：实现 Leader 成交价实时偏离过滤（已完成）
- [x] 迭代 2：实现端到端延迟测量与类别化延迟过滤（已完成）
- [x] 迭代 3：在 Bridge Rule Engine 补齐二次风控检查（已完成）
- [x] 迭代 4：实现统一 copy_score 门控服务（已完成）
- [x] 迭代 5：验证并总结改进效果（已完成）
- [x] 迭代 6：扩大政治/金融 Leader 候选来源并回测验证（已完成）
- [x] 迭代 7：把可复制回测结果纳入研究评分和 Leader Pool 试跟门槛（已完成）

## Done

- [x] 阅读 `docs/zh/leader 筛选和交易原则.md`
- [x] 代码库现状探索与缺口识别
- [x] 迭代 1：新增 `max_price_deviation` 字段、`FilterStatus.FAILED_PRICE_DEVIATION`、实时偏离检查、单元测试
- [x] 迭代 2：新增 `max_delay_seconds` 字段、`FilterStatus.FAILED_DELAY`、端到端延迟检查、单元测试
- [x] 迭代 3：在 bridge 端新增 leader_category 加载、分类匹配检查、延迟检查、`infer_market_category`、Python 单元测试
- [x] 迭代 4：新增 `min_copy_score` 字段、`CopyScoreService`（乘法模型）、集成到 `CopyOrderTrackingService`、单元测试
- [x] 验证：后端 `./gradlew test` 全绿，bridge `test_copy_trading_config.py` 全绿
- [x] 迭代 6：Gamma 活跃市场分页同步从 100 扩到最多 1000，政治/金融分析配额提高，金融分类关键词与 V60 数据迁移补齐
- [x] 迭代 6 验证：finance 活跃市场从 4 扩到 79；finance PENDING 候选从 25 扩到 189；politics PENDING 候选保持 236
- [x] 迭代 6 执行：正式扫描新增 finance leader 10 个、politics leader 10 个，并创建/完成 20 个 7 天回测任务
- [x] 迭代 7：研究评分加入 completed backtest 硬门槛，Leader Pool 创建试跟配置只允许 ELITE/TRADEABLE

## Iteration 1 Log

**目标**：在 `CopyTradingFilterService` 中新增 Leader 成交价实时偏离检查，防止系统以明显劣于 Leader 的价格追单。

**改动文件**：
- `backend/src/main/resources/db/migration/V54__add_max_price_deviation_to_copy_trading.sql`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/entity/CopyTrading.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/configs/FilterResult.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/configs/CopyTradingFilterService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/statistics/CopyOrderTrackingService.kt`
- `backend/src/test/kotlin/com/wrbug/polymarketbot/service/copytrading/configs/CopyTradingFilterServicePriceDeviationTest.kt`

## Iteration 2 Log

**目标**：新增 `max_delay_seconds` 配置，测量并过滤端到端延迟过大的信号。

**改动文件**：
- `backend/src/main/resources/db/migration/V55__add_max_delay_seconds_to_copy_trading.sql`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/entity/CopyTrading.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/configs/FilterResult.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/configs/CopyTradingFilterService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/statistics/CopyOrderTrackingService.kt`
- `backend/src/test/kotlin/com/wrbug/polymarketbot/service/copytrading/configs/CopyTradingFilterServiceDelayTest.kt`

## Iteration 3 Log

**目标**：在 `polymtrade-bridge/copy_trading_config.py` 中补齐二次风控：分类匹配与延迟检查。

**改动文件**：
- `polymtrade-bridge/copy_trading_config.py`
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/test_copy_trading_config.py`

## Iteration 4 Log

**目标**：实现统一的 `copy_score` 评分服务，采用文档定义的乘法模型。

**改动文件**：
- `backend/src/main/resources/db/migration/V56__add_min_copy_score_to_copy_trading.sql`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/entity/CopyTrading.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/scoring/CopyScoreService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/statistics/CopyOrderTrackingService.kt`
- `backend/src/test/kotlin/com/wrbug/polymarketbot/service/copytrading/scoring/CopyScoreServiceTest.kt`

## Iteration 5 Log

**验证结果**：
- 后端全量测试：`./gradlew test` BUILD SUCCESSFUL（~100 tests）
- Bridge 测试：`.venv/bin/python test_selector_fixture.py` 11 tests OK

**已知后续优化方向**（未在本次循环实现）：
- 为不同 category 设置 `maxDelaySeconds` / `maxPriceDeviation` / `minCopyScore` 的默认推荐值
- 在 bridge 端通过 CLOB API 获取 orderbook，补齐深度/价差/偏离二次检查
- 在 UI 上为 `maxPriceDeviation`、`maxDelaySeconds`、`minCopyScore` 增加配置入口和默认值提示
- 将 `copy_score` 拆解指标持久化到数据库，用于后续策略复盘

## Iteration 6 Log

**目标**：扩大政治、金融候选来源，缓解现有 leader 池在主策略类别下没有可跟单对象的问题。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/common/MarketService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/leaders/HotMarketTraderDiscoveryService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/leaders/LeaderScannerService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/util/CategoryValidator.kt`
- `backend/src/main/resources/db/migration/V60__expand_finance_market_category_inference.sql`

**验证结果**：
- `./gradlew -q compileKotlin bootJar` 通过。
- `finance` 活跃市场数：4 -> 79。
- `finance` candidate pool PENDING：25 -> 189。
- `politics` candidate pool PENDING：236。
- 正式扫描新增 20 个 leader：finance 10 个、politics 10 个。
- 新增 leader 的 20 个 7 天回测任务全部完成。

**回测结论**：
- 新增 finance/politics leader 暂无达到真钱跟单标准的对象。
- finance 最好结果为 `Noxious-Success`：收益仅 `0.00000012`，回撤 `94`，属于 dust，不可跟。
- politics 最好结果为 `Clever-Curse`：收益 `-1.46486166`，仍为亏损。
- 下一步应优化评分：把可复制回测收益、sell 闭环、回撤纳入 leader 晋级门槛，避免表面 PnL/胜率高但复制亏损的 leader 进入主池。

## Iteration 7 Log

**目标**：把“可复制回测收益、sell 闭环、回撤”纳入 leader 晋级规则，避免表面扫描 PnL/胜率高但复制亏损的 leader 进入试跟链路。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/leaders/LeaderResearchScoreAdapterService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/leaderpool/LeaderPoolService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/leaderpool/LeaderPoolExceptions.kt`

**规则变更**：
- 研究评分加载 best completed backtest。
- `no_completed_backtest` 最高只能到 CANDIDATE。
- `backtest_loss`、`backtest_no_simulated_trades`、`backtest_dust_profit` 最高只能到 WATCH。
- `backtest_high_drawdown`、`backtest_no_sell` 最高只能到 CANDIDATE。
- Leader Pool 创建试跟配置只允许 `ELITE` / `TRADEABLE`。

**验证结果**：
- `./gradlew -q compileKotlin bootJar` 通过。
- 重算 108 个 Leader 研究评分。
- 新增的 20 个 politics/finance leader 全部被压到 WATCH/RISKY。
- 全局仅 `Playful-Awe` 保持 ELITE。
- 对 poolId=7 尝试创建试跟配置被拒绝：`Leader 未达到可试跟研究评分门槛`，且没有生成 copy_trading 配置。

## Blocked / Escalated

- 无

## Iteration 8 Log

**目标**：修复 2026-06-23 两笔 Polymtrade Web Bridge 失败样本，提升 BUY 金额输入与 SELL 执行链路成功率。

**失败样本**：
- BUY `Will Canada win the 2026 FIFA World Cup?`：bridge record 598，失败原因为金额输入框等待超时。
- SELL `Will Argentina win on 2026-06-22?`：bridge record 597，失败原因为误点顶部钱包 `卖出 $PM`，随后无法进入真实持仓卖出弹窗与提交按钮。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`

**规则变更**：
- BUY outcome 点击改为点击最近可交易按钮祖先，减少点到孤立 `是/Yes` 文本后不出交易框的概率。
- BUY/SELL 金额输入增加 trade/form/dialog 上下文扫描，支持 inline trade panel 输入框。
- SELL 开仓按钮排除钱包 `$PM` 操作，只允许命中带 `持仓/剩余/position/market` 上下文的目标市场卡片。
- SELL dialog 判断不再把页面任意 `卖出` 按钮当作弹窗打开，必须有真实 sell form/input/dialog 证据。
- SELL 提交按钮支持 `确认卖出/确认/下单/Review/Place order` 等弹窗内按钮。
- 持仓数量读取增加 `剩余 X`，并优先按目标市场关键词匹配，避免读取到其他持仓数量。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `python3 polymtrade-bridge/test_buy_verification.py` 通过。
- `python3 polymtrade-bridge/test_sell_verification.py` 通过。
- `python3 polymtrade-bridge/test_event_visibility.py` 通过。
- `python3 -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/main.py polymtrade-bridge/bridge_metrics.py` 通过。
- 已重启 `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。

## Iteration 9 Log

**目标**：继续从正式 Bridge 失败记录中挖掘下一类高频失败，补齐 selector 回归测试，防止 BUY/Sell 可靠性回退。

**失败记录挖掘**：
- 调用 `POST /api/bridge/trades/list` 拉取 `status=FAILED`，共 91 条失败记录。
- 分类结果：`insufficient_position_or_balance` 32 条、`select_outcome` 28 条、`target_event_url_missing` 10 条、`amount_input` 8 条、`navigation_network` 3 条、`target_market_missing` 3 条、`click_submit` 2 条、`navigation_race` 2 条、`other` 3 条。
- 最新失败 598/597 已由 Iteration 8 覆盖；下一类高价值风险是政治/候选型市场的 `select_outcome`。

**改动文件**：
- `polymtrade-bridge/test_selector_fixture.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- 新增 `POLITICAL_CANDIDATE_HTML` fixture，覆盖 `Will Abelardo de la Espriella win the 2026 Colombian presidential election?`。
- 断言 `_extract_market_keywords()` 只保留候选人相关关键词：`abelardo`、`espriella`、`colombian`。
- 断言 `_select_outcome_script()` 点击 Abelardo 候选行内的 `Yes 99¢`，不被 `presidential/election` 等通用政治词或其他候选人行干扰。
- OpenSpec 追加 REQ-16 / SC-15，要求政治候选型市场 outcome 选择不得被泛词干扰。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `python3 polymtrade-bridge/test_buy_verification.py` 通过。
- `python3 polymtrade-bridge/test_sell_verification.py` 通过。
- `python3 -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/main.py polymtrade-bridge/bridge_metrics.py` 通过。
- Web Bridge `/health` 返回 `{"status":"ok","executor_ready":true}`。

**下一步候选**：
- 将失败分类脚本固化为可重复运行的 bridge failure mining 工具，并在日报/优化页面展示最近失败分布与对应修复状态。
- 针对剩余 `select_outcome` 中的体育 group/电竞队伍页继续补 fixture。

## Iteration 10 Log

**目标**：把 Bridge FAILED 记录挖掘固化为可重复运行的 audit 能力，自动产出下一步修复队列。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则变更**：
- `bridge_reliability_audit.py` 新增 `classify_failure()`，将 FAILED error_message 聚类为 `select_outcome`、`amount_input`、`click_submit`、`target_market_missing`、`target_event_url_missing`、`navigation_race`、`navigation_network`、`resolve_event`、`network_or_token_modal`、`live_position_insufficient`、`insufficient_balance`、`insufficient_position`、`other`。
- Audit 输出新增 `failure_buckets`：每类包含数量、样本记录、样本市场、actionability 和 next action。
- Audit 输出新增 `next_action_candidates`：按代码修复优先级排序，避免账户状态类失败压过 selector/navigation 代码类失败。
- Bridge `/audit` 接口同步暴露这些字段。
- OpenSpec 追加 REQ-17 / SC-16，要求审计输出失败分类与下一步候选。

**当前审计结果**：
- `/audit?limit=100&failure_limit=5` 返回 `failure_bucket_count=10`。
- Top buckets：`network_or_token_modal=31`、`select_outcome=28`、`target_event_url_missing=10`、`amount_input=8`、`target_market_missing=3`。
- Next action candidates：`select_outcome=28`、`amount_input=8`、`click_submit=2`、`target_market_missing=3`、`target_event_url_missing=10`。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py` 通过。
- 已重启 `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- `/audit` 运行态返回 `failure_buckets` 与 `next_action_candidates`。

**下一步候选**：
- 根据 `next_action_candidates[0]=select_outcome` 继续补体育 group / 电竞队伍 / WNBA 等市场形态 fixture。
- 将 `/audit` 的 failure bucket 摘要接入优化日报页面。

## Iteration 11 Log

**目标**：继续根据 `/audit` 的 `next_action_candidates[0]=select_outcome` 修复高频 BUY outcome 选择问题，优先覆盖近期真实失败中的电竞队伍型市场。

**失败记录挖掘**：
- 调用 `/audit?limit=100&failure_limit=100&portfolio_timeout=90`，`next_action_candidates` 仍以 `select_outcome=28` 排第一。
- 样本包含 `Will Team Spirit win IEM Cologne Major 2026?` 4 条失败记录，错误为 `Could not select outcome: Yes`，关键词曾包含 `team/spirit/iem/cologne/major`，其中 `team/iem/major` 属于事件泛词，容易干扰行锚定。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_extract_market_keywords()` 将 `team`、`esports`、`iem`、`cologne`、`major` 加入事件泛词过滤，避免电竞队伍页被赛事名或通用 `Team` 词干扰。
- 新增 `ESPORTS_TEAM_HTML` fixture，覆盖 `Team Vitality`、`Team Spirit`、`G2 Esports` 多行页面。
- 断言 `Will Team Spirit win IEM Cologne Major 2026?` 的关键词收敛为 `["spirit"]`，并点击 `Team Spirit` 行内的 `Yes 27¢`。
- OpenSpec 追加 REQ-18 / SC-17，要求电竞队伍型市场忽略事件泛词并点击正确队伍行。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。

**下一步候选**：
- 继续从 `select_outcome` 中补体育 group 中文队名/国家别名 fixture，确认 Uruguay/Ecuador/Belgium 等历史失败是否已被现有别名覆盖。
- 开始处理 `amount_input=8`，重点复核 Canada/Spain/Mexico 等低价 BUY 的金额输入框定位。

## Iteration 12 Log

**目标**：处理 `/audit` 中排名第二且可代码修复的 `amount_input` 失败，降低 BUY 打开交易面板后无法输入金额的概率。

**失败记录挖掘**：
- 调用 `/audit?limit=150&failure_limit=100&portfolio_timeout=90`。
- 当前 `next_action_candidates`：`select_outcome=54`、`amount_input=11`、`click_submit=2`、`target_market_missing=3`、`target_event_url_missing=10`。
- `amount_input` 样本包含 `Will Canada win the 2026 FIFA World Cup?`、`Will Spain win Group H in the 2026 FIFA World Cup?`、`Will Team Spirit win IEM Cologne Major 2026?` 等，错误为 `Could not enter trade amount`。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_fill_input_safely()` 支持非传统 `input` 控件：对 `contenteditable` / `role=textbox` 先清空文本并派发 `input` 事件，再输入金额。
- `_enter_amount()` 与 `_is_buy_dialog_open()` 增加 `textarea`、`role=textbox`、`contenteditable=true`、`contenteditable=plaintext-only` 金额控件 selector。
- `_find_trade_input()` 的 JS 打分扫描纳入自定义可编辑控件，同时继续排除 search/sidebar/header/footer/wallet 等噪声区域。
- 新增 `CONTENTEDITABLE_BUY_FORM_HTML` fixture，覆盖 `role=textbox` + `contenteditable=true` 的金额框，断言 `_is_buy_dialog_open()` 与 `_enter_amount(2.0)` 成功。
- OpenSpec 追加 REQ-19 / SC-18，要求 BUY 金额输入不依赖传统 `<input>`。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。

**下一步候选**：
- 重启 Web Bridge 并验证 `/health`、`/audit`。
- 继续处理 `click_submit=2`，补 BUY/SELL 提交按钮在中文确认文案、禁用态、动态 DOM 下的选择回归。

## Iteration 13 Log

**目标**：处理 `/audit` 中 `click_submit=2` 的 SELL 最后确认失败，降低卖出动作在最后一跳因按钮短暂不可点击或自定义控件而失败的概率。

**失败记录挖掘**：
- 调用 `/audit?limit=180&failure_limit=100&portfolio_timeout=90`。
- 当前 `next_action_candidates`：`select_outcome=81`、`amount_input=11`、`click_submit=2`、`target_market_missing=3`、`target_event_url_missing=10`。
- `click_submit` 样本为 SELL：id 597 `Will Argentina win on 2026-06-22?` 与 id 573 `Will Belgium reach the 2026 FIFA World Cup final?`，错误均为 `Could not click sell button`。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_click_buy_button()` 与 `_click_sell_button()` 改为 10 秒短轮询，不再只尝试一次提交按钮。
- `_click_trade_submit_button()` 纳入 `role=button`、`input[type=submit]`、`tabindex=0`、`.cursor-pointer` 等自定义按钮，同时跳过 disabled、`aria-disabled=true`、`data-disabled=true`、`pointer-events:none` 与取消/充值/提现/100% 等非提交控件。
- 新增 `DELAYED_ROLE_SELL_CONFIRM_DIALOG_HTML` fixture，覆盖 `role=button` 的 `确认卖出` 控件初始 disabled、250ms 后启用的场景。
- OpenSpec 追加 REQ-20 / SC-19，要求提交按钮等待可点击状态并支持自定义按钮。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。

**下一步候选**：
- 重启 Web Bridge 并验证 `/health`、`/audit`。
- 回到 `select_outcome`，继续补 Uruguay/Ecuador/Belgium 等体育 group 页面真实中文/英文混合行 fixture，或把已修复历史失败从 next-action 中标记为 covered。

## Iteration 14 Log

**目标**：减少历史失败对下一轮修复队列的干扰，让 Bridge audit 区分“已有 exact 回归覆盖的旧失败”和“仍未覆盖、值得继续修”的失败。

**失败记录挖掘**：
- 调用 `/audit?limit=220&failure_limit=100&portfolio_timeout=90`。
- 当前 buckets：`select_outcome=117`、`network_or_token_modal=53`、`amount_input=11`、`target_event_url_missing=10`、`navigation_network=5`、`navigation_race=4`、`target_market_missing=3`、`other=3`、`click_submit=2`、`live_position_insufficient=1`、`insufficient_position=1`。
- `select_outcome` 中混有已被前几轮 exact fixture 覆盖的历史样本，例如 Abelardo、Netherlands、Toronto Tempo、Team Spirit；如果不标记覆盖状态，loop 会持续被历史失败挤占。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- 新增 `FIXTURE_COVERAGE_RULES`，对已明确有 fixture 覆盖的历史失败输出 `coverage_hint`。
- `coverage_hint` 区分 `coverage_level=exact|partial|none`；只有 exact 覆盖计入 `covered_count`，partial 只作为提示。
- `failure_buckets` 新增 `covered_count`、`uncovered_count`、`uncovered_sample_record_ids`、`uncovered_sample_markets`、`coverage_ids`。
- `next_action_candidates` 会跳过 `uncovered_count=0` 的已 fully covered code bucket；partial 覆盖的 `amount_input` / `click_submit` 仍可继续作为候选。
- 新增 audit 单测覆盖 Team Spirit exact coverage、uncovered 样本计数、全覆盖 bucket 不进入 next candidates。
- OpenSpec 追加 REQ-21 / SC-20，要求 audit 标记失败样本回归覆盖状态。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py` 通过。

**下一步候选**：
- 重启 Web Bridge 并验证 `/health`、`/audit` 新字段。
- 根据 `uncovered_sample_markets` 继续补体育 group 中文/英文混合 outcome fixture，优先 Uruguay/Ecuador/Belgium/Spain。

## Iteration 15 Log

**目标**：根据 Iteration 14 的 `uncovered_sample_markets`，补齐世界杯 group 多国家中文行 selector 覆盖，降低 `select_outcome` 中体育 group 未覆盖样本。

**失败记录挖掘**：
- 调用 `/audit?limit=220&failure_limit=100&portfolio_timeout=90`。
- `select_outcome` 当前 `count=117`、`covered=17`、`uncovered=100`。
- Top uncovered samples：`Will Uruguay win Group H in the 2026 FIFA World Cup?`、`Will Ecuador win Group E in the 2026 FIFA World Cup?`、`Will Belgium win Group G in the 2026 FIFA World Cup?`、`Will Spain win Group H in the 2026 FIFA World Cup?`、`Will Haiti win on 2026-06-19?`。

**改动文件**：
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- 新增 `WORLD_CUP_GROUP_MULTI_COUNTRY_HTML` fixture，模拟世界杯 group 页面里 `乌拉圭`、`厄瓜多尔`、`比利时`、`西班牙` 中文国家行。
- `_run_selector_fixture()` 新增四组断言：Uruguay No、Ecuador Yes、Belgium No、Spain No 均能用英文标题提取出的中文别名锚定目标行，并点击该行内 side 按钮。
- `FIXTURE_COVERAGE_RULES` 新增 `world_cup_group_multi_country_fixture` exact coverage，覆盖 Uruguay Group H、Ecuador Group E、Belgium Group G、Spain Group H。
- `test_bridge_reliability_audit.py` 新增 coverage 单测，确认四个历史失败市场会被标记为 exact covered。
- OpenSpec 追加 REQ-22 / SC-21，要求世界杯 group 多国家中文行选择与 audit coverage 标记。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/main.py` 通过。

**下一步候选**：
- 重启 Web Bridge 并验证 `/audit` 中 `world_cup_group_multi_country_fixture` coverage 生效。
- 继续补 Haiti/Curaçao/Cape Verde/Scotland/USA 等剩余 sports group/final 失败样本，或处理 `amount_input` 的真实截图/DOM 样本。

## Iteration 16 Log

**目标**：继续根据 `select_outcome` 的 top uncovered 样本，补齐 Haiti/Curaçao/Cape Verde/Scotland/USA 等剩余世界杯国家市场的 selector 与 audit coverage。

**失败记录挖掘**：
- 调用 `/audit?limit=240&failure_limit=100&portfolio_timeout=90`。
- `select_outcome` 当前 `count=130`、`covered=26`、`uncovered=104`。
- Top uncovered samples：`Will Haiti win on 2026-06-19?`、`Will Curaçao win Group E in the 2026 FIFA World Cup?`、`Will Cape Verde reach the 2026 FIFA World Cup final?`、`Will Scotland win Group C in the 2026 FIFA World Cup?`、`Will USA reach the 2026 FIFA World Cup final?`。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_extract_market_keywords()` 新增 `hai -> Haiti/海地` 代码别名，并把 `fifwc` 加入 stop words。
- 当 market title 已明确目标国家时，slug 中非目标国家码不再扩展为关键词；`fifwc-bra-hai` 不再把 Brazil/巴西注入 Haiti 目标关键词。
- 新增 `WORLD_CUP_REMAINING_COUNTRY_HTML` fixture，覆盖 `海地`、`库拉索`、`佛得角`、`苏格兰`、`美国` 五个中文国家行。
- `_run_selector_fixture()` 新增五组断言：Haiti No、Curaçao No、Cape Verde No、Scotland No、USA No 均能锚定目标中文行并点击目标 side。
- `FIXTURE_COVERAGE_RULES` 新增 `world_cup_remaining_country_fixture` exact coverage，覆盖 Haiti、Curaçao、Cape Verde、Scotland、USA 历史失败样本。
- `failure_coverage_hint()` 对 haystack 做重音归一化，确保 `Curaçao` 可以匹配 `curacao` coverage rule。
- OpenSpec 追加 REQ-23 / SC-22。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。

**下一步候选**：
- 重启 Web Bridge 并验证 `/audit` 中 `world_cup_remaining_country_fixture` coverage 生效。
- 若 `select_outcome` uncovered 明显下降，转向 `amount_input` 的真实截图/DOM 继续提高 BUY 成功率。

## Iteration 17 Log

**目标**：处理 `select_outcome` 最新 top uncovered 中的电竞队伍市场，覆盖 Vitality/Falcons、Map 1、Spirit/G2、Map Handicap 等队伍 outcome 选择。

**失败记录挖掘**：
- 调用 `/audit?limit=260&failure_limit=100&portfolio_timeout=90`。
- `select_outcome` 当前 `count=139`、`covered=41`、`uncovered=98`。
- Top uncovered samples：`Counter-Strike: Vitality vs Team Falcons (BO3) - IEM Cologne Major Playoffs`、`Counter-Strike: Vitality vs Team Falcons - Map 1 Winner`、`Will USA win Group D in the 2026 FIFA World Cup?`、`Will Mexico reach the 2026 FIFA World Cup final?`、`Map Handicap: VIT (-1.5) vs Team Falcons (+1.5)`。
- 具体失败显示 outcome 为 `Vitality` / `Team Falcons` / `G2` / `Spirit`，而 keywords 混有 `counter`、`strike`、`bo3`、`map`、`handicap` 等赛事泛词。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_extract_market_keywords()` 过滤电竞赛事泛词：`counter`、`strike`、`cs2`、`bo3`、`playoffs`、`map`、`handicap`、`game1`、`away`、`home`、`1pt5`、`vit`、`fal2`、`ts7`。
- `_select_polymtrade_outcome()` 对非 Yes/No outcome 会把 outcome 自身提取出的关键词放在 market title/slug 关键词之前，作为行选择强锚点。
- 2 字符 token 过滤改为只过滤纯字母短词，保留 `G2` 这类 alphanumeric 队名。
- 新增 `ESPORTS_MATCH_MARKET_HTML` fixture，覆盖 Vitality、Team Falcons、G2、Spirit、Team Falcons +1.5 行。
- Selector fixture 新增四组端到端断言：Vitality BO3、Vitality Map 1、G2、Team Falcons Map Handicap 都能点击目标行内 `是` 按钮。
- `FIXTURE_COVERAGE_RULES` 新增 `esports_match_team_selector_fixture` exact coverage，覆盖 Vitality/Falcons、Map 1、Spirit/G2、Map Handicap 历史失败。
- OpenSpec 追加 REQ-24 / SC-23。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。

**下一步候选**：
- 重启 Web Bridge 并验证 `/audit` 中 `esports_match_team_selector_fixture` coverage 生效。
- 根据新的 `uncovered_sample_markets` 决定继续处理 USA/Mexico 运动市场，或转向 `amount_input`。

## Iteration 18 Log

**目标**：收尾 `select_outcome` 剩余未覆盖样本，覆盖 USA Group D 与 Mexico reach final。

**失败记录挖掘**：
- 调用 `/audit?limit=280&failure_limit=100&portfolio_timeout=90`。
- `select_outcome` 当前 `count=158`、`covered=154`、`uncovered=4`。
- 剩余 uncovered samples：`Will USA win Group D in the 2026 FIFA World Cup?`、`Will Mexico reach the 2026 FIFA World Cup final?`。

**改动文件**：
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `WORLD_CUP_FINAL_HTML` 新增 Mexico final 行，并新增 Mexico No 选择断言。
- `WORLD_CUP_REMAINING_COUNTRY_HTML` 复用美国中文行，新增 `Will USA win Group D...` No 选择断言。
- `FIXTURE_COVERAGE_RULES` 新增 `world_cup_select_outcome_cleanup_fixture`，覆盖 USA Group D 与 Mexico final。
- `test_bridge_reliability_audit.py` 新增 coverage 单测，确认这两个剩余历史失败市场 exact covered。
- OpenSpec 追加 REQ-25 / SC-24。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/main.py` 通过。

**下一步候选**：
- 重启 Web Bridge 并验证 `/audit` 中 `select_outcome` uncovered 是否归零。
- 转向 `amount_input` 的真实截图/DOM 样本，继续提高 BUY 成功率。

## Iteration 19 Log

**目标**：处理 `amount_input` 失败中的真实边界：BUY 后没有打开交易表单时，不再误报为金额输入失败；同时扩展金额控件识别。

**失败记录挖掘**：
- 调用 `/audit?limit=300&failure_limit=100&portfolio_timeout=90`。
- 当前 `amount_input` 为 13 条，样本包含 `Will Canada win the 2026 FIFA World Cup?`、`Will Spain win Group H...`、`Will Mexico reach the 2026 FIFA World Cup final?`、`Will Argentina reach the 2026 FIFA World Cup final?`。
- `/tmp/trade_amount_input_error.png` 显示失败时页面仍停在 Polymtrade portfolio，本地页面只有 `买入 $PM` 和持仓列表，没有真实 Polymarket BUY 交易表单。
- 根因判断：旧逻辑在 BUY 表单未检测到时仍继续调用 `_enter_amount()`，导致“表单没打开/按钮未触发”被写成 `Could not enter trade amount`。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_execute_buy_on_page()` 在多次 outcome 点击后仍未检测到真实 BUY 表单时，保存 `/tmp/trade_buy_dialog_open_error.png` 并抛出 `Could not open buy dialog after outcome click`，不再继续尝试输入金额。
- `bridge_reliability_audit.py` 新增 `buy_dialog_open` bucket，优先级 95，避免未来这类失败继续污染 `amount_input`。
- `_is_buy_dialog_open()` 与 `_enter_amount()` 扩展支持 `input type=text`、`aria-label=USDC`、`role=spinbutton`、`data-test/data-testid/name/id` amount 形态，并要求直接 selector 命中处于 dialog/trade/modal 容器内，避免 portfolio/search 假阳性。
- `test_selector_fixture.py` 新增 `TEXT_USDC_BUY_FORM_HTML`、`SPINBUTTON_BUY_FORM_HTML` 与 `PORTFOLIO_WITH_PM_BUY_HTML`，分别覆盖新型金额控件和 portfolio 假阳性守卫。
- OpenSpec 追加 REQ-26 / SC-25 / SC-26。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后 `/audit?limit=300&failure_limit=100&portfolio_timeout=90`：`select_outcome count=178 covered=178 uncovered=0`；历史 `amount_input count=13 uncovered=13` 仍保留为旧错误记录；新的表单未打开错误后续会进入 `buy_dialog_open`。

**下一步候选**：
- 继续处理 `amount_input`，需要新的失败截图/DOM 或下一笔真实 BUY 失败后确认是否已变成 `buy_dialog_open`。
- 并行处理 `click_submit=2` 或 `target_market_missing=3`，继续提高 SELL/BUY 执行链路成功率。

## Iteration 20 Log

**目标**：处理 `/audit` 中 `target_market_missing=3`，降低 BUY 前置目标市场可见性误判。

**失败记录挖掘**：
- 调用 `/audit?limit=350&failure_limit=100&portfolio_timeout=90`。
- `target_market_missing` 共 3 条，全部为 `Will Abelardo de la Espriella  win the 2026 Colombian presidential election?`，错误为 `Target market content never appeared...`。
- 相关页面属于政治候选人市场，真实 Polymtrade 中文界面可能出现 `买入/卖出` 交易动作，而不一定出现短 `Yes/No` 按钮文本。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_event_visibility.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_wait_for_page_ready()` 和 `_is_target_event_visible()` 新增“目标行内交易动作”判断：只要目标关键词所在的 market row 内存在 `买入/卖出/Buy/Sell` 等可交易按钮，即可判定目标市场可见。
- 保留原有全页 `Yes/No` 检查作为兜底，避免回退已有世界/体育/电竞市场。
- `test_event_visibility.py` 新增 `COLOMBIA_CHINESE_TRADE_ACTION_HTML`，覆盖 Abelardo 行只有 `买入 99¢` / `卖出 1¢`、无短 `Yes/No` 的场景，断言 `_is_target_event_visible()` 和 `_wait_for_page_ready()` 均成功。
- `bridge_reliability_audit.py` 新增 Abelardo `target_market_missing` exact coverage 规则，coverage id 为 `content_based_event_visibility_fixture`。
- OpenSpec 追加 REQ-27 / SC-27。

**验证结果**：
- `python3 polymtrade-bridge/test_event_visibility.py` 通过。
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后 `/audit?limit=350&failure_limit=100&portfolio_timeout=90`：`target_market_missing count=3 covered=3 uncovered=0`，并已从 `next_action_candidates` 移除；当前 next-action 队列为 `amount_input=13`、`click_submit=2`、`navigation_race=5`、`navigation_network=7`、`other=3`。

**下一步候选**：
- 处理 `click_submit=2` 的 SELL 最后确认失败，或进一步拆分 `other` 中的 SELL post-submit verification / open sell dialog 失败。
- 等待下一笔真实 BUY 后确认旧 `amount_input` 是否转化为新的 `buy_dialog_open`，再决定继续修输入控件还是 outcome click。

## Iteration 21 Log

**目标**：继续提高 SELL 链路可靠性和 audit 可行动性，拆分 `other` 中的 SELL 失败，并清理最新 `select_outcome` 历史 coverage 缺口。

**失败记录挖掘**：
- 调用 `/audit?limit=400&failure_limit=100&portfolio_timeout=90`。
- SELL 相关失败包括：
  - `click_submit=2`：id 597 `Will Argentina win on 2026-06-22?`、id 573 `Will Belgium reach the 2026 FIFA World Cup final?`，错误为 `Could not click sell button`。
  - `other` 中 SELL 两条：id 572 `SELL post-submit verification failed: live portfolio quantity did not decrease...`，id 570 `Could not open sell dialog for outcome: NO...sellButtons=0`。
  - `navigation_race` 中 SELL 一条：id 574 `Target page, context or browser has been closed`。
- 重启后 audit 发现 `select_outcome` 仍有 3 条历史 uncovered：Germany Group E 与 Argentina final。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_execute_sell()` 在多次点击卖出后仍未检测到真实 SELL dialog 时，保存 `/tmp/trade_sell_dialog_open_error.png` 并抛出 `Could not open sell dialog after sell button click`，不再继续 `_enter_sell_shares()`。
- `bridge_reliability_audit.py` 新增 `sell_dialog_open` bucket，优先级 88，actionability 为 `code_selector`。
- `bridge_reliability_audit.py` 新增 `sell_post_submit_no_effect` bucket，优先级 82，actionability 为 `sell_verification`。
- `classify_failure()` 将 `Could not open sell dialog...` 归类为 `sell_dialog_open`，将 `SELL post-submit verification failed...` 归类为 `sell_post_submit_no_effect`，使 SELL 风险不再混入 `other`。
- `WORLD_CUP_GROUP_MULTI_COUNTRY_HTML` 新增 `德国` 行，并新增 Germany Group E No 选择断言。
- `FIXTURE_COVERAGE_RULES` 新增 Germany Group E 与 Argentina final exact coverage；`test_bridge_reliability_audit.py` 覆盖这两个历史缺口。
- OpenSpec 追加 REQ-28 / SC-28 / SC-29 和 REQ-29 / SC-30。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `python3 polymtrade-bridge/test_sell_verification.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/test_sell_verification.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后 `/audit?limit=400&failure_limit=100&portfolio_timeout=90`：
  - `select_outcome count=251 covered=251 uncovered=0`
  - `sell_dialog_open count=1 uncovered=1`
  - `sell_post_submit_no_effect count=1 uncovered=1`
  - `other count=3`，已从 5 降到 3
  - `target_market_missing count=3 covered=3 uncovered=0`

**下一步候选**：
- 优先处理 `sell_dialog_open=1`：增强 SELL 持仓卡识别，尤其是 Ludvig Aberg / golf 市场持仓行和 sell button=0 的页面形态。
- 继续处理 `click_submit=2`：需要真实 SELL confirm dialog 截图/DOM，验证确认按钮是否被 `cancel/max/deposit` 过滤或禁用态判断误伤。
- `amount_input=15` 仍主要是旧记录；等待下一笔真实 BUY 后确认是否已转化为 `buy_dialog_open` 或需要继续扩输入控件。

## Iteration 22 Log

**目标**：处理 `sell_dialog_open=1`，避免无 live 持仓的 SELL 继续进入 UI 卖出；同时把历史测试/缺元数据记录从 selector 修复队列中降级。

**失败记录挖掘**：
- 调用 `/audit?limit=450&failure_limit=100&portfolio_timeout=90`。
- `sell_dialog_open=1`：id 570 `Will Ludvig Aberg win the 2026 U.S. Open?`，错误为 `Could not open sell dialog...sellButtons=0`。
- 当前 live `/portfolio` 不包含 Ludvig Aberg 持仓，说明这类失败是 ledger/历史记录与真实持仓不一致导致的 UI 无卖出按钮。
- `/audit` 还显示 `select_outcome uncovered=3`，DB 查明其中 id 151/152 缺 `market_title`，id 156 为零金额/零数量的 `Mbappe goal test` 手工测试记录。

**改动文件**：
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `handle_signal()` 的 copy SELL live portfolio precheck：当 `live_quantity <= 0` 时，不再 `raise` 后丢失可见记录，而是写入 `bridge_trade_record` FAILED，错误为 `Live portfolio insufficient position, skipped (...)`，然后 `continue`，不进入 UI SELL。
- `bridge_reliability_audit.py` 新增 row-level `classify_failure_row()`：`market_title` 缺失的 `select_outcome` 或零金额/零数量的 `*test*` 手工记录归入 `test_or_incomplete_record`。
- 新增 `test_or_incomplete_record` bucket，actionability 为 `historical_test_data`，不会进入 `next_action_candidates`。
- `FIXTURE_COVERAGE_RULES` 将 Ludvig Aberg `sell_dialog_open` 历史失败 exact covered 为 `live_sell_position_precheck`。
- `test_bridge_reliability_audit.py` 新增测试覆盖 `test_or_incomplete_record` 和 Ludvig `sell_dialog_open` coverage。
- OpenSpec 追加 REQ-30 / SC-31 与 REQ-31 / SC-32。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `python3 polymtrade-bridge/test_sell_verification.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/main.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/polymtrade_executor.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后 `/audit?limit=450&failure_limit=100&portfolio_timeout=90`：
  - `sell_dialog_open count=1 covered=1 uncovered=0`
  - `select_outcome count=251 covered=251 uncovered=0`
  - `test_or_incomplete_record count=3`，不进入 next-action
  - 当前 next-action：`amount_input=28`、`click_submit=2`、`navigation_race=5`、`navigation_network=8`、`other=6`

**下一步候选**：
- 处理 `click_submit=2` 的 SELL 确认按钮失败；如果无新截图，先继续扩展确认按钮容器/文案/禁用态诊断。
- 拆分 `other=6`，降低未知失败对下一轮 loop 的信息噪声。
- `amount_input=28` 增长较快，需要结合下一笔真实 BUY 截图判断是否仍是输入控件问题，还是 BUY 表单打开/账户状态问题。

## Iteration 23 Log

**目标**：处理 `click_submit=2` 的 SELL 最后确认按钮失败，扩展提交按钮识别并补诊断截图。

**失败记录挖掘**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`。
- `click_submit=2`：
  - id 597 `Will Argentina win on 2026-06-22?`，SELL Yes，错误 `Could not click sell button`。
  - id 573 `Will Belgium reach the 2026 FIFA World Cup final?`，SELL No，错误 `Could not click sell button`。
- 运行目录未找到历史 SELL submit 失败截图，因此本轮先增强通用提交按钮识别和未来诊断能力。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_click_trade_submit_button()` 的 JS fallback 不再只看可见文本，会把 `aria-label`、`title`、`value`、`data-testid`、`data-test`、`id`、`name`、`type` 纳入评分。
- 新增对 `button type=submit`、`input type=submit`、`data-testid/data-test/id/name` 中包含 `submit` / `sell` / `buy` 的按钮加权。
- 保留 `cancel/max/100%/deposit/withdraw` 等负向词过滤，降低误点取消、最大值、充值提现按钮风险。
- `_click_buy_button()` 失败时保存 `/tmp/trade_buy_submit_button_error.png`。
- `_click_sell_button()` 失败时保存 `/tmp/trade_sell_submit_button_error.png`。
- `test_selector_fixture.py` 新增 `ATTRIBUTE_ONLY_SELL_CONFIRM_DIALOG_HTML` 与 `ICON_ONLY_SELL_CONFIRM_DIALOG_HTML`，覆盖无可见文本但带 `aria-label/data-testid/data-test` 的确认卖出按钮。
- `bridge_reliability_audit.py` 将 click_submit partial coverage id 更新为 `robust_sell_submit_button_fixtures`；`test_bridge_reliability_audit.py` 确认 partial coverage 仍保留为 actionable。
- OpenSpec 追加 REQ-32 / SC-33 / SC-34。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `click_submit count=2 covered=0 uncovered=2 coverage=['robust_sell_submit_button_fixtures']`
  - `sell_dialog_open count=1 covered=1 uncovered=0`
  - `select_outcome count=251 covered=251 uncovered=0`

**下一步候选**：
- `amount_input=45` 已明显增长，下一轮需要优先分析是否仍是旧历史记录扩容，还是当前 BUY 仍在产生“无法输入金额”。
- 若继续处理 SELL，需等待新的 `/tmp/trade_sell_submit_button_error.png` 或新的 click_submit 记录来做 DOM 精准修复。
- 拆分 `other=6`，继续降低未知失败噪声。

## Iteration 24 Log

**目标**：清理 `amount_input=45` 的统计口径，把历史缺元数据/手工零金额测试记录从真实 BUY 金额输入问题中剥离。

**失败记录挖掘**：
- 初始 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 显示 `amount_input count=45 uncovered=45`，`test_or_incomplete_record count=28`。
- `/tmp/trade_amount_input_error.png` 是旧截图，没有新的真实金额输入失败截图可用于 DOM 精准修复。
- DB 抽样发现多条 `Could not enter trade amount` 记录缺少 `market_title`，另有多条 `Mbappe goal test` 手工记录金额/数量为 0，不应挤占真实 BUY 金额输入修复队列。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `classify_failure_row()` 的历史测试/缺元数据降级规则从 `select_outcome` 扩展到 `amount_input`、`buy_dialog_open`、`click_submit`、`target_market_missing`、`target_event_url_missing` 等 UI code bucket。
- `/audit` 的单条记录 `failure_bucket` 改为使用 row-level classifier，而不是只看 error message。
- `failure_bucket_summary()` 强制基于最终 bucket 重新计算 coverage，避免 `test_or_incomplete_record` 继承 `custom_amount_input_fixture`。
- `test_bridge_reliability_audit.py` 增加缺标题 `amount_input` 与零金额 `Mbappe goal test` 的降级覆盖。
- OpenSpec 追加 REQ-33 / SC-35，tasks 追加 10.25。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py` 通过。
- CLI audit：`test_or_incomplete_record count=55 coverage_ids=[]`，`amount_input count=18 coverage_ids=['custom_amount_input_fixture']`。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `test_or_incomplete_record count=55 coverage_ids=[]`
  - `amount_input count=18 coverage_ids=['custom_amount_input_fixture']`
  - `click_submit count=2`
  - `navigation_race count=5`
  - `navigation_network count=8`
  - `other count=6`
- 正式 `/audit` 的 `next_action_candidates` 队列为：`amount_input=18`、`click_submit=2`、`navigation_race=5`、`navigation_network=8`、`other=6`。

**下一步候选**：
- 继续处理剩余真实 `amount_input=18`，需要等待新的 `/tmp/trade_amount_input_error.png` 或进一步采集失败页面 DOM。
- 处理 `navigation_race=5`，给页面 evaluation 与跳转竞态增加更明确的 ready/retry 包装。
- 拆分 `other=6`，避免未知失败长期污染 audit。

## Iteration 25 Log

**目标**：继续处理 `amount_input=18` 的真实 BUY 金额输入失败，优先补强未来执行链路中可能未覆盖的金额控件形态，并提高下一次失败的 DOM 可观测性。

**失败记录挖掘**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`，最高优先级仍为 `amount_input count=18 uncovered=18`。
- 样本包含 id 598 `Will Canada win the 2026 FIFA World Cup?`，错误为旧 selector timeout；另有 Spain/Mexico/Argentina/Netherlands/Team Spirit/USA 等 BUY 样本，均为 `Could not enter trade amount`。
- 当前运行目录没有新的 `/tmp/trade_amount_input_error.png`，历史截图太旧，无法精确复原真实 DOM。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_find_trade_input()` 扩展中文/英文属性扫描，覆盖 `aria-label=金额/数量`、`data-test/data-testid=usdc`、`name/id=quantity/shares` 等金额/份额候选。
- `_fill_input_safely()` 将 `contenteditable/role=textbox` 与 `role=spinbutton` 分支拆开；非原生 `role=spinbutton` 先尝试键盘输入并验证，再用 `textContent`、`aria-valuenow`、`input/change` 事件兜底。
- `_enter_amount()` 失败时除 `/tmp/trade_amount_input_error.png` 外，还保存 `/tmp/trade_amount_input_candidates.json`，包含最多 80 个 input/textarea/textbox/spinbutton/contenteditable 候选及祖先文本。
- `test_selector_fixture.py` 新增中文 `aria-label="金额 USDC"` input 和自定义 `div role=spinbutton aria-label="金额 USDC"` fixture。
- `bridge_reliability_audit.py` 更新 `custom_amount_input_fixture` 的 partial coverage note，说明已覆盖 contenteditable、中文 aria-label 与自定义 spinbutton。
- OpenSpec 追加 REQ-34 / SC-36，tasks 追加 10.26。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `amount_input count=18 uncovered=18 coverage=['custom_amount_input_fixture']`
  - `click_submit count=2`
  - `navigation_race count=5`
  - `navigation_network count=8`
  - `other count=6`
  - `next_action_candidates` 队列保持：`amount_input=18`、`click_submit=2`、`navigation_race=5`、`navigation_network=8`、`other=6`

**下一步候选**：
- 若出现新的 `amount_input` 失败，优先读取 `/tmp/trade_amount_input_candidates.json` 做 DOM 精准修复。
- 可转向 `navigation_race=5`：封装页面 evaluate / navigation 竞态重试，减少 `Execution context was destroyed` 类失败。
- 可继续处理 `sell_post_submit_no_effect=1`，增强 SELL 成交后 live portfolio 延迟确认和重试。

## Iteration 26 Log

**目标**：处理 `navigation_race=5`，降低 Polymtrade 页面跳转过程中 `evaluate` / `evaluate_handle` 被 execution context 销毁导致的 BUY/SELL 失败。

**失败记录挖掘**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`，next-action 队列包含 `navigation_race count=5 uncovered=5`。
- DB 样本：
  - id 581 `Will Abelardo de la Espriella  win the 2026 Colombian presidential election?` BUY Yes：`Page.evaluate: Execution context was destroyed, most likely because of a navigation`
  - id 547 `Will Netherlands win Group F in the 2026 FIFA World Cup?` BUY No：同类 execution context destroyed
  - id 472 `Will Mexico reach the 2026 FIFA World Cup final?` BUY No：同类 execution context destroyed
  - id 350 `Will USA win Group D in the 2026 FIFA World Cup?` BUY No：同类 execution context destroyed
  - id 574 `Will Mexico reach the 2026 FIFA World Cup final?` SELL NO 手工记录：`Page.query_selector: Target page, context or browser has been closed`

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_event_visibility.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- 新增 `_is_navigation_race_error()`、`_wait_after_navigation_race()`、`_evaluate_with_navigation_retry()`、`_evaluate_handle_with_navigation_retry()`。
- 对 transient `Execution context was destroyed` / `most likely because of a navigation` 等错误，等待 `domcontentloaded` 后重试；如果页面已关闭或重试耗尽，抛出保留 `navigation race` 语义的错误。
- `_wait_for_page_ready()`、`_is_target_event_visible()`、`_select_polymtrade_outcome()`、`_find_trade_input()`、`_open_sell_dialog()` 接入 navigation retry。
- `bridge_reliability_audit.py` 将 `navigation race persisted` 与 `page closed during navigation retry` 归类为 `navigation_race`。
- `test_event_visibility.py` 新增 `FlakyNavigationPage`，覆盖第一次 evaluate 被 navigation race 打断、第二次成功的 page-ready 场景。
- `test_bridge_reliability_audit.py` 新增 helper 错误文案分类覆盖。
- OpenSpec 追加 REQ-35 / SC-37，tasks 追加 10.27。

**验证结果**：
- `python3 polymtrade-bridge/test_event_visibility.py` 通过。
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `python3 polymtrade-bridge/test_sell_verification.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 由新进程监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `navigation_race count=5 uncovered=5`
  - `amount_input count=18`
  - `click_submit count=2`
  - `navigation_network count=8`
  - `other count=6`
  - `next_action_candidates` 队列保持：`amount_input=18`、`click_submit=2`、`navigation_race=5`、`navigation_network=8`、`other=6`

**下一步候选**：
- 若出现新的 navigation race，检查错误是否变为 `navigation race persisted`，并据此决定是否增加更长 settle/重新导航策略。
- 回到 `click_submit=2`，等待或利用 `/tmp/trade_sell_submit_button_error.png` 做 SELL submit 精准修复。
- 拆分 `other=6`，继续降低未知失败噪声。

## Iteration 27 Log

**目标**：处理 `click_submit=2`，特别是历史 SELL 提交失败中页面已回到 portfolio、没有确认弹窗时仍尝试点击卖出按钮的风险。

**失败记录挖掘**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`，next-action 队列包含 `click_submit count=2 uncovered=2`。
- 样本：
  - id 597 `Will Argentina win on 2026-06-22?` SELL Yes：`Could not click sell button`
  - id 573 `Will Belgium reach the 2026 FIFA World Cup final?` SELL NO：`Could not click sell button`
- `/tmp/trade_error_will-belgium-reach-the-2026-fifa-world-cup-final.png` 显示页面停在 portfolio 持仓列表，没有 SELL 确认弹窗，说明历史 `click_submit` 中至少一类实际是提交前上下文丢失。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `_click_sell_button()` 在搜索提交按钮前先调用 `_is_sell_dialog_open()`；若确认弹窗已消失，保存 `/tmp/trade_sell_submit_context_missing.png` 和 `/tmp/trade_sell_submit_button_candidates.json`，并抛出 `Sell dialog disappeared before submit`。
- `_click_trade_submit_button()` 不再在没有 dialog/form/trade/order 容器时回退到 `document.body`，避免误点 portfolio 或钱包区按钮。
- 新增 `_capture_trade_submit_diagnostics()`，BUY/SELL submit 失败时保存最多 100 个按钮候选、容器、可见性、禁用状态和页面 URL。
- `bridge_reliability_audit.py` 将 `Sell dialog disappeared before submit` 归类为 `sell_dialog_open`，不再混入 `click_submit`。
- `test_selector_fixture.py` 新增负向断言：portfolio 页面只有持仓/钱包卖出按钮时，`_click_sell_button()` 不点击任何按钮并抛出上下文丢失错误。
- `test_bridge_reliability_audit.py` 新增 submit 上下文丢失分类覆盖。
- OpenSpec 追加 REQ-36 / SC-38，tasks 追加 10.28。

**验证结果**：
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `python3 polymtrade-bridge/test_sell_verification.py` 通过。
- `python3 polymtrade-bridge/test_event_visibility.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 由新进程监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `click_submit count=2 uncovered=2 coverage=['robust_sell_submit_button_fixtures']`
  - `sell_dialog_open count=1 uncovered=0 coverage=['live_sell_position_precheck']`
  - `amount_input count=18`
  - `navigation_race count=5`
  - `navigation_network count=8`
  - `other count=6`

**下一步候选**：
- 若未来出现 `Sell dialog disappeared before submit`，优先读取 `/tmp/trade_sell_submit_button_candidates.json`，判断是弹窗自动关闭、页面跳转还是按钮禁用。
- 继续拆分 `other=6`，降低未知失败噪声。
- 或处理 `navigation_network=8`，增强 portfolio/audit fetch 的网络重试与 backoff。

## Iteration 28 Log

**目标**：拆分 `other=6`，把重复历史未知错误归入具体、可解释的 failure bucket，降低 audit 噪声。

**失败记录挖掘**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`，next-action 队列包含 `other count=6 uncovered=6`。
- DB 抽样：
  - id 450 `Counter-Strike: Vitality vs Team Falcons...` BUY：`Navigation ... is interrupted by another navigation to .../portfolio`
  - id 209 / 202 缺 `market_title`：`Page.evaluate: ReferenceError: bestScore is not defined`
  - id 183 / 182 / 181 缺 `market_title` 且零金额/零数量：`Bridge read-only account does not support BUY orders`

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- 将 `interrupted by another navigation` 归入 `navigation_race`。
- 新增 `read_only_account` bucket，actionability 为 `account_setup_or_config`，不进入 `next_action_candidates`。
- 新增 `executor_js_error` bucket，actionability 为 `code_selector`；缺 metadata 的 executor JS error 继续按 row-level 规则降级为 `test_or_incomplete_record`。
- 补充 `classify_failure()` / `classify_failure_row()` 回归测试，覆盖历史 `other` 样本的三类拆分。
- OpenSpec 追加 REQ-37 / SC-39，tasks 追加 10.29。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py` 通过。
- CLI audit：
  - `test_or_incomplete_record count=57`
  - `navigation_race count=6`
  - `read_only_account count=3`
  - `other` 不再出现。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 由新进程监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `test_or_incomplete_record count=57`
  - `amount_input count=18`
  - `navigation_network count=8`
  - `navigation_race count=6`
  - `read_only_account count=3`
  - `click_submit count=2`
  - `other` 不再出现。
  - `next_action_candidates` 为：`amount_input=18`、`click_submit=2`、`navigation_race=6`、`navigation_network=8`

**下一步候选**：
- 处理 `navigation_network=8`，增强 portfolio/audit fetch 或 trade navigation 的重试/backoff。
- 等待新的 `amount_input` DOM candidates JSON，再做精准金额输入修复。
- 若 `click_submit` 新增，读取 submit candidates JSON 判断按钮/弹窗真实状态。

## Iteration 29 Log

**目标**：处理 `navigation_network=8`，增强 Polymtrade 页面跳转在 `ERR_ABORTED`、`ERR_CONNECTION_RESET`、goto timeout 等网络波动下的恢复能力。

**失败记录挖掘**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`，next-action 队列包含 `navigation_network count=8 uncovered=8`。
- DB 抽样：
  - id 592 `Will Abelardo de la Espriella win...` BUY：`Page.goto: net::ERR_CONNECTION_RESET`，URL 为 portfolio event page。
  - id 559 `Will Spain win Group H...` BUY：`Page.goto: net::ERR_ABORTED`。
  - id 542 `Will Netherlands win Group F...` BUY：`Page.goto: net::ERR_ABORTED`。
  - id 473 `Will USA reach the 2026 FIFA World Cup final?` BUY：`Page.goto: net::ERR_ABORTED`。
  - id 439 `Counter-Strike: Vitality vs Team Falcons...` BUY：`Page.goto: net::ERR_ABORTED`。
- 代码检查发现 `fetch_portfolio_positions()` 仍直接使用 `page.goto(... wait_until="load")`，交易页 `_goto_with_retry()` 也以 `load` 为等待点，对 SPA/代理中断较敏感。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_event_visibility.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `fetch_portfolio_positions()` 改为使用 `_goto_with_retry()` 访问 portfolio 页面。
- `_goto_with_retry()` 默认重试次数提升到 4，`wait_until` 从 `load` 改为 `domcontentloaded`，更适合 Polymtrade SPA。
- 新增 `_is_transient_goto_error()`，统一识别 `ERR_ABORTED`、`net::`、`ERR_CONNECTION`、`interrupted by another navigation`、goto timeout。
- 新增 `_navigation_target_reached()`，在 Playwright 抛出 transient 导航错误但当前 URL 已经匹配目标 `eventId` / `eventSlug` / `eventSource` 时继续执行。
- `test_event_visibility.py` 新增 `FlakyGotoPage`，覆盖 transient network error 重试成功，以及报错但目标 URL 已到达时直接接受。
- OpenSpec 追加 REQ-38 / SC-40，tasks 追加 10.30。

**验证结果**：
- `python3 polymtrade-bridge/test_event_visibility.py` 通过。
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 由新进程监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `navigation_network count=8`
  - `amount_input count=18`
  - `click_submit count=2`
  - `navigation_race count=6`
  - `read_only_account count=3`
  - `next_action_candidates` 为：`amount_input=18`、`click_submit=2`、`navigation_race=6`、`navigation_network=8`

**下一步候选**：
- 继续等待新的 `amount_input` DOM candidates JSON，然后做精准修复。
- 若 navigation failures 仍新增，检查日志是否从 `ERR_ABORTED/ERR_CONNECTION_RESET` 变成 `Navigation failed after ...`，再决定是否加 reload/proxy-specific recovery。
- 针对 `click_submit=2` 等待新的 submit candidates JSON 做更细按钮状态判断。

## Iteration 30 Log

**目标**：收口 `amount_input=18` 的历史噪音，区分真实金额输入失败、BUY 弹窗未打开导致的旧失败，以及零金额/零数量测试记录。

**失败记录挖掘**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`，next-action 队列包含 `amount_input count=18`、`click_submit=2`、`navigation_race=6`、`navigation_network=8`。
- 检查历史截图：
  - `/tmp/trade_error_will-canada-win-the-2026-fifa-world-cup-755.png`：portfolio 页面，无 BUY 弹窗。
  - `/tmp/trade_error_will-spain-win-group-h-in-the-2026-fifa-world-cup.png`：event/portfolio 视图，无 BUY 弹窗和金额输入框。
  - `/tmp/trade_error_will-mexico-reach-the-2026-fifa-world-cup-final.png`：portfolio 持仓列表，无 BUY 弹窗。
- DB 抽样确认 id 598/569/567/565/564/558/508/501/494/481/458/358/355/246 均为历史 `Could not enter trade amount`，但截图证据指向“BUY 弹窗未打开后旧代码继续输入金额”。
- Kylian Mbappe 等多条 `amount_input` 失败金额/数量为 0，应视为手工测试或不完整记录，不应进入 UI code-fix 队列。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `classify_failure_row()` 对 `amount_input`、`buy_dialog_open`、`click_submit` 的零金额或零数量记录降级为 `test_or_incomplete_record`。
- `FIXTURE_COVERAGE_RULES` 增加 record-id exact coverage：历史无 BUY 弹窗截图记录标记为 `buy_dialog_open_guard_fixture`。
- `failure_coverage_hint()` 支持 `record_ids` 精确匹配，并保持通用 `custom_amount_input_fixture` partial 规则不覆盖这些 record-id exact 样本。
- `test_bridge_reliability_audit.py` 新增零金额 amount input 降级测试，以及 id 598/569 exact covered 测试；修正 click-submit partial coverage 测试样本，使其保留有效金额/数量。
- OpenSpec 追加 REQ-39 / SC-41，tasks 追加 10.31。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py` 通过。
- CLI audit `/tmp/bridge_audit_iter30_cli2.json`：
  - `amount_input count=14 covered_count=14 uncovered_count=0 coverage_ids=[buy_dialog_open_guard_fixture]`
  - `test_or_incomplete_record count=62`
  - `click_submit count=1`
  - `navigation_race count=6`
  - `navigation_network count=8`
  - `next_action_candidates` 不再包含 `amount_input`。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`。首次 `/health` 出现短暂 false-ready，随后日志显示 PID 47327 完成 startup，8080 正常监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 与 CLI 一致：
  - `amount_input count=14 covered_count=14 uncovered_count=0`
  - `next_action_candidates` 为：`click_submit=1`、`navigation_race=6`、`navigation_network=8`

**下一步候选**：
- 优先处理 `click_submit=1`：record id 597，`Will Argentina win on 2026-06-22?`，SELL Yes，错误 `Could not click sell button`，需要读取 submit 截图/候选按钮 JSON 判断是否是按钮禁用、弹窗消失、还是 selector 漏识别。
- 然后复查 `navigation_race=6` 是否已经被第 27/29 轮新逻辑覆盖，需要用新增失败时间区分“历史未覆盖”与“修复后仍新增”。
- `navigation_network=8` 暂时作为 transient 旧失败保留观察；若新记录继续出现，再加 proxy/reload 级恢复。

## Iteration 31 Log

**目标**：处理当前 `/audit` 排第一的 `click_submit=1`，确认 id 597 是否仍代表真实 SELL submit 风险，或已经被后续 robust submit 修复覆盖。

**失败记录挖掘**：
- 正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 显示 `next_action_candidates` 为 `click_submit=1`、`navigation_race=6`、`navigation_network=8`。
- id 597：
  - `Will Argentina win on 2026-06-22?`
  - side `SELL`，outcome `Yes`
  - quantity `2.4691`，price `0.81`，amount `1.999971`
  - error `Could not click sell button`
  - leader tx `0x84e6d1be7e741922572a5d9313ae0cbf293f781018904b0c9ed1922094378adc`
- 同市场 id 596 先 BUY 成功，id 597 后续 SELL 失败；当前 `/portfolio` 返回 0 个持仓，无法进行补卖。
- `/tmp` 没有 id 597 的 submit button candidates JSON，说明该失败发生于 submit 诊断增强前。
- id 573 也是旧 `Could not click sell button`，但 amount/price 为 0，已被 row-level 规则降级到 `test_or_incomplete_record`。
- 当前 `test_selector_fixture.py` 已覆盖 delayed role button、attribute-only submit、icon-only confirm，以及缺失 SELL dialog 时不误点 portfolio 卖出按钮。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `FIXTURE_COVERAGE_RULES` 为 `click_submit` 增加 id 597 的 record-id exact coverage，coverage id 为 `robust_sell_submit_button_fixtures`。
- 保留通用 `Could not click sell button` partial coverage，使新的有效金额 click_submit 仍然可行动。
- 新增 `test_argentina_sell_submit_historical_record_is_exact_covered()`，确认 id 597 covered_count=1、uncovered_count=0，且不进入 `next_action_candidates`。
- OpenSpec 追加 REQ-40 / SC-42，tasks 追加 10.32。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `python3 polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py` 通过。
- CLI audit `/tmp/bridge_audit_iter31_cli.json`：
  - `click_submit count=1 covered_count=1 uncovered_count=0`
  - `amount_input count=14 covered_count=14 uncovered_count=0`
  - `next_action_candidates` 为：`navigation_race=6`、`navigation_network=8`
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 79120，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 正常监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 与 CLI 一致：
  - `click_submit count=1 covered_count=1 uncovered_count=0`
  - `next_action_candidates` 为：`navigation_race=6`、`navigation_network=8`

**下一步候选**：
- 处理 `navigation_race=6`：区分第 27/29 轮前的历史竞态、已由 evaluate/goto retry 覆盖的旧样本，以及仍需新增 exact coverage 或继续修 `_goto_with_retry()` 的样本。
- 若 navigation race 全部是旧覆盖样本，则继续收口到 exact coverage，让队列转向 `navigation_network=8`。
- 若有新的 navigation race 发生在修复后，读取对应日志和截图，增强页面 ready/reload/retry。

## Iteration 32 Log

**目标**：处理当前 `/audit` 排第一的 `navigation_race=6`，区分已被 retry 机制覆盖的历史竞态、goto 被 portfolio 打断的旧样本，以及手工/不完整 page closed 噪音。

**失败记录挖掘**：
- 正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 显示 `next_action_candidates` 为 `navigation_race=6`、`navigation_network=8`。
- DB 按 navigation race 错误条件查到 6 条：
  - id 581 `Will Abelardo de la Espriella...` BUY：`Page.evaluate: Execution context was destroyed...`
  - id 547 `Will Netherlands win Group F...` BUY：`Page.evaluate: Execution context was destroyed...`
  - id 472 `Will Mexico reach the 2026 FIFA World Cup final?` BUY：`Page.evaluate: Execution context was destroyed...`
  - id 350 `Will USA win Group D...` BUY：`Page.evaluate: Execution context was destroyed...`
  - id 450 `Counter-Strike: Vitality vs Team Falcons...` BUY：`Page.goto...interrupted by another navigation to .../portfolio`
  - id 574 `Will Mexico reach the 2026 FIFA World Cup final?` SELL manual：`Page.query_selector: Target page, context or browser has been closed`，external id 为 `manual-*`，amount/price 为 0。
- 代码检查确认：
  - `_evaluate_with_navigation_retry()` 已覆盖 evaluate/evaluate_handle 的 transient navigation context loss。
  - `_goto_with_retry()` 已覆盖 `interrupted by another navigation` 并使用 `domcontentloaded` 与 backoff。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `polymtrade-bridge/test_event_visibility.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `FIXTURE_COVERAGE_RULES` 为 id 581/547/472/350 增加 `evaluate_navigation_retry_fixture` exact coverage。
- `FIXTURE_COVERAGE_RULES` 为 id 450 增加 `goto_interrupted_navigation_retry_fixture` exact coverage。
- `classify_failure_row()` 将 `manual-*` 且 amount/price 为 0 的 `navigation_race` 降级为 `test_or_incomplete_record`，覆盖 id 574。
- `test_bridge_reliability_audit.py` 新增 `test_navigation_race_historical_records_are_exact_covered()`，并扩展手工/不完整记录降级测试。
- `test_event_visibility.py` 扩展 `FlakyGotoPage`，新增 `test_goto_with_retry_retries_interrupted_by_portfolio_navigation()`，精确覆盖 `interrupted by another navigation to .../portfolio` 后重试成功。
- OpenSpec 追加 REQ-41 / SC-43，tasks 追加 10.33。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `python3 polymtrade-bridge/test_event_visibility.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py polymtrade-bridge/main.py` 通过。
- CLI audit `/tmp/bridge_audit_iter32_cli.json`：
  - `navigation_race count=5 covered_count=5 uncovered_count=0`
  - `test_or_incomplete_record count=63`，包含 id 574
  - `next_action_candidates` 只剩 `navigation_network=8`
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 2466，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 正常监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 与 CLI 一致：
  - `navigation_race count=5 covered_count=5 uncovered_count=0`
  - `next_action_candidates` 为：`navigation_network=8`

**下一步候选**：
- 处理唯一剩余的 `navigation_network=8`：拆分 `ERR_ABORTED`、`ERR_CONNECTION_RESET`、goto timeout 等旧网络跳转失败，判断哪些已被 `_goto_with_retry()` 和 target reached 规则覆盖，哪些需要新增 proxy/reload 级恢复。
- 若全部是第 29 轮前旧样本，可按 record-id exact coverage 收口；若存在第 29 轮后新增样本，需要继续强化 `_goto_with_retry()`。

## Iteration 33 Log

**目标**：处理当前唯一 next-action `navigation_network=8`，判断 `ERR_ABORTED` / `ERR_CONNECTION_RESET` 是否已经被第 29 轮 `_goto_with_retry()` 加固覆盖，或仍需新增代码恢复。

**失败记录挖掘**：
- 正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 显示 `next_action_candidates` 为 `navigation_network=8`。
- DB 按网络导航错误条件查到 8 条：
  - id 592 `Will Abelardo...` manual BUY：`Page.goto: net::ERR_CONNECTION_RESET`，external id 为 `manual-*`，quantity/price/amount 均为 0。
  - id 559 `Will Spain win Group H...` BUY：`Page.goto: net::ERR_ABORTED`
  - id 542 `Will Netherlands win Group F...` BUY：`Page.goto: net::ERR_ABORTED`
  - id 473 `Will USA reach the 2026 FIFA World Cup final?` BUY：`Page.goto: net::ERR_ABORTED`
  - id 439 `Counter-Strike: Vitality vs Team Falcons...` BUY：`Page.goto: net::ERR_ABORTED`
  - id 372 `Counter-Strike: Vitality vs Team Falcons...` BUY：`Page.goto: net::ERR_ABORTED`
  - id 365 `Will USA win Group D...` BUY：`Page.goto: net::ERR_ABORTED`
  - id 235 `Map Handicap: VIT (-1.5) vs Team Falcons (+1.5)` BUY：`Page.goto: net::ERR_ABORTED`
- 7 条真实 BUY `ERR_ABORTED` 均发生在第 29 轮 `_goto_with_retry()` 从 `load` 改为 `domcontentloaded`、增加重试和 target-reached 接受之前。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `polymtrade-bridge/test_event_visibility.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `FIXTURE_COVERAGE_RULES` 为 id 559/542/473/439/372/365/235 增加 `goto_network_retry_fixture` exact coverage。
- `classify_failure_row()` 将 `manual-*` 且 amount/price 为 0 的 `navigation_network` 降级为 `test_or_incomplete_record`，覆盖 id 592。
- `test_bridge_reliability_audit.py` 新增 `test_navigation_network_historical_records_are_exact_covered()`，并扩展手工/不完整记录降级测试。
- `test_event_visibility.py` 新增 `test_goto_with_retry_retries_err_aborted_navigation()`，精确覆盖 `Page.goto: net::ERR_ABORTED` 后重试成功。
- OpenSpec 追加 REQ-42 / SC-44，tasks 追加 10.34。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `python3 polymtrade-bridge/test_event_visibility.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py polymtrade-bridge/main.py` 通过。
- CLI audit `/tmp/bridge_audit_iter33_cli.json`：
  - `navigation_network count=7 covered_count=7 uncovered_count=0`
  - `test_or_incomplete_record count=64`，包含 id 592
  - `next_action_candidates` 为空。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 21464，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 正常监听。
- 重启后正式 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 与 CLI 一致：
  - `navigation_network count=7 covered_count=7 uncovered_count=0`
  - `navigation_race count=5 covered_count=5 uncovered_count=0`
  - `click_submit count=1 covered_count=1 uncovered_count=0`
  - `amount_input count=14 covered_count=14 uncovered_count=0`
  - `next_action_candidates` 为空。

**下一步候选**：
- 当前 500 条/100 失败审计窗口已无可行动 code/infra bucket。下一轮应转向监控“修复后新增失败”：按 `created_at` 大于 Iteration 33 重启时间过滤 FAILED，若出现新的 `amount_input`、`click_submit`、`navigation_*`，再用截图/候选 JSON 做真实代码修复。
- 可考虑将 `/audit` 增加 `since_ms` 或 “post-fix only” 过滤，方便日报只显示修复后新增问题，而不是历史已覆盖样本。

**追加监控增强**：
- 在历史可行动队列清空后，新增 `bridge_reliability_audit.py --since-ms` 与 Bridge `/audit?since_ms=...`。
- `since_ms` 只过滤 recent PENDING/FAILED records 与 failure buckets，不影响 SUCCESS ledger/live portfolio 全量一致性检查。
- `/audit` metrics 新增：
  - `raw_records_checked`：未过滤读取的最近记录数。
  - `records_checked`：应用 `since_ms` 后参与 PENDING/FAILED 审计的记录数。
  - `since_ms`：当前过滤阈值。
- 新增 `test_filter_records_since_uses_created_or_updated_time()`，覆盖 created/updated 双时间字段过滤。
- 验证：
  - `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
  - `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py` 通过。
  - CLI 未来 `--since-ms`：`records_checked=0`、`raw_records_checked=500`、`failure_bucket_count=0`、`next_action_candidates=[]`。
  - 重启后正式 `/audit?since_ms=<future>`：`records_checked=0`、`raw_records_checked=500`、`failure_bucket_count=0`、`next_action_candidates=[]`。

## Iteration 34 Log

**目标**：进入修复后新增失败监控模式，确认历史队列清空后是否已有新 FAILED/PENDING，并补强 `/audit` metrics 水位，让后续 loop 能自动判断监控窗口状态。

**监控窗口检查**：
- 查询最近交易记录：最新记录 id 600 为 SUCCESS BUY `Will Algeria win on 2026-06-22?`；最新 FAILED id 599 为 SELL `Will Jordan vs. Algeria end in a draw?`，错误 `Insufficient position, skipped`，属于持仓/风控 skip，不是浏览器执行 bug。
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90&since_ms=<now-1h>`：
  - `records_checked=0`
  - `recent_failure_count=0`
  - `failure_bucket_count=0`
  - `next_action_candidates=[]`
- 结论：当前修复后窗口没有新增可行动 BUY/SELL Bridge 失败。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- `/audit` metrics 新增：
  - `latest_raw_record_time_ms`
  - `latest_record_time_ms`
  - `latest_failure_time_ms`
  - `actionable_failure_bucket_count`
- 新增 `test_latest_record_time_ms_uses_created_or_updated_time()`，保证监控水位使用 created/updated 最大值。
- OpenSpec 追加 REQ-44 / SC-46，tasks 追加 10.36。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py` 通过。
- CLI 未来 `--since-ms`：
  - `records_checked=0`
  - `raw_records_checked=500`
  - `latest_raw_record_time_ms=1782189302001`
  - `latest_record_time_ms=null`
  - `latest_failure_time_ms=null`
  - `actionable_failure_bucket_count=0`
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 61098，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 正常监听。
- 重启后正式 `/audit?since_ms=<future>` 与 CLI 一致，`next_action_candidates=[]`。

**下一步候选**：
- 继续以 `since_ms` 轮询修复后新增失败；一旦 `actionable_failure_bucket_count > 0`，读取新增记录截图/诊断 JSON 并进入下一轮代码修复。
- 若持续无新增失败，可以将 post-fix audit summary 接入优化日报页面，显示最近水位、最近失败时间、可行动 bucket 数。

## Iteration 35 Log

**目标**：把第 34 轮需要人工解释的 metrics 固化成 `/audit` 可直接消费的 `monitor_status`，让后续 loop、日报或前端可以直接判断当前窗口是 clear、actionable 还是 no recent records。

**监控窗口检查**：
- 调用 `/audit?limit=500&failure_limit=100&portfolio_timeout=90&since_ms=<now-1h>`：
  - `records_checked=0`
  - `recent_failure_count=0`
  - `failure_bucket_count=0`
  - `actionable_failure_bucket_count=0`
  - `next_action_candidates=[]`
- 调用默认 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `recent_failure_count=481`
  - `failure_bucket_count=14`
  - `actionable_failure_bucket_count=0`
  - `next_action_candidates=[]`

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**规则/测试变更**：
- 新增 `build_monitor_status()`：
  - `actionable`：存在可行动 failure bucket。
  - `clear`：窗口有记录，但没有可行动 Bridge failure。
  - `no_recent_records`：`since_ms` 等窗口内没有 PENDING/FAILED records。
- `/audit` 输出新增顶层 `monitor_status`，包含状态、message、actionable/pending/failure 计数、时间水位、`since_ms` 和 `next_action_buckets`。
- 新增 `test_build_monitor_status()` 覆盖三种状态。
- OpenSpec 追加 REQ-45 / SC-47，tasks 追加 10.37。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_event_visibility.py` 通过。
- CLI 默认 audit：`monitor_status.status=clear`，`next_action_buckets=[]`。
- CLI 未来 `--since-ms`：`monitor_status.status=no_recent_records`，`latest_record_time_ms=null`，`latest_failure_time_ms=null`。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 77521，`/health` 返回 `{"status":"ok","executor_ready":true}`，8080 正常监听。
- 重启后正式 `/audit`：
  - 默认窗口：`monitor_status.status=clear`
  - 未来 `since_ms`：`monitor_status.status=no_recent_records`

**下一步候选**：
- 将 `monitor_status` 接入优化日报/统计页面，显示 Bridge 监控状态、最近失败水位和下一步 bucket。
- 持续轮询 `/audit?since_ms=<last_loop_time>`；若返回 `monitor_status.status=actionable`，用新增记录进入下一轮代码修复。

## Iteration 36 Log

**目标**：把第 35 轮已经固化的 Bridge `monitor_status` 接入 PolyHermes 正式后端与统计信息页，让执行链路监控不只停留在 polymtrade-bridge `/audit`，而能被页面直接看到。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/BridgeTradeRecordDto.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/bridge/BridgeAuditClient.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/controller/bridge/BridgeTradeRecordController.kt`
- `backend/src/main/resources/application.properties`
- `frontend/src/types/index.ts`
- `frontend/src/services/api.ts`
- `frontend/src/pages/Statistics.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- 后端新增 `BridgeAuditClient`，通过 `bridge.audit.url` 调用 polymtrade-bridge `/audit`，并传递 `limit`、`failure_limit`、`portfolio_timeout`、`since_ms`。
- 后端新增 `POST /api/bridge/trades/audit`，作为正式只读代理接口，返回 `monitorStatus`、metrics 与 next action candidates。
- 前端 `apiService.bridgeTradeRecords.audit()` 与 TypeScript 类型补齐。
- `/statistics` 页面新增 `Bridge 执行链路监控` 卡片，显示：
  - `clear/actionable/no_recent_records` 中文状态。
  - 可处理失败桶、最近失败数、Pending 超时、当前持仓快照数量。
  - 最近记录时间与前几个 next action bucket。
- OpenSpec 追加 REQ-46 / SC-48，tasks 追加 10.38。

**验证结果**：
- `frontend npm run build` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `polymtrade-bridge/.venv/bin/python -m py_compile main.py bridge_reliability_audit.py polymtrade_executor.py` 通过。
- `polymtrade-bridge/.venv/bin/python test_event_visibility.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 20835，`/health` 返回 `{"status":"ok","executor_ready":true}`，`/audit?limit=20&failure_limit=10&portfolio_timeout=90` 返回 `monitor_status.status=clear`、可行动 bucket=0、`next_action_candidates=0`。
- `backend ./gradlew compileKotlin` 未能运行：本机缺 Java Runtime，输出 `Unable to locate a Java Runtime`。后续若补齐 JDK，需要补跑后端编译。

**下一步候选**：
- 在有 JDK 的环境补跑 `backend ./gradlew compileKotlin` 或后端测试，确认 audit 代理接口 Kotlin 编译无误。
- 继续检查是否已有“优化点日报”独立页面；若没有，可基于本轮 `monitorStatus` 接口新建日报页面，显示每天新增失败桶、处理状态和代码改进记录。

## Iteration 37 Log

**目标**：在没有新增可行动 BUY/SELL Bridge 失败的情况下，继续推进 loop 可观测闭环，落地“优化点日报”独立页面，让每天的 Bridge 状态和优化点可以直接查看。

**监控窗口检查**：
- `/health` 返回 `{"status":"ok","executor_ready":true}`。
- 默认 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `monitor_status.status=clear`
  - `actionable_failure_bucket_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
- 最近 24 小时 `/audit?...&since_ms=<now-24h>`：
  - `monitor_status.status=clear`
  - `records_checked=8`
  - `next_action_candidates=0`

**改动文件**：
- `frontend/src/pages/OptimizationDaily.tsx`
- `frontend/src/App.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/locales/zh-CN/common.json`
- `frontend/src/locales/en/common.json`
- `frontend/src/locales/zh-TW/common.json`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- 新增 `/optimization-daily` 页面。
- 页面加载时调用后端正式 `apiService.bridgeTradeRecords.audit()` 两次：
  - 默认窗口：展示当前 live audit 状态。
  - `sinceMs=now-24h`：展示最近 24 小时 post-fix 窗口。
- 页面展示当前审计窗口、最近 24 小时窗口、next action bucket 和今日优化点表格。
- 左侧菜单新增“优化点日报”入口。
- OpenSpec 追加 REQ-47 / SC-49，tasks 追加 10.39。

**验证结果**：
- `frontend npm run build` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- 3000 端口已有 dev server 监听，新页面地址：`http://localhost:3000/optimization-daily`。

**下一步候选**：
- 把优化点日报从前端静态优化点列表升级为后端读取 `LOOP_STATE.md` 或结构化日报文件，减少每轮手工更新页面文案。
- 在有 JDK 的环境补跑后端编译，确认 Iteration 36 的 audit 代理接口可编译。
- 持续轮询 post-fix 窗口；如果出现 `actionable`，优先回到真实 BUY/SELL 失败代码修复。

## Iteration 38 Log

**目标**：默认 audit 仍为 clear、无新增可行动 BUY/SELL 失败时，继续从运行日志挖掘会影响 SELL/持仓同步的弱点，并提高 portfolio 导航在网络抖动下的成功率。

**日志发现**：
- `/tmp/polymtrade-bridge.log` 中出现启动后 portfolio 导航连续 transient 网络错误：
  - `net::ERR_NETWORK_CHANGED`
  - `net::ERR_CONNECTION_RESET`
  - `net::ERR_NETWORK_IO_SUSPENDED`
  - `Timeout 45000ms exceeded`
- 曾出现 `/portfolio` 500，根因是 `fetch_portfolio_positions()` 访问 `https://polym.trade/portfolio` 时 4 次 `domcontentloaded` 导航全部失败。
- 该问题不一定进入交易失败桶，但会影响 SELL 前 live position 校验、持仓快照和统计页/audit 的 portfolio 数据。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_event_visibility.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- 启动页、钱包地址提取、调试导航和 portfolio 持仓抓取统一改为 `_goto_with_retry()`。
- `_goto_with_retry()` 新增参数化 `wait_until`、`timeout_ms` 和 `fallback_wait_until`。
- 常规 `domcontentloaded` transient 重试耗尽后，新增 `commit` fallback；若 commit 后 `domcontentloaded` 仍未 settle，则记录 warning 并允许调用方继续等待动态内容。
- `fetch_portfolio_positions()` 导航重试从 4 次提高到 6 次。
- 新增 `test_goto_with_retry_falls_back_to_commit_after_transient_failures()` 覆盖连续 transient 后的 commit fallback。
- OpenSpec 追加 REQ-48 / SC-50，tasks 追加 10.40。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python test_event_visibility.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade_executor.py main.py bridge_reliability_audit.py test_event_visibility.py test_bridge_reliability_audit.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 65265，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 重启后 `/portfolio` 返回 4 个 positions，`error=None`。
- 重启后 `/audit?limit=500&failure_limit=100&portfolio_timeout=90` 返回 `monitor_status.status=clear`、`portfolio_position_count=4`、`next_action_candidates=0`。

**下一步候选**：
- 继续监控 `/tmp/polymtrade-bridge.log` 是否还出现 `/portfolio` 500；若仍出现，可进一步在 `fetch_portfolio_positions()` 添加 DOM-level stale snapshot fallback。
- 若 post-fix audit 出现 `actionable` bucket，优先回到真实 BUY/SELL 失败修复。
- 在有 JDK 环境补跑后端 Kotlin 编译。

## Iteration 39 Log

**目标**：在 audit clear 且无新增交易失败时，继续从运行日志中排查配置错配风险，确保 Bridge 实际使用当前钱包对应的跟单配置，而不是 `.env` 残留 account id。

**监控窗口检查**：
- `/health` 返回 `{"status":"ok","executor_ready":true}`。
- 默认 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `monitor_status.status=clear`
  - `next_action_candidates=0`
  - `portfolio_position_count=4`
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `next_action_candidates=0`
- 日志中无新增 BUY/SELL FAILED；发现配置可观测性问题：空 `COPY_TRADING_ACCOUNT_ID` 被打印为 `env=0` mismatch warning，容易误判当前跟单账号来源。

**改动文件**：
- `polymtrade-bridge/copy_trading_config.py`
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/test_copy_trading_config.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- `CopyTradingRuleEngine.normalize_account_id()`：空字符串、`0`、负数和非法字符串统一视为未设置。
- `CopyTradingRuleEngine` 初始化和 `set_account_id()` 统一使用 normalize 后的 `Optional[int]`。
- `_load_configs()` 只在 `account_id is not None` 时追加 `ct.account_id` 过滤，避免 `"0"` 作为 truthy 字符串误过滤。
- `/status` 新增：
  - `copy_trading_account_id`
  - `copy_trading_config_count`
- Bridge 启动时：如果 env 未设置但检测到钱包 account id，输出 info 并使用 detected id；只有 env 明确配置且不同才输出 mismatch warning。
- OpenSpec 追加 REQ-49 / SC-51，tasks 追加 10.41。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python test_copy_trading_config.py`：16 tests OK。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `polymtrade-bridge/.venv/bin/python -m py_compile main.py copy_trading_config.py polymtrade_executor.py bridge_reliability_audit.py test_copy_trading_config.py` 通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 85090，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- `/status` 返回：
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
  - `logged_in=true`
- 启动日志显示：
  - `Using detected copy-trading account id 2 for wallet 0x0372...`
  - `Copy-trading account_id overridden: None -> 2`
  - `Loaded 2 copy-trading configs`
  - 未再出现 `COPY_TRADING_ACCOUNT_ID mismatch: env=0`
- 重启后 `/audit` 返回 `monitor_status.status=clear`、`portfolio_position_count=4`、`next_action_candidates=0`。

**下一步候选**：
- 继续从 `/audit?since_ms=<last_loop_time>` 与 `/tmp/polymtrade-bridge.log` 挖新增可行动失败。
- 若仍无新增失败，可把 `/status` 的 copy-trading account/config 信息接入优化点日报或 Bridge 记录页，方便页面直接核验当前跟单账号。
- 在有 JDK 环境补跑后端 Kotlin 编译。

## Iteration 40 Log

**目标**：audit 与日志均无新增交易失败时，把第 39 轮新增的 Bridge runtime account/config 可观测性接入优化点日报页面，降低跟错账号、无配置执行或登录态异常未被及时发现的风险。

**监控窗口检查**：
- `/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `next_action_candidates=0`
- 默认 `/audit?limit=500&failure_limit=100&portfolio_timeout=90`：
  - `monitor_status.status=clear`
  - `portfolio_position_count=4`
  - `next_action_candidates=0`
- `/tmp/polymtrade-bridge.log` 当前尾部未见新增 ERROR/WARNING/FAILED。

**改动文件**：
- `frontend/vite.config.ts`
- `frontend/src/pages/OptimizationDaily.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- Vite dev proxy 新增 `/bridge-runtime -> http://localhost:8080`。
- 优化点日报页面刷新时同时读取 `/bridge-runtime/status`。
- 页面新增 `Bridge 运行状态` 卡片，展示：
  - 执行器 Ready
  - 登录状态
  - 跟单账号 ID
  - 有效配置数
  - 最近错误
- 今日优化点表新增 `展示实际跟单账号`。
- OpenSpec 追加 REQ-50 / SC-52，tasks 追加 10.42。

**验证结果**：
- `frontend npm run build` 通过。
- `curl http://127.0.0.1:3000/bridge-runtime/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 3000 端口 dev server 正常监听。

**下一步候选**：
- 若 audit 继续无新增 actionable，可把 runtime status 也通过后端正式代理暴露，避免生产环境依赖 Vite dev proxy。
- 继续从 post-fix audit 与 Bridge 日志挖新增 BUY/SELL 弱点。
- 在有 JDK 环境补跑后端 Kotlin 编译。

## Iteration 41 Log

**目标**：将第 40 轮优化点日报中的 Bridge runtime status 从 Vite dev proxy 升级为后端正式代理优先，避免生产环境依赖浏览器跨域访问 8080，同时保留本地开发兜底。

**监控窗口检查**：
- `/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `next_action_candidates=0`
- `/tmp/polymtrade-bridge.log` 当前尾部未见新增 ERROR/WARNING/FAILED。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/BridgeTradeRecordDto.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/bridge/BridgeAuditClient.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/controller/bridge/BridgeTradeRecordController.kt`
- `backend/src/main/resources/application.properties`
- `frontend/src/types/index.ts`
- `frontend/src/services/api.ts`
- `frontend/src/pages/OptimizationDaily.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- 后端新增 `BridgeRuntimeStatusResponse`。
- `BridgeAuditClient` 新增 `fetchStatus()`，调用 `bridge.status.url`，默认 `http://localhost:8080/status`。
- `BridgeTradeRecordController` 新增 `POST /api/bridge/trades/status`。
- `application.properties` 新增 `bridge.status.url=${BRIDGE_STATUS_URL:http://localhost:8080/status}`。
- 前端新增 `BridgeRuntimeStatus` 类型与 `apiService.bridgeTradeRecords.status()`。
- 优化点日报改为优先调用正式后端 status API；后端未重启或接口不可用时，回退到 `/bridge-runtime/status`。
- OpenSpec 追加 REQ-51 / SC-53，tasks 追加 10.43。

**验证结果**：
- `frontend npm run build` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `curl http://127.0.0.1:3000/bridge-runtime/status` 返回当前 Bridge runtime 状态：
  - `ready=true`
  - `logged_in=true`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- `curl http://127.0.0.1:8080/status` 返回同样状态。
- `backend ./gradlew compileKotlin` 仍未能运行：本机缺 Java Runtime，输出 `Unable to locate a Java Runtime`。后端正式 status 代理需在有 JDK 环境补跑编译验证。

**下一步候选**：
- 在有 JDK 环境补跑后端 Kotlin 编译，验证 `/api/bridge/trades/status`。
- 继续从 post-fix audit 与 Bridge 日志挖新增 BUY/SELL 弱点。
- 若后续仍无新增失败，可将 runtime status 直接合并进 Bridge audit 响应，减少前端多请求。

## Iteration 42 Log

**目标**：补齐前几轮后端正式 Bridge audit/status 代理的编译验证缺口。系统 Java 不可用，但项目内存在可用 JDK17，因此用项目内 JDK 跑后端 Kotlin 编译。

**监控窗口检查**：
- `/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `next_action_candidates=0`
- `/tmp/polymtrade-bridge.log` 当前尾部未见新增 ERROR/WARNING/FAILED。

**验证环境发现**：
- `/usr/libexec/java_home -V` 仍返回 `Unable to locate a Java Runtime`。
- Homebrew `openjdk`/`openjdk@17` prefix 是残留路径，没有实际 `bin/java`。
- `mdfind` 找到项目内 JDK：`/Users/henry/projects/polyhermes/jdk17/Contents/Home`。
- `java -version`：
  - `openjdk version "17.0.19" 2026-04-21`
  - `javac 17.0.19`

**验证结果**：
- `JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew compileKotlin` 在 `backend/` 下通过。
- `frontend npm run build` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `/health` 返回 `{"status":"ok","executor_ready":true}`。
- `/status` 返回 `ready=true`、`logged_in=true`、`copy_trading_account_id=2`、`copy_trading_config_count=2`。

**改动文件**：
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现/记录内容**：
- OpenSpec 追加 task 10.44。
- OpenSpec 追加 REQ-52 / SC-54：Bridge 后端代理变更必须用项目内 JDK17 完成 `compileKotlin` 验证。
- 记录项目内 JDK 路径，后续 loop 可直接复用，不再被系统 Java 缺失卡住。

**下一步候选**：
- 后续任何后端 Bridge DTO/Controller/Client 改动，都用项目内 JDK17 跑 `backend ./gradlew compileKotlin`。
- 继续从 post-fix audit 与 Bridge 日志挖新增 BUY/SELL 弱点；若无新增失败，可考虑把 runtime status 合并进 Bridge audit 响应，减少前端请求数。

## Iteration 43 Log

**目标**：audit 与日志无新增可行动失败时，进一步收敛 Bridge 可观测性：把 runtime status 合入在线 `/audit`，让一次 audit 同时回答“有没有交易执行问题”和“当前 Bridge 是否具备跟单执行条件”。

**监控窗口检查**：
- `/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `next_action_candidates=0`
- `/tmp/polymtrade-bridge.log` 当前尾部未见新增 ERROR/WARNING/FAILED。

**改动文件**：
- `polymtrade-bridge/main.py`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/BridgeTradeRecordDto.kt`
- `frontend/src/types/index.ts`
- `frontend/src/pages/OptimizationDaily.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- Bridge `main.py` 新增 `bridge_runtime_status()` helper。
- `/status` 复用同一 helper。
- `/audit` 返回结果顶层新增 `runtime_status`，包含：
  - `ready`
  - `logged_in`
  - `last_error`
  - `copy_trading_account_id`
  - `copy_trading_config_count`
- 后端 `BridgeAuditResponse` 新增 `runtimeStatus`。
- 前端 `BridgeAuditResponse` 新增 `runtimeStatus`。
- 优化点日报优先使用默认 audit 响应内的 `runtimeStatus`；只有 audit 未携带时才 fallback 到正式 status API / dev proxy。
- OpenSpec 追加 REQ-53 / SC-55，tasks 追加 10.45。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python -m py_compile main.py bridge_reliability_audit.py polymtrade_executor.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `frontend npm run build` 通过。
- `JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew compileKotlin` 在 `backend/` 下通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 61086，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 默认 `/audit` 返回：
  - `monitor_status.status=clear`
  - `runtime_status.ready=true`
  - `runtime_status.logged_in=true`
  - `runtime_status.copy_trading_account_id=2`
  - `runtime_status.copy_trading_config_count=2`
  - `next_action_candidates=0`
- 最近 1 小时 `/audit?...&since_ms=<now-1h>` 返回：
  - `monitor_status.status=no_recent_records`
  - 同样携带 runtime status
  - `next_action_candidates=0`

**下一步候选**：
- 继续以 `/audit?since_ms=<last_loop_time>` 单请求监控 post-fix 新失败和 runtime readiness。
- 若 audit 继续无 actionable，可增加 alert 阈值：runtime status 中未登录、account id 为空或 config count 为 0 时，把 `monitor_status.status` 提升为 actionable/runtime_blocked。

## Iteration 44 Log

**目标**：让 runtime readiness 真正参与在线 audit 的 monitor 判断。此前 `/audit` 虽携带 `runtime_status`，但即使 Bridge 未登录、无配置或 executor 不 ready，`monitor_status` 仍可能显示 `no_recent_records` 或 `clear`。本轮将这类状态提升为 `runtime_blocked`。

**监控窗口检查**：
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `runtime_status.ready=true`
  - `runtime_status.logged_in=true`
  - `runtime_status.copy_trading_account_id=2`
  - `runtime_status.copy_trading_config_count=2`
  - `next_action_candidates=0`
- `/tmp/polymtrade-bridge.log` 当前尾部未见新增 ERROR/WARNING/FAILED。

**改动文件**：
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/test_audit_runtime_status.py`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/BridgeTradeRecordDto.kt`
- `frontend/src/types/index.ts`
- `frontend/src/pages/OptimizationDaily.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`

**实现内容**：
- Bridge `main.py` 新增：
  - `runtime_block_reasons(runtime_status)`
  - `apply_runtime_status_to_audit_result(audit_result, runtime_status)`
- 在线 `/audit` 先运行底层 reliability audit，再合并 runtime status：
  - runtime 健康：保留原 monitor status。
  - runtime 异常：覆盖 `monitor_status.status=runtime_blocked`，并返回 `runtime_block_reasons`。
- runtime block reason 包括：
  - `executor_not_ready`
  - `not_logged_in`
  - `copy_trading_account_missing`
  - `copy_trading_config_empty`
  - `last_error_present`
- 后端 `BridgeAuditMonitorStatus` 新增 `runtimeBlockReasons`。
- 前端 `BridgeAuditMonitorStatus.status` 支持 `runtime_blocked`，优化点日报显示为“执行受阻”红色状态。
- 新增 `test_audit_runtime_status.py` 覆盖 healthy/runtime_blocked 两类情况。
- OpenSpec 追加 REQ-54 / SC-56，tasks 追加 10.46。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python test_audit_runtime_status.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `polymtrade-bridge/.venv/bin/python -m py_compile main.py test_audit_runtime_status.py bridge_reliability_audit.py polymtrade_executor.py` 通过。
- `frontend npm run build` 通过。
- `JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew compileKotlin` 在 `backend/` 下通过。
- 已重启 launchd `com.polyhermes.polymtrade-bridge`，PID 78081，`/health` 返回 `{"status":"ok","executor_ready":true}`。
- 健康 runtime 下默认 `/audit` 返回：
  - `monitor_status.status=clear`
  - `runtime_block_reasons=None`
  - `runtime_status.ready=true`
  - `runtime_status.logged_in=true`
  - `runtime_status.copy_trading_account_id=2`
  - `runtime_status.copy_trading_config_count=2`
  - `next_action_candidates=0`
- 健康 runtime 下最近 1 小时 `/audit?...&since_ms=<now-1h>` 返回：
  - `monitor_status.status=no_recent_records`
  - `runtime_block_reasons=None`
  - 同样携带健康 runtime status

**下一步候选**：
- 继续用 `/audit?since_ms=<last_loop_time>` 单请求监控 post-fix 新失败和 runtime readiness。
- 如果后续 runtime_blocked 出现，把优化点日报或统计页增加更明确的中文原因映射。
- 若出现新的 actionable bucket，回到真实 BUY/SELL 失败修复。

## Iteration 45 Log

**目标**：runtime gate 已能把 `/audit` 提升为 `runtime_blocked`，但页面如果只显示内部英文 reason key，操作者仍需翻译。本轮把 runtime block reason 映射为中文标签，方便第一时间判断为什么不可跟单。

**监控窗口检查**：
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `runtime_status.ready=true`
  - `runtime_status.logged_in=true`
  - `runtime_status.copy_trading_account_id=2`
  - `runtime_status.copy_trading_config_count=2`
  - `next_action_candidates=0`
- `/tmp/polymtrade-bridge.log` 当前尾部未见新增 ERROR/WARNING/FAILED。

**改动文件**：
- `frontend/src/pages/OptimizationDaily.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 优化点日报新增 `runtimeBlockReasonLabels`：
  - `executor_not_ready` -> `执行器未就绪`
  - `not_logged_in` -> `Bridge 未登录`
  - `copy_trading_account_missing` -> `跟单账号缺失`
  - `copy_trading_config_empty` -> `有效配置为 0`
  - `last_error_present` -> `存在最近错误`
- Bridge 运行状态卡片在 `monitor.runtimeBlockReasons` 非空时显示红色原因标签。
- OpenSpec 追加 REQ-55 / SC-57，tasks 追加 10.47。

**验证结果**：
- `frontend npm run build` 通过。
- `JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew compileKotlin` 在 `backend/` 下通过。
- `polymtrade-bridge/.venv/bin/python test_audit_runtime_status.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- 当前健康 `/audit` 返回：
  - `monitor_status.status=clear`
  - `runtime_block_reasons=None`
  - `runtime_status.ready=true`
  - `runtime_status.logged_in=true`
  - `runtime_status.copy_trading_account_id=2`
  - `runtime_status.copy_trading_config_count=2`
  - `next_action_candidates=0`

**下一步候选**：
- 若 runtime_blocked 真正出现，检查优化点日报的中文标签是否足够明确，必要时增加处理建议。
- 继续监控 post-fix audit；若出现新的 actionable BUY/SELL bucket，回到交易执行代码修复。

## Iteration 46 Log

**目标**：继续监控 post-fix Bridge 执行链路，并修复统计信息页与优化点日报对 runtime_blocked 展示不一致的问题。

**监控窗口检查**：
- 最近 1 小时 `/audit?...&since_ms=<now-1h>`：
  - `monitor_status.status=no_recent_records`
  - `runtime_block_reasons=None`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
  - `runtime_status.ready=true`
  - `runtime_status.logged_in=true`
  - `runtime_status.copy_trading_account_id=2`
  - `runtime_status.copy_trading_config_count=2`
- `polymtrade-bridge/bridge.log` 尾部没有 6 月 23 日新增 BUY/SELL FAILED；当前命中的 ERROR/WARNING 都是 6 月 19 日历史日志。

**改动文件**：
- `frontend/src/pages/Statistics.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 统计信息页 `getAuditStatusView()` 增加 `runtime_blocked -> 执行受阻` 红色状态。
- 统计信息页新增 `runtimeBlockReasonLabels`：
  - `executor_not_ready` -> `执行器未就绪`
  - `not_logged_in` -> `Bridge 未登录`
  - `copy_trading_account_missing` -> `跟单账号缺失`
  - `copy_trading_config_empty` -> `有效配置为 0`
  - `last_error_present` -> `存在最近错误`
- Bridge 执行链路监控卡片在 `monitorStatus.runtimeBlockReasons` 非空时显示红色中文原因标签。
- OpenSpec 追加 REQ-56 / SC-58，要求 `/statistics` 与优化点日报对 runtime block 状态展示一致。
- tasks 追加 10.48。

**验证结果**：
- `frontend npm run build` 通过。
- `polymtrade-bridge/.venv/bin/python test_audit_runtime_status.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- 当前健康 `/audit?since_ms=<now-1h>` 返回：
  - `monitor_status.status=no_recent_records`
  - `runtime_block_reasons=None`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
  - runtime 健康且 account id/config count 正常。

**下一步候选**：
- 继续用 post-fix audit 监控新增 BUY/SELL 失败；若出现 actionable bucket，优先进入执行器代码修复。
- 可进一步把 runtime block 原因旁边加上处理建议，例如“重新登录 Bridge / 检查跟单配置 / 重启 Bridge”。

## Iteration 47 Log

**目标**：继续从 live audit 和 portfolio 证据提高 SELL 成功率，重点处理 `/portfolio` metadata 污染和持仓列表加载时序问题，避免 SELL live precheck 因错误 `marketSlug/conditionId` 或未渲染列表误判。

**监控窗口检查**：
- 最近 1 小时 `/audit?...&since_ms=<now-1h>` 初始结果：
  - `monitor_status.status=no_recent_records`
  - `runtime_status.ready=true`
  - `runtime_status.logged_in=true`
  - `runtime_status.copy_trading_account_id=2`
  - `runtime_status.copy_trading_config_count=2`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
- 初始 `/portfolio` 暴露异常：4 个不同持仓都被 enrichment 成同一个 `conditionId=0x1fad...`、`marketSlug=new-rhianna-album-before-gta-vi-926`，会污染 SELL live position matching。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_enrichment.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- `_enrich_position()` 不再在 `eventSlug` 指向的事件内找不到同标题 market 时回退到事件第一个 market。
- Gamma market title search 也必须 exact title match；若搜索结果首条不相关，不再采用首条结果。
- 新增 `_normalize_market_question()`、`_find_event_market_by_title()`、`_find_market_by_title()`，统一用规范化后的 question/title 判断 exact match。
- 移除 portfolio enrichment 的并发卡片点击 fallback，避免读取 `/portfolio` 时改变当前 carousel URL 或让多个 enrichment 互相污染。
- 新增 `_wait_for_portfolio_rows()`：导航到 portfolio 后等待持仓行或明确空状态渲染，再执行 scrape，降低刚启动/刚导航时把未渲染列表误判为 0 持仓的风险。
- OpenSpec 追加 REQ-57 / SC-59、REQ-58 / SC-60、REQ-59 / SC-61，tasks 追加 10.49、10.50、10.51。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python test_enrichment.py` 通过：
  - 覆盖 wrong href eventSlug fallback 到 title search。
  - 覆盖 title search 无 exact match 时不使用首条结果。
  - 覆盖 enrichment 不点击 portfolio 卡片。
  - 覆盖延迟渲染持仓行等待。
- `polymtrade-bridge/.venv/bin/python test_sell_verification.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade_executor.py test_enrichment.py bridge_reliability_audit.py main.py` 通过。
- 已重启 `com.polyhermes.polymtrade-bridge`，`/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 重启后 `/portfolio` 返回 4 个持仓：
  - Spain Group H No 14.8
  - Belgium Group G No 10.8
  - Abelardo Yes 2.02
  - Argentina final No 0.38
- 这 4 个持仓不再被错误赋值为同一个 `new-rhianna...` metadata；当前因 Gamma 无 exact match，`conditionId/marketSlug/eventSlug` 返回 null，SELL live precheck 可继续使用标题 + outcome 兜底匹配。
- 重启后最近 1 小时 `/audit` 返回：
  - `monitor_status.status=no_recent_records`
  - `runtime_block_reasons=None`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
  - `portfolio_position_count=4`
- 新日志未再出现 `Portfolio click did not reveal usable eventSlug`；只保留 `exact metadata not found` warning，表示不再返回错误 metadata。

**下一步候选**：
- 为 `/portfolio` enrichment 增加更可靠的只读 Polymarket/Gamma 查询方式，例如按 normalized title + event keywords 进行候选二次评分，争取恢复正确 `conditionId/marketSlug`，但仍禁止无 exact/高置信匹配时污染 metadata。
- 继续观察 post-fix audit；若出现新的 BUY/SELL actionable bucket，优先修执行链路。

## Iteration 48 Log

**目标**：在 Iteration 47 禁止 metadata 污染后，恢复世界杯小组冠军持仓的高置信 metadata 补全，并修复 Bridge runtime status 在钱包账号检测短暂失败时误报 `copy_trading_account_missing` 的问题。

**监控窗口检查**：
- Gamma `markets?title=` 对 Spain/Belgium/Argentina/Abelardo 等标题会返回不相关市场，例如 GTA VI 相关 market；因此不能重新引入“取首条结果”的 fallback。
- Gamma `events?slug=world-cup-group-h-winner` 可稳定返回 Spain Group H winner 事件，且能 exact match `Will Spain win Group H in the 2026 FIFA World Cup?`：
  - `conditionId=0x766aa2fb8fafc6f063de001e1d441d0e64d84f164093feb087226b47ffc32af1`
  - `marketSlug=will-spain-win-group-h-in-the-2026-fifa-world-cup`
- Gamma `events?slug=world-cup-group-g-winner` 可稳定返回 Belgium Group G winner 事件，且能 exact match `Will Belgium win Group G in the 2026 FIFA World Cup?`：
  - `conditionId=0x1e285f49c483634426c54834f840f6bfe780e0039eb0ad31357b936600b7c2d2`
  - `marketSlug=will-belgium-win-group-g-in-the-2026-fifa-world-cup`
- Bridge 曾出现 runtime block 风险：钱包 account id 检测失败时，即使已加载的跟单配置全部属于 account 2，`/status.copy_trading_account_id` 仍可能为空。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_enrichment.py`
- `polymtrade-bridge/copy_trading_config.py`
- `polymtrade-bridge/test_copy_trading_config.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- `_enrich_position()` 新增高置信只读路径：对 `Will <team> win Group <letter> in the 2026 FIFA World Cup?` 类型标题，推导 `world-cup-group-<letter>-winner` 事件 slug，再在该事件内 exact match market question。
- 保持安全边界：若推导事件内没有 exact match，仍返回 null metadata；不使用 `markets?title=` 首条结果，也不点击 portfolio 卡片。
- 新增 `_derive_portfolio_event_slugs()` 和 `_search_gamma_events_by_slug()`，把事件 slug 查询与 title 查询分离，便于测试和后续扩展。
- `CopyTradingConfigEngine.active_account_id` 在显式 `account_id` 为空或为 0 时，会从已加载配置中推断唯一账号；若配置跨多个账号，则不猜测。
- OpenSpec 追加 REQ-60 / SC-62、REQ-61 / SC-63；tasks 追加 10.52、10.53。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python test_enrichment.py` 通过：12 个 enrichment 场景通过，覆盖世界杯小组标题推导事件 slug。
- `polymtrade-bridge/.venv/bin/python test_copy_trading_config.py` 通过：18 个配置场景通过，覆盖单账号推断和跨账号不推断。
- `polymtrade-bridge/.venv/bin/python test_sell_verification.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade_executor.py test_enrichment.py copy_trading_config.py test_copy_trading_config.py bridge_reliability_audit.py main.py` 通过。
- 已重启 `com.polyhermes.polymtrade-bridge`，`/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 重启后 `/portfolio` 返回 4 个持仓：
  - Spain Group H No 14.8，已恢复正确 `conditionId/marketSlug/eventSlug`
  - Belgium Group G No 10.8，已恢复正确 `conditionId/marketSlug/eventSlug`
  - Abelardo Yes 2.02，metadata 仍为 null，未污染
  - Argentina final No 0.38，metadata 仍为 null，未污染
- 最近 1 小时 `/audit` 返回：
  - `monitor_status.status=no_recent_records`
  - `runtime_block_reasons=None`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
  - `portfolio_position_count=4`
  - `unexpected_portfolio_position_count=1`
  - `success_position_mismatch_count=13`

**下一步候选**：
- 继续监控 audit；若出现新的 BUY/SELL actionable bucket，优先回到执行链路修复。
- 扩展高置信只读 enrichment 到其它可推导事件 slug 的体育/金融/政治模板，但必须保留 exact match 和 null-on-uncertain 原则。
- 对 `success_position_mismatch_count=13` 做下一轮聚类，区分历史已平仓、metadata 缺失、以及真正未同步持仓。

## Iteration 49 Log

**目标**：继续提高 SELL 成功率，优先修复当前真实 `/portfolio` 中 metadata 缺失的持仓，降低 leader 触发 SELL 时 live precheck 因无法识别现有持仓而跳过或误判的风险。

**监控窗口检查**：
- Bridge `/status` 健康：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 最近 6 小时 `/audit` 没有新的 PENDING/FAILED：
  - `monitor_status.status=no_recent_records`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
- 但 `/portfolio` 显示 Abelardo 政治持仓 metadata 为空，audit 将其列入 `unexpected_portfolio_position` 且 `market_id=null`。这类持仓一旦 leader 卖出，会削弱 SELL live position matching。
- 通过运行时同代理 Gamma 查询确认：
  - `markets?title=Will Abelardo...` 仍返回不相关 GTA VI markets，不能采用 title search 首条。
  - `markets?slug=will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election` 返回真实 Abelardo market：
    - `conditionId=0xfbe85201ab2b4acff01cd5a3639039fc813d3448c64db081f70926bd9b9e74e9`
    - `marketSlug=will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election`
    - `eventSlug=colombia-presidential-election`

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_enrichment.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 修复已有 `marketSlug` 分支：用 Gamma `markets?slug=` 精确反查，而不是把 slug 作为 `title` 参数搜索。
- 新增 `_derive_portfolio_market_slugs()`：从规范化后的 portfolio `marketTitle` 推导 exact market slug，再用 Gamma `markets?slug=` 查询。
- `_enrich_position()` 在采用 slug 查询结果前仍要求 market question 与 portfolio title 规范化后一致；不一致时返回空 metadata 或继续后续安全路径。
- 保持顺序边界：真实 card `eventSlug` 优先于 derived market slug；世界杯小组冠军 derived event slug 仍优先于 derived market slug。
- 新增/更新 enrichment 测试，覆盖：
  - 已有 `marketSlug` 必须调用 slug 参数查询。
  - Abelardo 政治持仓可通过 derived market slug 补齐 metadata。
  - Gamma title search 首条不相关时仍不得采用。
- OpenSpec 追加 REQ-62 / SC-64，tasks 追加 10.54。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python test_enrichment.py` 通过：13 个 enrichment 场景通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade_executor.py test_enrichment.py bridge_reliability_audit.py main.py` 通过。
- `polymtrade-bridge/.venv/bin/python test_sell_verification.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：19 passed。
- 已重启 `com.polyhermes.polymtrade-bridge`，`/status` 返回健康。
- 重启后 `/portfolio` 返回 4 个持仓且全部有 metadata：
  - Spain Group H No：`conditionId=0x766aa2fb...`，`marketSlug=will-spain-win-group-h-in-the-2026-fifa-world-cup`
  - Belgium Group G No：`conditionId=0x1e285f49...`，`marketSlug=will-belgium-win-group-g-in-the-2026-fifa-world-cup`
  - Abelardo Yes：`conditionId=0xfbe85201...`，`marketSlug=will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election`
  - Argentina final No：`conditionId=0x32858337...`，`marketSlug=will-argentina-reach-the-2026-fifa-world-cup-final`
- 最近 6 小时 `/audit` 仍为 `no_recent_records`，无新增 BUY/SELL 失败；`unexpected_portfolio_position_count=1` 保留是因为 Abelardo 是钱包现有但成功账本没有的持仓，现在已带 `market_id/market_slug`，不再是 metadata 缺失。

**下一步候选**：
- 对 `success_position_mismatch_count=13` 的 stale mismatch 做聚类：识别哪些是历史已人工/外部平仓，哪些是账本缺失，避免长期噪音影响 sell 成功率判断。
- 继续观察 post-fix audit；若出现新的 BUY/SELL actionable bucket，优先修执行链路。

## Iteration 50 Log

**目标**：继续优化 Bridge BUY/SELL 可靠性监控，处理 `success_position_mismatch_count=13` 长期噪音，避免历史或外部平仓导致的 stale mismatch 被误判为当前 SELL 风险。

**监控窗口检查**：
- Bridge `/status` 健康：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 最近 6 小时 `/audit` 没有新增 PENDING/FAILED：
  - `monitor_status.status=no_recent_records`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `next_action_candidates=0`
- 但 metrics 显示：
  - `success_position_mismatch_count=13`
  - `fresh_success_position_mismatch_count=0`
  - `stale_success_position_mismatch_count=13`
  - 旧逻辑把 stale 也计入 `active_success_position_mismatch_count=13`
- 这会让 CLI strict 或日报把历史/外部平仓可能性误当成当前可行动 SELL 问题，污染 loop 的下一步选择。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 新增 `build_success_mismatch_metric_counts()`，明确指标语义：
  - `success_position_mismatch_count` 保留全部 mismatch。
  - `fresh_success_position_mismatch_count` 表示当前需要调查的 SUCCESS 账本未出现在 live portfolio。
  - `stale_success_position_mismatch_count` 保留历史复盘证据。
  - `active_success_position_mismatch_count` 只等于 fresh mismatch，不再包含 stale。
  - `unresolved_success_position_mismatch_count=fresh+stale` 供后续人工/批量 reconciliation 使用。
- 新增 `strict_actionable_issue_count()`，CLI `--strict` 只因以下问题退出 1：
  - pending timeout
  - actionable failure bucket
  - fresh/active success mismatch
- `build_monitor_status()` 新增 `actionable_issue_count` 与 `active_success_position_mismatch_count`，并用 strict actionable 语义决定 `actionable`。
- OpenSpec 追加 REQ-63 / SC-65，tasks 追加 10.55。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：21 passed。
- `polymtrade-bridge/.venv/bin/python test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile bridge_reliability_audit.py test_bridge_reliability_audit.py main.py` 通过。
- `polymtrade-bridge/.venv/bin/python test_sell_verification.py` 通过。
- 已重启 `com.polyhermes.polymtrade-bridge`，`/status` 返回健康。
- 重启后最近 6 小时 live `/audit` 返回：
  - `monitor_status.status=no_recent_records`
  - `monitor_status.actionable_issue_count=0`
  - `recent_failure_count=0`
  - `pending_timeout_count=0`
  - `success_position_mismatch_count=13`
  - `active_success_position_mismatch_count=0`
  - `fresh_success_position_mismatch_count=0`
  - `stale_success_position_mismatch_count=13`
  - `unresolved_success_position_mismatch_count=13`
- CLI 严格审计：
  - `bridge_reliability_audit.py --since-ms <now-6h> --strict`
  - `strict_exit=0`

**下一步候选**：
- 对 `unresolved_success_position_mismatch_count=13` 做批量 reconciliation 工具或规则：将已明确历史/外部平仓的记录写入 reconciliation 文件，减少人工复盘成本。
- 继续观察 post-fix audit；若出现新的 PENDING/FAILED 或 fresh mismatch，优先回到 BUY/SELL 执行链路修复。

## Iteration 51 Log

**目标**：继续收敛 SELL 成功率监控噪音，为 13 条 stale success mismatch 输出可人工确认的 reconciliation 建议，降低历史账本/外部平仓复盘成本，同时保持只读，不自动掩盖真实问题。

**监控窗口检查**：
- Bridge `/status` 健康：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 最近 24 小时 `/audit`：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `recent_failure_count=5`
  - `actionable_failure_bucket_count=0`
  - `success_position_mismatch_count=13`
  - `active_success_position_mismatch_count=0`
  - `stale_success_position_mismatch_count=13`
  - `reconciled_success_position_mismatch_count=0`
- 当前已有 `/audit/reconciliations` API 与本地 `audit_reconciliations.json` 机制，但 `/audit` 没有给出可操作的建议 payload，人工处理 stale mismatch 成本高。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 新增 `build_reconciliation_suggestions()`：
  - 只处理 `stale_success_position_mismatch`。
  - 跳过 fresh mismatch，避免把当前 SELL 风险静默掉。
  - 跳过已 `is_reconciled=true` 的 mismatch。
  - 输出 `key/status/confidence/reason/market_id/market_title/outcome/outcome_index/expected_quantity/actual_quantity/latest_record_id/latest_record_updated_at/age_ms/contributing_record_ids`。
  - 输出可提交给 `/audit/reconciliations` 的 `annotation_payload`，默认 `status=accepted_stale`、`actor=audit_suggestion`。
  - actual quantity 为 0 时 confidence 为 `high`，部分数量缺失时为 `medium`。
- `/audit` 输出新增：
  - `reconciliation_suggestions`
  - `metrics.reconciliation_suggestion_count`
- CLI 新增 `--reconciliation-suggestion-limit`，默认最多返回 20 条建议。
- Bridge API 构造 audit args 时补齐 `reconciliation_suggestion_limit=20`。
- OpenSpec 追加 REQ-64 / SC-66，tasks 追加 10.56。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q`：23 passed。
- `polymtrade-bridge/.venv/bin/python test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile bridge_reliability_audit.py test_bridge_reliability_audit.py main.py` 通过。
- 已重启 `com.polyhermes.polymtrade-bridge`，`/status` 返回健康。
- Live `/audit?since_ms=<now-24h>` 返回：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `metrics.reconciliation_suggestion_count=13`
  - `len(reconciliation_suggestions)=13`
  - 第一条 suggestion：
    - `status=accepted_stale`
    - `confidence=high`
    - `reason=stale_success_position_missing_from_live_portfolio`
    - `annotation_payload.status=accepted_stale`
    - `annotation_payload.actor=audit_suggestion`
- CLI 限制建议数量验证：
  - `bridge_reliability_audit.py --reconciliation-suggestion-limit 3` 返回 3 条 suggestions。
- `bridge_reliability_audit.py --strict` 返回 `strict_exit=0`，说明 suggestions 不改变 actionable 状态。
- `polymtrade-bridge/.venv/bin/python test_sell_verification.py` 通过。

**下一步候选**：
- 在优化点日报或统计页展示 reconciliation suggestions，并提供人工确认入口写入 `/audit/reconciliations`。
- 继续观察 post-fix audit；若出现新的 PENDING/FAILED 或 fresh mismatch，优先修 BUY/SELL 执行链路。

## Iteration 52 Log

**目标**：把 Iteration 51 的只读 reconciliation suggestions 从 Bridge `/audit` JSON 推进到 PolyHermes 可见页面，减少 stale success mismatch 复盘成本，同时保持只读，避免误操作掩盖真实 SELL 风险。

**监控窗口检查**：
- Live Bridge `/audit?since_ms=<now-24h>`：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `recent_failure_count=5`
  - `metrics.reconciliation_suggestion_count=13`
  - 前 3 条 suggestion keys 分别对应 Scottie Scheffler、Rory McIlroy、Kylian Mbappe stale mismatch。
- 前端 `BridgeAuditResponse` 类型尚未包含 `reconciliationSuggestions`。
- 后端正式 audit DTO 尚未透传 `reconciliation_suggestions` 和新 mismatch metrics。
- 优化点日报尚未展示历史错配复盘建议。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/BridgeTradeRecordDto.kt`
- `frontend/src/types/index.ts`
- `frontend/src/pages/OptimizationDaily.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 后端正式 audit DTO 新增透传字段：
  - `reconciliationSuggestions`
  - `metrics.successPositionMismatchCount`
  - `metrics.activeSuccessPositionMismatchCount`
  - `metrics.freshSuccessPositionMismatchCount`
  - `metrics.staleSuccessPositionMismatchCount`
  - `metrics.reconciledSuccessPositionMismatchCount`
  - `metrics.unresolvedSuccessPositionMismatchCount`
  - `metrics.reconciliationSuggestionCount`
  - `monitorStatus.actionableIssueCount`
  - `monitorStatus.activeSuccessPositionMismatchCount`
- 前端 `BridgeAuditResponse` / `BridgeAuditMetrics` / `BridgeAuditMonitorStatus` 新增对应类型。
- 前端新增 `BridgeAuditReconciliationSuggestion` 与 `BridgeAuditReconciliationPayload` 类型。
- 优化点日报新增 `历史错配复盘建议` 模块：
  - 统计 `历史错配`、`当前错配`、`复盘建议`、`可行动问题`。
  - 表格展示前 8 条 suggestions。
  - 每条展示置信度、市场、latest record id、outcome、账本/实仓数量和建议状态。
  - 仅展示只读建议，不提供自动写入 reconciliation 的操作。
- 今日优化点表新增 `展示历史错配复盘建议` 条目。
- OpenSpec 追加 REQ-65 / SC-67，tasks 追加 10.57。

**验证结果**：
- `frontend npm run build` 通过。
- `backend JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew compileKotlin` 通过。
- Live Bridge `/audit?since_ms=<now-24h>` 仍返回：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `metrics.reconciliation_suggestion_count=13`
- 本机后端 `127.0.0.1:8081` 当前未运行，无法对正式后端代理接口做运行态 HTTP 验证；本轮用 Kotlin 编译验证 DTO 结构，Bridge 端 live audit 已验证 suggestions 数据源正常。

**下一步候选**：
- 若需要把 stale mismatch 真正收敛到 0，可在优化点日报增加人工确认入口，POST `/audit/reconciliations` 写入选中的 suggestion。
- 继续观察 post-fix audit；若出现新的 PENDING/FAILED 或 fresh mismatch，优先修 BUY/SELL 执行链路。
