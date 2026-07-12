# G4 Loop State

## Control

- Goal: G4 人工控制 Leader 的模型化跟单决策
- Priority: P0 / FIRST PRIORITY
- Mode: Loop Engineering
- Status: ACTIVE
- Current phase: Phase 1 - 标签与数据合同
- Trigger: 当前持久目标持续执行；每轮完成后依据状态文件选择下一项
- Isolation: 当前仓库单执行流；不并行修改相同文件
- Maker: 当前实现迭代
- Checker: 自动测试、数据对账、时间切分验证和运行健康检查
- Goal contract: `docs/goals/G4-model-gated-copy-trading.md`

## Stop Conditions

- 目标契约 8 项完成条件全部有当前证据。
- 未经人工确认，不开放模型拒绝、金额选择或自动 SELL 权限。

## Open

- [x] 已枚举 candidate、过滤、执行、FAILED、未结算和结算的真实数据源与关联键。
- [x] 已量化标签覆盖率、延迟、冲突和不可归属比例。
- [x] 已定义不含未来信息的特征可用时间合同。
- [ ] 建立确定性基线和严格时间切分数据集。

## Done

- [x] G4 已由 PROPOSED 提升为 ACTIVE / P0。
- [x] 已建立独立目标契约、决策合同、六阶段计划和人工权限边界。
- [x] G3 已按人工决定记录为部分交付，未误标完成；现有安全能力继续运行。

## Iteration 0 - 目标切换（2026-07-11）

### Decision

- 用户明确要求进入 G4。
- G3 Phase 5/6 跳过，未实现项保留在 G3 状态，不带入 G4 完成定义。
- G4 Phase 1 从真实标签和关联键审计开始，不直接训练模型。

### Next

- Iteration 1：审计 BridgeTradeRecord、ProcessedTrade、FilteredOrder、CopyOrderTracking、风险决策和结算记录，输出 candidate → decision → execution → settlement 当前关联覆盖率与缺口。

## Iteration 1 - 标签链路与未来信息审计（2026-07-11）

### Objective

证明当前哪些数据可以作为模型输入、过滤标签、执行标签和收益标签，并量化 candidate → decision → execution → settlement 的实际覆盖率。

### Key Findings

- 当前没有账户/配置粒度的统一 candidate 主键；稳定粒度必须是 `leaderId + leaderTradeId + copyTradingId + accountId`。
- Bridge 12,445 条 FAILED 混合人工策略过滤、风险过滤、SELL 安全跳过、资金问题和 UI 执行失败，不能直接作为“坏交易”或亏损标签。
- Bridge 238 条真实 BUY SUCCESS 没有统一 realized PnL 结算标签，只能作为执行成功标签。
- PAPER 4,500 条记录键唯一、无标签冲突；3,208 条 PASSED 全部有 realized PnL。
- PAPER 的 4,500 条 `quote_timestamp` 全部晚于 `event_time`，事后 quote/模拟价格在证明时点可用前必须排除，避免未来信息泄漏。
- G3 风险决策 18 条，仅 3 条有完整输入快照，尚无自然 FINAL/correlation 样本。

### Artifacts

- `docs/goals/G4-phase1-label-data-contract.md`：事件链、数据源、标签语义、特征可用时间和阻断项。
- `scripts/g4_label_coverage.sql`：只读、可重复运行的覆盖率与冲突报告。

### Verification

- 报告在真实 MySQL 成功运行且只执行 SELECT。
- 当前分类：POLICY_FILTER 6,295、RISK_FILTER 2,488、SELL_SAFETY_SKIP 1,249、ACCOUNT_FUNDING 414、UI_EXECUTION_FAILURE 395、其余待结构化 1,604。
- Bridge 历史 `copyTradingId` 覆盖 12,725/12,764；账户 ID 和风险 correlation 各仅 3 条。
- PAPER candidate/trade 唯一键 4,500/4,500，冲突 0。

### Safety Decision

- 不直接训练模型，不把 FAILED 当亏损，不使用事件后 quote。
- G3 人工暂停与硬风控继续运行，G4 尚无任何实盘权限。

### Next

- Iteration 2：V81 建立统一 `model_trade_candidate` 审计表，在任何 deterministic filter 之前写入账户/配置粒度候选；先接 Bridge fallback 与旧直连跟单入口，并验证同一 Leader 成交多配置时各自拥有稳定 candidate ID。

## Iteration 2 - 统一候选 ID（2026-07-11）

### Objective

在任何确定性过滤或 Bridge/直连执行分流之前，为每个 `Leader 成交 + 跟单配置 + 账户` 建立稳定候选，并将同一 ID 贯通现有决策和执行记录。

### Delivered

- V81 新建 `model_trade_candidate`，唯一约束为 `leader_id + leader_trade_id + copy_trading_id + account_id`。
- candidate ID 由唯一粒度确定性生成；重复监听复用同一 ID，多配置产生不同 ID。
- `modelCandidateId` 已进入 Bridge raw payload、G3 组合风险输入快照、`filtered_order` 和旧直连 `copy_order_tracking`。
- 候选在账户启用后、凭证/Bridge 分流以及所有业务过滤之前创建；仅增加审计数据，不改变任何交易决定。
- 覆盖率 SQL 已增加候选唯一性和各下游关联计数。

### Verification

- 后端全量测试通过；候选服务覆盖重复监听与多配置语义。
- Bridge 46 项测试通过，包含 raw payload 和风险请求传播断言。
- Flyway V81 成功应用；候选表及两个下游关联列已在真实 MySQL 验证。
- 后端 `/actuator/health` 为 `UP`；Bridge `/health` 为 `ok` 且 `executor_ready=true`。

### Safety Decision

- 模型仍没有 SKIP、金额或 SELL 权限；G3 Shadow 风险和人工暂停边界不变。
- 不制造测试交易，等待自然候选验证实时覆盖。

### Next

- Iteration 3：建立严格时间切分的确定性基线数据集，只使用 candidate `event_time` 当时可获得的特征；先输出 Crypto、金融、政治各领域覆盖率和不可用原因，不训练模型、不改变交易。
