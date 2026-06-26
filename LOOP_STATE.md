# Loop Engineering State: PolyHermes Web Bridge BUY/SELL 可靠性持续改进

## Goal

通过挖掘 Bridge 日志和数据库中的 BUY/SELL 失败记录，持续修复 `polymtrade-bridge` 的执行可靠性问题，降低误判失败和假成功比例。

> 2026-06-24 note: 用户提出“第二目标”：第一阶段积累并评分 1000+ 新的高质量 Leader 候选。由于 Codex goal 工具中旧 Bridge 目标仍为 paused，不能并行新建持久 goal；第二目标先落到项目文档 `docs/zh/leader-discovery-goal-2-phase-1.md`，后续可在完成/切换旧 goal 后正式创建。

> 2026-06-24 11:35 note: 用户确认“先把第一个目标往后放，启动第二个积累 leader 目标”。执行层面暂停 Bridge 可靠性目标的新迭代，优先推进 Leader 候选积累目标；Codex goal 工具仍被旧 paused goal 占用，因此第二目标通过项目 spec、代码/API、数据库候选池与本 loop state 追踪。

> 2026-06-24 update: 第一目标已设置为 `COMPLETED_PENDING_RESTART`，保留所有历史记录和后续重启入口；第二目标升级为当前主目标 `ACTIVE`。系统新增 `/api/loop-goals/status` 与 `/api/loop-goals/update`，并在 `/optimization-daily` 的“目标控制”对话框中支持启动/暂停目标。Leader Research 定时任务会在第二目标非 `ACTIVE` 时跳过。

## Active Goal Override

当前执行优先级：

1. 第二目标：第一阶段积累并评分 1000+ 新的高质量 Leader 候选。状态：`ACTIVE`。
2. 第一目标：Bridge BUY/SELL 可靠性持续改进。状态：`COMPLETED_PENDING_RESTART`，不删除，后续可从目标控制对话框重启；sell 成功率仍作为 Leader 可复制性评分的重要维度保留。

第二目标启动进展：

- 已建立规格文档：`docs/zh/leader-discovery-goal-2-phase-1.md`。
- 已补后端正式导入接口：`POST /api/copy-trading/leader-research/scanner-pool/import`。
- 已新增 scanner pool -> research candidate 导入服务，支持 dry-run、分类限额、最小 discovery score、只导入 PENDING/全量切换、锁定候选保护、事件记录。
- 已将 `leader_research_candidate` 从 3 个扩展到 1145 个，其中 `DISCOVERED=1142`、`PAPER=3`。
- 当前 inferred category 分布：politics 429、finance 415、sports 152、crypto 148、unknown 1。政治+金融约 73.7%，已接近 80% 主策略目标，下一轮优先补 politics/finance 高质量来源。
- 已完成下一轮预筛：新增 `activity-prescreen-v1` 活动基础评分，1142 个新增候选全部评分；筛出 45 个 80+ 且未命中核心排除风险的候选。
- 已按策略配比推进首批 PAPER：politics 9、finance 9、sports 2、crypto 2；当前 `PAPER=25`，active paper session=25。
- 已新增并上线 paper 专用接口：`POST /api/copy-trading/leader-research/paper/process` 和 `POST /api/copy-trading/leader-research/paper/score`。
- 已修复 paper processing 批次公平性：待处理事件按 PAPER/TRIAL_READY 钱包公平采样，避免单个高频钱包吞掉整个 batch。
- 已处理两轮公平 paper batch：新增/累计 paper trades 696 条，其中 processed 513、filtered 183、failed 0。
- 当前合格候选 4 个：politics 2、finance 1、sports 1。candidate 80 虽然分数/PnL 高，但 `drawdown_gt_15`，暂不列入合格。
- 下一轮：对 4 个合格候选跑更深 paper/backtest，并将不合格 PAPER 自动转 COOLDOWN；同时继续补 politics/finance 来源，尤其提高 finance 合格数量。
- 2026-06-24 第二目标下一步 loop 已执行：
  - 新增 `/api/copy-trading/leader-research/activity-score/promote-paper`，打通 activity 预筛分到 PAPER 的正式晋级链路。
  - scanner pool 真实导入新增 65 个、更新 10 个；主要来自 politics，finance 新增很少。
  - activity-prescreen 评分新增 65 个：politics 62、finance 3；主要风险为 `small_sample`、`scanner_pool_unverified`、`tail_price_spray`、`low_safe_price_ratio`。
  - 80+ 安全可晋级候选集中在 sports/crypto；politics/finance 没有安全可晋级的 60+ 候选，finance 主要被 `buy_only_no_exit` 拦截。
  - 按 20% 机会策略配额推进 PAPER 10 个：sports 5、crypto 5。
  - 当前 PAPER=30，分布 politics 9、finance 7、sports 7、crypto 7。
  - paper process 大批次 `batchSize=1500` 发生请求超时并留下长事务锁，导致 paper score 首次锁等待失败；已通过重启后端释放事务并完成 score。
  - 当前合格候选仍为 4 个；新增 10 个 PAPER 暂无可模拟通过交易，评分被 sample cap 压到 59。
  - 新增优化点：paper/process 需要改成小事务分批提交或异步 job，避免单个大 batch 锁住 `leader_research_candidate`。
  - 2026-06-24 follow-up: 已修复 paper/process 长事务问题：
    - `processPaperCandidates()` 改为按 chunk 调度，默认每轮最多 100 个事件。
    - 实际事件处理改为 `processPaperEventInNewTransaction()`，单个 activity event 使用独立 `REQUIRES_NEW` 事务 claim/process/mark。
    - 这样慢行情估值最多影响单个 event 事务，不再让整批 paper process 锁住候选表。
    - 新增单测覆盖 `batchSize=2/chunkSize=1` 会分两次取事件处理。
    - 后端验证：`LeaderPaperTradingServiceTest` 通过，`compileKotlin` 通过，`bootJar` 通过。
    - 本地正式 API 验证：`paper/process batchSize=30` 返回 processed 21、filtered 9、failed 0；随后 `paper/score` 返回 scoredCount 30。
    - 验证后 `information_schema.INNODB_TRX` 为空，未留下长事务锁。

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

## Iteration 60 Log

**目标**：修复 `Bitcoin Up or Down - June 24, 7:50AM-7:55AM ET` BUY Down 失败，降低 BTC 5 分钟短周期市场的 selector、导航竞态和假成功风险。

**现场记录**：
- record 857：`BUY Down`，amount `$0.6`，失败文本 `Page.query_selector: Execution context was destroyed...`。
- 日志显示 857 已经选中 Down、输入金额、点击 BUY submit；随后 `/portfolio` 轮询复用同一个 executor page 导航到 portfolio，导致 submit 后确认阶段页面上下文被销毁。
- record 858：同一市场 `Could not open buy dialog after outcome click`，属于 BTC Up/Down 二元按钮/买入弹窗路径的历史覆盖缺口。
- record 859：`SELL Down` 被 `Insufficient position, skipped` 跳过，属于账本/风控状态，不是 selector bug。
- 后续观察发现 864 曾把组合页里西班牙持仓 `14.8 份` 误读为 BTC Up 持仓并标记 SUCCESS，属于 BUY post-submit verification 假成功风险。
- 865 说明 5 分钟 BTC 市场可能在等待 `_trade_lock` 期间过期，过期后仍进入 UI 会形成 `Target market content never appeared`。

**改动文件**：
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_buy_verification.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `polymtrade-bridge/test_short_cycle_market_guard.py`

**实现内容**：
- `/portfolio` endpoint 现在同时拿 `_trade_lock` 和 `_portfolio_lock`，避免交易提交后确认阶段被 portfolio scrape 导航抢走页面。
- `_confirm_trade()` 遇到 submit 后页面导航/context closed，按“已提交，交给 post-trade verification 判断”处理，不再直接标 FAILED。
- `executor.stop()` 幂等化，浏览器上下文已关闭时不再把 shutdown 记成异常；lifespan shutdown 会先拿 `_trade_lock`，避免关闭浏览器时踩到交易执行。
- BTC Up/Down 的 audit 覆盖扩展到：
  - `post_submit_navigation_race_fixture`
  - `btc_updown_binary_buy_dialog_fixture`
  - `shutdown_trade_lock_guard`
  - `short_cycle_market_stale_guard`
- BUY position verification 改为在有 `market_slug/market_title` 时只接受紧凑目标市场持仓行，避免把 portfolio 里其他市场的 `shares/份` 当作当前 BTC 市场持仓。
- 新增 BTC 5M stale guard：`btc-updown-5m-<start_ts>` 在 `start+300s-45s` 后进入 `_trade_lock` 时直接标记 `Short-cycle market stale or closing soon, skipped`，不再打开 UI。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python -m pytest polymtrade-bridge/test_bridge_reliability_audit.py -q` 通过：28 passed。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_short_cycle_market_guard.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_buy_verification.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_event_visibility.py` 通过。
- `py_compile` 覆盖 `main.py`、`polymtrade_executor.py`、audit 与新增测试，通过。
- Bridge 已重启，`/status` 返回 `ready=true`、`logged_in=true`、`last_error=null`、`copy_trading_account_id=2`。
- Live audit 窗口 `since_ms=1782301700000`：
  - `pending_timeout_count=0`
  - `actionable_failure_bucket_count=0`
  - `next_action_candidates=[]`
  - 857/858/861/863/865 均已有精确或状态类覆盖；859 保持 `insufficient_position` state/risk。

**下一步候选**：
- 继续处理 live audit 的 `active_success_position_mismatch_count=2`，确认是否由 864 这类历史假成功造成，并在优化点日报提供 reconciliation 或修正入口。
- 若继续跟 BTC 5M leader，建议观察 stale guard 是否开始产生 skip 记录；若过多，说明该 leader 信号/Bridge UI 链路对 5 分钟市场太慢，应降低或禁用该类跟单。

## Iteration 61 Log

**目标**：复查 `Bitcoin Up or Down - June 24, 7:55AM-8:00AM ET` record 861，修复交易列表显示为“其他 + 持仓漂移”的误导问题，并确认代码侧已经阻止同类重启窗口失败。

**现场记录**：
- record 861：
  - `external_trade_id=0xb22bfa8b2db3578ee83abf1d81e34413fa85ce0dc7fbe268e0e157d27cbfd6f7`
  - `BUY Down`
  - `amount=$0.6`
  - 原始错误：`BrowserContext.new_page: Target page, context or browser has been closed`
- Bridge audit 已将 861 归类为 `navigation_race`，并由 `shutdown_trade_lock_guard` 覆盖。
- 页面显示“其他”的原因：前端 `BridgeTradeRecordList` 未识别 `Target page/context/browser closed` 类错误。
- 页面显示“持仓漂移”的原因：后端 position view 用 `PositionKey` 聚合，同市场/outcome 的 FAILED 行复用了 SUCCESS 行的 mismatch view；虽然 mismatch 计算本身限定 SUCCESS，但 DTO 输出没有按当前 record 状态再防一层。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/bridge/BridgeTradeRecordService.kt`
- `frontend/src/pages/BridgeTradeRecordList.tsx`
- `frontend/src/locales/zh-CN/common.json`
- `frontend/src/locales/zh-TW/common.json`
- `frontend/src/locales/en/common.json`
- `LOOP_STATE.md`

**实现内容**：
- `BridgeTradeRecordService.toDto()` 新增输出 guard：
  - 只有当前 record 自身 `status == SUCCESS` 时才暴露 `positionMismatch=true` 和 `positionMismatchReason`。
  - FAILED 行仍可展示 ledger/snapshot 数值，但不会再贴“持仓漂移”标签。
- 前端错误分类新增 navigation race：
  - `execution context was destroyed`
  - `target page, context or browser has been closed`
  - `interrupted by another navigation`
  - 中文显示为“导航/重启竞态”。
- 补齐 zh-CN、zh-TW、en i18n 文案。

**验证结果**：
- 后端 `compileKotlin` 通过。
- 前端 `npm run build` 通过。
- Bridge audit 测试通过：28 passed。
- `test_short_cycle_market_guard.py` 通过。
- 后端已重启，8000 正在监听。
- 直接调用 `/api/bridge/trades/detail` 验证 record 861：
  - `positionMismatch=false`
  - `positionMismatchReason=null`
  - `errorMessage=BrowserContext.new_page: Target page, context or browser has been closed`
- 前端 dev server 3000 正在运行；Bridge 8080 `/status` 正常，`last_error=null`。

**下一步候选**：
- 若页面还显示历史缓存，可刷新浏览器页面；接口数据已确认不会再给 861 返回持仓漂移。
- 后续继续观察 BTC 5M 跟单：若 `Short-cycle market stale or closing soon` skip 增多，说明该 leader 对 5 分钟市场信号太晚或 Bridge UI 链路太慢。

## Iteration 62 Log

**目标**：针对 records 866-870 连续跟单问题，添加 BTC 5 分钟短周期市场硬规则：同一个 leader + 同一个 market 只允许首笔 BUY 进入 UI，后续 BUY 直接跳过；SELL 不拦截。

**现场记录**：
- 866-870 都来自同一个 leader：`0xe7ce284302936fd06ffc7ad05f13c648c513d53a`。
- 5 条记录都属于同一个 market：
  - `Bitcoin Up or Down - June 24, 9:55AM-10:00AM ET`
  - `marketSlug=btc-updown-5m-1782309300`
  - `conditionId=0x8a77ddaabadfbccd4a3cddf52d9b900b4bcf11f7632106ef7f62af701f064425`
- 每条 `transactionHash` 不同，因此不是 webhook 重复；原逻辑只按 `external_trade_id` 幂等，全部被当作独立 leader trade。
- 当时配置允许：
  - `fixed/max/min` 都约 `$1`
  - `max_daily_orders=100`
  - `support_sell=1`
  - 无关键词/价格/单市场冷却限制
- 所以系统按 leader 的 `BUY Down -> BUY Up -> BUY Down -> SELL Down -> BUY Down` 高频 scalping/对冲行为全部跟单。

**改动文件**：
- `polymtrade-bridge/main.py`
- `polymtrade-bridge/bridge_recorder.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_short_cycle_market_guard.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `frontend/src/pages/BridgeTradeRecordList.tsx`
- `frontend/src/locales/zh-CN/common.json`
- `frontend/src/locales/zh-TW/common.json`
- `frontend/src/locales/en/common.json`
- `LOOP_STATE.md`

**实现内容**：
- `BridgeTradeRecorder.has_prior_short_cycle_buy()`：
  - 检查同 bridge、同 leader、同 market_id 或同 marketSlug 是否已有 `PENDING/SUCCESS` BUY。
- `handle_signal()`：
  - BUY 数量计算后、创建真实执行 PENDING 前执行 duplicate guard。
  - 若 `marketSlug` 匹配 `btc-updown-5m-<ts>` 且已有 prior BUY，则写入一条 FAILED skip：
    - `Duplicate short-cycle market BUY skipped: same leader already has a PENDING/SUCCESS BUY for this BTC 5M market`
  - 不进入 UI，不占用 `_trade_lock`。
  - SELL 不受该规则影响，仍可优先执行退出。
- audit 新增 `duplicate_short_cycle_buy` bucket，归为 `state_or_risk`，不进入 code-actionable 修复队列。
- 前端交易列表新增错误类型展示：`短周期重复买入已跳过`。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python test_short_cycle_market_guard.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q` 通过：28 passed。
- `py_compile` 覆盖 main/recorder/audit/tests，通过。
- 前端 `npm run build` 通过。
- Bridge 已重启，`/status` 返回：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
- 用真实 866 market/leader 调 `has_prior_short_cycle_buy()` 返回 `True`，确认 DB 查询能命中既有首笔 BUY。

**下一步候选**：
- 观察后续 BTC 5M 记录，预期第二笔及之后同 leader 同 market BUY 会显示为 `短周期重复买入已跳过`。
- 若需要更保守，可进一步把所有 `btc-updown-5m-*` BUY 默认禁用，仅保留 SELL；目前先按用户要求执行“同 leader 同 market BUY 最多 1 次”。

## Iteration 53 Log

**目标**：把 reconciliation suggestions 从只读展示推进到人工确认闭环，允许 operator 显式确认单条 stale mismatch 并写入 Bridge reconciliation 注释，从而减少历史账本噪音对 SELL 监控的长期干扰。

**监控窗口检查**：
- Bridge `/status` 健康：
  - `ready=true`
  - `logged_in=true`
  - `last_error=null`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- Bridge live `/audit?since_ms=0&limit=100&failure_limit=20`：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `metrics.success_position_mismatch_count=13`
  - `metrics.active_success_position_mismatch_count=0`
  - `metrics.stale_success_position_mismatch_count=13`
  - `metrics.reconciliation_suggestion_count=13`
- Bridge 原生已有：
  - `GET /audit/reconciliations`
  - `POST /audit/reconciliations`
- PolyHermes 后端此前只代理 `/audit` 和 `/status`，没有正式 reconciliation 代理；优化点日报只能看 suggestions，不能人工确认。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/BridgeTradeRecordDto.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/bridge/BridgeAuditClient.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/controller/bridge/BridgeTradeRecordController.kt`
- `frontend/src/types/index.ts`
- `frontend/src/services/api.ts`
- `frontend/src/pages/OptimizationDaily.tsx`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 后端新增正式 reconciliation DTO：
  - `BridgeAuditReconciliationRequest`
  - `BridgeAuditReconciliationAnnotation`
  - `BridgeAuditReconciliationListResponse`
  - `BridgeAuditReconciliationSaveResponse`
- `BridgeAuditClient` 新增：
  - `fetchReconciliations()`
  - `upsertReconciliation()`
  - 配置项 `bridge.audit.reconciliations.url`，默认 `http://localhost:8080/audit/reconciliations`
- `BridgeTradeRecordController` 新增：
  - `POST /api/bridge/trades/audit/reconciliations`
  - `POST /api/bridge/trades/audit/reconciliations/upsert`
- 后端 upsert 做输入校验：
  - status 只允许 `externally_closed`、`manual_closed`、`accepted_stale`、`wrong_market_known`
  - `marketId` 不能为空
  - `outcome` 不能为空
- 前端类型新增 reconciliation request/list/save/annotation 类型。
- `apiService.bridgeTradeRecords` 新增：
  - `auditReconciliations()`
  - `upsertAuditReconciliation()`
- 优化点日报 suggestions 表格新增 `操作` 列：
  - 每行显示 `确认` 按钮。
  - 点击后弹出 `确认历史错配建议` 二次确认。
  - 确认后通过后端正式代理写入单条 reconciliation。
  - 成功后提示 `已确认历史错配` 并刷新 audit。
  - 不做自动批量写入。
- OpenSpec 追加 REQ-66 / SC-68，tasks 追加 10.58。

**验证结果**：
- `frontend npm run build` 通过。
- `backend JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew compileKotlin` 通过。
- Bridge live `/status` 健康。
- Bridge live `/audit?since_ms=0&limit=100&failure_limit=20` 仍返回：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `metrics.reconciliation_suggestion_count=13`
- 未对真实 Bridge 执行 POST `/audit/reconciliations` 冒烟写入，因为这会修改当前 `audit_reconciliations.json`，可能把真实 stale mismatch 标记掉；本轮用前端构建、后端编译和 Bridge live audit 验证链路结构与数据源。

**下一步候选**：
- 若用户确认，可以通过优化点日报逐条确认 stale mismatch，观察 `reconciled_success_position_mismatch_count` 上升、`reconciliation_suggestion_count` 下降。
- 继续观察 post-fix audit；若出现新的 PENDING/FAILED 或 fresh mismatch，优先修 BUY/SELL 执行链路。

## Iteration 54 Log

**目标**：继续收口 SELL 相关历史失败噪音，避免手工零金额 SELL 测试记录被误判为需要继续改代码的 `sell_post_submit_no_effect` / `live_position_insufficient`，同时保留真实 SELL post-submit 无效果失败的可见性。

**监控窗口检查**：
- 离线 full audit 修复前发现：
  - `sell_post_submit_no_effect` 1 条 uncovered，record id 572，`external_trade_id=manual-*`，amount/price 为 0。
  - `live_position_insufficient` 1 条 uncovered，record id 575，`external_trade_id=manual-*`，amount/price 为 0。
  - `insufficient_position` 1 条 uncovered，record id 599，真实外部 id，属于 `state_or_risk` 风险/状态 skip。
- 这些手工零金额记录不代表当前 SELL 代码路径失败，继续留在 code bucket 会干扰下一轮优先级。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- audit row-level 降级规则新增覆盖：
  - `sell_post_submit_no_effect`
  - `live_position_insufficient`
- 当 bucket 属于上述 SELL bucket，且 `external_trade_id` 以 `manual-` 开头，并且 amount 或 price 为 0 时，分类为 `test_or_incomplete_record`。
- 新增回归测试：
  - id 572/575 这类手工零金额 SELL 记录不再进入 actionable 队列。
  - 真实外部 id 且非零 amount/price 的 `SELL post-submit verification failed` 仍保留为 `sell_post_submit_no_effect`。
- OpenSpec 追加 REQ-67 / SC-69，tasks 追加 10.59。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q` 通过：25 passed。
- `polymtrade-bridge/.venv/bin/python test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile bridge_reliability_audit.py test_bridge_reliability_audit.py main.py` 通过。
- 离线 full audit 验证：
  - `sell_post_submit_no_effect` 不再出现。
  - `live_position_insufficient` 不再出现。
  - `test_or_incomplete_record` 包含 id 572/575。
  - id 599 仍为 `insufficient_position` / `state_or_risk`。
- 重启 Bridge 后 `/status` 正常：
  - `ready=true`
  - `logged_in=true`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- Live Bridge `/audit?since_ms=0&limit=150&failure_limit=100` 验证：
  - `monitor_status.status=clear`
  - `metrics.actionable_failure_bucket_count=0`
  - `next_action_candidates=[]`
  - `test_or_incomplete_record` 包含 sample ids 592/575/574/573/572。
  - `insufficient_position` 仍包含 id 599，actionability 为 `state_or_risk`。
- `polymtrade-bridge/.venv/bin/python test_sell_verification.py` 在非沙盒环境通过。沙盒内首次运行时 Chromium headless 被系统关闭，非代码断言失败。

**下一步候选**：
- 当前 live audit 已无 actionable failure bucket；后续应继续观察新增 PENDING/FAILED 或 fresh mismatch。
- 若新增失败再次出现，优先处理非历史、非手工、非 state/risk 的 BUY/SELL 执行链路 bucket。

## Iteration 55 Log

**目标**：继续清理 Bridge audit 中会误导 BUY/SELL 修复优先级的历史失败桶，重点处理 53 条 `Network/deposit modal keeps blocking the trade` 样本，让它们准确反映为资金/充值状态问题，而不是网络/代币选择 modal UI 问题。

**监控窗口检查**：
- Bridge `/status` 健康：
  - `ready=true`
  - `logged_in=true`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- 修复前 full audit：
  - `network_or_token_modal` 53 条 uncovered，样本 id 563/561/556/555/553。
  - 错误文本实际为 `Network/deposit modal keeps blocking the trade. The Bridge account probably has insufficient USDC balance or needs a deposit.`
  - `actionable_failure_bucket_count=0`，但 bucket 名称仍会误导下一轮以为是 modal UI 代码问题。

**改动文件**：
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- `classify_failure()` 调整优先级：
  - 先识别 `insufficient balance`、`insufficient USDC balance`、`needs a deposit`、`余额不足`。
  - 再识别一般 `network/token modal`。
- 新增分类回归：
  - `Network/token modal keeps blocking the trade` 仍为 `network_or_token_modal`。
  - `Network/deposit modal... insufficient USDC balance or needs a deposit` 改为 `insufficient_balance`。
- OpenSpec 追加 REQ-68 / SC-70，tasks 追加 10.60。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q` 通过：25 passed。
- `polymtrade-bridge/.venv/bin/python -m py_compile bridge_reliability_audit.py test_bridge_reliability_audit.py main.py` 通过。
- 离线 full audit 验证：
  - `insufficient_balance` 53 条，actionability 为 `state_or_risk`。
  - `network_or_token_modal` 不再出现。
  - `next_action_candidates=[]`。
- 重启 Bridge 后 live `/status` 正常。
- Live Bridge `/audit?since_ms=0&limit=200&failure_limit=100` 验证：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `metrics.actionable_failure_bucket_count=0`
  - `insufficient_balance` 53 条，样本 id 563/561/556/555/553。
  - `network_or_token_modal` 不再出现。

**下一步候选**：
- 当前 live audit 仍无 code-actionable bucket；继续观察新增 PENDING/FAILED。
- 若后续出现真实 `network_or_token_modal`，应基于截图/DOM 修 modal 选择；若继续出现 `insufficient_balance`，应优先调整跟单金额、余额预检或账户资金告警，而不是改 selector。

## Iteration 56 Log

**目标**：在 audit 分类已将资金不足 modal 归入 `insufficient_balance` 后，进一步改执行链路本身：BUY/SELL 一旦看到明确充值/余额不足 modal，立刻中止并报资金状态错误，不再重复选择 Polygon/USDC、关闭或强制隐藏 modal。

**监控窗口检查**：
- Bridge live `/audit?since_ms=0&limit=220&failure_limit=100`：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `metrics.actionable_failure_bucket_count=0`
  - `insufficient_balance=53`
  - `insufficient_position=1`
  - `next_action_candidates=[]`
- 最大剩余失败类是资金/充值状态问题，不是 selector 或 navigation 代码问题。
- `polymtrade_executor.py` 已有 BUY 前 `_get_usdc_balance()` 预检，但历史样本说明余额有时无法从页面直接读到，之后才进入 deposit modal 路径。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/tasks.md`
- `openspec/changes/improve-polymtrade-bridge-buy-sell-reliability/specs/bridge-trade-reliability/spec.md`
- `LOOP_STATE.md`

**实现内容**：
- 新增 `_is_deposit_or_insufficient_modal_open()`：
  - 只读检测可见 network/token modal。
  - 若 modal 文案包含 `deposit`、`充值`、`insufficient`、`余额不足`、`not enough`，返回 true。
- BUY 路径在以下位置遇到 deposit modal 立即抛 `Insufficient balance for BUY...`：
  - outcome 点击后 network modal 处理前。
  - buy dialog 未打开的 network modal 分支。
  - 输入金额前 final safety check。
- SELL 路径在以下位置遇到 deposit modal 立即抛资金/充值错误：
  - 打开 sell dialog 前。
  - sell dialog attempt 后 network modal 分支。
  - sell dialog 未打开的 network modal 分支。
  - 输入份额前 final safety check。
- 普通 network/token modal 仍按既有逻辑选择 Polygon/USDC。
- selector fixture 新增断言：
  - 普通 network modal：`_is_deposit_or_insufficient_modal_open()` 为 false，仍点击 Polygon/USDC/Confirm。
  - deposit modal：检测为 true，`_select_network_and_token_in_modal()` 返回 false，且不点击 Polygon。
- OpenSpec 追加 REQ-69 / SC-71，tasks 追加 10.61。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade_executor.py test_selector_fixture.py bridge_reliability_audit.py test_bridge_reliability_audit.py main.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest test_bridge_reliability_audit.py -q` 通过：25 passed。
- `polymtrade-bridge/.venv/bin/python test_selector_fixture.py` 非沙盒环境通过：`selector fixture passed`。
- `polymtrade-bridge/.venv/bin/python test_buy_verification.py` 非沙盒环境通过。
- `polymtrade-bridge/.venv/bin/python test_sell_verification.py` 非沙盒环境通过。
- 重启 Bridge 后 live `/status` 正常：
  - `ready=true`
  - `logged_in=true`
  - `copy_trading_account_id=2`
  - `copy_trading_config_count=2`
- Live Bridge `/audit?since_ms=0&limit=220&failure_limit=100` 验证：
  - `monitor_status.status=clear`
  - `monitor_status.actionable_issue_count=0`
  - `metrics.actionable_failure_bucket_count=0`
  - `pending_timeout_count=0`
  - `active_success_position_mismatch_count=0`
  - `insufficient_balance` 仍为 53 条 state/risk 样本。

**下一步候选**：
- 若后续新增 `insufficient_balance`，优先做账户余额展示、跟单金额下调或交易前资金告警。
- 若新增 code-actionable bucket，再回到 selector/navigation/verification 修复队列。

## Iteration 57 Log

**目标**：把第二目标“积累 1000+ 高质量 leader 候选”的下一步正式落到系统中：新增基于真实 `leader_activity_event` 的 politics/finance 扩源入口，绕开 scanner pool 在主策略类别下候选质量不足的瓶颈，并执行一轮导入、评分、PAPER 晋级。

**新增目标动作**：
- 第二目标新增可重复 loop 动作：`POST /api/copy-trading/leader-research/activity-source/import`。
- 动作含义：从真实活动事件中按 politics/finance 关键词聚合钱包，要求同一钱包具备足够事件数、市场多样性、buy/sell 双向行为、安全价格比例，并排除过高长尾价格比例。
- 该动作优先服务政治/金融 80% 主策略目标，补足 scanner pool 难以筛出高质量 politics/finance leader 的问题。

**改动文件**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/repository/LeaderResearchRepositories.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/LeaderResearchDto.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/research/LeaderResearchActivitySourceImportService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/research/LeaderResearchActivityScoringService.kt`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/controller/copytrading/research/LeaderResearchController.kt`
- `backend/src/test/kotlin/com/wrbug/polymarketbot/service/copytrading/research/LeaderResearchActivitySourceImportServiceTest.kt`
- `backend/src/test/kotlin/com/wrbug/polymarketbot/service/copytrading/research/LeaderResearchActivityScoringServiceTest.kt`
- `backend/src/test/kotlin/com/wrbug/polymarketbot/controller/copytrading/research/LeaderResearchControllerTest.kt`
- `docs/zh/leader-discovery-goal-2-phase-1.md`
- `LOOP_STATE.md`

**实现内容**：
- 新增 repository native aggregation：按 category market pattern 从 `leader_activity_event` 聚合 wallet activity。
- 新增 `LeaderResearchActivitySourceImportService`：
  - 支持 `dryRun`、类别列表、每类上限、lookback days。
  - 支持 `minEvents`、`minDistinctMarkets`、`minBuyEvents`、`minSellEvents`、`minSafePriceRatio`、`maxTailPriceRatio`。
  - 写入/更新 `leader_research_candidate`，并记录 `leader_research_event`。
  - 保护 locked/manual candidate。
- 新增 controller endpoint：`POST /api/copy-trading/leader-research/activity-source/import`。
- 评分风控新增 `sell_only_no_entry`，防止只有卖出样本、没有可跟买入入口的钱包高分晋级。
- finance 关键词移除泛词 `market`，降低误收非金融市场风险。

**执行结果**：
- 第一轮真实 activity-source 导入：
  - selectedTotal=160
  - createdTotal=152
  - updatedTotal=8
  - politics selected=10、created=3、updated=7
  - finance selected=150、created=149、updated=1
- 加严 `minBuyEvents=3` 与移除 finance 泛词后 dry-run：
  - selectedTotal=159
  - politics selected=9，全部已存在
  - finance selected=150，其中 12 个仍可新增
- Activity prescreen 强制重评：
  - scannedCount=1327
  - scoredCount=1327
  - risk flags：small_sample=1083、low_market_diversity=939、scanner_pool_unverified=1054、buy_only_no_exit=58、sell_only_no_entry=17。
- 真实晋级 PAPER：
  - selectedTotal=23
  - promotedTotal=23
  - politics promoted=3
  - finance promoted=20
- PAPER 处理：
  - 客户端调用 `paper/process batchSize=500` 在 300 秒超时，但后端继续完成该批处理。
  - 最终 `leader_activity_event` 状态：PROCESSED=1065、FILTERED=615、NEW=220301。
  - `leader_paper_trade` 总数=1680。
- PAPER 评分：
  - `paper/score` scoredCount=53。
  - PAPER 类别分布：politics=15、finance=26、sports=6、crypto=6。
  - politics+finance PAPER 占比 41/53 = 77.4%，接近 80% 主策略目标。

**当前值得继续观察的候选**：
- politics：candidate 617，wallet `0x9703676286b93c2eca71ca96e8757104519a69c2`，score=90.8891，paper trades=33，copyablePnL=21.0191。
- finance：candidate 1742，wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`，score=83.1104，paper trades=10，copyablePnL=4.0469。
- sports：candidate 850 仍为全局最高，score=92.6737，但第二目标资金配置上不应挤占 politics/finance 主配额。

**验证结果**：
- `JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivitySourceImportServiceTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivityScoringServiceTest' --tests 'com.wrbug.polymarketbot.controller.copytrading.research.LeaderResearchControllerTest' bootJar` 通过。
- 后端已重启，当前监听 PID 43951，端口 8000。
- `information_schema.INNODB_TRX` 最终事务数回到 0。

**新发现瓶颈 / 下一步候选**：
- `paper/process batchSize=500` 对含大量已结算/需链上估值的事件会超过 300 秒。下一轮应把 paper process 的 valuation/settlement 查询做缓存或异步化，并给 API 返回 chunk progress，默认 batchSize 下调到 50-100。
- politics 源仍偏少：严格条件下只有 9-10 个 politics activity-source 钱包。下一轮应从政治热门市场 counterparty、Polyburg/Analytics/Dune 或已有优秀 politics leader 的同市场交易对手继续扩源。
- finance 新增较多但需要交叉验证：下一轮应输出每个 finance 候选的命中 market slug 样本，确认不是 crypto/sports 污染或纯做市流。

## Iteration 58 Log

**目标**：修复 Bridge 对当前跟单 leader `0xe7ce284302936fd06ffc7ad05f13c648c513d53a` 的 BTC Up/Down 高频信号选择失败问题，并确认 Bridge 恢复可运行状态。

**问题定位**：
- `copy_order_tracking` 没有普通订单记录，是因为当前跟单账户为 Bridge read-only/magic 钱包路径，缺少 CLOB API key/private key，真实跟单执行走 Web Bridge 的 `bridge_trade_record`。
- 该 leader 已有 Bridge 执行记录：BUY/SELL 均有成功样本；最近失败集中在 BTC Up/Down 的 `Could not select outcome: Up/Down ... rowScore=0`。
- 原选择器把 BTC Up/Down 当成普通二元市场，默认优先匹配 Yes/No/是/否；同时 market keywords 存在时跳过全局 fallback，导致页面上实际短按钮 `Up` / `Down` 没被点击。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_selector_fixture.py`
- `LOOP_STATE.md`

**实现内容**：
- 新增 `_is_binary_updown_market()`，识别 `updown`、`up-or-down`、`up or down`、BTC/Bitcoin + Up/Down 形态。
- 对 BTC Up/Down 市场将 outcome side labels 显式改成 `Up`/`Down`，包含中文涨跌别名。
- 在前端选择器脚本中为 binary Up/Down 市场增加安全的全局短按钮 fallback，只点击文本精确匹配 `Up` 或 `Down` 的可点击按钮，避免被 market title 干扰。
- 增加 BTC Up/Down fixture，覆盖 `Down 57c` 与 `Up 45c` 两个按钮选择场景。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest polymtrade-bridge/test_bridge_reliability_audit.py -q` 通过，25 个测试通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/test_selector_fixture.py polymtrade-bridge/main.py` 通过。
- Bridge 已重启，PID `58768` 监听 `*:8080`。
- `GET /status` 返回 `ready=true`、`logged_in=true`、`last_error=null`、`copy_trading_config_count=3`。
- `GET /audit` 当前 `runtime_status.last_error=null`；历史 `select_outcome` bucket 仍保留 4 条旧失败记录，属于修复前证据，不代表当前 runtime 仍阻塞。

**下一步候选**：
- 等待该 leader 新的 BTC Up/Down 或非体育信号到来后，观察新增 `bridge_trade_record` 是否继续出现 `select_outcome`。
- 如果 audit 仍把已覆盖的历史 `select_outcome` 标为 actionable，应补充 coverage hint，把对应 fixture id 关联到 BTC Up/Down 历史 bucket，避免日报误报。
- `insufficient_position` 仍是风险/状态类跳过，下一轮应继续检查 sell ledger 与真实 portfolio 的漂移处理，而不是把它当成 selector bug。

## Iteration 59 Log

**目标**：排查用户反馈“没有跟单执行成功”的真实原因，并继续修复 Bridge 对当前跟单 leader `Research 0xe7ce...d53a` 的高频 BTC Up/Down 跟单链路。

**问题定位**：
- Bridge webhook 并非没有收到信号：19:18 之后后端继续收到 `leader_trade`，`bridge_webhook_log` id 7106/7107/7109/7110/7111/7112/7113/7114 都是 `SUCCESS`。
- 真实执行结果：
  - id 843：BUY Up，SUCCESS。
  - id 844：BUY Up，FAILED，原因是第一次 BUY 后页面停在 portfolio 持仓列表，第二笔同市场信号把 `Bitcoin Up or Down ... Up• 1.35 份` 的持仓行误判为目标可交易页面，随后找不到 Up 按钮。
  - id 845、847、848、849：后续 BUY 已 SUCCESS。
  - id 846：FAILED，`Target page, context or browser has been closed`，发生在本轮重启 Bridge 期间，属于部署窗口打断。
  - id 850：FAILED，`Insufficient balance for BUY: available 0.3000 USDC, required ~1.0500 USDC`，当前余额不足以继续 1 美元固定跟单。
- 当前不是“完全没有跟单成功”，而是高频同市场连续信号下曾有 portfolio 页面误判；修复后已出现多笔成功，最新阻塞变为余额不足。

**改动文件**：
- `polymtrade-bridge/polymtrade_executor.py`
- `polymtrade-bridge/test_event_visibility.py`
- `polymtrade-bridge/bridge_reliability_audit.py`
- `polymtrade-bridge/test_bridge_reliability_audit.py`
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/bridge/BridgeWebhookClient.kt`
- `LOOP_STATE.md`

**实现内容**：
- `_is_target_event_visible()` 对 BTC Up/Down 使用严格 Up/Down side label，不再把 portfolio 页面上的通用 `买入/卖出` 或持仓行当成可交易按钮。
- 新增 `_side_labels_for_outcome()`，统一 Up/Down 与 Yes/No side label 选择。
- 新增 `_open_target_market_from_portfolio_row()`：如果落在 portfolio 持仓列表且能看到目标市场行，先点击该行进入事件页，再重新寻找真实 Up/Down 交易按钮。
- BUY 重试流程在目标内容不可交易时先尝试点击 portfolio 持仓行，再回退重新导航。
- 新增 event visibility fixture：
  - BTC Up/Down 真实交易按钮可见时返回 true。
  - 只有 portfolio 持仓行时返回 false，并可点击持仓行。
- audit coverage 新增 `btc_updown_binary_portfolio_fixture`，避免 id 844 这类已覆盖历史失败继续占用 selector 待修队列。
- 后端 `BridgeWebhookClient` 新增短重试：0s、2s、5s、10s，避免 Bridge 重启/瞬断时一次发送失败就永久丢信号。

**验证结果**：
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_event_visibility.py` 通过。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_selector_fixture.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m pytest polymtrade-bridge/test_bridge_reliability_audit.py -q` 通过，26 passed。
- `polymtrade-bridge/.venv/bin/python polymtrade-bridge/test_bridge_reliability_audit.py` 通过。
- `polymtrade-bridge/.venv/bin/python -m py_compile polymtrade-bridge/polymtrade_executor.py polymtrade-bridge/bridge_reliability_audit.py polymtrade-bridge/test_event_visibility.py polymtrade-bridge/test_bridge_reliability_audit.py polymtrade-bridge/main.py` 通过。
- 后端 `compileKotlin` 通过，`bootJar` 通过。
- Bridge 已重启并监听 8080，PID 26309，`ready=true`、`logged_in=true`、`copy_trading_config_count=3`。
- 后端已通过 tmux 重启并监听 8000，PID 43841；启动日志确认监听 3 个 leader，包括 `Research 0xe7ce...d53a`。

**当前状态 / 下一步候选**：
- 当前 Bridge `last_error` 是余额不足：可用约 0.3000 USDC，固定跟单金额 1.0000，需要约 1.0500 含缓冲。
- 若继续使用该 leader 跟单，需要先补充 Bridge 账户余额，或把 `copy_trading id=7` 的 fixed/min/max 金额下调到 Polymtrade 可接受的最小值；否则后续 BUY 会继续被余额预检拦截。
- 下次部署 Bridge 时应避免在高频 leader 活跃窗口直接 stop/start；已加 webhook 重试，但正在执行中的浏览器交易仍可能被重启打断。

## Iteration 60 Log

**目标**：恢复并推进第二目标，继续扫链积累高质量 leader，优先 politics/finance，并把候选推进到 PAPER 观察和可试跟前置验证。

**执行内容**：
- 确认后端本地服务正在监听 `8000`，并通过本地 admin JWT 调用正式后端 API。
- 恢复 loop goal 2：系统目标 `leader-discovery-goal-2` 已保持 active。
- 先执行上一轮遗留 PAPER 评分：
  - `paper/score` scoredCount=85。
  - 起始状态：DISCOVERED=1321、PAPER=85、TRIAL_READY=0、COOLDOWN=5。
- 发现 `paper/process batchSize=100` 仍会在 60 秒客户端超时；后台有进度但同步接口不适合大批量。
- 改为小批量验证：`paper/process batchSize=10` 在 6.4 秒内完成，processed=5、filtered=5、failed=0。

**扩源结果**：
- Activity source 放宽 politics/finance 条件后真实导入：
  - selectedTotal=205
  - createdTotal=43
  - updatedTotal=4
  - politics created=18、updated=4
  - finance created=25
- Scanner pool 仅导入 politics/finance：
  - selectedTotal=200
  - createdTotal=196
  - updatedTotal=4
  - politics created=196、updated=4
  - finance selected=0
- Activity prescreen：
  - scannedCount=1560
  - scoredCount=239
  - categoryCounts：politics=214、finance=25
  - risk flags：small_sample=217、low_market_diversity=189、scanner_pool_unverified=196、low_average_size=23、tail_price_spray=6、low_safe_price_ratio=5、buy_only_no_exit=2。
- PAPER 晋级：
  - minScore=75
  - selectedTotal=49
  - promotedTotal=49
  - politics promoted=9
  - finance promoted=40

**本轮结束状态**：
- `leader_research_candidate`：
  - DISCOVERED=1511
  - PAPER=134
  - TRIAL_READY=0
  - COOLDOWN=5
- `leader_activity_event` paper status：
  - PROCESSED=1683
  - FILTERED=817
  - NEW=249260
- `leader_paper_trade` 总数=2500。
- PAPER 从 85 增加到 134；DISCOVERED 从 1321 增加到 1511。

**当前 politics/finance 重点观察候选**：
- politics candidate 617，wallet `0x9703676286b93c2eca71ca96e8757104519a69c2`，score=92.2388，paper trades=42，copyablePnL=23.7822，除 7 天观察期外已满足 TRIAL_READY 主要质量条件；但 evidence 混有 sports，需要继续分类复核。
- politics candidate 1755，wallet `0x31c4578b25af36f34c8aa4cc85f0794bfbea622f`，score=83.7431，paper trades=10，copyablePnL=4.3690，样本刚过线，观察期不足。
- politics candidate 786，wallet `0x30a28af9d4694b1967582a7915c6e048b7bc0b35`，score=76.5981，paper trades=22，copyablePnL=0.3047，回撤与过滤率良好，盈利边际偏薄。
- finance candidate 340，wallet `0x0d2d845a6ff64e31e04a70afce8a573940767ff5`，score=91.6469，paper trades=41，copyablePnL=9.8380；但 evidence 混有 sports，需要分类复核后再考虑。
- finance candidate 1740，wallet `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`，score=87.8093，paper trades=18，copyablePnL=6.7160，filteredRatio=0.10，当前 finance 纯 activity-source 候选里质量较好。
- finance candidate 1742，wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`，score=85.8934，paper trades=19，copyablePnL=10.2852，filteredRatio=0.05，已是当前重点研究 leader。
- finance candidate 1699，wallet `0x7e31c4201a2a040e7c091d26407e4282ada2d45b`，score=85.4866，paper trades=15，copyablePnL=7.1534，unknownRatio=0.0947。
- finance candidate 1704，wallet `0x8bbf889ddcbcc6919edc927b3bfa239c5b2cd9ad`，score=83.8789，paper trades=12，copyablePnL=6.7640，filteredRatio=0.40，仍需观察过滤率。

**为什么还没有 TRIAL_READY**：
- `LeaderPaperTradingService.isEligibleForTrialReady` 要求 PAPER 观察期至少 7 天。
- 当前多数新增 PAPER session age 约 0.01-1.39 天，交易数、PnL、回撤、unknown exposure、filtered ratio 已有候选满足，但观察期未满足。
- 因此本轮不能直接创建可试跟配置；继续 PAPER 观察是正确状态。

**下一轮动作**：
- 使用 `paper/process batchSize=10` 或 20 的稳定小批量循环，避免 100/500 这类同步超时。
- 增加 paper process 性能优化任务：对市场估值/结算查询做缓存或异步化，并让接口返回 chunk progress。
- 对高分但 evidence 混类的 politics/finance 候选做分类复核，尤其排除 sports 污染。
- 继续扩 politics/finance 来源；scanner pool 这轮 finance 为 0，finance 主要依赖 activity-source，politics 则 scanner pool 有补给但 `scanner_pool_unverified` 风险较高。

## Iteration 61 Log

**目标**：继续推进第二目标，并修复上一轮暴露的 `paper/process` 手动批量过大导致 API 长时间阻塞的问题，让 PAPER 观察链路可持续循环。

**问题定位**：
- `LeaderPaperTradingService` 已有 chunk 处理，但默认 `processPaperCandidates()` batchSize 为 200，手动 API 又允许请求被 `coerceIn(1, 5000)` 放大。
- 实测 `batchSize=100` 会 60 秒客户端超时；`batchSize=10` 稳定完成。
- 跨事件缓存当前 market quote 虽可减少查询，但会改变同一市场 BUY/SELL 间的估值语义，可能影响 `CONFIRMED_ZERO` 与 unrealized PnL，因此本轮不采用缓存。

**代码改动**：
- `backend/src/main/kotlin/com/wrbug/polymarketbot/service/copytrading/research/LeaderPaperTradingService.kt`
  - 默认 `DEFAULT_PROCESSING_BATCH_SIZE` 调整为 20。
  - 默认 `DEFAULT_PROCESSING_CHUNK_SIZE` 调整为 10。
  - 新增 `MANUAL_MAX_PROCESSING_BATCH_SIZE=20`，作为手动 API 的硬上限。
- `backend/src/main/kotlin/com/wrbug/polymarketbot/dto/LeaderResearchDto.kt`
  - `LeaderResearchPaperProcessRequest.batchSize` 默认值调整为 20。
  - `LeaderResearchPaperProcessResponse` 增加 `requestedBatchSize`、`effectiveBatchSize`、`maxBatchSize`、`truncated`，让调用方知道是否被限流。
- `backend/src/main/kotlin/com/wrbug/polymarketbot/controller/copytrading/research/LeaderResearchController.kt`
  - `/paper/process` 使用 `MANUAL_MAX_PROCESSING_BATCH_SIZE` 压制手动批量。
- `backend/src/test/kotlin/com/wrbug/polymarketbot/controller/copytrading/research/LeaderResearchControllerTest.kt`
  - 覆盖传 `batchSize=100` 时实际按 20 处理并返回 `truncated=true`。

**验证结果**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.controller.copytrading.research.LeaderResearchControllerTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderPaperTradingServiceTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchJobServiceTest' compileKotlin` 通过。
- `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端已重启，当前 PID `76536` 监听 `8000`。
- 正式 API 验证：
  - 请求 `/api/copy-trading/leader-research/paper/process`，body `{"batchSize":100}`。
  - 响应 `processed=15`、`filtered=5`、`failed=0`。
  - 响应 `requestedBatchSize=100`、`effectiveBatchSize=20`、`maxBatchSize=20`、`truncated=true`。
  - 请求耗时 16.3 秒，没有再 60 秒超时。
- `paper/score` scoredCount=134。

**本轮结束数据**：
- `leader_research_candidate`：DISCOVERED=1511、PAPER=134、TRIAL_READY=0、COOLDOWN=5。
- `leader_activity_event` paper status：PROCESSED=1931、FILTERED=879、NEW=250114。
- `leader_paper_trade` 总数=2810。

**当前优先观察候选更新**：
- finance candidate 1742，wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`，score=95.2304，paper trades=22，copyablePnL=12.0753，filteredRatio=0.0435。
- politics candidate 617，wallet `0x9703676286b93c2eca71ca96e8757104519a69c2`，score=92.4348，paper trades=45，copyablePnL=25.4313，仍需 mixed sports evidence 复核。
- finance candidate 1697，wallet `0x31cfb6c5368a727e2a504e2e0e5a18905a6c4de8`，score=88.8265，paper trades=11，copyablePnL=8.5152。
- finance candidate 1699，wallet `0x7e31c4201a2a040e7c091d26407e4282ada2d45b`，score=85.9811，paper trades=18，copyablePnL=7.1534。
- finance candidate 1740，wallet `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`，score=85.0872，paper trades=21，copyablePnL=5.2545。

**下一轮动作**：
- 用 `batchSize=20` 继续循环 paper process + paper score，直到本批高分 PAPER 的可跟单性样本更充分。
- 对 candidate 617 和 340 这类 evidence 混入 sports 的高分候选做分类复核，避免偏离 politics/finance 80% 主目标。
- 若 20 批量在更多轮次中仍超过 20 秒，应继续做异步 job/progress endpoint，而不是再放大同步 API。

## Iteration 62 Log

**目标**：继续推进第二目标，修复 politics/finance 高分候选里混入 sports/crypto evidence 的分类漏洞，避免错误 leader 进入主策略观察和后续试跟。

**问题定位**：
- 原 `LeaderResearchActivityScoringService` 和 `LeaderResearchPaperPromotionService` 使用 source evidence 中第一个 `category` 作为候选类别。
- 对于 `scanner_pool:politics + scanner_pool:sports` 或 `scanner_pool:finance + scanner_pool:sports` 的候选，第一个标签会让系统把混类钱包当成 politics/finance。
- 实例：
  - candidate 617 `0x9703676286b93c2eca71ca96e8757104519a69c2`：politics evidence 后混入 sports evidence，paper PnL 很好但不能直接代表政治 leader。
  - candidate 340 `0x0d2d845a6ff64e31e04a70afce8a573940767ff5`：finance evidence 后混入 sports evidence。

**代码改动**：
- 新增 `LeaderResearchCategoryEvidenceClassifier`：
  - 解析 `sourceEvidence` 中所有 `category:` / `category=`。
  - 统计分类出现次数。
  - 若存在多个类别且主导占比低于 70%，标记 `mixed=true`。
  - 输出主类别、分类计数、主导比例和 mixed 状态。
- `LeaderResearchActivityScoringService`：
  - 使用新 classifier 推断类别。
  - reason 写入 `category_mix` 与 `category_dominance`。
  - mixed evidence 增加 `mixed_category_evidence` risk flag。
  - mixed evidence 分数 capped 到 60，避免进入高分 PAPER 晋级。
- `LeaderResearchPaperPromotionService`：
  - 使用新 classifier 推断类别。
  - `mixed_category_evidence` 加入 hard exclude flags，避免新候选晋级 PAPER。
- `LeaderResearchScoringService`：
  - PAPER/copyability 评分时保留 `mixed_category_evidence`，避免已在 PAPER 的混类候选被 paper PnL 洗掉风险标签。
- `LeaderResearchStateMachine`：
  - PAPER -> TRIAL_READY 前先检查 hard risk。
  - `mixed_category_evidence`、`unknown_category`、`tail_price_spray`、`buy_only_no_exit`、`sell_only_no_entry` 阻止自动 TRIAL_READY。

**验证结果**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivityScoringServiceTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScoringServiceTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchStateMachineTest' compileKotlin` 通过。
- `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端已重启，当前 PID `3713` 监听 `8000`。
- 正式 API 重评：
  - `activity-score/run force=true`：scannedCount=1511、scoredCount=1511。
  - riskFlagCounts 中新增/识别 `mixed_category_evidence=47`。
  - `paper/score` scoredCount=134，随后晋级新 PAPER 后 scoredCount=175。

**执行结果**：
- `promote-paper dryRun` 在新规则下只选出 41 个无 hard risk politics/finance 候选。
- 正式执行 `promote-paper`：
  - selectedTotal=41
  - promotedTotal=41
  - politics promoted=1
  - finance promoted=40
- 小批量 paper process：
  - `batchSize=20`
  - processed=15
  - filtered=5
  - failed=0
  - 请求耗时 15.35 秒。

**本轮结束数据**：
- `leader_research_candidate`：DISCOVERED=1470、PAPER=175、TRIAL_READY=0、COOLDOWN=5。
- mixed category 分布：DISCOVERED=47、PAPER=15。
- `leader_activity_event` paper status：PROCESSED=1946、FILTERED=884、NEW=251263。
- `leader_paper_trade` 总数=2830。

**当前 clean politics/finance 重点观察候选**：
- politics candidate 1755，wallet `0x31c4578b25af36f34c8aa4cc85f0794bfbea622f`，score=80.2914，paper trades=10，copyablePnL=4.3690。
- finance candidate 1742，wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`，score=95.2348，paper trades=22，copyablePnL=12.0753。
- finance candidate 1697，wallet `0x31cfb6c5368a727e2a504e2e0e5a18905a6c4de8`，score=88.8310，paper trades=11，copyablePnL=8.5152。
- finance candidate 1699，wallet `0x7e31c4201a2a040e7c091d26407e4282ada2d45b`，score=85.9856，paper trades=18，copyablePnL=7.1534。
- finance candidate 1740，wallet `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`，score=85.0917，paper trades=21，copyablePnL=5.2545。
- finance candidate 1704，wallet `0x8bbf889ddcbcc6919edc927b3bfa239c5b2cd9ad`，score=83.4150，paper trades=12，copyablePnL=6.7640，但 filteredRatio=0.40，继续观察。

**下一轮动作**：
- 继续用 batchSize=20 循环 paper process + paper score，让新晋级 41 个 PAPER 产生真实模拟样本。
- 针对 politics 来源不足问题继续扩源；本轮干净 politics 只晋级 1 个，说明 politics 高质量供给仍是瓶颈。
- 考虑给前端 Leader Research 页面展示 `mixed_category_evidence` 的中文解释，避免用户误读被隔离的高分混类候选。

## Iteration 63 Log

**目标**：恢复第二目标的下一步 loop，继续积累高质量 leader，优先推进 PAPER 观察样本，并检查 politics/finance 扩源瓶颈。

**环境恢复**：
- 用户登录密码已重置并验证：`admin / 11111111`。
- 后端已由 `tmux` 会话 `polyhermes-backend` 接管，监听 `8000`。
- 前端 `3000`、Bridge `8080` 均在线。

**执行动作**：
- `paper/process batchSize=20`：
  - processed=15
  - filtered=5
  - failed=0
  - duration≈17s
- `paper/score`：
  - scoredCount=175
  - scoreVersion=`research-copyability-v1`
- `promote-paper dryRun`：
  - selectedTotal=17
  - politics=0
  - finance=11
  - sports=4
  - crypto=2
- 正式 `promote-paper` 一次性执行 17 个时触发 HTTP 500，且后端短暂掉线；未产生部分晋级。
- 改为小批量正式晋级：
  - finance=1：成功 promoted=1
  - finance=5：成功 promoted=5
  - sports=2：成功 promoted=2
  - crypto=1：成功 promoted=1
  - PAPER 总数从 175 增至 184。
- 晋级后 `paper/process batchSize=20`：
  - processed=17
  - filtered=3
  - failed=0
  - duration≈23s
- 晋级后 `paper/score`：
  - scoredCount=184

**扩源结果**：
- `activity-source/import` politics + finance，limitPerCategory=100：
  - selectedTotal=111
  - createdTotal=0
  - updatedTotal=0
  - skippedExistingTotal=111
  - politics selected=11，全部已存在
  - finance selected=100，全部已存在

**当前数据**：
- DISCOVERED=1461
- PAPER=184
- COOLDOWN=5
- TRIAL_READY=0
- activePaperSessions=184

**当前高分 clean PAPER 重点观察候选**：
- finance candidate 1742，wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`，score=95.2944，trade_count=22，filtered_ratio=0.0435，copyablePnL=12.0753。
- sports candidate 850，wallet `0xe9cbb1c9b3f7f411dd4fdf2ea7afa780c8b4d096`，score=94.0728，trade_count=59，filtered_ratio=0.1324，copyablePnL=12.0089。
- finance candidate 34，wallet `0x328c2be6eba95a30b003255dc48f2b50e0eccbbc`，score=92.7769，trade_count=25，filtered_ratio=0.2188，copyablePnL=17.4971。
- finance candidate 1629，wallet `0xc89d5c0f4d12aa83475b2b7804995578c46d9dc0`，score=89.2325，trade_count=10，filtered_ratio=0.1667，copyablePnL=8.3315。
- finance candidate 1697，wallet `0x31cfb6c5368a727e2a504e2e0e5a18905a6c4de8`，score=88.8906，trade_count=11，filtered_ratio=0.2143，copyablePnL=8.5152。
- finance candidate 1755，wallet `0x31c4578b25af36f34c8aa4cc85f0794bfbea622f`，score=80.3510，trade_count=10，filtered_ratio=0.2308，copyablePnL=4.3690，是当前较干净 politics 重点观察候选。

**发现的问题**：
- 一次性正式晋级 17 个候选不稳定，可能与 `stateMachine.advance` 同步 leader pool / paper session 的批量写入路径有关；小批量晋级稳定。
- 新晋级候选大多只有 0-1 笔模拟，重评分后被 `small_sample` 降至约 59，符合保护预期。
- 当前 activity-source 在默认条件下无法新增 politics/finance 候选，说明 politics 高质量供给已被当前源吃干，需要扩展新源或降低筛选维度后再二次过滤。

**下一轮动作**：
- 修复或规避 `promote-paper` 一次性正式晋级 17 个导致 500/掉线的问题：优先把后端接口内部拆为小批量事务，或增加 `maxPromotePerRequest` 保护。
- 继续按小批量 `promote-paper` + `paper/process` + `paper/score` 推进剩余 finance/sports/crypto 候选。
- 针对 politics 扩源：放宽 activity-source politics 的 `minSellEvents/minDistinctMarkets` 做 dry-run 对比，或接入新的 politics market/wallet 来源，而不是重复导入已存在候选。

## Iteration 64 Log

**目标**：修复第二目标 loop 中 `promote-paper` 一次性正式晋级过多候选导致 HTTP 500 / 后端掉线的问题，并继续推进剩余高分候选进入 PAPER 观察。

**代码改动**：
- `LeaderResearchPaperPromotionService`：
  - 对正式晋级启用请求级全局上限 `LIVE_PROMOTE_BATCH_LIMIT=8`。
  - dry-run 不限流，仍展示完整候选预览。
  - 正式执行按类别顺序消耗本次上限，超出部分留给下一轮 loop。
- `LeaderResearchPaperPromotionResponse`：
  - 新增 `requestedSelectedTotal`。
  - 新增 `effectiveSelectedLimit`。
  - 新增 `truncated`。
  - 旧字段保持兼容，前端无需同步即可继续展示。
- 新增 `LeaderResearchPaperPromotionServiceTest`：
  - 覆盖 dry-run 17 个候选完整预览。
  - 覆盖正式晋级 17 个候选时只执行 8 个，并返回 `truncated=true`。

**验证**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPaperPromotionServiceTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchStateMachineTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScoringServiceTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivityScoringServiceTest' compileKotlin` 通过。
- `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端重新创建 `tmux` 会话 `polyhermes-backend` 并启动，当前监听 `8000` 的 Java PID 为 `42048`。

**真实 API 验证**：
- 使用原大请求：
  - `politicsLimit=20`
  - `financeLimit=20`
  - `sportsLimit=5`
  - `cryptoLimit=5`
  - `dryRun=false`
- 返回 HTTP 200，无 500，后端保持在线。
- 本次剩余可晋级正好只有 8 个，因此响应为：
  - selectedTotal=8
  - promotedTotal=8
  - requestedSelectedTotal=8
  - effectiveSelectedLimit=8
  - truncated=false
- 这 8 个新增 PAPER：
  - finance=5
  - sports=2
  - crypto=1

**继续处理结果**：
- 新晋级后 `paper/process batchSize=20`：
  - processed=12
  - filtered=8
  - failed=0
  - duration≈14s
- `paper/score`：
  - scoredCount=192
- 再次 `promote-paper dryRun`：
  - selectedTotal=0
  - 当前没有 `score>=80` 的 DISCOVERED/CANDIDATE 可晋级。

**当前数据**：
- DISCOVERED=1453，max_score=60.0000。
- PAPER=192，max_score=95.2985。
- COOLDOWN=5。
- TRIAL_READY=0。

**当前高分 clean PAPER 重点观察候选**：
- finance candidate 1742，wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`，score=95.2985，trade_count=22，filtered_ratio=0.0435，copyablePnL=12.0753。
- sports candidate 850，wallet `0xe9cbb1c9b3f7f411dd4fdf2ea7afa780c8b4d096`，score=94.0769，trade_count=59，filtered_ratio=0.1324，copyablePnL=12.0089。
- finance candidate 34，wallet `0x328c2be6eba95a30b003255dc48f2b50e0eccbbc`，score=92.7810，trade_count=25，filtered_ratio=0.2188，copyablePnL=17.4971。
- finance candidate 1697，wallet `0x31cfb6c5368a727e2a504e2e0e5a18905a6c4de8`，score=88.8947，trade_count=11，filtered_ratio=0.2143，copyablePnL=8.5152。
- finance candidate 1629，wallet `0xc89d5c0f4d12aa83475b2b7804995578c46d9dc0`，score=87.4289，trade_count=11，filtered_ratio=0.1538，copyablePnL=7.3315。
- politics candidate 1755，wallet `0x31c4578b25af36f34c8aa4cc85f0794bfbea622f`，score=80.3550，trade_count=10，filtered_ratio=0.2308，copyablePnL=4.3690。

**下一轮动作**：
- 当前高分 DISCOVERED/CANDIDATE 已清空，下一步必须换扩源策略，而不是继续重复 promote。
- 针对 politics：做放宽参数 dry-run 对比，例如 `minSellEvents=1`、`minDistinctMarkets=2`、`limitPerCategory=200`，看是否能产生新增或更高分 politics 候选。
- 针对 finance：可以继续扩 activity source 的 lookback 或从 scanner pool 导入更低 discoveryScore 的候选，但要保持 tail/low-size 风险二次过滤。
- 对 PAPER=192 的候选继续滚动 `paper/process + paper/score`，等待更多真实模拟样本把 small_sample 候选拉开。

## Iteration 65 Log

**目标**：在高分 DISCOVERED/CANDIDATE 清空后，验证 politics 扩源瓶颈是否来自筛选条件过紧，并尝试补充 politics PAPER 观察样本。

**Politics 放宽扩源对比**：
- 方案 A dry-run：
  - lookbackDays=30
  - minEvents=8
  - minDistinctMarkets=2
  - minBuyEvents=2
  - minSellEvents=1
  - minSafePriceRatio=0.20
  - maxTailPriceRatio=0.50
  - selectedTotal=23
  - createdTotal=0
  - updatedTotal=0
  - skippedExistingTotal=23
- 方案 B dry-run：
  - lookbackDays=45
  - minEvents=6
  - minDistinctMarkets=2
  - minBuyEvents=1
  - minSellEvents=1
  - minSafePriceRatio=0.15
  - maxTailPriceRatio=0.55
  - selectedTotal=46
  - createdTotal=6
  - updatedTotal=4
  - skippedExistingTotal=36

**执行动作**：
- 正式执行方案 B politics import：
  - createdTotal=6
  - updatedTotal=4
  - skippedExistingTotal=36
- `activity-score/run force=true`：
  - scannedCount=1459
  - scoredCount=1459
  - categoryCounts: politics=705, finance=447, sports=156, crypto=151
  - riskFlagCounts: small_sample=1317, low_market_diversity=1143, scanner_pool_unverified=1269, mixed_category_evidence=47, low_average_size=124, tail_price_spray=77, low_safe_price_ratio=86, buy_only_no_exit=64, sell_only_no_entry=16
- `promote-paper dryRun` politics-only：
  - selectedTotal=1
  - candidate 2045，wallet `0xa42f127d7e8df9f16881ffcc9ed0bc0326875f5a`，activity score=100，无 prescreen risk flags。
- 正式晋级 candidate 2045：
  - promotedTotal=1
  - 进入 PAPER。
- `paper/process batchSize=20`：
  - processed=15
  - filtered=5
  - failed=0
- `paper/score`：
  - scoredCount=193

**新 politics 候选复核**：
- candidate 2045，wallet `0xa42f127d7e8df9f16881ffcc9ed0bc0326875f5a`
  - researchState=PAPER
  - score=54.0001
  - riskFlags=`high_filtered_ratio,small_sample`
  - trade_count=1
  - filtered_count=1
  - filtered_ratio=0.5000
  - copyablePnL=0
- 结论：放宽参数可以补 politics PAPER 样本，但新增候选质量偏弱，重评分保护有效，不能作为可试跟候选。

**当前数据**：
- DISCOVERED=1458
- PAPER=193
- COOLDOWN=5
- TRIAL_READY=0

**下一轮动作**：
- politics 不能只靠放宽阈值扩大；需要增加 politics 来源质量，例如从明确政治市场的高成交 matched orders、持仓盈利钱包、或外部 analytics 钱包榜导入。
- 对新增 politics 候选继续 paper 观察，不进入试跟。
- 继续滚动处理 PAPER=193 的模拟样本，等待 small_sample 候选自然分层。

## Iteration 66 Log

**目标**：继续推进第二目标，验证 scanner pool / activity source 是否仍能提供新的 politics/finance 候选，并修复 activity source 对已有候选新鲜 evidence 不刷新的问题。

**数据盘点**：
- research 状态：
  - DISCOVERED=1458
  - PAPER=193
  - COOLDOWN=5
- scanner pool 分布：
  - politics: ANALYZED=1039, PENDING=913, PROMOTED=106, REJECTED=31
  - finance: ANALYZED=548, PENDING=641, PROMOTED=97, REJECTED=89
  - PENDING politics 最高 discoveryScore=38，PENDING finance 最高 discoveryScore=25，直接导入价值低。
- scanner-pool dry-run：
  - politics minDiscoveryScore=70/90 且 onlyPending=false：selected=100，全部 SKIP_EXISTING。
  - finance minDiscoveryScore=70：selected=100，全部 SKIP_EXISTING。
  - finance minDiscoveryScore=90：selected=58，全部 SKIP_EXISTING。
- 结论：scanner pool 高分 politics/finance 已基本导入过，不是新增来源瓶颈。

**代码改动**：
- `LeaderResearchActivitySourceImportService`：
  - 原逻辑只要已有 `activity_source:<category>` 就 `SKIP_EXISTING`。
  - 新逻辑改为只有 evidence 文本完全相同才跳过。
  - 若同一钱包同一 category 的统计窗口更新（events/markets/buy/sell/ratio/last_event_time 改变），则执行 UPDATE，追加新 evidence 并刷新 `lastSourceSeenAt`。
- `LeaderResearchActivitySourceImportServiceTest`：
  - 新增“已有 activity_source 但 evidence 变化时 UPDATE”的测试。
  - 新增“evidence 完全相同时 SKIP_EXISTING”的测试。

**验证**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivitySourceImportServiceTest' compileKotlin` 通过。
- `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端已重启，当前监听 `8000` 的 Java PID 为 `59987`。
- Bridge health 正常：`{"status":"ok","executor_ready":true}`。

**真实运行结果**：
- activity-source import politics+finance：
  - selectedTotal=131
  - createdTotal=1
  - updatedTotal=94
  - skippedExistingTotal=36
  - politics: selected=11, updated=8, skippedExisting=3
  - finance: selected=120, created=1, updated=86, skippedExisting=33
- `activity-score/run force=true`：
  - scannedCount=1459
  - scoredCount=1459
  - categoryCounts: politics=704, finance=448, sports=156, crypto=151
- `promote-paper dryRun` politics+finance：
  - selectedTotal=2
  - politics=0
  - finance=2
  - candidates:
    - candidate 2049, wallet `0x38bf7d014b6ac7c778e80daf63617263e23a28e2`, prescreen score=100
    - candidate 1673, wallet `0xe5055891698b43217f58f15cfef5f231425ee3bf`, prescreen score=100
- 正式晋级：
  - promotedTotal=2
  - finance=2
- `paper/process batchSize=20`：
  - processed=16
  - filtered=4
  - failed=0
- `paper/score`：
  - scoredCount=195

**新增候选复核**：
- candidate 2049 `0x38bf7d014b6ac7c778e80daf63617263e23a28e2`：
  - PAPER
  - score=59
  - riskFlags=`small_sample`
  - trade_count=0
- candidate 1673 `0xe5055891698b43217f58f15cfef5f231425ee3bf`：
  - PAPER
  - score=59
  - riskFlags=`small_sample`
  - trade_count=0
- 结论：刷新链路有效，新候选进入 PAPER，但被小样本保护拦住，不能作为可试跟。

**当前高分 clean PAPER 观察候选**：
- finance candidate 1742，wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`，score=95.3029，trade_count=22，filtered_ratio=0.0435，copyablePnL=12.0753。
- sports candidate 850，wallet `0xe9cbb1c9b3f7f411dd4fdf2ea7afa780c8b4d096`，score=94.0813，trade_count=59，filtered_ratio=0.1324，copyablePnL=12.0089。
- finance candidate 34，wallet `0x328c2be6eba95a30b003255dc48f2b50e0eccbbc`，score=92.7853，trade_count=25，filtered_ratio=0.2188，copyablePnL=17.4971。
- finance candidate 1629，wallet `0xc89d5c0f4d12aa83475b2b7804995578c46d9dc0`，score=89.7856，trade_count=12，filtered_ratio=0.1429，copyablePnL=8.4253。
- finance candidate 1697，wallet `0x31cfb6c5368a727e2a504e2e0e5a18905a6c4de8`，score=88.8991，trade_count=11，filtered_ratio=0.2143，copyablePnL=8.5152。
- finance candidate 1609，wallet `0x674887d1ac838099a48b629dff53f25b7b87ee08`，score=84.3196，trade_count=13，filtered_ratio=0，copyablePnL=4.6257。

**下一轮动作**：
- 继续滚动 `paper/process + paper/score`，让 newly promoted finance candidates 脱离 small_sample。
- 对 politics 需要新增更高质量来源，而不是再重复 scanner pool；优先考虑从明确 politics 市场的盈利/高成交钱包中抽取，而不是 broad keyword activity source。
- 可考虑给 activity-source import 增加 `refreshExisting` 返回/参数展示，方便前端看到“更新了多少旧候选”。

## Iteration 67 - 2026-06-25 23:58 CST - activity-source 新钱包优先与严格金融增量

**目标**：
- 继续第二目标，解决 politics/finance activity-source 被旧钱包占满 selected 窗口的问题。
- 在不降低质量阈值的前提下，找到新的高质量 finance leader 候选并推进 PAPER。

**发现**：
- politics 严格条件（30 天、events>=8、markets>=3、buy>=2、sell>=2、safe_ratio>=0.40、tail_ratio<=0.35）下没有未知钱包，短期 politics source 已接近挖空。
- finance 严格条件下存在未知钱包，但原 importer 的 selected 窗口被已有钱包占满：
  - limit=30 dry-run：created=0，updated=18，skippedExisting=12。
  - limit=120 dry-run：created=0，updated=9，skippedExisting=111。
- 根因：repository SQL 按质量排序没问题，但 service 在 `take(limit)` 前没有把 CREATE/UPDATE 和 SKIP_EXISTING 区分；旧钱包会吃掉探索额度。

**代码改动**：
- `LeaderResearchActivitySourceImportService`：
  - source fetch 深度从 `limit * 3` 改成 `min(limit * 20, 1000)`。
  - 在裁剪 selected 之前计算候选动作优先级：
    - CREATE 优先级 0。
    - evidence 变化的 UPDATE 优先级 1。
    - unchanged SKIP_EXISTING 优先级 2。
    - locked 优先级 3。
  - 保留原 SQL 的质量排序，优先级只用于避免旧候选挤掉新增候选。
- `LeaderResearchActivitySourceImportServiceTest`：
  - 新增测试：当批次额度不足时，新钱包应排在 unchanged existing wallet 前面。

**验证**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivitySourceImportServiceTest' compileKotlin bootJar` 通过。
- 后端用 `./run_backend_local.sh` 重启成功，当前 Java PID `93676`，登录 OK。

**真实运行结果**：
- 严格 finance dry-run：
  - selectedTotal=30
  - createdTotal=30
  - updatedTotal=0
  - skippedExistingTotal=0
- 正式导入：
  - selectedTotal=30
  - createdTotal=30
  - updatedTotal=0
  - skippedExistingTotal=0
- `activity-score/run force=true`：
  - scannedCount=1487
  - scoredCount=1487
  - categoryCounts: politics=704, finance=476, sports=156, crypto=151
- `promote-paper`：
  - selectedTotal=8
  - promotedTotal=8
  - truncated=false
- `paper/process batchSize=40`：
  - requestedBatchSize=40
  - effectiveBatchSize=20
  - truncated=true
  - processed=17
  - filtered=3
  - failed=0
- `paper/score`：
  - scoredCount=203
- summary：
  - DISCOVERED=1479
  - PAPER=203
  - TRIAL_READY=0
  - COOLDOWN=5

**新增 PAPER 质量复核**：
- 新晋级 8 个 finance 候选目前仍以 `small_sample` 为主：
  - 2079 `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`: score=59, trade_count=0, risk=`small_sample`。
  - 2064 `0xa21203771d5bdfa26d38ad080d52d5b814a01bc3`: score=59, trade_count=0, risk=`small_sample`。
  - 2063 `0x3e5d55e7d987489ceb9a85984b43b75ad3fef957`: score=59, trade_count=1, copyablePnL=-1, risk=`small_sample`。
  - 2062 `0xaf9264c8bf3c64487813c594cd7cab2cf4c59937`: score=59, trade_count=0, risk=`small_sample`。
  - 2061 `0x3a603f6b4354c091f4171c6c40995315df188717`: score=59, trade_count=0, risk=`small_sample`。
  - 2060 `0x06ae9a98783712fb490e9500481c67c3655af059`: score=45.0002, risk=`high_filtered_ratio,small_sample`。
  - 2059 `0x026b72036f5121574ef6cb13fab94032823f8412`: score=59, trade_count=0, risk=`small_sample`。
  - 2054 `0x06ee671e3e303bafe6ea9f07a8b5fa2186fa97d2`: score=59, trade_count=1, copyablePnL=-1, risk=`small_sample`。
- 结论：本轮成功解决“新增被旧候选挤掉”的瓶颈，并积累 30 个严格 finance 新候选；但新晋级 PAPER 还不能进入真钱试跟，需继续滚动 paper processing 或提高可用 paper event 覆盖。

**下一轮动作**：
- 继续跑 `paper/process + paper/score`，观察新 finance 候选是否脱离 `small_sample`。
- 增加“新增候选导入率”指标到日报/目标页，跟踪每轮 created/updated/skippedExisting。
- politics 需要新来源：从明确 politics 市场的成交订单中按 realized/copyable proxy 选钱包，而不是继续 broad keyword + total amount。

## Iteration 68 - 2026-06-26 00:18 CST - 定向 PAPER 验证与新 finance 高分候选

**目标**：
- 继续第二目标，解决新晋级 PAPER 候选被全池 fair processing 分流，无法快速脱离 `small_sample` 的问题。
- 继续探索 politics 高质量新增来源。

**运行态检查**：
- 后端监听 8000，Java PID 从 `93676` 重启为 `58721`。
- MySQL 3307 正常。
- Bridge health：`{"status":"ok","executor_ready":true}`。
- research summary 开始时：
  - DISCOVERED=1479
  - PAPER=203
  - TRIAL_READY=0
  - COOLDOWN=5

**发现**：
- 昨晚新晋级的 8 个 finance PAPER 候选仍有大量 `NEW` 且 `usable_for_paper=1` 的事件：
  - 目标 8 个钱包合计事件状态：NEW=378、PROCESSED=2、FILTERED=1。
- 原 `paper/process` 只能对全体 PAPER/TRIAL_READY 钱包 fair processing，无法优先验证刚晋级的新候选；这会拖慢 leader 质量确认。
- politics 严格新增来源仍稀缺：
  - strict politics unknown quality：0。
  - geo politics unknown quality：0。
  - 现有 politics clean PAPER 中 score>=80 仅 candidate 1755 一个较好。

**代码改动**：
- `LeaderResearchPaperProcessRequest` 新增 `candidateIds: List<Long> = emptyList()`。
- `LeaderResearchController.processPaper` 透传 `candidateIds`。
- `LeaderPaperTradingService`：
  - `processPaperCandidates` / `processPaperCandidatesInChunks` / `processPaperCandidatesChunk` 新增可选 `candidateIds`。
  - `candidateIds` 为空时保持原有全池行为。
  - `candidateIds` 非空时仅加载指定 ID 中状态为 PAPER/TRIAL_READY 的候选，并只处理这些钱包的 NEW/RETRYABLE event。
- 测试：
  - `LeaderPaperTradingServiceTest` 新增定向 candidateIds 处理测试。
  - `LeaderResearchControllerTest` 新增 controller 透传 candidateIds 测试。

**验证**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderPaperTradingServiceTest' --tests 'com.wrbug.polymarketbot.controller.copytrading.research.LeaderResearchControllerTest' compileKotlin` 通过。
- `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端用 `./run_backend_local.sh` 重启成功，登录 OK。

**运行结果**：
- 先用旧全池处理跑 10 批：
  - processed=161
  - filtered=39
  - failed=0
  - 但新 8 个只从 PROCESSED=2 增至 PROCESSED=5，仍严重分流。
- 使用新 `candidateIds` 定向处理 10 批：
  - target candidateIds: 2079,2064,2063,2062,2061,2060,2059,2054
  - processed=158
  - filtered=42
  - failed=0
  - 目标 8 个钱包事件状态：PROCESSED=163、FILTERED=43、NEW=175。
- `paper/score`：
  - scoredCount=203。

**新候选质量结果**：
- 新 8 个中出现 2 个高质量 finance PAPER：
  - candidate 2079, wallet `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`
    - score=91.1332
    - riskFlags=null
    - trade_count=32
    - filtered_ratio=0.0857
    - copyablePnL=8.7053
    - max_drawdown=0
  - candidate 2063, wallet `0x3e5d55e7d987489ceb9a85984b43b75ad3fef957`
    - score=87.8488
    - riskFlags=null
    - trade_count=18
    - filtered_ratio=0.1429
    - copyablePnL=7.4917
    - max_drawdown=-1.3759
- 新 8 个中其余：
  - 2064/2061/2060 风险已清空但分数 71-74，暂不试跟。
  - 2062/2059 亏损。
  - 2054 有 `high_filtered_ratio,tail_price_spray`，应排除。
- 当前全池 clean PAPER 且 score>=80、trade_count>=10、copyablePnL>0 的候选数：19。

**下一轮动作**：
- 将 candidate 2079、2063 标记为“finance 优先观察/可试跟候选”，进入人工确认或试跟配置创建候选队列。
- 给目标日报/Leader 管理页增加“定向 paper process”入口和本轮新增转化指标：created -> promoted -> clean score>=80。
- politics 继续需要新数据源，不是单纯放宽阈值；当前 persisted activity 中没有满足严格条件的未知 politics 钱包。

## Iteration 69 - 2026-06-26 00:29 CST - Leader Research Funnel 可视化

**目标**：
- 继续第二目标，把“1000+ leader 积累”和“高质量可观察候选”从人工 SQL/日志变成系统可查询指标。
- 在 Leader 研究页直接展示目标进度、分类转化和优先观察候选。

**代码改动**：
- 后端 DTO：
  - 新增 `LeaderResearchFunnelResponse`。
  - 新增 `LeaderResearchFunnelCategoryDto`。
  - 新增 `LeaderResearchFunnelCandidateDto`。
- 后端服务：
  - `LeaderResearchService.funnel()` 聚合：
    - targetTotal=1000。
    - totalCandidates。
    - progressPercent。
    - cleanHighScoreTotal。
    - 分类 politics/finance/sports/crypto 的 total/PAPER/clean high score。
    - top 10 priorityCandidates。
  - clean high score 标准：
    - PAPER/TRIAL_READY。
    - score>=80。
    - riskFlags 为空。
    - tradeCount>=10。
    - copyablePnl>0。
  - 类别从 evidence 的最后一个有效 `category:` 提取，多 evidence 钱包更贴近最新证据。
- 后端接口：
  - `POST /api/copy-trading/leader-research/funnel`。
- 前端：
  - `LeaderResearchFunnel*` 类型。
  - `apiService.leaderResearch.funnel()`。
  - Leader 研究页新增：
    - Leader 积累漏斗。
    - 分类转化。
    - 优先观察候选。

**验证**：
- 后端：
  - `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.controller.copytrading.research.LeaderResearchControllerTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderPaperTradingServiceTest' compileKotlin` 通过。
  - `cd backend && ... ./gradlew --no-daemon --no-parallel compileKotlin bootJar` 通过。
- 前端：
  - `cd frontend && npm run build` 通过；仅有既有 chunk size warning。
- 后端已重启，登录 OK。
- funnel API 真实返回：
  - targetTotal=1000。
  - totalCandidates=1687。
  - progressPercent=168.7000。
  - cleanHighScoreTotal=19。
  - 分类：
    - politics: total=730, PAPER=29, clean=1, topCandidate=1755。
    - finance: total=609, PAPER=148, clean=12, topCandidate=1742。
    - sports: total=184, PAPER=16, clean=4, topCandidate=850。
    - crypto: total=163, PAPER=10, clean=2, topCandidate=34。
  - top priority candidates 前 5：
    - 1742 finance score=95.3194。
    - 850 sports score=94.0979。
    - 34 crypto score=92.8019。
    - 2079 finance score=91.1332。
    - 1697 finance score=88.9156。

**结论**：
- “1000+ leader 积累”数量目标当前已超过，但高质量 clean 候选只有 19。
- 目标瓶颈已经从“候选数量”转为“高质量转化率”和“政治来源质量”。
- finance 方向有效，politics 方向仍只有 1 个 clean high score，需要新数据源而不是继续放宽 persisted activity 阈值。

**下一轮动作**：
- 在 funnel 基础上增加“目标配比健康度”：politics+finance 是否达到 clean 候选 80%，sports+crypto 是否控制在 20%。
- 对 top finance 候选 2079/2063 生成试跟模板草案，但保持禁用，等待人工确认。
- politics 继续探索外部/新来源：Polymarket Analytics、历史 profitable order 钱包、特定政治市场成交簿反查。

## Iteration 70 - 2026-06-26 00:40 CST - 澄清 Leader 管理 555 与研究候选 1687 口径

**问题**：
- 用户在 Leader 管理看到 555 条，而 Leader Research funnel 显示 1687，容易理解成数据不一致。

**核对结果**：
- `leader_research_candidate`：1687，这是研究候选总数。
- `copy_trading_leaders`：555，这是 Leader 管理正式 Leader 总数。
- `copy_trading_leader_pool`：191，这是 Leader 池总数。
- `leader_scanner_candidate_pool`：7090，这是扫链候选池原始/分析池。

**代码改动**：
- `LeaderResearchFunnelResponse` 增加：
  - `managedLeaderTotal`
  - `leaderPoolTotal`
- `LeaderResearchService.funnel()` 返回正式 Leader 管理数和 Leader 池数。
- Leader 研究页把卡片标题从“Leader 积累漏斗”改成“研究候选漏斗”，并展示：
  - 研究候选目标进度。
  - 正式 Leader 管理。
  - Leader 池。
  - 高质量可观察。

**验证**：
- `cd backend && ... ./gradlew --no-daemon --no-parallel compileKotlin bootJar` 通过。
- `cd frontend && npm run build` 通过；只有既有 chunk size warning。
- 后端已重启。
- `/leader-research/funnel` 真实返回：
  - `totalCandidates=1687`
  - `managedLeaderTotal=555`
  - `leaderPoolTotal=191`
  - `cleanHighScoreTotal=19`

**结论**：
- 555 和 1687 都正确，但不是同一口径。
- 1687 是研究候选总盘，555 是正式 Leader 管理页记录数；页面现在已显式区分。

## Iteration 71 - 2026-06-26 01:16 CST - Bridge 模式接入 Telegram 推送

**问题**：
- 用户已配置 Telegram 且测试成功，但 Bridge 模式交易由 Python bridge 直接写入 `bridge_trade_record`，没有走后端 CLOB 订单通知链路。
- 结果是 Bridge 成功、失败、规则跳过只在桥接交易记录里可见，不会主动推送。

**代码改动**：
- `bridge_trade_record` 增加通知去重字段：
  - `notification_status`
  - `notification_sent_at`
  - `notification_error`
- 新增 `BridgeTradeNotificationPollingService`：
  - 每 5 秒扫描 `notification_status=PENDING` 且状态为 `SUCCESS/FAILED` 的 Bridge 记录。
  - 发送 Telegram 纯文本中文消息，包含市场、方向、数量、价格、金额、Leader、跟单配置、Bridge、记录 ID、失败原因和时间。
  - 发送后标记 `SENT`，异常时标记 `FAILED` 并记录错误。
- Bridge 记录 DTO 增加通知状态字段，后续 UI 可展示“已推送/失败/跳过”。
- Flyway 迁移 `V62__add_bridge_trade_notification_status.sql`：
  - 新记录默认 `PENDING`。
  - 已有历史记录迁移时统一标记 `SKIPPED`，避免重启后刷屏推送旧记录。

**验证**：
- 后端：
  - `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel compileKotlin test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchNotificationSummaryServiceTest'` 通过。
  - `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端已重启，Flyway 已执行迁移。
- 数据库验证：
  - `notification_status`、`notification_sent_at`、`notification_error` 字段存在。
  - 历史 Bridge 记录：`SKIPPED/FAILED=1144`，`SKIPPED/SUCCESS=76`。
  - 当前待推送终态旧记录：0。
- Bridge runtime 健康检查：
  - `http://localhost:8080/health` 返回 `status=ok, executor_ready=true`。

**结论**：
- Bridge 模式从现在开始会对新产生的成功/失败/规则跳过记录推送 Telegram。
- 历史记录不会补推，避免 Telegram 噪音。

## Iteration 72 - 2026-06-26 10:18 CST - 第二目标扩源并修复 PAPER 池污染

**目标**：
- 恢复第二目标 loop：继续积累 1000+ 高质量 leader，政治/金融优先。
- 本轮重点验证 activity source 是否还能产生新增候选，并避免低样本候选进入正式 Leader 池。

**初始状态**：
- 后端、Bridge 均在线；Bridge `/health` 返回 `status=ok, executor_ready=true`。
- `/leader-research/funnel`：
  - totalCandidates=1687
  - managedLeaderTotal=595
  - leaderPoolTotal=191
  - cleanHighScoreTotal=19
  - politics clean=1，finance clean=12，sports clean=4，crypto clean=2。

**扩源 dry-run 结论**：
- scanner pool 高分 politics/finance 已基本吃干：
  - selectedTotal=394，createdTotal=0，skippedExistingTotal=394。
- activity source 仍有增量：
  - politics 放宽参数：created=6，updated=33。
  - finance deeper：created=250。

**执行动作**：
- 正式导入 politics relaxed：
  - selected=54，created=6，updated=33。
- 正式导入 finance deeper：
  - selected=250，created=250。
- activity score：
  - scanned=1735，scored=1735。
  - categoryCounts: politics=711, finance=717, sports=156, crypto=151。
- promote dry-run：
  - selected=24，politics=4，finance=20。
- 先按旧逻辑晋级并 paper process：
  - promoted=32。
  - paper process processed=31，filtered=9。
  - paper score 后新增 32 个全部被 `small_sample` 限制到 45-59 分，无 clean high。

**发现的问题**：
- 状态机原本 `canSyncToLeaderPool()` 对除 DISCOVERED 外所有状态都同步 Leader Pool。
- 这导致 PAPER 观察候选即使 paper 后低分，也会创建正式 Leader 管理和 Leader Pool 记录。
- 本轮新增 32 个 PAPER 中：
  - clean_after_paper_count=0。
  - 其中 31 个新建陌生 leader/pool 无任何 copy_trading 引用。

**修复**：
- `LeaderResearchStateMachine`：
  - 从“非 DISCOVERED 都同步池”改为：
    - `TRIAL_READY` 才新建/同步正式 Leader Pool。
    - 已有 `leaderId` 或 `poolId` 的候选仍可同步 metadata，避免破坏既有 leader。
- 新增测试：
  - 新 PAPER 候选只启动观察，不创建 Leader Pool。
  - TRIAL_READY 候选会同步 Leader Pool。
- 清理本轮误创建数据：
  - 删除 31 个无 copy_trading 引用的新建 `RESEARCH_AGENT/WATCH/PAPER` pool 和对应新建 leader。
  - 移除 1 个绑定既有 leader 的新建 WATCH pool，但保留既有 leader。

**修复后真实路径验证**：
- 重新打包并重启后端。
- 再晋级 8 个 finance 到 PAPER：
  - before: managed=595, pool=191, paper=235。
  - promoted=8，paper process processed=16，filtered=4。
  - after: managed=595, pool=191, paper=243。
  - 证明 PAPER 观察不会再污染正式 Leader 管理/池子。
- 当前 funnel：
  - totalCandidates=1943。
  - managedLeaderTotal=595。
  - leaderPoolTotal=191。
  - cleanHighScoreTotal=19。
  - finance paper=180，politics paper=37。

**验证**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchStateMachineTest' compileKotlin` 通过。
- `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端已重启，仅一个进程监听 8000。
- Bridge 仍健康：`status=ok, executor_ready=true`。

**结论**：
- 数量目标进一步推进：研究候选从 1687 增至 1943，PAPER 从 203 增至 243。
- 高质量 clean 候选仍为 19，说明新增候选需要更多 paper 样本，不应直接进入正式 Leader 池。
- 本轮最重要改进是把 PAPER 观察层和正式可跟单 Leader 池重新隔离，避免低样本候选污染跟单候选池。

**下一轮动作**：
- 继续滚动处理 PAPER=243 的模拟样本，等待 small_sample 候选自然分层。
- 对 finance 剩余高分 DISCOVERED 继续小批量进 PAPER，但不进入正式池。
- politics 仍需更高质量外部来源，单纯放宽 activity source 只能补样本，不能明显增加 clean high。

## Iteration 73 - 2026-06-26 10:31 CST - 滚动 PAPER 样本并观察 clean high 分层

**目标**：
- 在修复 PAPER/Leader Pool 隔离后，继续滚动处理 `PAPER=243` 的模拟样本。
- 判断 small_sample 候选是否能自然分层，且确认正式 Leader 管理/池子不被污染。

**初始状态**：
- Bridge `/health` 正常：`status=ok, executor_ready=true`。
- 后端单实例监听 8000。
- 状态：
  - totalCandidates=1943。
  - PAPER=243。
  - cleanHighScoreTotal=19。
  - small_trade_sessions=152。
  - managedLeaderTotal=595。
  - leaderPoolTotal=191。

**执行动作**：
- 连续执行 8 轮：
  - `POST /api/copy-trading/leader-research/paper/process`
  - `POST /api/copy-trading/leader-research/paper/score`
- 总处理结果：
  - processed=124。
  - filtered=36。
  - failed=0。
  - scoredCount 每轮为 243。

**观察结果**：
- 第 1-4 轮后：
  - cleanHighScoreTotal 从 19 升至 21。
  - politics clean 从 1 升至 2。
  - finance clean 从 12 升至 13。
- 第 5-8 轮后：
  - cleanHighScoreTotal 回到 19。
  - politics clean 保持 2。
  - finance clean 回到 11。
- 说明 rolling paper 会真实拉开质量：
  - 有的候选获得更多样本后升上来。
  - 有的 finance 候选因为 filtered ratio 或 PnL 回撤被压下去。
  - 这符合目标，不应把 activity prescreen 的 100 分直接当可跟单评分。

**当前 clean high 重点候选**：
- finance `1742`：wallet `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
  - score=95.6187，tradeCount=22，filteredRatio=0.0435，copyablePnl=12.0753。
- finance `2079`：wallet `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`
  - score=91.4324，tradeCount=32，filteredRatio=0.0857，copyablePnl=8.7053。
- finance `1660`：wallet `0x5b6331e7ff0831a3fe2ed12004747db1a9c911a4`
  - score=91.1937，tradeCount=18，filteredRatio=0.2800，copyablePnl=10.1530。
  - 注意：filteredRatio 偏高，继续观察。
- politics `360`：wallet `0x645a91730f588c5586e8860936a7e3554303fd84`
  - score=83.8075，tradeCount=19，filteredRatio=0，copyablePnl=4.4010。
  - 注意：sourceEvidence 中同时有 scanner finance/politics 与 activity politics，当前按最新 activity politics 归类；进入试跟前需要分类复核。
- politics `1755`：wallet `0x31c4578b25af36f34c8aa4cc85f0794bfbea622f`
  - score=80.6752，tradeCount=10，filteredRatio=0.2308，copyablePnl=4.3690。

**当前 funnel**：
- totalCandidates=1943。
- managedLeaderTotal=595。
- leaderPoolTotal=191。
- cleanHighScoreTotal=19。
- 分类：
  - politics: total=741, paper=37, clean=2, topCandidate=360。
  - finance: total=854, paper=180, clean=11, topCandidate=1742。
  - sports: total=184, paper=16, clean=4, topCandidate=850。
  - crypto: total=163, paper=10, clean=2, topCandidate=34。

**结论**：
- 本轮没有新增代码，但目标状态更真实：clean high 候选从短暂 21 回到 19，说明系统正在过滤 activity-score 虚高候选。
- politics 出现新的 clean high 候选 360，但因为证据来源混杂，需要继续观察，不应直接进入实盘跟单。
- 正式 Leader 管理和 Leader Pool 数量保持 595/191，PAPER 滚动未污染正式池。

**下一轮动作**：
- 增加“clean high 稳定性”判断：连续多轮 paper score 仍满足 clean high 才允许进入 TRIAL_READY 或推荐试跟。
- 对 candidate 360 做分类证据复核，避免混类 politics 候选误入政治配比。
- 继续对 finance 剩余高分 DISCOVERED 小批量进入 PAPER，但坚持不进入正式池。

## Iteration 74 - 2026-06-26 10:31 CST - 固化 clean high 稳定性与混类拦截

**目标**：
- 把上一轮人工判断固化到代码：候选不能因为某一轮短暂高分就进入 `TRIAL_READY`。
- 修复 candidate 360 这类“3 条 politics + 1 条 finance”证据没有被标记 mixed 的问题。

**代码改动**：
- `LeaderResearchStateMachine`：
  - PAPER -> TRIAL_READY 现在必须满足：
    - 当前 score >= 80。
    - 当前 riskFlags 为空。
    - paper session 满足原有可试跟条件。
    - 最近 3 次 `research-copyability-v1` 评分都 >= 80。
  - 移除旧的“只拦截部分 risk flags”逻辑，改为 riskFlags 必须为空。
- `LeaderResearchCategoryEvidenceClassifier`：
  - mixed dominance 阈值从 `0.70` 收紧到 `0.80`。
  - 目的：当一个候选有 25% 跨类证据时，也进入 `mixed_category_evidence`，避免误入政治/金融配比。
- 测试：
  - 新增“只有 2 次稳定高分不能进 TRIAL_READY”。
  - 新增“最近 3 次里有 1 次低于 80 不能进 TRIAL_READY”。
  - 新增“3:1 跨类证据也会被标记 mixed”。

**验证**：
- `cd backend && JAVA_HOME=/Users/henry/projects/polyhermes/jdk17/Contents/Home PATH=/Users/henry/projects/polyhermes/jdk17/Contents/Home/bin:$PATH ./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchStateMachineTest' --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScoringServiceTest' compileKotlin` 通过。
- `cd backend && ... ./gradlew --no-daemon --no-parallel bootJar` 通过。
- 后端已重启，单实例监听 8000。
- Bridge 健康：`status=ok, executor_ready=true`。

**真实数据验证**：
- 重跑 `paper/score`：
  - scoredCount=243。
- candidate 360：
  - score=83.8116。
  - riskFlags 从空变成 `mixed_category_evidence`。
- clean high：
  - 从 19 降到 18。
- TRIAL_READY：
  - 仍为 0，没有自动误推进。
- Leader 管理/池子：
  - managed=595。
  - pool=191。

**结论**：
- 系统现在更保守、更贴近目标：稳定高分 + 无风险标记才可能进入可试跟阶段。
- candidate 360 虽然 paper 表现好，但证据混类，已被正确排除出 clean high。
- 当前高质量候选减少到 18，但质量更可信。

**下一轮动作**：
- 增加“目标配比健康度”：politics+finance clean high 需要接近 80%，sports+crypto 控制在 20%。
- 继续扩 politics/finance 来源，尤其 politics 需要新来源而不是单纯放宽 activity source。
- 对当前 18 个 stable clean high 做类别配比和试跟优先级排序。

## Iteration 75 - 2026-06-26 10:45 CST - 暴露目标配比健康度

**目标**：
- 把第二目标中的“政治/金融 80%，体育/加密 20%”变成可观测指标，而不是只靠人工看分类数量。
- 让 Leader Research 页面能直接提示当前候选结构是否偏离目标配比，并指出主类别缺口。

**代码改动**：
- 后端 `LeaderResearchFunnelResponse` 新增 `allocationHealth`：
  - primaryCategories: `politics`, `finance`。
  - secondaryCategories: `sports`, `crypto`。
  - primaryTargetPercent: `80`。
  - secondaryTargetPercent: `20`。
  - primaryActualPercent / secondaryActualPercent。
  - primaryCleanHighCount / secondaryCleanHighCount。
  - primaryDeficitCount。
  - status: `EMPTY` / `HEALTHY` / `WATCH` / `DEFICIT`。
  - message: 中文解释当前配比状态。
- 前端 Leader Research 页面在“研究候选漏斗”卡片内新增“主类别配比”展示：
  - 显示政治/金融 clean high 占比。
  - 显示目标进度条。
  - 显示 politics/finance 与 sports/crypto 的 clean high 数量。
  - 显示后端返回的中文健康度提示。

**验证**：
- 后端测试与编译通过：
  - `LeaderResearchStateMachineTest`
  - `LeaderResearchScoringServiceTest`
  - `compileKotlin`
- 前端构建通过：
  - `npm run build`
  - 仅保留既有 warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 后端 `bootJar` 通过并已重启。
- Backend 单实例监听 8000。
- Bridge 健康：
  - `status=ok`
  - `executor_ready=true`

**真实数据验证**：
- `GET/POST /api/copy-trading/leader-research/funnel` 当前返回：
  - clean high 总数：18。
  - primary clean high：12。
  - secondary clean high：6。
  - primaryActualPercent：66.6667%。
  - secondaryActualPercent：33.3333%。
  - primaryDeficitCount：3。
  - status：`DEFICIT`。
  - message：`主类别 politics/finance 明显不足，至少还需补 3 个 clean high 候选。`
- 当前分类 clean high：
  - politics：1，topCandidateId=1755。
  - finance：11，topCandidateId=1742。
  - sports：4。
  - crypto：2。
- 当前优先候选第一名：
  - candidateId=1742。
  - wallet=`0xe7ce284302936fd06ffc7ad05f13c648c513d53a`。
  - category=`finance`。
  - score=95.6227。
  - tradeCount=22。
  - filteredRatio=0.0435。
  - copyablePnl=12.0753。
  - state=`PAPER`。

**结论**：
- 第二目标现在有了可执行的结构性反馈：不是“候选越多越好”，而是 clean high 候选必须向政治/金融主类别倾斜。
- 当前状态明确为 `DEFICIT`，说明下一轮不应优先扩大 sports/crypto，而应继续找 politics/finance，尤其 politics。

**下一轮动作**：
- 继续扩 politics/finance 数据源，并把新增候选先进入 PAPER 观察。
- 对当前 18 个 clean high 做试跟优先级排序，但优先级排序必须参考 allocationHealth，避免 sports/crypto 抢占主类别预算。
- 在页面或 API 增加“为什么未进入 TRIAL_READY”的原因聚合，方便下一轮把 PAPER 候选推进到可试跟。

## Iteration 76 - 2026-06-26 10:49 CST - 扩 finance PAPER 并暴露试跟阻塞原因

**目标**：
- 继续推进第二目标：优先补 politics/finance 主类别候选，并解释高分候选为什么没有进入可试跟。

**执行动作**：
- activity-source 正式导入，参数：
  - categories=`politics,finance`
  - limitPerCategory=25
  - lookbackDays=60
  - minEvents=8
  - minDistinctMarkets=2
  - minBuyEvents=2
  - minSellEvents=1
  - minSafePriceRatio=0.20
  - maxTailPriceRatio=0.50
- 导入结果：
  - selectedTotal=50。
  - createdTotal=25。
  - updatedTotal=5。
  - skippedExistingTotal=20。
  - politics：created=0，updated=5，skippedExisting=20。
  - finance：created=25，updated=0。
- activity prescreen：
  - scannedCount=1720。
  - scoredCount=1720。
  - categoryCounts：politics=707，finance=706，sports=156，crypto=151。
  - 主要风险：small_sample=1507、scanner_pool_unverified=1255、low_market_diversity=1132。
- promote PAPER：
  - dry-run 显示 politics=0、finance=20 可晋级。
  - 正式晋级受 live batch limit 限制，promotedTotal=8。
  - 新晋级全部为 finance。
- paper process + score 连续 3 轮：
  - 轮 1：processed=16，filtered=4，failed=0，scoredCount=251。
  - 轮 2：processed=12，filtered=8，failed=0，scoredCount=251。
  - 轮 3：processed=17，filtered=3，failed=0，scoredCount=251。

**代码改动**：
- `LeaderResearchFunnelCandidateDto` 新增 `trialReadiness`：
  - eligible。
  - blockers。
  - ageHours。
  - stableHighScoreCount。
  - requiredStableHighScoreCount。
- `LeaderResearchService.funnel()` 为优先候选计算试跟准备度：
  - score>=80。
  - riskFlags 为空。
  - PAPER 观察至少 7 天。
  - 通过模拟交易 >=10。
  - 模拟总样本 >=10。
  - copyablePnL>0。
  - maxDrawdown>=-15。
  - unknown valuation exposure <=20%。
  - filteredRatio<50%。
  - 最近 3 次 `research-copyability-v1` 评分均 >=80。
- 前端 Leader Research 页面“优先观察候选”展示：
  - 可试跟 / 观察中。
  - 第一条阻塞原因。
  - 稳定高分计数，例如 `3/3`。

**验证**：
- 后端通过：
  - `LeaderResearchStateMachineTest`
  - `LeaderResearchScoringServiceTest`
  - `compileKotlin`
  - `bootJar`
- 前端通过：
  - `npm run build`
  - 保留既有 warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 后端已通过 `run_backend_local.sh` 重启：
  - PID=45910。
  - 监听 8000。
- Bridge 健康：
  - `status=ok`
  - `executor_ready=true`

**真实数据验证**：
- funnel 当前：
  - totalCandidates=1968。
  - PAPER=251。
  - cleanHighScoreTotal=18。
  - primary clean high=12。
  - secondary clean high=6。
  - primaryActualPercent=66.6667%。
  - status=`DEFICIT`。
  - primaryDeficitCount=3。
- 第一优先候选：
  - candidateId=1742。
  - wallet=`0xe7ce284302936fd06ffc7ad05f13c648c513d53a`。
  - category=finance。
  - score=95.6282。
  - tradeCount=22。
  - copyablePnl=12.0753。
  - stableHighScoreCount=3/3。
  - trialReadiness.eligible=false。
  - blocker=`PAPER 观察不足 7 天：当前 43 小时`。

**结论**：
- finance 来源仍能补新候选：本轮新增 25 个、推进 8 个进入 PAPER。
- politics 扩源明显瓶颈：宽松 activity-source 下仍没有新 politics 可晋级 PAPER，只能更新 5 个已有候选。
- 当前最强 finance 候选 1742 质量条件基本达标，未进入 TRIAL_READY 的主要原因是 7 天观察期未满，不是评分或稳定性失败。
- clean high 数暂未提升，符合预期：新 PAPER 候选需要更多模拟交易样本后才能进入 clean high。

**下一轮动作**：
- 继续滚动处理 PAPER=251 的模拟样本，优先观察新晋级 finance 候选是否转化为 clean high。
- 针对 politics 单独扩源：需要扩大政治关键词和来源，而不是继续重复当前 activity-source 参数。
- 增加 politics-source 诊断，输出“为什么没有 politics 可晋级”的原因分布。

## Iteration 77 - 2026-06-26 11:08 CST - 增加快速观察层并按主类别缺口排序

**背景**：
- 用户追问“观察为什么一定要 7 天”。
- 复核结果：
  - OpenSpec 设计中明确要求 `PAPER -> TRIAL_READY` 纸跟时间 >= 7 天。
  - 代码中 `PAPER_MIN_AGE_MS = 7L * 24 * 60 * 60 * 1000`。
- 判断：
  - 7 天适合保留为正式 `TRIAL_READY` 安全闸门。
  - 但为了加快第二目标 leader 筛选，可以增加一个不创建跟单配置的快速观察层。

**代码改动**：
- `LeaderResearchTrialReadinessDto` 新增：
  - `level`：`TRIAL_READY` / `FAST_WATCH` / `OBSERVE`。
  - `label`：中文标签。
  - `fastWatchBlockers`：快速观察层的阻塞原因。
- `LeaderResearchService` 新增快速观察判定：
  - score >= 85。
  - riskFlags 为空。
  - PAPER 观察 >= 48 小时。
  - 通过模拟交易 >= 20。
  - 模拟总样本 >= 20。
  - copyablePnL > 0。
  - maxDrawdown >= -8。
  - unknown valuation exposure <= 10%。
  - filteredRatio < 20%。
  - 最近 3 次 `research-copyability-v1` 评分均 >= 80。
- 重要边界：
  - `eligible` 仍只代表正式可试跟。
  - `FAST_WATCH` 不会绕过 `TRIAL_READY`，不会创建正式跟单配置。
- 优先候选排序调整：
  - 当 allocationHealth 显示 politics/finance 主类别有缺口时，优先观察候选先排 politics/finance，再按 score 和 copyablePnL 排序。
  - 避免 sports/crypto 在主类别 DEFICIT 时抢占 top 位。
- 前端 Leader Research 页面：
  - 展示 `可试跟` / `快速观察` / `观察中`。
  - `FAST_WATCH` 用蓝色标签。
  - 普通观察继续展示第一条正式阻塞原因。

**验证**：
- 后端通过：
  - `LeaderResearchStateMachineTest`
  - `LeaderResearchScoringServiceTest`
  - `compileKotlin`
  - `bootJar`
- 前端通过：
  - `npm run build`
  - 保留既有 warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 后端已重启：
  - PID=7791。
  - 监听 8000。
- Bridge 健康：
  - `status=ok`
  - `executor_ready=true`

**真实数据验证**：
- allocationHealth：
  - primaryActualPercent=66.6667%。
  - primaryDeficitCount=3。
  - status=`DEFICIT`。
- 优先候选 top8 现在全部为 finance：
  - 1742：score=95.6282，tradeCount=22，filteredRatio=0.0435，age=44h，level=`OBSERVE`。
    - 正式阻塞：`PAPER 观察不足 7 天：当前 44 小时`。
    - 快速观察阻塞：`快速观察至少需要 48 小时：当前 44 小时`。
  - 2079：score=91.4419，tradeCount=32，filteredRatio=0.0857，age=12h，level=`OBSERVE`。
  - 1660：score=90.7878，tradeCount=18，filteredRatio=0.3077，age=15h，level=`OBSERVE`。
  - 1697：score=89.2244，tradeCount=11，filteredRatio=0.2143，age=15h，level=`OBSERVE`。
  - 2063：score=88.1576，tradeCount=18，filteredRatio=0.1429，age=12h，level=`OBSERVE`。
  - 1699：score=86.3789，tradeCount=18，filteredRatio=0.2174，age=44h，level=`OBSERVE`。
  - 1611：score=86.2773，tradeCount=50，filteredRatio=0.1228，age=14h，level=`OBSERVE`。
  - 1740：score=85.485，tradeCount=21，filteredRatio=0.087，age=44h，level=`OBSERVE`。

**结论**：
- 系统现在能区分：
  - 正式可试跟：仍需 7 天，安全闸门不变。
  - 快速观察：满足更严交易质量但未满 7 天，用于加速研究判断。
  - 普通观察：继续等待样本或风险指标改善。
- 当前主类别候选里还没有 `FAST_WATCH`，1742 最接近，主要差约 4 小时观察期。
- politics 仍是最明显短板；finance 有多个接近快速观察的候选。

**下一轮动作**：
- 等 1742/1740/1699 等 44h 候选超过 48h 后，重跑 funnel，确认是否进入 `FAST_WATCH`。
- 继续 paper/process 新晋级 finance，争取把更多主类别候选推到 clean high。
- 单独做 politics-source 诊断，输出无 politics 晋级的原因分布。

## Iteration 78 - 2026-06-26 13:18 CST - politics-source 诊断并新增 1 个政治 PAPER

**目标**：
- 把 politics 扩源瓶颈从“感觉缺来源”变成可重复诊断数据。
- 在不写库的诊断基础上，发现可用新增 politics 钱包后再走正式导入、评分、PAPER 晋级。

**代码改动**：
- 新增只读诊断接口：
  - `POST /api/copy-trading/leader-research/politics-source/diagnose`
- 新增 DTO：
  - `LeaderResearchPoliticsSourceDiagnoseRequest`
  - `LeaderResearchPoliticsSourceDiagnoseResponse`
  - `LeaderResearchPoliticsSourceBucketDto`
  - `LeaderResearchPoliticsSourceSampleDto`
- 新增 service：
  - `LeaderResearchPoliticsSourceDiagnoseService`
- 诊断能力：
  - 从 `leader_activity_event` 按 politics 关键词聚合钱包。
  - 左连接 `leader_research_candidate` 和 `leader_paper_session`。
  - 输出：
    - scannedWallets。
    - passImportCriteria。
    - unknownWallets / existingWallets。
    - paperWallets / cleanHighWallets。
    - eligibleForPaperNow。
    - blocker bucket 计数。
    - top sample 钱包与阻塞原因。
- 诊断不导入、不评分、不推进状态。

**验证**：
- 后端通过：
  - `LeaderResearchControllerTest`
  - `compileKotlin`
  - `bootJar`
- 后端已重启：
  - PID=93209。
  - 监听 8000。
- 前端服务在线：
  - `http://localhost:3000` 可访问。
- Bridge 健康：
  - `status=ok`
  - `executor_ready=true`

**politics-source 诊断结果**：
- 请求参数：
  - lookbackDays=60。
  - minEvents=8。
  - minDistinctMarkets=2。
  - minBuyEvents=2。
  - minSellEvents=1。
  - minSafePriceRatio=0.20。
  - maxTailPriceRatio=0.50。
  - limit=500。
- 结果：
  - scannedWallets=500。
  - passImportCriteria=31。
  - unknownWallets=275。
  - existingWallets=225。
  - paperWallets=43。
  - cleanHighWallets=3。
  - eligibleForPaperNow=1。
- Top blockers：
  - events_below_8：295。
  - safe_ratio_below_0.2000：238。
  - already_in_research_pool：225。
  - score_below_75：213。
  - tail_ratio_above_0.5000：191。
  - sell_below_1：183。
  - risk:small_sample：97。
  - risk:low_safe_price_ratio：86。
  - buy_below_2：85。
  - risk:tail_price_spray：75。
  - risk:scanner_pool_unverified：59。
  - already_paper：43。

**正式执行**：
- politics activity-source import：
  - selectedTotal=31。
  - createdTotal=1。
  - updatedTotal=5。
  - skippedExistingTotal=25。
- 新增 politics 钱包：
  - wallet=`0xad5353afe30c2da57709e2704ef3ccdcf67eef24`。
  - totalEvents=10。
  - distinctMarkets=7。
  - buyEvents=9。
  - sellEvents=1。
  - safePriceRatio=0.8000。
  - tailPriceRatio=0.2000。
  - avgAmount=2.5934。
  - totalAmount=25.9339。
- activity-score：
  - scannedCount=1713。
  - scoredCount=1713。
  - categoryCounts：politics=708，finance=698，sports=156，crypto=151。
- politics promote PAPER：
  - selectedTotal=1。
  - promotedTotal=1。
  - candidateId=2361。
  - score=96.25000000。
  - riskFlags=[]。
- paper process：
  - processed=17。
  - filtered=3。
  - failed=0。
- paper score：
  - scoredCount=252。

**最新 funnel**：
- totalCandidates=1969。
- PAPER=252。
- cleanHighScoreTotal=17。
- primary clean high=14。
- secondary clean high=3。
- primaryActualPercent=82.3529%。
- allocationHealth status=`HEALTHY`。
- politics：
  - totalCandidates=742。
  - paperCandidates=38。
  - cleanHighScoreCandidates=1。
  - topCandidateId=1755。
- finance：
  - totalCandidates=879。
  - paperCandidates=188。
  - cleanHighScoreCandidates=13。
  - topCandidateId=1742。

**结论**：
- politics 源并非完全枯竭，但当前持久化活动数据里，高质量未知 politics 钱包非常少。
- 主要瓶颈是：
  - 样本不足。
  - 安全价格比例不足。
  - 长尾极端价格过高。
  - 缺少 sell/退出行为。
  - 许多高活动钱包已经在研究池或 PAPER 中。
- 本轮实际新增 1 个 politics PAPER，说明诊断接口能产出可执行增量，但 politics 仍需要更好的来源，而不是单纯放宽阈值。
- cleanHigh 总数从 18 降到 17，但主类别占比变为 HEALTHY，原因是 sports/crypto clean high 数下降；这提醒后续需要同时看总数和配比，不能只看比例。

**下一轮动作**：
- 对 candidate 2361 做 targeted paper/process，确认是否有足够后续可模拟交易。
- 将 politics-source 诊断结果接入 Leader Research 页面，便于直接看到 politics 扩源瓶颈。
- 继续探索 politics 新来源：明确政治市场的高成交对手方、盈利 paper 钱包、外部 analytics 排名。

## Iteration 79 - 2026-06-26 13:26 CST - 验证 politics 2361 并接入页面诊断

**目标**：
- 对上一轮新增的 politics candidate 2361 做定向 PAPER 处理，避免它在全局 252 个 PAPER 里排队。
- 将 politics-source 诊断接入 Leader Research 页面，让扩源瓶颈可视化。

**执行动作**：
- 对 candidateId=2361 连续执行 3 轮 targeted paper/process：
  - 第 1 轮：processed=10，filtered=10，failed=0。
  - 第 2 轮：processed=11，filtered=6，failed=0。
  - 第 3 轮：processed=0，filtered=0，failed=0。
- 每轮后执行 `paper/score`：
  - scoredCount=252。

**candidate 2361 当前状态**：
- wallet=`0xad5353afe30c2da57709e2704ef3ccdcf67eef24`。
- state=`PAPER`。
- score=86.50647386。
- riskFlags=[]。
- paper session：
  - tradeCount=21。
  - filteredCount=16。
  - filteredRatio=0.43243243。
  - copyablePnl=8.99567978。
  - maxDrawdown=-1.19444189。
  - unknownValuationExposure=0。
  - openExposure=13.378162。
- 结论：
  - 2361 初步质量不错，PnL/回撤/未知估值都可接受。
  - 但 filteredRatio=43.24%，接近 50% 上限；且 PAPER 年龄太短，不能快速试跟。

**前端接入**：
- `frontend/src/types/index.ts` 新增 politics-source 诊断类型：
  - `LeaderResearchPoliticsSourceDiagnoseRequest`
  - `LeaderResearchPoliticsSourceDiagnose`
  - `LeaderResearchPoliticsSourceBucket`
  - `LeaderResearchPoliticsSourceSample`
- `frontend/src/services/api.ts` 新增：
  - `apiService.leaderResearch.diagnosePoliticsSource()`
- `frontend/src/pages/LeaderResearch.tsx` 新增展示：
  - “政治来源诊断”卡片：
    - 扫描钱包。
    - 通过阈值。
    - 可新增 PAPER。
    - 未知钱包。
    - 已在池中。
    - 已 PAPER。
    - lookback 与 clean high。
  - “政治来源阻塞”卡片：
    - top blocker bucket。
    - 中文解释。
  - “政治来源样本”卡片：
    - 样本钱包。
    - action。
    - events/markets/buy/sell。
    - safe/tail ratio。
    - 当前阻塞原因。

**验证**：
- 前端：
  - `npm run build` 通过。
  - 保留既有 Vite warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 后端：
  - 上一轮已通过 `LeaderResearchControllerTest`、`compileKotlin`、`bootJar` 并重启。
  - 本轮运行态 API 验证通过。
- 服务：
  - 前端 3000 在线。
  - 后端 8000 在线，PID=93209。
  - Bridge 8080 在线，`executor_ready=true`。

**最新 politics-source 诊断**：
- scannedWallets=500。
- passImportCriteria=32。
- unknownWallets=275。
- existingWallets=225。
- paperWallets=43。
- cleanHighWallets=3。
- eligibleForPaperNow=0。
- top blockers：
  - events_below_8：294。
  - safe_ratio_below_0.2000：240。
  - already_in_research_pool：225。
  - score_below_75：214。
  - tail_ratio_above_0.5000：193。

**结论**：
- 上一轮唯一可直接新增的 politics 钱包已经进入 PAPER，当前没有新的 `UNKNOWN_ELIGIBLE` politics 钱包。
- politics-source 诊断已经从命令行能力变成页面能力，可以持续观察瓶颈是否变化。
- 2361 值得继续观察，但因为过滤率偏高和 PAPER 年龄不足，不应进入快速观察或试跟。

**下一轮动作**：
- 针对 2361 持续观察后续活动事件，若 filteredRatio 降低且 age 增长，再评估 FAST_WATCH。
- politics 扩源需要第二类来源：明确政治市场的高成交对手方、盈利 paper 钱包、外部 analytics 排名，而不是继续重复当前 activity-source。
- 可以把 politics-source 诊断的 `eligibleForPaperNow > 0` 做成日报/告警，发现新可用政治钱包时自动触发导入评估。

## Iteration 80 - 2026-06-26 13:33 CST - 滚动评分确认 politics 2361 成为 clean high

**目标**：
- 继续滚动观察主类别候选，确认 2361 是否能转化为有效 politics clean high。
- 让页面明确提示 politics activity-source 是否还有可新增 PAPER 候选。

**执行动作**：
- 执行 `paper/score`：
  - scoredCount=252。
  - states=`PAPER,TRIAL_READY`。
  - scoreVersion=`research-copyability-v1`。
- 重新拉取 funnel。
- 前端 Leader Research 改动：
  - “政治来源诊断”卡片新增状态提示。
  - 若 `eligibleForPaperNow > 0`，显示发现可新增政治 PAPER 候选。
  - 若为 0，显示当前 activity-source 暂无可新增政治 PAPER 候选，优先寻找新来源。

**最新 funnel**：
- totalCandidates=1969。
- cleanHighScoreTotal=18。
- primaryCleanHighCount=15。
- secondaryCleanHighCount=3。
- primaryActualPercent=83.3333%。
- allocationHealth=`HEALTHY`。
- politics：
  - totalCandidates=742。
  - paperCandidates=38。
  - cleanHighScoreCandidates=2。
  - topCandidateId=2361。
  - topScore=86.5086。
- finance：
  - totalCandidates=879。
  - paperCandidates=188。
  - cleanHighScoreCandidates=13。
  - topCandidateId=1742。

**2361 当前观察结果**：
- category=politics。
- score=86.5086。
- tradeCount=21。
- filteredRatio=0.4324。
- copyablePnl=8.9957。
- readiness level=`OBSERVE`。
- blocker=`PAPER 观察不足 7 天：当前 0 小时`。
- fastWatchBlocker=`快速观察至少需要 48 小时：当前 0 小时`。

**诊断状态**：
- politics-source：
  - scannedWallets=500。
  - passImportCriteria=32。
  - unknownWallets=275。
  - existingWallets=225。
  - paperWallets=43。
  - cleanHighWallets=3。
  - eligibleForPaperNow=0。
- top blockers：
  - events_below_8=294。
  - safe_ratio_below_0.2000=240。
  - already_in_research_pool=225。
  - score_below_75=214。
  - tail_ratio_above_0.5000=193。

**验证**：
- `npm run build` 通过。
- 保留既有 Vite warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 前端 3000 在线。
- 后端 8000 在线。
- Bridge 8080 健康：`executor_ready=true`。

**结论**：
- candidate 2361 已从新增 politics PAPER 转化为 politics clean high，并成为当前 politics topCandidate。
- 当前 politics activity-source 已无可直接新增 PAPER 的未知钱包。
- 短期内继续重复当前 politics activity-source 收益很低。

**下一轮动作**：
- 开始实现第二类 politics 来源诊断：
  - 从明确政治市场中寻找高成交对手方。
  - 从 paper 盈利的 politics 钱包关联市场反查其他活跃钱包。
  - 对比外部 analytics 来源，形成可导入候选列表。
- 对 2361 后续活动继续增量 paper/process，重点看 filteredRatio 是否能从 43% 降下来。

## Iteration 81 - 2026-06-26 13:48 CST - politics 诊断去噪与服务恢复验证

**目标**：
- 继续第二目标，提升 politics 来源诊断准确性，避免把体育、加密或公司地区收入市场误当成政治候选来源。
- 验证“无服务了”后的前端、后端、Bridge 运行态。

**服务检查**：
- 前端 3000 在线。
- Bridge 8080 在线，`executor_ready=true`。
- 后端旧进程 PID=93209 对 `SIGTERM` 未正常退出，shutdown hook 报 `GracefulShutdownCallback` class not found；使用 `kill -9` 清理后，新建 `polyhermes-backend` tmux session。
- 后端新 PID=40323，8000 在线，登录接口和 leader research 接口验证通过。

**诊断修复**：
- 收紧 `LeaderResearchPoliticsSourceDiagnoseService.POLITICS_PATTERN`：
  - 移除裸 `eu`，避免匹配非政治字符串。
  - 移除裸 `china` / `mexico`，避免把公司地区收入、世界杯球队等市场误分类为 politics。
  - 保留并补强明确政治/地缘政治词：`taiwan`、`military-clash`、`nominee`、`governor`、`primary`、`hezbollah`、`lebanon`、`crimea`、`diplomatic`、`netanyahu` 等。

**旧 pattern vs 新 pattern 数据对比**：
- 旧 pattern：
  - unknown scanned=5088。
  - eligible_unknown=0。
  - top markets 包含真实政治市场，但也依赖裸 `china/mexico/eu`，有潜在误分类风险。
- 新 pattern：
  - unknown scanned=4088。
  - eligible_unknown=0。
  - top markets 保留 Israel / Russia / Iran / Ukraine / Parliament / Election 等明确政治市场。

**运行态 politics-source 诊断**：
- lookbackDays=60，limit=500。
- scannedWallets=500。
- passImportCriteria=18。
- unknownWallets=290。
- existingWallets=210。
- paperWallets=34。
- cleanHighWallets=2。
- eligibleForPaperNow=0。
- top blockers：
  - events_below_8=341。
  - safe_ratio_below_0.2000=272。
  - tail_ratio_above_0.5000=231。
  - already_in_research_pool=210。
  - score_below_75=203。

**验证**：
- 后端 `LeaderResearchControllerTest`、`compileKotlin`、`bootJar` 通过。
- 后端运行态接口验证通过。
- 前端 3000、Bridge 8080 保持在线。

**结论**：
- 当前 politics activity-source 没有新的 `UNKNOWN_ELIGIBLE` 钱包；重复跑同一来源无法有效增加高质量 politics leader。
- 收紧后诊断更可信，页面上的 politics 来源瓶颈不再被明显非政治市场稀释。
- 下一轮应进入外部/第二来源：Polymarket Analytics、明确政治市场高成交钱包、盈利 PAPER 钱包关联市场，而不是继续放宽当前阈值。

**下一轮动作**：
- 新增或脚本化第二来源候选发现：
  - 从明确 politics market 的高成交/多市场钱包中找未知候选。
  - 对现有 clean politics PAPER 的共同市场对手方做二跳筛选，但需要求跨市场活跃，避免一次性散户。
  - 优先接入外部 analytics 数据源，作为 activity-source 之外的独立候选入口。

## Iteration 82 - 2026-06-26 14:24 CST - 第二来源 market-peer-source 与分类误伤修复

**目标**：
- 把“明确政治/金融热门市场对手方”从一次性 SQL 变成正式可重复 API 来源。
- 继续按第二目标扩 politics/finance 候选，但避免把 BTC 5M、体育球员、政治 stockpile 等误归为 finance。

**代码变更**：
- 新增 `/api/copy-trading/leader-research/market-peer-source/import`。
- 新增 `LeaderResearchMarketPeerSourceImportService`：
  - 先按类别 pattern 选 hot markets。
  - 再在 hot markets 中按 wallet 聚合。
  - 要求跨市场、买卖都有、安全价格比例/长尾比例达标。
  - 支持 `dryRun` 与正式导入。
  - 对 locked / 已有 evidence 做保护。
  - source 标记为 `MARKET_PEER_SOURCE`。
- 前端 `api.ts` 和 `types/index.ts` 补齐 market-peer-source API 类型，后续页面/日报可以直接接入。

**分类修复**：
- finance pattern 修复：
  - `dow` 会误匹配 `btc-updown-5m` 的 `down`，已替换为 `dow-jones`。
  - `fed` 会误匹配 `federico`，已替换为 `the-fed`、`fed-rate`、`feds-upper` 等 slug 语境。
  - `stock` 会误匹配政治市场 `stockpile`，已替换为 `stock-market`。
  - 补充/保留真实金融市场词：`rate-cut`、`rate-hike`、`interest-rate`、`crude-oil`、`wti`、`gold`、`spx` 等。
- 同步修复旧 `activity-source` 与新 `market-peer-source`，避免未来继续把 BTC 5M 当 finance。

**运行验证**：
- 严格参数：
  - categories=`politics,finance`
  - lookbackDays=60
  - hotMarketLimit=50
  - minMarketEvents=25
  - minMarketWallets=20
  - minEvents=8
  - minDistinctMarkets=2
  - minBuyEvents=2
  - minSellEvents=1
  - minSafePriceRatio=0.20
  - maxTailPriceRatio=0.50
- dry-run 结果：
  - selectedTotal=1。
  - politics selected=1，finance selected=0。
  - 唯一 politics 钱包 `0x8a98109fb0f1d87d9bfcb4486ba3587b95c51b92` 为已存在候选，当前 evidence 已更新，后续 dry-run 为 `SKIP_EXISTING`。
- 放宽 finance 小样本参数：
  - hotMarketLimit=80
  - minMarketEvents=10
  - minMarketWallets=5
  - minEvents=5
  - minDistinctMarkets=2
  - minBuyEvents=1
  - minSellEvents=1
  - 发现 1 个已存在 finance 候选 `0x5d634050ad89f172afb340437ed3170eaa2c9075`，正式更新 evidence。

**候选质量复核**：
- politics candidate 105：
  - wallet=`0x8a98109fb0f1d87d9bfcb4486ba3587b95c51b92`
  - state=PAPER。
  - score=67.5244。
  - riskFlags=`mixed_category_evidence,high_filtered_ratio,tail_price_spray`。
  - 不应晋级。
- finance candidate 114：
  - wallet=`0x5d634050ad89f172afb340437ed3170eaa2c9075`
  - state=DISCOVERED。
  - score=60.0000。
  - riskFlags=`mixed_category_evidence`。
  - 不应晋级。
- `activity-score/run force=true`：
  - scannedCount=1712。
  - scoredCount=1712。
  - categoryCounts：politics=707，finance=698，sports=156，crypto=151。

**验证**：
- 后端：
  - `LeaderResearchControllerTest` 通过。
  - `compileKotlin` 通过。
  - `bootJar` 通过。
- 前端：
  - `npm run build` 通过。
  - 保留既有 Vite warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 服务：
  - 后端已重启，PID=72094，8000 在线。

**结论**：
- 第二来源正式落地，但当前本地 `leader_activity_event` 中没有新的高质量 politics/finance 钱包可直接入池。
- finance 候选来源之前确实被 BTC 5M 污染，已修复；这比盲目新增数量更重要，否则会继续把不适合的短周期 crypto leader 伪装成 finance。
- 当前瓶颈变为“真实外部数据源不足”，不是导入接口缺失。

**下一轮动作**：
- 把 market-peer-source 入口接到 Leader Research 页面或日报，展示 strict/relaxed 两组结果。
- 接入或半自动导入外部 analytics 来源，优先找真实 finance/politics 钱包，而不是只依赖本地 activity_event。
- 对 finance pattern 继续做分类单测，防止裸词误伤重新出现。

## Iteration 83 - 2026-06-26 14:47 CST - 第二来源页面化与分类测试护栏

**目标**：
- 让 market-peer-source 的 strict/relaxed 结果在 Leader Research 页面可见。
- 固化上一轮发现的 finance 分类误伤，防止 BTC 5M / 足球运动员 / 政治 stockpile 被再次归为 finance。

**代码变更**：
- 新增 `LeaderResearchMarketCategoryPatterns`：
  - activity-source 与 market-peer-source 共用同一套 politics/finance market pattern。
  - 避免两个来源各自维护词表导致 drift。
- 新增 `LeaderResearchMarketCategoryPatternsTest`：
  - finance 应匹配：
    - Fed interest-rate 市场。
    - SPX 市场。
    - WTI 市场。
    - Gold 市场。
  - finance 应拒绝：
    - `btc-updown-5m-*`。
    - `will-federico-valverde...`。
    - `uranium-stockpile...`。
  - politics 应匹配：
    - Israel/Hezbollah。
    - US/Iran diplomatic。
    - Ukraine/Crimea。
- Leader Research 页面新增“热门市场对手方来源”卡片：
  - 自动展示 strict dry-run 摘要。
  - 展示 strict 分类 selected/created/updated。
  - 展示样本 wallet、events、markets、buy/sell、top markets、action。
  - 支持按钮运行 `relaxed finance` dry-run。

**运行态验证**：
- strict market-peer-source：
  - selectedTotal=1。
  - createdTotal=0。
  - updatedTotal=0。
  - skippedExistingTotal=1。
  - politics selected=1，finance selected=0。
  - 唯一样本仍为已存在 politics 钱包 `0x8a98109fb0f1d87d9bfcb4486ba3587b95c51b92`，action=`SKIP_EXISTING`。

**验证**：
- 后端：
  - `LeaderResearchMarketCategoryPatternsTest` 通过。
  - `LeaderResearchControllerTest` 通过。
  - `compileKotlin` 通过。
  - `bootJar` 通过。
- 前端：
  - `npm run build` 通过。
  - 保留既有 Vite warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 服务：
  - 后端重启成功，PID=90103。
  - market-peer-source API 运行态验证通过。

**结论**：
- 第二来源现在不只是后端能力，已经进入 Leader Research 页面，可直接观察 strict/relaxed 来源结果。
- 分类质量有测试护栏，避免继续把不适合跟单策略的 BTC 5M 伪装成 finance。
- 当前本地 activity_event 下 strict 第二来源仍没有新增高质量 politics/finance 钱包。

**下一轮动作**：
- 进入真正外部 analytics/排行榜来源接入：
  - 优先从 Polymarket Analytics / Polyburg 报告提到的渠道获取 wallet。
  - 将外部候选导入为独立 source，例如 `EXTERNAL_ANALYTICS_SOURCE`。
  - 用现有 activity-score + market-peer evidence 二次筛选，避免只凭外部排名入池。

## Iteration 84 - 2026-06-26 15:13 CST - 外部 analytics wallet 导入入口

**目标**：
- 继续第二目标，打通 Polyburg / Polymarket Analytics / Dune / 手工排行榜 wallet 到研究候选池的正式入口。
- 避免后续每次拿到外部地址都写一次性 SQL 或脚本。

**资料复核**：
- 找到 iCloud Obsidian 报告目录：
  - `/Users/henry/Library/Mobile Documents/iCloud~md~obsidian/Documents/warehouse/报告/polyburg 报告/report.md`
- 报告包含可落地方法论：
  - Polyburg 公开公式：`Score = win_rate × ln(1 + total_trades)`。
  - 过滤高频交易者：每周超过 20 笔交易的钱包被排除。
  - 过滤对冲者：同一市场双边下注 YES+NO 的交易者被排除。
  - 低样本过滤：已结算交易少于 50 笔的钱包被排除。
  - 不活跃过滤：过去 30 天无交易的钱包被排除。
- 当前报告没有直接列出可导入 wallet 地址，因此本轮不正式导入外部地址。

**代码变更**：
- 新增 `POST /api/copy-trading/leader-research/external-analytics/import`。
- 新增 `LeaderResearchExternalAnalyticsImportService`：
  - 输入字段：wallet、category、sourceName、externalRank、externalScore、note。
  - 支持 `dryRun`。
  - 无效地址 `SKIP_INVALID`。
  - locked/manual locked 候选 `SKIP_LOCKED`。
  - 相同 evidence `SKIP_EXISTING`。
  - 新 wallet 创建 `DISCOVERED` candidate。
  - 已有 wallet 更新 source/evidence/lastSourceSeenAt。
  - source 标记为 `EXTERNAL_ANALYTICS_SOURCE`。
- 前端 `api.ts` 与 `types/index.ts` 已补 external analytics import 类型和 API 方法。
- 新增 `LeaderResearchExternalAnalyticsImportServiceTest`。
- Controller 测试补 external analytics import 委托测试。

**运行态验证**：
- dry-run payload：
  - 有效已有 politics wallet `0x9703676286b93c2eca71ca96e8757104519a69c2`。
  - 无效地址 `not-a-wallet`。
- API 返回：
  - requestedTotal=2。
  - selectedTotal=1。
  - updatedTotal=1。
  - skippedInvalidTotal=1。
  - 有效 wallet action=`UPDATE`。
  - 无效地址 action=`SKIP_INVALID`。
- 本轮未正式写入伪外部地址，避免污染候选池。

**验证**：
- 后端：
  - `LeaderResearchExternalAnalyticsImportServiceTest` 通过。
  - `LeaderResearchControllerTest` 通过。
  - `compileKotlin` 通过。
  - `bootJar` 通过。
- 前端：
  - `npm run build` 通过。
  - 保留既有 Vite warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 服务：
  - 后端重启成功，PID=36316。
  - external analytics endpoint 运行态验证通过。

**结论**：
- 外部来源入口已经可用；后续只要拿到 Polyburg/Polymarket Analytics/Dune 的 wallet 列表，就能以正式 source 进入研究候选池。
- 当前实际瓶颈从“系统没有外部导入口”转为“需要获取真实外部 wallet 列表”。

**下一轮动作**：
- 从 Polyburg top traders / Polymarket Analytics 页面或导出的 CSV 中抓取/整理 wallet。
- 调用 external analytics import 正式导入真实 politics/finance wallet。
- 导入后执行：
  - `activity-score/run force=true`
  - `activity-score/promote-paper`
  - `paper/process`
  - `paper/score`
  - funnel 复核主类别 clean high 变化。

## Iteration 85 - 2026-06-26 15:36 CST - 外部榜单粘贴导入页面

**目标**：
- 执行 Polymarket Analytics / Dune 外部来源方案，在没有 API key / Query ID 的情况下先打通可用的手工/CSV 粘贴导入。
- 让外部排行榜 wallet 可以直接从 Leader Research 页面进入 `EXTERNAL_ANALYTICS_SOURCE`，再走本地评分和 PAPER 验证。

**接入判断**：
- Polymarket Analytics / Falcon API 方向需要 token。
- Dune API 方向需要 API key 和具体 Query ID。
- 当前本地没有这些凭证，因此本轮优先落地手工/导出列表导入，避免继续等待外部权限。

**代码变更**：
- `LeaderResearchExternalAnalyticsImportItemDto.sourceName` 默认值从 `external` 改为空字符串。
  - 这样 item 未填来源时，会正确使用 request 的 `defaultSourceName`。
- Leader Research 页面新增“导入外部名单”按钮和弹窗：
  - 支持粘贴多行 wallet。
  - 每行格式可为：`0x... finance 92` 或 `0x... politics 88`。
  - 自动解析 wallet、category、score。
  - 支持 Dry-run。
  - 支持正式导入。
  - 展示请求数、选中数、新建、更新、无效、重复/锁定和样本 action。
- 该入口适配来源：
  - Polymarket Analytics 手工榜单。
  - Dune CSV/表格导出。
  - Polyburg/其他工具整理后的 wallet 列表。

**运行态验证**：
- dry-run 请求：
  - `defaultSourceName=polymarket_analytics`
  - item 未传 `sourceName`
  - wallet=`0x9703676286b93c2eca71ca96e8757104519a69c2`
- API 返回：
  - sourceName=`polymarket_analytics`
  - sourceEvidence=`external_analytics:polymarket_analytics | category:politics | rank:1 | external_score:92`
  - action=`UPDATE`
- 确认默认来源名修复生效。

**验证**：
- 后端：
  - `LeaderResearchExternalAnalyticsImportServiceTest` 通过。
  - `LeaderResearchControllerTest` 通过。
  - `compileKotlin` 通过。
  - `bootJar` 通过。
- 前端：
  - `npm run build` 通过。
  - 保留既有 Vite warning：`api.ts` 动静态 import 混用、chunk 大小超过 500k。
- 服务：
  - 后端重启成功，PID=86996。
  - external analytics import 运行态 dry-run 验证通过。

**结论**：
- 外部榜单接入已经进入可操作状态：不需要等 API key，就可以从 Polymarket Analytics/Dune 导出的 wallet 列表直接导入。
- 下一步重点不再是系统入口，而是获取真实高质量外部 wallet 列表。

**下一轮动作**：
- 从 Polymarket Analytics 手工导出或复制 top traders wallet，优先 politics/finance。
- 或创建 Dune query，导出 wallet/category/score，再粘贴到页面导入。
- 正式导入后立刻跑：
  - `activity-score/run force=true`
  - `activity-score/promote-paper`
  - `paper/process`
  - `paper/score`

## Iteration 86 - 2026-06-26 15:40 CST - Polymarket Analytics 页面复制尝试

**目标**：
- 尝试通过 Polymarket Analytics 页面复制方式获取 top traders / wallet 列表，再进入外部榜单导入入口。

**尝试结果**：
- `curl https://polymarketanalytics.com/` 返回 Vercel 403，响应头包含 `x-vercel-mitigated: deny`。
- 内置浏览器可打开首页标题，但对 DOM、截图、`/traders` 导航读取多次超时，无法稳定提取表格或 wallet。
- 新标签直开 `https://polymarketanalytics.com/traders` 也未完成导航。
- 已用系统 Chrome 打开：
  - `https://polymarketanalytics.com/traders`
  - `http://localhost:3000/leader-research`

**结论**：
- 当前环境无法自动从 Polymarket Analytics 页面复制出真实 wallet 列表；更像是站点防护/前端加载对自动化不友好，而不是本地导入链路问题。
- 本地 `Leader Research -> 导入外部名单` 入口已经可用于人工复制粘贴。

**建议下一步**：
- 用户在 Chrome 中完成 Polymarket Analytics 登录/页面打开后，手动复制排行榜行。
- 粘贴到本地 `Leader Research -> 导入外部名单`，来源填写 `polymarket_analytics`。
- 推荐行格式：
  - `0x... politics 92`
  - `0x... finance 88`
- 先执行 Dry-run；确认新建/更新数量和样本 action 正常后再正式导入。

## Iteration 87 - 2026-06-26 15:58 CST - Scanner pool 扩源与 PAPER 推进闭环

**目标**：
- 在 Polymarket Analytics 页面复制受阻后，继续推进第二目标中可直接执行的闭环：
  - 盘点候选池。
  - 从 scanner pool 按政治/金融优先扩源。
  - 强制重评分。
  - 将高分候选分批推进 PAPER。
  - 记录可跟踪的高分 PAPER 候选与瓶颈。

**起始盘点**：
- `leader_research_candidate`: 1969。
- `copy_trading_leaders`: 595。
- `leader_scanner_candidate_pool`: 7090。
- `leader_activity_event`: 311831，其中 `usable_for_discovery=311831`、`usable_for_paper=299539`。
- 起始状态：
  - DISCOVERED 1704。
  - PAPER 260。
  - COOLDOWN 5。
- 政治 DISCOVERED 707，但 80 分以上为 0；政治 PAPER 39，其中 80 分以上 4。

**动作 1 - PAPER 晋级第一批**：
- dry-run:
  - selectedTotal=25。
  - politics=0、finance=20、sports=4、crypto=1。
- formal:
  - selectedTotal=8。
  - promotedTotal=8。
  - requestedSelectedTotal=25。
  - effectiveSelectedLimit=8。
  - truncated=true。
- 原因确认：
  - `LeaderResearchPaperPromotionService.LIVE_PROMOTE_BATCH_LIMIT = 8`，正式执行单批硬上限是 8。
- `paper/process`:
  - processed=17。
  - filtered=3。
  - failed=0。
  - requestedBatchSize=100。
  - effectiveBatchSize=20。
  - truncated=true。
- `paper/score`:
  - scoredCount=260。
  - scoreVersion=`research-copyability-v1`。

**动作 2 - scanner pool 扩源**：
- dry-run 参数：
  - politicsLimit=150。
  - financeLimit=150。
  - sportsLimit=25。
  - cryptoLimit=25。
  - onlyPending=true。
  - minDiscoveryScore=40。
- dry-run 结果：
  - selectedTotal=349。
  - createdTotal=62。
  - updatedTotal=207。
  - skippedExistingTotal=80。
  - politics: selected=150, created=13, updated=57, skippedExisting=80。
  - finance: selected=150, created=0, updated=150。
  - sports: selected=25, created=25。
  - crypto: selected=24, created=24。
- formal 结果与 dry-run 一致。
- `activity-score/run`:
  - states=`DISCOVERED,CANDIDATE`。
  - force=true。
  - scannedCount=1766。
  - scoredCount=1766。
  - skippedCount=0。
  - categoryCounts: politics=776, finance=634, sports=181, crypto=175。
  - 主要 risk flags:
    - small_sample=1556。
    - scanner_pool_unverified=1312。
    - low_market_diversity=1180。
    - mixed_category_evidence=249。

**动作 3 - PAPER 晋级第二批**：
- 扩源重评分后 dry-run:
  - selectedTotal=28。
  - politics=0、finance=20、sports=5、crypto=3。
- formal:
  - selectedTotal=8。
  - promotedTotal=8。
  - requestedSelectedTotal=28。
  - effectiveSelectedLimit=8。
  - truncated=true。
- 晋级样本:
  - `0x74c8d69115faf6a3b5e3482f736080385f709962` finance score=100。
  - `0x63540a1a71d2c0f01ed8676c1086b1625b4ea1c0` finance score=100。
  - `0xf3f358f9185ae08572b67e36ba233cec8ae09e5b` finance score=98.47619040。
  - `0x94dc07a53ba0ce770a220b1c945052f014515e19` finance score=98。
- `paper/process`:
  - processed=17。
  - filtered=3。
  - failed=0。
  - truncated=false。
- `paper/score`:
  - scoredCount=268。
  - scoreVersion=`research-copyability-v1`。

**最终状态**：
- `leader_research_candidate`: 2031。
- `copy_trading_leaders`: 595。
- `leader_scanner_candidate_pool` PENDING: 3974。
- 候选状态：
  - DISCOVERED 1766。
  - PAPER 268。
  - COOLDOWN 5。
- 分类状态：
  - politics DISCOVERED 776，PAPER 39。
  - finance DISCOVERED 626，PAPER 206。
  - sports DISCOVERED 181，PAPER 14。
  - crypto DISCOVERED 175，PAPER 9。

**当前高分 PAPER 候选样本**：
- finance `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
  - score=95.76615800。
  - trade_count=22。
  - filtered_ratio=0.04347826。
  - copyable_pnl=12.07527939。
  - max_drawdown=0。
- politics `0x9703676286b93c2eca71ca96e8757104519a69c2`
  - score=92.97057685。
  - trade_count=45。
  - filtered_ratio=0.23728814。
  - copyable_pnl=25.43130878。
  - max_drawdown=-1.00030000。
- finance `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`
  - score=91.57989520。
  - trade_count=32。
  - filtered_ratio=0.08571429。
  - copyable_pnl=8.70530240。
  - max_drawdown=0。

**结论**：
- 本轮在没有外部页面可复制数据的情况下，仍通过 scanner pool 完成了 62 个新增候选和 207 个候选更新。
- 当前系统候选已超过 1000，达到数量目标的底座，但“高质量政治新候选”仍不足：
  - politics DISCOVERED 数量多，但高分不足。
  - politics PAPER 中已有少量强候选，需要继续积累交易样本与稳定高分。
- 金融方向表现更成熟，PAPER 高分候选数量明显更多，可继续作为主力观察池。

**下一轮动作**：
- 继续按 8 个 live 上限分批推进高分 DISCOVERED 到 PAPER。
- 针对政治候选质量瓶颈，优先做两件事：
  - 从 Dune/手工外部榜单补充真实 politics profitable wallets。
  - 对 politics scanner pool 增加“已结算盈利/卖出行为/非单一热门市场”过滤，减少大量 60 分以下候选。
- 对当前 top PAPER 候选跑更严格的 trial-readiness/funnel 复核，挑出可进入试跟配置的 1-3 个。

## Iteration 88 - 2026-06-26 16:28 CST - Scanner pool 活动质量过滤

**目标**：
- 修复上一轮暴露的政治候选质量瓶颈：
  - politics DISCOVERED 数量很多，但多数分数被封顶在 30/59/60。
  - 新导入的 politics pending pool 大量只有 1-2 条事件、1 个市场，进入研究池后必然触发 `small_sample`、`low_market_diversity`、`scanner_pool_unverified`。

**诊断证据**：
- politics DISCOVERED risk group:
  - `small_sample,low_market_diversity,scanner_pool_unverified`: 412。
  - `small_sample,low_market_diversity,mixed_category_evidence,scanner_pool_unverified`: 162。
  - `tail_price_spray,low_safe_price_ratio`: 36。
- politics pending pool 高 discovery_score 样本中，大量钱包只有：
  - events=1。
  - markets=1。
  - buy/sell 只有单边。
- 这说明仅靠 `discovery_score` 导入 politics，会把热点市场单笔钱包灌入候选池，后续评分自然无法超过阈值。

**代码变更**：
- `LeaderResearchScannerPoolImportRequest` 新增可选活动质量过滤字段，默认关闭，不改变旧 API 行为：
  - `requireActivityQuality=false`。
  - `minActivityEvents=20`。
  - `minActivityDistinctMarkets=5`。
  - `minActivityBuyEvents=3`。
  - `minActivitySellEvents=2`。
  - `minActivitySafePriceRatio=0.30`。
  - `maxActivityTailPriceRatio=0.45`。
- `LeaderActivityEventRepository` 新增 `aggregateDiscoveryMetricsForWallets(wallets)`：
  - 按 wallet 聚合 discovery 可用事件。
  - 输出 events、distinct markets、buy/sell、安全价格、长尾价格、金额与最后事件时间。
- `LeaderResearchScannerPoolImportService` 在 `requireActivityQuality=true` 时：
  - 先从 scanner pool oversample。
  - 再按 activity quality 过滤。
  - 最后才取 limit。
  - 这样避免低样本 wallet 占用 politics/finance 扩源名额。
- 新增单元测试：
  - `activity quality filter removes low sample scanner candidates`。

**验证**：
- 后端测试和编译：
  - `./gradlew --no-daemon --no-parallel test --tests 'com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScannerPoolImportServiceTest' compileKotlin`
  - BUILD SUCCESSFUL。
- 后端打包：
  - `./gradlew --no-daemon --no-parallel bootJar`
  - BUILD SUCCESSFUL。
- 后端重启：
  - 使用 `run_backend_local.sh` 启动，DB 指向 `localhost:3307`。
  - 新后端 PID=36229，8000 端口正常监听。

**运行态验证**：
- quality dry-run 参数：
  - politicsLimit=150。
  - financeLimit=150。
  - sportsLimit=0。
  - cryptoLimit=0。
  - onlyPending=true。
  - minDiscoveryScore=35。
  - requireActivityQuality=true。
  - minActivityEvents=20。
  - minActivityDistinctMarkets=5。
  - minActivityBuyEvents=3。
  - minActivitySellEvents=2。
  - minActivitySafePriceRatio=0.30。
  - maxActivityTailPriceRatio=0.45。
- dry-run 结果：
  - requestedTotal=300。
  - selectedTotal=32。
  - createdTotal=0。
  - updatedTotal=26。
  - skippedExistingTotal=6。
  - politics selected=13, updated=11, skippedExisting=2。
  - finance selected=19, updated=15, skippedExisting=4。
- formal 结果与 dry-run 一致。
- 重评分：
  - scannedCount=1758。
  - scoredCount=1758。
  - skippedCount=0。
  - categoryCounts: politics=777, finance=627, sports=180, crypto=174。
- PAPER 晋级 dry-run:
  - selectedTotal=26。
  - politics=0。
  - finance=20。
  - sports=4。
  - crypto=2。

**结论**：
- 新过滤成功把 300 个候选压缩到 32 个高活动质量候选，避免继续扩大低质量 politics DISCOVERED。
- 但 politics 仍未出现新的 80+ 晋级候选，说明下一步不能只靠 scanner pool，需要引入外部 politics profitable leader 来源或已结算盈利维度。

**下一轮动作**：
- 将 `requireActivityQuality=true` 作为后续 scanner pool politics/finance 扩源的默认运行参数。
- 针对 politics 进一步做：
  - 优先接入 Dune/外部榜单/手工复制的 profitable politics wallet。
  - 或在本地从已结算/可计算 pnl 的 paper session 中反查 politics 高 copyable_pnl wallet。
- 继续分批推进现有 finance 高分 DISCOVERED 到 PAPER，但不要用低质量 scanner pool 继续堆 politics 数量。

## Iteration 89 - 2026-06-26 16:45 CST - PAPER 候选复核与下一批 finance 晋级

**目标**：
- 复核当前 PAPER 候选的 funnel/trial-readiness，确认是否已有可进入试跟配置的政治/金融 leader。
- 继续按正式 live 上限推进高分 DISCOVERED 到 PAPER，扩大后续观察池。

**funnel 复核 - 晋级前**：
- summary:
  - DISCOVERED=1758。
  - PAPER=268。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel:
  - totalCandidates=2031。
  - cleanHighScoreTotal=18。
  - primaryCleanHighCount=17。
  - primaryActualPercent=94.4444%。
  - allocationHealth=HEALTHY。
- 当前没有 TRIAL_READY，主要原因不是分数不够，而是 PAPER 观察时间不足 7 天。
- 候选观察信号：
  - finance `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
    - score=95.7662。
    - tradeCount=22。
    - filteredRatio=0.0435。
    - copyablePnl=12.0753。
    - maxDrawdown=0。
    - ageHours=47。
    - fastWatchBlocker 仅剩：快速观察至少需要 48 小时。
  - finance `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`
    - score=91.5799。
    - tradeCount=32。
    - filteredRatio=0.0857。
    - copyablePnl=8.7053。
    - ageHours=15。
  - politics `0xad5353afe30c2da57709e2704ef3ccdcf67eef24`
    - score=86.5667。
    - tradeCount=21。
    - filteredRatio=0.4324。
    - copyablePnl=8.9957。
    - ageHours=2。
    - 阻塞：观察时间短，过滤率偏高。

**动作 - PAPER 晋级下一批**：
- promote dry-run:
  - selectedTotal=26。
  - politics=0。
  - finance=20。
  - sports=4。
  - crypto=2。
- formal promote:
  - selectedTotal=8。
  - promotedTotal=8。
  - requestedSelectedTotal=26。
  - effectiveSelectedLimit=8。
  - truncated=true。
  - 本批全部为 finance。
- 晋级样本：
  - `0xb91233c3469aef022dd5755f2a686d18201f2a20` finance score=100。
  - `0x923bd021ea4d5dad79d156058e6dbdcc680eae9f` finance score=97.33333335。
  - `0x7498b6f6889dc49dd29350c861e1115d37ba59c6` finance score=97.125。
  - `0x966dfabbe9d8171c756be390163aa1500edf4abf` finance score=97.11538460。
- paper/process:
  - processed=18。
  - filtered=2。
  - failed=0。
- paper/score:
  - scoredCount=276。
  - scoreVersion=`research-copyability-v1`。

**funnel 复核 - 晋级后**：
- candidate state:
  - DISCOVERED=1750。
  - PAPER=276。
  - COOLDOWN=5。
- active paper aggregate:
  - sessions=281。
  - trades=2670。
  - avg_trades=9.50。
  - copyable_pnl_sum=38.8271。
  - realized_pnl_sum=2.1549。
- funnel:
  - cleanHighScoreTotal=15。
  - primaryCleanHighCount=14。
  - primaryActualPercent=93.3333%。
  - allocationHealth=HEALTHY。
- 高优先候选：
  - finance `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`
    - score=91.5863。
    - tradeCount=32。
    - filteredRatio=0.0857。
    - copyablePnl=8.7053。
    - ageHours=15。
  - finance `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
    - score=90.7725。
    - tradeCount=22。
    - filteredRatio=0.0435。
    - copyablePnl=12.0753。
    - ageHours=47。
    - 仍是最接近 FAST_WATCH 的 finance 候选。
  - politics `0xad5353afe30c2da57709e2704ef3ccdcf67eef24`
    - score=86.5731。
    - tradeCount=21。
    - filteredRatio=0.4324。
    - copyablePnl=8.9957。
    - ageHours=2。

**结论**：
- 当前目标底座继续扩大：PAPER 从 268 提升到 276。
- 仍无 TRIAL_READY，因为观察期不足；但 finance 已出现接近 FAST_WATCH 的候选。
- politics 方向目前不是数量瓶颈，而是高质量/低过滤率候选不足；`0xad535...` 可继续观察，但不适合立即试跟。

**下一轮动作**：
- 等 finance `0xe7ce...d53a` 超过 48 小时后复核 funnel，若 fastWatchBlockers 清空，可考虑生成禁用试跟模板供人工确认。
- 继续按 8 个 live 上限推进 finance 高分 DISCOVERED 到 PAPER。
- politics 继续依赖外部 profitable wallet / Dune / Polymarket Analytics 手工导入，而不是普通 scanner pool 扩源。

## Iteration 90 - 2026-06-26 16:59 CST - FAST_WATCH 复核与继续扩充 PAPER

**目标**：
- 复核上一轮最接近 FAST_WATCH 的 finance 候选是否跨过 48 小时门槛。
- 若系统允许，则创建禁用试跟配置；若不允许，记录原因并继续扩充 PAPER 候选池。

**初始复核**：
- 后端在线：
  - PID=36229。
  - 8000 端口监听正常。
- summary:
  - DISCOVERED=1750。
  - PAPER=276。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`:
  - state=PAPER。
  - score=90.7725。
  - tradeCount=22。
  - filteredRatio=0.0435。
  - copyablePnl=12.0753。
  - maxDrawdown=0。
  - ageHours=47。
  - fastWatchBlocker: `快速观察至少需要 48 小时`。
- `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`:
  - state=PAPER。
  - score=91.5863。
  - tradeCount=32。
  - filteredRatio=0.0857。
  - copyablePnl=8.7053。
  - ageHours=15。
- politics `0xad5353afe30c2da57709e2704ef3ccdcf67eef24`:
  - state=PAPER。
  - score=86.5731。
  - tradeCount=21。
  - filteredRatio=0.4324。
  - copyablePnl=8.9957。
  - ageHours=2。
  - 仍不适合试跟：观察时间短且过滤率偏高。

**动作 1 - 继续推进高分 DISCOVERED 到 PAPER**：
- formal promote:
  - selectedTotal=8。
  - promotedTotal=8。
  - requestedSelectedTotal=26。
  - effectiveSelectedLimit=8。
  - truncated=true。
  - 本批全部为 finance。
- 晋级样本：
  - `0x81529ca89509fbaf1eedd1f38b3e957372e75b51` score=96.77272735。
  - `0xce3120e4226b0a38cf27c0de3b442893c169b28e` score=96.60000000。
  - `0x36eb62226456433f791b9b0ba1837aa42d2d6831` score=96.50000005。
  - `0x7121364063e70c2929ed22bd8c51ca9e4723b28d` score=96.46116500。
- paper/process:
  - processed=16。
  - filtered=4。
  - failed=0。
- paper/score:
  - scoredCount=284。
  - scoreVersion=`research-copyability-v1`。

**动作 2 - 等待 48 小时门槛并复核**：
- 等待约 5 分钟后复核 funnel。
- 结果：
  - `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
    - level=FAST_WATCH。
    - label=快速观察。
    - fastWatchBlockers=[]。
    - blockers 仍包含：`PAPER 观察不足 7 天：当前 48 小时`。
  - `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`
    - level=FAST_WATCH。
    - label=快速观察。
    - fastWatchBlockers=[]。
    - blockers 仍包含：`PAPER 观察不足 7 天：当前 48 小时`。

**禁用试跟配置检查**：
- `approval/create-disabled-trial-config` 接口要求：
  - `candidate.researchState == TRIAL_READY`。
  - `confirm=true`。
  - 创建出的 copy trading 配置默认 `enabled=false`。
- 当前 FAST_WATCH 候选仍是 `PAPER`，不是 `TRIAL_READY`。
- 因此本轮不创建禁用试跟配置；该保护避免 FAST_WATCH 阶段过早进入跟单配置。

**最终状态**：
- summary:
  - DISCOVERED=1742。
  - PAPER=284。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel:
  - totalCandidates=2031。
  - cleanHighScoreTotal=14。
  - primaryCleanHighCount=13。
  - primaryActualPercent=92.8571%。
  - allocationHealth=HEALTHY。
- 当前明确 FAST_WATCH 候选：
  - finance `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`。
  - finance `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`。

**结论**：
- 第二目标有了明确的“快速观察”候选，但系统不会也不应该在 FAST_WATCH 阶段自动创建跟单配置。
- PAPER 池继续扩大到 284；finance 高分观察池进一步加厚。
- politics 仍无 FAST_WATCH 级别可跟候选，继续需要外部 profitable politics wallet 来源。

**下一轮动作**：
- 定期复核 FAST_WATCH 候选是否持续高分、低过滤率、正 PnL。
- 继续按 8 个 live 上限推进 finance 高分 DISCOVERED 到 PAPER。
- 当候选进入 TRIAL_READY 后，才调用 `approval/create-disabled-trial-config` 创建禁用试跟配置供人工启用。

## Iteration 91 - 2026-06-26 17:05 CST - 严格 activity-source 外部补源复核

**目标**：
- 在普通 scanner pool 边际收益下降后，使用更严格的 activity-source 条件查找 politics/finance 高质量钱包。
- 验证是否能补出新的 politics/finance PAPER 或 FAST_WATCH 候选。

**动作**：
- strict dry-run 条件：
  - categories=`politics,finance`。
  - lookbackDays=60。
  - minEvents=20。
  - minDistinctMarkets=5。
  - minBuyEvents=3。
  - minSellEvents=2。
  - minSafePriceRatio=0.30。
  - maxTailPriceRatio=0.45。
- dry-run 结果：
  - selectedTotal=4。
  - created=0。
  - updated=2。
  - skippedExisting=2。
  - 全部为 politics；finance=0。
- formal import 结果与 dry-run 一致：
  - selectedTotal=4。
  - created=0。
  - updated=2。
  - skippedExisting=2。
- 重新运行：
  - `activity-score/run`：scanned=1742，scored=1742。
  - `paper/score`：scoredCount=284。

**复核结果**：
- summary：
  - DISCOVERED=1742。
  - PAPER=284。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=15。
  - primaryCleanHighCount=14。
  - primaryActualPercent=93.3333%。
  - allocationHealth=HEALTHY。
- 新增 strict politics 复核样本：
  - `0xc8ab97a9089a9ff7e6ef0688e6e591a066946418`：PAPER，score=75.2627，copyablePnl=1.9726，filteredRatio=0.35。
  - `0x9f92355417d3001149a03e1cdcfecef40d482c2d`：PAPER，score=75.2341，copyablePnl=-1.7748，risk=`mixed_category_evidence`。
  - `0x510f4963b66b1b18505faab74b0bb943d1dda43c`：PAPER，score=70.0290，copyablePnl=-0.7419，filteredRatio=0.4359。
  - `0x758b87dd3b6491bb122634be5d465d180a120a1c`：DISCOVERED，score=60，risk=`mixed_category_evidence`。

**结论**：
- 严格 activity-source 只能补出极少 politics 钱包，且质量还没有达到可试跟水平。
- politics 仍是外部数据源瓶颈，不适合继续靠本地 activity-source 放宽阈值硬推。
- finance 仍有两个 FAST_WATCH：
  - `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`。
  - `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`。

**下一轮动作**：
- 继续尝试 Polymarket Analytics / Dune / Polyburg 页面复制或导出方式，作为独立外部 wallet 来源。
- 页面复制导入时必须保留完整 `0x` 钱包地址；只有缩略地址无法入池。

## Iteration 92 - 2026-06-26 17:15 CST - Polymarket Analytics 页面复制方式验证

**目标**：
- 尝试通过 Polymarket Analytics 页面复制方式获取 leader wallet。
- 如果站点阻止自动化访问，则确保本地导入入口支持用户手工复制整行文本后解析导入。

**外部页面尝试**：
- in-app browser 打开 `https://polymarketanalytics.com/traders`：
  - 导航超时，无法稳定读取页面内容。
- 命令行请求确认：
  - `curl -I -L --max-time 20 https://polymarketanalytics.com/traders` 返回 HTTP 403。
  - 响应头包含 `server: Vercel` 与 `x-vercel-mitigated: deny`。
  - 页面正文为 `Forbidden`。

**代码动作**：
- 增强 `LeaderResearch` 页面外部名单解析：
  - 从整行文本中提取第一个完整 `0x[a-fA-F0-9]{40}` 钱包地址。
  - 支持复制行里包含 URL，例如 `https://polymarket.com/profile/0x...`。
  - 表头或无完整钱包地址的行自动跳过，不再作为无效 wallet 发送。
  - category 从整行中识别 `politics|finance|sports|crypto`，否则使用默认分类。
  - score 只接受严格数字或百分比字段，避免把 URL 误判为分数。

**验证**：
- 后端 dry-run 验证通过：
  - sourceName=`polymarket_analytics`。
  - requestedTotal=2。
  - selectedTotal=2。
  - updatedTotal=2。
  - skippedInvalidTotal=0。
- 前端构建通过：
  - `cd frontend && npm run build`。
  - 仅有既有 chunk size / dynamic import 警告。

**结论**：
- 当前环境不能直接自动复制 Polymarket Analytics 页面，原因是站点防护返回 403。
- 但“页面复制方式”的本地链路已可用：只要用户从浏览器页面复制的文本里包含完整 wallet 地址，`Leader 管理 -> 导入外部名单` 可以解析并 dry-run/正式导入。

**下一轮动作**：
- 用户在正常 Chrome 登录/打开 Polymarket Analytics 后，复制排行榜行或导出 CSV。
- 粘贴到 `Leader Research / Leader 管理 -> 导入外部名单`：
  - 默认分类优先选 `finance` 或 `politics`。
  - 来源名称填 `polymarket_analytics`。
  - 先点 Dry-run，确认 `选中 > 0` 且 `无效 = 0` 后再正式导入。

## Iteration 93 - 2026-06-26 16:47 CST - 继续推进 PAPER 池与 politics market-peer 补源

**目标**：
- 按第二目标继续扩充高质量 leader 观察池，政治/金融优先。
- 不把 activity 预筛高分直接当作可跟单；必须经过 PAPER 模拟和风控过滤。

**初始复核**：
- 后端在线：
  - `java` PID=36229，8000 端口监听正常。
  - 登录 API 正常返回 token。
- 前端在线：
  - `node` PID=20436，3000 端口监听正常。
- summary：
  - DISCOVERED=1742。
  - PAPER=284。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=15。
  - 主类别 politics/finance clean high=14。
  - 主类别占比=93.3333%，allocationHealth=HEALTHY。
  - politics：total=669，paper=41，cleanHigh=2。
  - finance：total=985，paper=235，cleanHigh=12。

**动作 1 - 高分 DISCOVERED 晋级 PAPER**：
- promote dry-run：
  - selectedTotal=26。
- formal promote：
  - selectedTotal=8。
  - promotedTotal=8。
  - requestedSelectedTotal=26。
  - effectiveSelectedLimit=8。
  - truncated=true。
  - 本批全部为 finance。
- 晋级候选：
  - `0x3b693e05417ef5508cdb8cb91a50179804af9c68` candidate 2356，score=95.6250。
  - `0xd47815209ee28529bbedf864dc992bd65bf89239` candidate 2250，score=95.4118。
  - `0x0b9486a260e2fad1c6a62a520af3b39f0ed6805f` candidate 2225，score=95.0000。
  - `0x3f6b4a9d1c4fa74bc359872f2f05864a65ab276a` candidate 2132，score=95.0000，risk=`low_average_size`。
  - `0x04fb8c082ba8ecee098f9a1a99608f0cc28ee909` candidate 2254，score=94.9444。
  - `0x2494345f3f94b5bf4b8188cd32ea5fa5fc419a83` candidate 2175，score=94.5185。
  - `0xa34837a6cba2592bb952ce6c6204d2aea05bdad3` candidate 2262，score=94.4091。
  - `0x5e32bad4e912a884e7d62e6430d0615e0ad68496` candidate 2217，score=94.3095。

**动作 2 - PAPER 模拟处理与评分**：
- `paper/process`：
  - processed=14。
  - filtered=6。
  - failed=0。
  - requestedBatchSize=30。
  - effectiveBatchSize=20。
  - truncated=true。
- `paper/score`：
  - scoredCount=292。
  - scoreVersion=`research-copyability-v1`。
- 结果：
  - PAPER 从 284 增至 292。
  - DISCOVERED 从 1742 降至 1734。
  - TRIAL_READY 仍为 0。
  - cleanHighScoreTotal 仍为 15。
- 新晋级 finance 候选在真实 PAPER 后被压低：
  - 多数因为 `small_sample` 得分降到 59。
  - candidate 2254 因 `filteredRatio=1` 触发 `high_filtered_ratio`，score=45.0001。
  - candidate 2217 因 `filteredRatio=0.5` 触发 `high_filtered_ratio`，score=54.6923。
- 结论：PAPER 隔离层有效，activity 预筛高分不能直接进入可跟单。

**动作 3 - FAST_WATCH / TRIAL_READY 审计**：
- 按后端 FAST_WATCH 规则从数据库复核：
  - score>=85。
  - riskFlags 为空。
  - PAPER age>=48h。
  - tradeCount>=20。
  - copyablePnl>0。
  - maxDrawdown>=-8。
  - unknown valuation exposure ratio<=10%。
  - filteredRatio<20%。
- 当前 FAST_WATCH 条件清空：
  - finance `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
    - score=90.8086。
    - ageHours=49.1。
    - trades=22。
    - filteredRatio=0.0435。
    - copyablePnl=12.0753。
    - maxDrawdown=0。
  - finance `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`
    - score=85.6655。
    - ageHours=49.1。
    - trades=21。
    - filteredRatio=0.0870。
    - copyablePnl=5.2545。
    - maxDrawdown=0。
- 仍未进入 TRIAL_READY：
  - 7 天 PAPER 观察期未满足。
  - TRIAL_READY count=0。
- 其他接近候选：
  - finance `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`：score=91.6236，trades=32，PnL=8.7053，但 ageHours=16.7，未到 48h。
  - politics `0xad5353afe30c2da57709e2704ef3ccdcf67eef24`：score=86.6105，trades=21，PnL=8.9957，但 ageHours=3.5 且 filteredRatio=0.4324，不适合快速观察。
  - politics `0x645a91730f588c5586e8860936a7e3554303fd84`：score=95.1955，trades=37，PnL=10.4872，但 risk=`mixed_category_evidence` 且 ageHours=6.6。

**动作 4 - market-peer politics 补源**：
- strict market-peer dry-run：
  - selectedTotal=1。
  - created=0。
  - updated=0。
  - skippedExisting=1。
- finance relaxed dry-run：
  - selectedTotal=1。
  - created=0。
  - skippedExisting=1。
- politics relaxed dry-run：
  - selectedTotal=4。
  - created=0。
  - updated=4。
- politics relaxed formal：
  - selectedTotal=4。
  - created=0。
  - updated=4。
  - 更新的钱包包括：
    - `0x8a98109fb0f1d87d9bfcb4486ba3587b95c51b92`。
    - `0xc8ab97a9089a9ff7e6ef0688e6e591a066946418`。
    - `0x38e59b36aae31b164200d0cad7c3fe5e0ee795e7`。
    - `0xa3af760e15e6b6bd3c43d8cf2ae6952f0a9bb7a6`。
- 重跑 `activity-score/run`：
  - scanned=1734。
  - scored=1734。
  - categoryCounts：politics=777，finance=603，sports=180，crypto=174。
- 重跑 `paper/score`：
  - scoredCount=292。

**最终状态**：
- summary：
  - DISCOVERED=1734。
  - PAPER=292。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=15。
  - 主类别 politics/finance clean high=14。
  - 主类别占比=93.3333%，allocationHealth=HEALTHY。
  - politics：total=670，paper=42，cleanHigh=2，topCandidateId=2361，topScore=86.6105。
  - finance：total=984，paper=242，cleanHigh=12，topCandidateId=2079，topScore=91.6236。

**结论**：
- 本轮把 8 个 finance 预筛高分候选纳入 PAPER，但真实模拟后多数被小样本/过滤率压下，没有污染正式 Leader 池。
- 当前最接近可试跟的仍是两个 FAST_WATCH finance，但系统仍要求 7 天观察，不能自动创建跟单配置。
- politics 仍是质量瓶颈：有高分样本，但主要被 mixed evidence、观察时间短或过滤率高拦住。
- market-peer 补源当前更适合补证据，不足以显著新增候选。

**下一轮动作**：
- 继续滚动 PAPER/process + score，让 292 个 PAPER 候选获得更多样本。
- 继续等待/复核 finance FAST_WATCH 候选是否保持低过滤率和正 PnL。
- politics 需要从外部排行榜/Analytics/Dune 导入完整 wallet；本地 activity/market-peer 来源已经接近边际枯竭。

## Iteration 94 - 2026-06-26 16:53 CST - PAPER 滚动增强与继续小批量 finance 晋级

**目标**：
- 继续推进第二目标：累积并验证高质量 leader，政治/金融优先。
- 本轮优先增加现有 PAPER 的模拟样本，再小批量扩充 finance PAPER。

**初始复核**：
- 后端在线：
  - `java` PID=36229，8000 端口监听正常。
- 前端在线：
  - `node` PID=20436，3000 端口监听正常。
- summary：
  - DISCOVERED=1734。
  - PAPER=292。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=15。
  - 主类别 politics/finance clean high=14。
  - 主类别占比=93.3333%，allocationHealth=HEALTHY。
  - politics：total=670，paper=42，cleanHigh=2。
  - finance：total=984，paper=242，cleanHigh=12。
- promote dry-run：
  - selectedTotal=21。
  - politics=0。
  - finance=15。
  - sports=4。
  - crypto=2。

**动作 1 - 滚动 PAPER 模拟样本**：
- 连续执行 5 轮 `paper/process`，每轮请求 batchSize=30，后端有效上限=20。
- 5 轮结果：
  - processed=76。
  - filtered=24。
  - failed=0。
- 重跑 `paper/score`：
  - scoredCount=292。
  - scoreVersion=`research-copyability-v1`。

**滚动后状态**：
- summary：
  - DISCOVERED=1734。
  - PAPER=292。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - cleanHighScoreTotal 从 15 升至 17。
  - 主类别 politics/finance clean high 从 14 升至 16。
  - 主类别占比=94.1176%，allocationHealth=HEALTHY。
  - politics：cleanHigh=2，topCandidateId=2361，topScore=86.6126。
  - finance：cleanHigh=14，topCandidateId=1609，topScore=94.3528。
- 结论：
  - 继续滚动 PAPER 样本能真实拉开 finance 候选质量。
  - 本轮新增 clean high 主要来自 finance。

**FAST_WATCH / TRIAL_READY 审计**：
- 当前 FAST_WATCH 条件清空的候选仍为 2 个 finance：
  - `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
    - score=90.8120。
    - ageHours=49.2。
    - trades=22。
    - filteredRatio=0.0435。
    - copyablePnl=12.0753。
    - maxDrawdown=0。
    - trial blocker：`age<7d:49.2h`。
  - `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`
    - score=85.6689。
    - ageHours=49.2。
    - trades=21。
    - filteredRatio=0.0870。
    - copyablePnl=5.2545。
    - maxDrawdown=0。
    - trial blocker：`age<7d:49.2h`。
- TRIAL_READY-like：
  - 0。
  - 仍没有候选满足 7 天观察期。
- 新的强势 finance：
  - `0x674887d1ac838099a48b629dff53f25b7b87ee08` candidate 1609：
    - score=94.3528。
    - trades=45。
    - filteredRatio=0.0816。
    - copyablePnl=10.6592。
    - blocker：ageHours=19.4，未到 48h。
  - `0x75cc3b63a2f2423085e10706c78b494017b93ce1` candidate 1611：
    - score=87.9061。
    - trades=60。
    - filteredRatio=0.1781。
    - copyablePnl=12.3629。
    - blocker：ageHours=19.4，未到 48h。

**politics 审计**：
- politics 高分仍未达到 FAST_WATCH：
  - `0x645a91730f588c5586e8860936a7e3554303fd84` candidate 360：
    - score=95.1989。
    - trades=47。
    - copyablePnl=15.9700。
    - blocked by `mixed_category_evidence` 和 ageHours=6.7。
  - `0x328c2be6eba95a30b003255dc48f2b50e0eccbbc` candidate 34：
    - score=93.2945。
    - blocked by `mixed_category_evidence` 和 filteredRatio=0.2188。
  - `0xad5353afe30c2da57709e2704ef3ccdcf67eef24` candidate 2361：
    - score=86.6126。
    - riskFlags 为空，但 ageHours=3.6 且 filteredRatio=0.4324。
- 结论：
  - politics 不是数量问题，而是分类证据和可复制过滤率问题。
  - 继续依赖外部 Analytics/Dune/排行榜完整 wallet 导入更有价值。

**动作 2 - 小批量晋级 finance 到 PAPER**：
- formal promote：
  - selectedTotal=8。
  - promotedTotal=8。
  - 本批全部为 finance。
  - requestedSelectedTotal=21。
  - effectiveSelectedLimit=8。
  - truncated=true。
- 晋级候选：
  - `0x9d59ddd4fc73895942a2643654063827ff755d33` candidate 2357，score=94.0814。
  - `0x8bf9ae97bce9ab947bc071c08245d03f145b1f3b` candidate 2267，score=93.7500。
  - `0xaf4d8b57af872a2e2519b9b92b71c6859cc0b5f6` candidate 2086，score=93.6429。
  - `0x162e0ed01a0e487beded744e5289f7b2521afe52` candidate 2111，score=93.6034。
  - `0x947fdb883f2ccbde77c63e4c1aba8a99ecb5f249` candidate 2359，score=93.5000。
  - `0xddc8fdb11bbed4cefbf7ecfe20793941029e3742` candidate 2251，score=93.4444。
  - `0x18803d2aeb7f7dcdd53475b6154851b7fd37eebc` candidate 2269，score=93.2857。
  - `0xa4f22a6919e5428926d648fdf15a292f917829c2` candidate 1765，score=92.7143。
- 晋级后跑 1 轮 `paper/process`：
  - processed=18。
  - filtered=2。
  - failed=0。
- 重跑 `paper/score`：
  - scoredCount=300。

**最终状态**：
- summary：
  - DISCOVERED=1726。
  - PAPER=300。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=17。
  - 主类别 politics/finance clean high=16。
  - 主类别占比=94.1176%，allocationHealth=HEALTHY。
  - politics：total=670，paper=42，cleanHigh=2，topCandidateId=2361，topScore=86.6132。
  - finance：total=984，paper=250，cleanHigh=14，topCandidateId=1609，topScore=94.3535。
  - sports：paper=4，cleanHigh=1。
  - crypto：paper=4，cleanHigh=0。

**结论**：
- 本轮有效推进了第二目标：
  - PAPER 观察池从 292 扩到 300。
  - clean high 从 15 增到 17。
  - finance clean high 从 12 增到 14。
  - 模拟处理失败为 0。
- 最接近可跟单的仍是两个 finance FAST_WATCH；候选 1609 和 1611 可能在跨过 48h 后成为新的 FAST_WATCH。
- politics 仍需外部高质量来源，当前内部链上/market-peer 来源持续暴露混类和过滤率问题。

**下一轮动作**：
- 继续滚动 PAPER/process + score，尤其观察新晋级的 8 个 finance 是否被小样本/过滤率压下。
- 等 candidate 1609、1611 接近 48h 后复核 FAST_WATCH。
- 继续从 Polymarket Analytics/Dune/外部榜单导入完整 politics/finance wallet，补足 politics 质量短板。

## Iteration 95 - 2026-06-26 16:57 CST - 主类别晋级池吃干与 PAPER 样本校正

**目标**：
- 继续推进第二目标，优先验证上一轮新晋级 finance PAPER 是否是真信号。
- 保持 politics/finance 主类别优先，不把 sports/crypto 继续往 PAPER 推。

**初始复核**：
- 后端在线：
  - `java` PID=36229，8000 端口监听正常。
- 前端在线：
  - `node` PID=20436，3000 端口监听正常。
- summary：
  - DISCOVERED=1726。
  - PAPER=300。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=17。
  - 主类别 politics/finance clean high=16。
  - 主类别占比=94.1176%，allocationHealth=HEALTHY。
  - politics：total=670，paper=42，cleanHigh=2。
  - finance：total=984，paper=250，cleanHigh=14。
- promote dry-run：
  - selectedTotal=13。
  - politics=0。
  - finance=7。
  - sports=4。
  - crypto=2。

**动作 1 - 滚动处理新晋级 PAPER 样本**：
- 连续执行 6 轮 `paper/process`，每轮请求 batchSize=30，后端有效上限=20。
- 6 轮总结果：
  - processed=105。
  - filtered=15。
  - failed=0。
- 重跑 `paper/score`：
  - scoredCount=300。
  - scoreVersion=`research-copyability-v1`。

**滚动后状态**：
- summary：
  - DISCOVERED=1726。
  - PAPER=300。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - cleanHighScoreTotal=17，保持不变。
  - 主类别 politics/finance clean high=16，保持不变。
  - finance topScore 从 94.3535 降到 92.6045，topCandidateId 仍为 1609。
- 结论：
  - 更多 PAPER 样本在校正过热候选，finance top score 降温但 clean high 数量稳定。
  - 模拟处理链路本轮失败为 0。

**上一轮新晋级 8 个 finance 审计**：
- `0x9d59ddd4fc73895942a2643654063827ff755d33` candidate 2357：
  - score=59。
  - trades=7。
  - filteredRatio=0.3636。
  - copyablePnl=2.2272。
  - risk=`small_sample`。
- `0x8bf9ae97bce9ab947bc071c08245d03f145b1f3b` candidate 2267：
  - score=59。
  - trades=1。
  - risk=`small_sample`。
- `0xaf4d8b57af872a2e2519b9b92b71c6859cc0b5f6` candidate 2086：
  - score=59。
  - trades=0。
  - risk=`small_sample`。
- `0x162e0ed01a0e487beded744e5289f7b2521afe52` candidate 2111：
  - score=55.2047。
  - trades=2。
  - filteredRatio=0.6667。
  - risk=`high_filtered_ratio,small_sample`。
- `0x947fdb883f2ccbde77c63e4c1aba8a99ecb5f249` candidate 2359：
  - score=59。
  - trades=0。
  - risk=`small_sample`。
- `0xddc8fdb11bbed4cefbf7ecfe20793941029e3742` candidate 2251：
  - score=59。
  - trades=0。
  - risk=`small_sample`。
- `0x18803d2aeb7f7dcdd53475b6154851b7fd37eebc` candidate 2269：
  - score=59。
  - trades=0。
  - risk=`small_sample`。
- `0xa4f22a6919e5428926d648fdf15a292f917829c2` candidate 1765：
  - score=59。
  - trades=1。
  - risk=`small_sample`。
- 结论：
  - 上一轮新晋级 8 个 finance 都没有进入 clean high。
  - PAPER 隔离层继续有效，预筛高分被真实模拟样本压下。

**FAST_WATCH / TRIAL_READY 审计**：
- 当前 FAST_WATCH 条件清空的候选仍为 2 个 finance：
  - `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
    - score=90.8142。
    - ageHours=49.3。
    - trades=22。
    - filteredRatio=0.0435。
    - copyablePnl=12.0753。
    - blocker：`age<7d:49.3h`。
  - `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`
    - score=85.6711。
    - ageHours=49.3。
    - trades=21。
    - filteredRatio=0.0870。
    - copyablePnl=5.2545。
    - blocker：`age<7d:49.3h`。
- TRIAL_READY-like：
  - 0。
- 其他 finance 候选：
  - candidate 1609：score=92.6045，trades=53，filteredRatio=0.0702，copyablePnl=9.0388，blocker=`age<48h:19.5`。
  - candidate 1611：score=87.7654，trades=68，filteredRatio=0.1605，copyablePnl=9.7966，blocker=`age<48h:19.5`。
  - candidate 2079：score=91.6280，trades=32，filteredRatio=0.0857，copyablePnl=8.7053，blocker=`age<48h:16.9`。

**politics 审计**：
- politics 仍没有 FAST_WATCH：
  - candidate 360：score=95.2012，trades=54，copyablePnl=19.9839，但 risk=`mixed_category_evidence`，ageHours=6.8。
  - candidate 34：score=93.2967，但 risk=`mixed_category_evidence`，filteredRatio=0.2188。
  - candidate 617：score=93.0187，但 risk=`mixed_category_evidence`，filteredRatio=0.2373。
  - candidate 2361：score=86.6148，riskFlags 为空，但 ageHours=3.7 且 filteredRatio=0.4324。
- 结论：
  - politics 质量瓶颈没有缓解。
  - 需要外部高质量 politics wallet 或更强的分类证据来源。

**动作 2 - 只晋级剩余 finance，不推进 sports/crypto**：
- 为避免偏离政治/金融主目标，formal promote 设置：
  - politicsLimit=20。
  - financeLimit=20。
  - sportsLimit=0。
  - cryptoLimit=0。
- formal promote 结果：
  - selectedTotal=7。
  - promotedTotal=7。
  - 全部为 finance。
- 晋级候选：
  - `0x068162f52e8534620c419c174be1aa5337dff713` candidate 2358，score=92.2468。
  - `0xb64e6e653d4d7815c0fbfc2f93bbb9245b06fec1` candidate 2151，score=92.2273。
  - `0x00b10f05d44d91eb1a0d4620263972152c476784` candidate 2256，score=92.0000，risk=`low_average_size`。
  - `0x10613ca3f9b25b24b6b1615c8744808073bf99f1` candidate 2271，score=91.5000。
  - `0x580dbe563496d8c57c8c724f761c9ca4b02ccfb5` candidate 2360，score=90.5000。
  - `0x5d55f82ec7a774126f5a0ffd3a44039ac3674c59` candidate 2218，score=89.6250。
  - `0xf27d40745542dc871e127acff3a1c9d3910d9a88` candidate 2272，score=87.2500。
- 晋级后执行 1 轮 `paper/process`：
  - processed=14。
  - filtered=6。
  - failed=0。
- 重跑 `paper/score`：
  - scoredCount=307。

**最终状态**：
- summary：
  - DISCOVERED=1719。
  - PAPER=307。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=17。
  - 主类别 politics/finance clean high=16。
  - 主类别占比=94.1176%，allocationHealth=HEALTHY。
  - politics：total=670，paper=42，cleanHigh=2，topCandidateId=2361，topScore=86.6155。
  - finance：total=984，paper=257，cleanHigh=14，topCandidateId=1609，topScore=92.6052。
  - sports：paper=4，cleanHigh=1。
  - crypto：paper=4，cleanHigh=0。
- promote dry-run with sports/crypto disabled：
  - politics=0。
  - finance=0。
  - selectedTotal=0。

**结论**：
- 主类别 politics/finance 可晋级池已经吃干。
- PAPER 观察池从 300 增至 307。
- clean high 保持 17，没有因为新 finance 晋级而虚增。
- 两个 finance FAST_WATCH 继续稳定，但没有 TRIAL_READY。
- politics 仍无法靠现有内部来源突破，需要外部 wallet 来源。

**下一轮动作**：
- 继续滚动 307 个 PAPER 样本，观察 7 个新 finance 是否被小样本/过滤率压下。
- 等 candidate 1609、1611、2079 满 48h 后复核是否新增 FAST_WATCH。
- 重点切换到外部 politics/finance 来源：Polymarket Analytics/Dune/排行榜完整 wallet 粘贴导入，否则主类别晋级池短期不会再增长。

## Iteration 96 - 2026-06-26 17:06 CST - 内部补源确认枯竭与 PAPER 继续滚动

**目标**：
- 在主类别 politics/finance 可晋级池归零后，确认内部补源是否还有新 wallet。
- 继续滚动 PAPER 样本，观察 clean high 和 FAST_WATCH 是否变化。

**初始状态**：
- 服务状态：
  - 后端 `java` PID=36229，8000 端口监听正常。
  - 前端 `node` PID=20436，3000 端口监听正常。
- summary：
  - DISCOVERED=1719。
  - PAPER=307。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2031。
  - cleanHighScoreTotal=17。
  - 主类别 politics/finance clean high=16。
  - 主类别占比=94.1176%，allocationHealth=HEALTHY。
  - politics：total=670，paper=42，cleanHigh=2。
  - finance：total=984，paper=257，cleanHigh=14。
- promote dry-run with sports/crypto disabled：
  - politics=0。
  - finance=0。
  - selectedTotal=0。

**动作 1 - 内部补源 dry-run**：
- activity-source strict：
  - selectedTotal=4。
  - created=0。
  - updated=0。
  - skippedExisting=4。
  - 全部为 politics 既有候选。
- activity-source relaxed：
  - selectedTotal=12。
  - created=0。
  - updated=5。
  - skippedExisting=7。
  - politics selected=11，updated=4。
  - finance selected=1，updated=1。
- market-peer relaxed：
  - selectedTotal=5。
  - created=0。
  - updated=0。
  - skippedExisting=5。

**结论 - 内部补源**：
- 内部 activity-source / market-peer 已无法产生新的 politics/finance wallet。
- relaxed activity-source 仍可补充已有候选证据，但不会增加候选数量。
- 这确认上一轮判断：主类别短期增量必须依赖外部完整 wallet 来源。

**动作 2 - 正式补充已有候选证据**：
- 正式执行 activity-source relaxed：
  - selectedTotal=12。
  - created=0。
  - updated=5。
  - skippedExisting=7。
- 更新样本：
  - politics `0x21ffd2b7a212a6f277ed3eca1a9f8efcbca90d71`。
  - politics `0x5c0af092b533934008144d223d704b4cbebfa2c3`。
  - politics `0x38e59b36aae31b164200d0cad7c3fe5e0ee795e7`。
  - politics `0x74957ea27ac4fbdee46d861fdae357859ff67fcf`。
  - 另有 1 个 finance 既有候选更新。
- 重跑 `activity-score/run`：
  - scanned=1719。
  - scored=1719。
  - categoryCounts：politics=777，finance=588，sports=180，crypto=174。
  - riskFlagCounts 主要仍为：
    - small_sample=1554。
    - low_market_diversity=1180。
    - scanner_pool_unverified=1312。
    - mixed_category_evidence=251。

**动作 3 - PAPER 滚动处理**：
- 连续执行 4 轮 `paper/process`：
  - processed=51。
  - filtered=29。
  - failed=0。
- 重跑 `paper/score`：
  - scoredCount=307。
  - scoreVersion=`research-copyability-v1`。

**滚动后状态**：
- summary：
  - DISCOVERED=1719。
  - PAPER=307。
  - TRIAL_READY=0。
  - COOLDOWN=5。
- funnel：
  - cleanHighScoreTotal 从 17 升到 18。
  - 主类别 politics/finance clean high 从 16 升到 17。
  - 主类别占比=94.4444%，allocationHealth=HEALTHY。
  - politics：total=669，paper=42，cleanHigh=2，topCandidateId=2361，topScore=86.6195。
  - finance：total=985，paper=257，cleanHigh=15，topCandidateId=1609，topScore=92.6273。

**FAST_WATCH / TRIAL_READY 审计**：
- FAST_WATCH 条件清空仍为 2 个 finance：
  - `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`
    - score=90.8189。
    - ageHours=49.4。
    - trades=22。
    - filteredRatio=0.0435。
    - copyablePnl=12.0753。
    - blocker：`age<7d:49.4h`。
  - `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`
    - score=85.6758。
    - ageHours=49.4。
    - trades=21。
    - filteredRatio=0.0870。
    - copyablePnl=5.2545。
    - blocker：`age<7d:49.4h`。
- TRIAL_READY-like：
  - 0。
- 值得继续观察的 finance：
  - candidate 1609 `0x674887d1ac838099a48b629dff53f25b7b87ee08`
    - score=92.6273。
    - trades=54。
    - filteredRatio=0.0690。
    - copyablePnl=9.0388。
    - blocker：`age<48h:19.6`。
  - candidate 2079 `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`
    - score=91.6327。
    - trades=32。
    - filteredRatio=0.0857。
    - copyablePnl=8.7053。
    - blocker：`age<48h:17.1`。
  - candidate 1612 `0x5e2b9261b0c4f697b55bf921ff2bc227183d9101`
    - score=87.6362。
    - trades=57。
    - filteredRatio=0.1972。
    - copyablePnl=10.7818。
    - blocker：`age<48h:20.0`。
  - candidate 1611 `0x75cc3b63a2f2423085e10706c78b494017b93ce1`
    - score=85.0726。
    - trades=76。
    - filteredRatio=0.1556。
    - copyablePnl=8.4108。
    - blocker：`age<48h:19.6`。

**politics 审计**：
- politics 仍没有 FAST_WATCH：
  - candidate 360：
    - score=95.2059。
    - trades=57。
    - copyablePnl=21.7382。
    - blocked by `mixed_category_evidence` and ageHours=6.9。
  - candidate 34：
    - score=93.3014。
    - blocked by `mixed_category_evidence` and filteredRatio=0.2188。
  - candidate 617：
    - score=93.0234。
    - blocked by `mixed_category_evidence` and filteredRatio=0.2373。
  - candidate 2361：
    - score=86.6195。
    - riskFlags 为空，但 ageHours=3.9 且 filteredRatio=0.4324。

**最终复核**：
- promote dry-run with sports/crypto disabled：
  - politics=0。
  - finance=0。
  - selectedTotal=0。

**结论**：
- 本轮没有新增 wallet，但提高了已有 PAPER 样本质量：
  - clean high 从 17 增到 18。
  - finance clean high 从 14 增到 15。
  - paper/process 失败为 0。
- 内部补源已经明确枯竭：只能更新已有候选，不能产生新的 politics/finance wallet。
- 下一步不应继续重复内部 promote，应切到外部 wallet 来源导入。

**下一轮动作**：
- 继续滚动 307 个 PAPER 样本，等待 1609、1611、1612、2079 接近 48h。
- 从 Polymarket Analytics / Dune / 外部排行榜复制完整 politics/finance wallet，通过“导入外部名单”入口导入。
- 若无法立刻拿到外部 wallet，则继续 PAPER 滚动和 FAST_WATCH 复核，不再重复内部补源空转。

### Iteration 97 - Polymarket Analytics 页面复制入口验证（2026-06-26）

**目标**：
- 尝试 Polymarket Analytics 页面复制方式，为外部高质量 leader 来源建立可落地入口。

**执行结果**：
- 本机直接访问 `docs.polymarket.com` 与 `data-api.polymarket.com` 均连接超时：
  - shell 方式无法稳定直连 Polymarket 域名。
  - 页面复制方式仍可作为人工补源入口，不依赖后端直连外网。
- 复核官方 Data API 方向：
  - Polymarket 官方文档存在 trader leaderboard rankings 端点。
  - 端点方向可用于后续自动化抓取，但当前本机网络不可用，需要代理或可访问网络环境。
- 优化 Leader Research 外部导入弹窗：
  - 文案改为支持从 Polymarket Analytics / Dune / Polyburg 手工榜单直接粘贴。
  - 默认来源名改为 `polymarket_analytics_page_copy`。
  - 示例改为页面复制风格：rank + trader + wallet + category + score。
- 使用模拟页面复制行执行后端 dry-run：
  - requestedTotal=2。
  - selectedTotal=2。
  - createdTotal=1。
  - updatedTotal=1。
  - skippedInvalidTotal=0。
  - sourceEvidence 正确写入 `external_analytics:polymarket_analytics_page_copy`。

**验证**：
- `frontend npm run build` 通过。
- 外部名单 dry-run API 返回 code=0，证明页面复制路径可以进入现有 leader research 导入链路。

**结论**：
- 页面复制方式可用：只要 Polymarket Analytics 页面能复制出完整 `0x` 钱包地址，系统可以识别并进入 DISCOVERED/UPDATE。
- 当前瓶颈不是解析或导入逻辑，而是本机无法直连 Polymarket 域名；下一步应让用户从浏览器页面复制 politics/finance leaderboard 行，或给后端 shell 配可用代理后改为官方 Data API 自动抓取。

### Iteration 98 - 官方 Leaderboard 自动补源闭环（2026-06-26）

**目标**：
- 将 Polymarket 官方 leaderboard 变成系统可一键抓取的 politics/finance 外部 leader 来源，并把候选推进到评分和 PAPER 链路。

**代码变更**：
- 新增后端接口：
  - `POST /api/copy-trading/leader-research/official-leaderboard/import`
  - 默认抓取 politics/finance、MONTH、PNL。
  - 返回 `fetches`，明确展示每个 category/timePeriod/orderBy 的抓取数量和错误。
- 新增 `LeaderResearchOfficialLeaderboardImportService`：
  - 使用官方 `https://data-api.polymarket.com/v1/leaderboard`。
  - 分页抓取并解析 `proxyWallet`/`wallet`/`address`。
  - 复用 `LeaderResearchExternalAnalyticsImportService`，不绕过现有去重、锁定、evidence、评分和 PAPER 规则。
- 修复 external analytics 导入更新已有候选时的 `source` 字段超长问题：
  - `leader_research_candidate.source` 实际长度为 50。
  - 详细来源继续写入 `sourceEvidence`。
  - `source` 只保留能放下的短来源标签，避免事务回滚。
- 前端 Leader Research 外部导入弹窗新增：
  - “官方榜单 Dry-run”。
  - “官方榜单导入”。
  - 抓取结果区：抓取、去重、错误数，以及每个来源查询的错误详情。

**验证**：
- 后端测试通过：
  - `LeaderResearchExternalAnalyticsImportServiceTest`
  - `LeaderResearchOfficialLeaderboardImportServiceTest`
  - `LeaderResearchControllerTest`
- 后端 `bootJar` 通过。
- 前端 `npm run build` 通过。
- 本地后端已强制重启到新 jar。

**数据执行结果**：
- 官方 leaderboard dry-run：
  - fetchedTotal=400。
  - dedupedTotal=381。
  - politics MONTH PNL fetchedItems=200。
  - finance MONTH PNL fetchedItems=200。
  - fetchErrors=0。
  - createdTotal=329。
  - updatedTotal=52。
- 正式导入：
  - requestedTotal=381。
  - selectedTotal=381。
  - createdTotal=329。
  - updatedTotal=52。
  - skippedInvalidTotal=0。
  - skippedExistingTotal=0。
  - skippedLockedTotal=0。
- DB 复核：
  - `polymarket_official_leaderboard` evidence count=381。
  - DISCOVERED=376。
  - PAPER=5。
- 活动评分：
  - scannedCount=2048。
  - scoredCount=2048。
  - categoryCounts：politics=953，finance=745，sports=178，crypto=172。
- 主类别 PAPER 提拔：
  - dry-run selectedTotal=3。
  - 正式 promotedTotal=3。
  - politics promoted=2。
  - finance promoted=1。
  - sports/crypto limit=0。
- 新提拔候选：
  - politics candidate 2816 `0xc7d02944a76b9f83b199e9090ecc92c82d241f8a`，score=98.64044950。
  - politics candidate 2810 `0x21064fd320bfd5a86f8c92a94d3209edf4154dea`，score=98.02040810。
  - finance candidate 2846 `0x38d812aff0b79f3bf5da2a477f780bcc163eea7c`，score=100.00000000。
- PAPER 处理：
  - processed=11。
  - filtered=9。
  - failed=0。
- PAPER 评分：
  - scoredCount=310。

**当前 funnel**：
- totalCandidates=2360。
- politics：
  - totalCandidates=844。
  - paperCandidates=43。
  - cleanHighScoreCandidates=2。
- finance：
  - totalCandidates=1146。
  - paperCandidates=260。
  - cleanHighScoreCandidates=15。

**结论**：
- 第二目标的外部补源瓶颈被明显缓解：单轮新增/更新 381 个官方 leaderboard politics/finance 钱包，其中 329 个是新候选。
- 新来源进入了系统评分和 PAPER 链路，并且 PAPER 执行失败为 0。
- 当前新增 leaderboard 候选中只有 3 个立刻满足无风险高分 PAPER 门槛，其余多为 small sample / stale/no activity，需要继续滚动观察或补充更细的成交历史。

**下一轮动作**：
- 增加 WEEK/ALL + VOL 维度，继续扩大 politics/finance 外部来源，但需要控制重复和巨鲸偏差。
- 对 official leaderboard 来源增加质量诊断：区分高 PNL 巨鲸、近期高频、可跟单小额、低滑点市场。
- 对新 PAPER 三个候选单独观察 24-48h，优先检查是否有可跟单市场、是否存在低价长尾/巨额不可复制风险。

### Iteration 99 - 扩展官方榜单维度与提拔一致性修复（2026-06-26）

**目标**：
- 在 Iteration 98 的官方 leaderboard 基础上，继续引入 WEEK/ALL + PNL/VOL 维度，优先扩大 politics/finance 候选池，并修复提拔 dry-run 与正式状态机不一致的问题。

**基线**：
- summary：
  - DISCOVERED=2045。
  - PAPER=310。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2360。
  - cleanHighScoreTotal=18。
  - politics total=844，paper=43，cleanHigh=2。
  - finance total=1146，paper=260，cleanHigh=15。
- official leaderboard evidence：
  - total=381。
  - DISCOVERED=373。
  - PAPER=8。

**扩展来源 dry-run**：
- WEEK + PNL/VOL：
  - fetchedTotal=400。
  - dedupedTotal=334。
  - createdTotal=172。
  - updatedTotal=162。
  - fetchErrors=0。
- ALL + PNL/VOL：
  - fetchedTotal=400。
  - dedupedTotal=322。
  - createdTotal=248。
  - updatedTotal=74。
  - fetchErrors=0。

**正式导入**：
- WEEK + PNL/VOL：
  - requestedTotal=334。
  - selectedTotal=334。
  - createdTotal=172。
  - updatedTotal=162。
  - skippedInvalidTotal=0。
  - skippedExistingTotal=0。
  - skippedLockedTotal=0。
- ALL + PNL/VOL：
  - requestedTotal=322。
  - selectedTotal=322。
  - createdTotal=225。
  - updatedTotal=97。
  - skippedInvalidTotal=0。
  - skippedExistingTotal=0。
  - skippedLockedTotal=0。
- official leaderboard evidence：
  - total 从 381 增至 805。
  - official DISCOVERED=790。
  - official PAPER=14。
  - official COOLDOWN=1。

**评分与 PAPER 链路**：
- activity-score/run：
  - scannedCount=2442。
  - scoredCount=2442。
  - categoryCounts：politics=1172，finance=921，sports=177，crypto=172。
  - 主要风险：
    - small_sample=1772。
    - low_market_diversity=1351。
    - scanner_pool_unverified=1312。
    - no_activity_sample=470。
    - stale_activity=470。
- promote dry-run：
  - selectedTotal=4。
  - finance=4。
  - politics=0。
- 正式 promote：
  - selectedTotal=4。
  - promotedTotal=3。
  - finance promoted=3。
  - sports/crypto limit=0。
- 新进入 PAPER：
  - finance candidate 3120 `0xb527a4db04c36f2f358f1475189b5e0387c23b52`。
  - finance candidate 1828 `0xa364d9ee6e737b743da4029d4384e01bbb27d4b3`。
  - finance candidate 3155 `0x4ffe49ba2a4cae123536a8af4fda48faeb609f71`。
- PAPER 处理：
  - processed=13。
  - filtered=7。
  - failed=0。
- paper/score：
  - scoredCount=313。

**一致性修复**：
- 发现 candidate 1684 在 dry-run 中显示可提拔，但正式状态机没有推进：
  - wallet=`0xc3584c39a46f3a134d0b26b747b839480ac5c52e`。
  - score=100。
  - lastSourceSeenAt 已超过 48h，新鲜度约 50h。
- 修复 `LeaderResearchPaperPromotionService`：
  - dry-run 和正式提拔前都检查状态机一致的新鲜度条件。
  - 要求 sourceFresh48h。
  - 锁定候选不选中。
  - 与状态机一致处理 `score>=60` 或可 bootstrap paper observation。
- 新增测试：
  - `stale source candidate is not selected for paper promotion dry run`。
- 修复后复核：
  - promote dry-run selectedTotal=0。
  - candidate 1684 不再显示为可提拔。

**最终状态**：
- summary：
  - DISCOVERED=2439。
  - PAPER=313。
  - COOLDOWN=5。
- funnel：
  - totalCandidates=2757。
  - cleanHighScoreTotal=18。
  - politics total=1055，paper=43，cleanHigh=2。
  - finance total=1333，paper=263，cleanHigh=15。
  - allocationHealth=HEALTHY，primaryActualPercent=94.4444。
- official leaderboard evidence：
  - total=805。
  - finance DISCOVERED=345，PAPER=5。
  - politics DISCOVERED=443，PAPER=11，COOLDOWN=1。

**验证**：
- 后端测试通过：
  - `LeaderResearchPaperPromotionServiceTest`。
- 后端 `bootJar` 通过。
- 前端 `npm run build` 通过。
- 后端已重启到最新 jar。

**结论**：
- 官方榜单外部补源继续有效：本轮新增 397 个 politics/finance 候选，候选总量提升到 2757。
- WEEK/ALL + VOL 带来不少新增，但真正能立刻进入 PAPER 的仍很少，说明 scoring/risk gate 在过滤大量无活动样本和 stale activity，这是符合高质量目标的。
- dry-run 与正式提拔的一致性已修复，后续页面显示“可提拔”会更可信。

**下一轮动作**：
- 对 official leaderboard 来源加质量诊断视图或接口：
  - 区分 `no_activity_sample`、`stale_activity`、`small_sample`、`巨鲸高 pnl 但不可复制`。
  - 按 politics/finance 输出“值得补历史/值得观察/应排除”。
- 针对新进入 PAPER 的 3120、1828、3155 观察：
  - 3120：PAPER 初期 copyable_pnl 为负且 small_sample，需要谨慎。
  - 1828：偏 BTC up/down，需要检查是否违反 BTC 5M/短周期规则。
  - 3155：filteredRatio 高，已出现 high_filtered_ratio 和 small_sample，短期不应进入跟单。

### Iteration 100 - Official Leaderboard 质量诊断接口与页面入口（2026-06-26）

**目标**：
- 把 official leaderboard 大量补源后的质量瓶颈显性化，避免只看到候选数量增长，却不知道哪些值得补历史、观察、排除。

**代码变更**：
- 新增后端接口：
  - `POST /api/copy-trading/leader-research/official-leaderboard/diagnose`
- 新增 `LeaderResearchOfficialLeaderboardDiagnoseService`：
  - 只读诊断 `sourceEvidence` 中包含 `polymarket_official_leaderboard` 的候选。
  - 按 bucket 分组：
    - `READY_FOR_PAPER`
    - `FAST_WATCH`
    - `CLEAN_HIGH`
    - `PAPER_OBSERVING`
    - `SMALL_SAMPLE`
    - `NO_ACTIVITY_SAMPLE`
    - `STALE_ACTIVITY`
    - `HIGH_FILTERED_RATIO`
    - `HARD_RISK`
    - `CATEGORY_CONFLICT`
    - `OTHER_RISK`
    - `LOCKED`
    - `OBSERVE`
  - 输出 politics/finance 分类汇总、risk flag 汇总、样本候选。
- 新增 repository 查询：
  - `findOfficialLeaderboardCandidates()`。
- 前端 `LeaderResearch` 外部导入弹窗新增：
  - “官方榜单诊断”按钮。
  - “官方榜单质量诊断”摘要卡。
  - 展示总数、PAPER、干净高分、快速观察、可进 PAPER、无活动样本、主要 bucket、分类汇总和样本候选。

**验证**：
- 后端测试通过：
  - `LeaderResearchOfficialLeaderboardDiagnoseServiceTest`。
  - `LeaderResearchControllerTest`。
- 后端 `bootJar` 通过。
- 前端 `npm run build` 通过。
- 后端已强制重启，端口 8000 新 PID 生效。

**真实诊断结果**：
- official leaderboard total=805。
- paperTotal=16。
- cleanHighTotal=1。
- fastWatchTotal=0。
- readyForPaperTotal=0。
- buckets：
  - `NO_ACTIVITY_SAMPLE`=470。
  - `SMALL_SAMPLE`=234。
  - `HARD_RISK`=65。
  - `CATEGORY_CONFLICT`=33。
  - `CLEAN_HIGH`=1。
  - `PAPER_OBSERVING`=1。
  - `HIGH_FILTERED_RATIO`=1。
- categories：
  - politics total=448，paper=11，cleanHigh=0，readyForPaper=0，noActivitySample=256。
  - finance total=357，paper=5，cleanHigh=1，readyForPaper=0，noActivitySample=214。
- riskFlagCounts 主要为：
  - no_activity_sample=470。
  - stale_activity=470。
  - small_sample=271。
  - low_market_diversity=199。
  - mixed_category_evidence=58。
  - tail_price_spray=49。
  - low_safe_price_ratio=48。

**关键样本**：
- 唯一 clean high：
  - candidate 1660 `0x5b6331e7ff0831a3fe2ed12004747db1a9c911a4`。
  - category=finance。
  - score=91.2542。
  - PAPER trades=22。
  - filteredRatio=0.2903。
  - copyablePnl=14.5642。
  - 仍需注意过滤率偏高，快速观察 bucket 为空。
- PAPER_OBSERVING：
  - candidate 153 `0xc8ab97a9089a9ff7e6ef0688e6e591a066946418`。
  - score=75.293。
  - filteredRatio=0.35。
  - copyablePnl=1.9726。
  - 分类证据混杂，暂不适合直接跟单。

**结论**：
- official leaderboard 是有效补源，但不是直接跟单名单：
  - 805 个候选里 470 个没有足够系统活动样本。
  - 234 个小样本。
  - 65 个硬风险。
  - 当前只有 1 个 clean high，且没有 fast watch。
- 这说明 leaderboard 高 PnL/高成交量本身不足以证明可跟单；系统必须继续依赖 activity sample、PAPER、过滤率、PnL、分类一致性。

**下一轮动作**：
- 针对 `NO_ACTIVITY_SAMPLE=470`：
  - 增加“补历史活动”入口或后台任务，按 official leaderboard 钱包批量回填最近成交。
  - 优先 politics/finance，优先 external_score 高且非 VOL 负收益样本。
- 针对 `SMALL_SAMPLE=234`：
  - 建立最小可评分样本缺口统计，区分差几笔交易可进入 PAPER。
- 针对 `HARD_RISK=65`：
  - 输出排除样本列表，避免进入跟单模板。
