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

## Done

- [x] 读取 loop-engineering 与 openspec-new-change skill
- [x] 探索 polymtrade-bridge 代码结构与 BUY/SELL 流程
- [x] 挖掘 `bridge.log` 与 `/private/tmp/polymtrade-bridge.log` 中的失败模式
- [x] 探索 `bridge_trade_record`、`bridge_reliability_audit.py`、`position_ledger.py` 等数据源
- [x] 识别主要根因：网络/代币模态框仅被关闭未选择、BUY 无成交后校验、部分异常日志缺失原因
- [x] 创建 OpenSpec 变更目录与初始提案/设计/任务/需求文档
- [x] 实现迭代 1 代码修复并验证

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
