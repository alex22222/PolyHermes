# G3 Loop State

## Control

- Goal: G3 统一资产与组合风险管理
- Priority: P0 / FIRST PRIORITY
- Mode: Loop Engineering
- Status: ACTIVE
- Current phase: Phase 6 - 回放、Shadow 与启用验收
- Trigger: 当前持久目标持续执行；每轮完成后依据状态文件选择下一项
- Isolation: 当前仓库单执行流；不并行修改相同文件
- Maker: 当前实现迭代
- Checker: 自动测试、构建、数据库对账和运行健康检查
- Goal contract: `docs/goals/G3-unified-asset-risk-management.md`

## Stop Conditions

- 目标契约中的 9 项完成条件全部有证据并通过。
- Phase 1 至 Phase 6 均完成验收。
- 未经人工确认，不启用新的真实资金阈值或执行减仓。

## User Scope Decision

- 2026-07-11：用户明确要求跳过 G3 Phase 5、Phase 6并进入 G4。
- 2026-07-11：用户后续明确恢复 G3 Phase 5/6，主动开发重启；真实 SELL 和硬阈值仍需逐项人工确认。
- 已完成能力继续运行，但 G3 未满足原完成条件，不标记 COMPLETE。
- 待观察/人工决策部分：至少三天 Shadow、自然结算样本、受审计的收益与回撤历史对比、人工逐项启用硬阈值。
- G3 当前主动执行 Phase 6 Shadow 观察与数据完整性修复；G4 保持独立目标。

## Open

- [ ] 观察并验证下一次北京时间零点后 120 秒窗口的真实 `MIDNIGHT` 快照。
- [ ] 观察下一笔自然发生的 BUY，确认 precheck/final 两阶段审计与真实交易记录关联完整。
- [ ] 下一完整自然日验证账户化每日 BUY 计数从 `INSUFFICIENT_DATA` 转为完整。
- [x] 旧 CLOB 跟单 BUY 已接入 Gateway；当前静态入口审计未发现仍可达的后端 BUY 绕过。
- [x] V79 后风险决策保存完整输入快照并支持确定性重算；V79 前记录明确标记不可完整回放。
- [ ] 将单市场归因覆盖率从 94.3071% 提升到 95% 以上，或保持 `INSUFFICIENT_DATA`。
- [ ] 为 11 个历史/人工 Leader 未归属仓位和 5 个缺失事件标识仓位补充可审计来源；无可靠证据时继续保留 `UNKNOWN`。

## Done

- [x] G3 已提升为项目 P0 第一优先级。
- [x] G3 已从项目总目标中独立为持久目标契约。
- [x] 已定义 Loop Engineering 的发现、实施、验证和记录闭环。
- [x] 已定义六阶段计划、完成条件和真实资金安全边界。
- [x] 已完成资产、余额、持仓与快照的第一轮数据源审计。
- [x] 已用真实账户完成首份资产分项对账基线。
- [x] 已修复纯现金账户不生成每日快照且旧持仓不清理的问题。
- [x] 已增加估值完整性字段，缺失持仓估值不再按零静默生成完整总资产。
- [x] 已分离每日历史快照与盘中最新资产估值，并记录零点采样偏移。
- [x] 已修复 Bridge 单次瞬时空持仓误清理真实镜像的安全回归。
- [x] 已把已结算待赎回价值纳入总资产，并显式区分零值和数据源失败。
- [x] Bridge `/portfolio` 已原子返回钱包、余额和持仓，消除跨页面采集竞态。
- [x] 已建立账户、Leader、领域、事件四层暴露 API 和持仓页总览。
- [x] 四层暴露对无法可靠归属的仓位使用显式 `UNKNOWN`，价值合计不丢失。
- [x] 已通过成交数量容差和金融分类证据，将 Leader 未归属从 13/25 降至 11/25、领域未知从 3/25 降至 0/25。
- [x] 已为 Leader、领域、事件暴露增加归因来源、质量、价值覆盖率和 95% Shadow 门槛。
- [x] 四层暴露已补齐成本、未实现盈亏、首次观察时间、占资时长展示和持仓下钻键。
- [x] 已知 Leader 暴露可直接下钻到按 Leader 筛选的跟单配置；UNKNOWN 不生成伪链接。
- [x] Phase 2 四层组合暴露已通过 25 个真实仓位的价值、成本、盈亏和下钻键对账。
- [x] 已建立 `G3-SHADOW-V1` 版本化组合风险策略、规则明细和幂等审计表。
- [x] BUY Shadow API 覆盖现金储备、单笔、事件、Leader 和领域；SELL 明确走优先退出路径。
- [x] 数据不完整或归因覆盖不足时返回 `INSUFFICIENT_DATA`，不生成伪 PASS。
- [x] Bridge 已在实际跟单金额生成后和最终 UI BUY 前接入同一 Shadow 风险契约。
- [x] Bridge 内部风险接口使用共享密钥认证；本机调用绕过外部代理，具备超时与未来 ENFORCED fail-closed 语义。
- [x] SELL 路径测试证明不调用 BUY 组合风险服务。
- [x] 已建立账户行锁保护的 BUY 并发预占，final 复用 precheck，具备 SUCCESS/FAILED/EXPIRED 生命周期。
- [x] 已加入每日资产亏损和账户化每日 BUY 数量 Shadow 规则；旧记录缺少账户时明确返回数据不足。
- [x] 新 Bridge 成交记录携带账户、跟单配置和风险 correlation，支持交易与风险审计关联。
- [x] Bridge `/execute` 手工 BUY 已接入 precheck/final/complete；手工 SELL 不运行 BUY 风险。
- [x] `G3-SHADOW-V3` 已增加单市场 8% 候选规则，归因不足时保持数据不足。
- [x] 已提供风险决策列表与规则结果完整性回放 API。
- [x] 已将 replay 升级为基于完整输入快照的逐规则确定性重算，并显式区分旧记录不可回放。

## Blocked / Escalated

- 无。

## Iteration 0 - Goal Bootstrap（2026-07-11）

### Objective

把 G3 建立为可以跨轮次持续执行、可验证停止且不会绕过人工资金控制的独立目标。

### Changes

- `PROJECT_GOALS.md`：G3 调整为 P0 第一优先级，G2 转为维护模式，G4 保持未实施。
- `docs/goals/G3-unified-asset-risk-management.md`：新增独立目标契约。
- `G3_LOOP_STATE.md`：新增循环状态、停止条件和 Phase 1 待办。

### Verification

- 目标契约和 Loop 状态文件存在。
- `PROJECT_GOALS.md` 的目标入口链接有效。
- `git diff --check` 通过。

### Next

- Iteration 1：只读审计当前资产账本、快照、余额和持仓估值链路，形成真实基线与首个可测试缺口。

## Iteration 1 - 资产基线与纯现金快照修复（2026-07-11）

### Objective

验证当前资产口径，并修复 Bridge 明确返回空持仓时总资产缺日和幽灵仓位残留的问题。

### Discover

- `BridgePortfolioSyncService` 原先在 `positions.isEmpty()` 时立即退出。
- 结果是纯现金账户无法生成每日资产点，数据库旧持仓也不会被清理。
- 缺失 `currentValue` 当前会按零累加，尚未表达估值未知。
- `DailyAssetSnapshot.dayStartAt` 是日期标签，`capturedAt` 才是真实采集时间；现有记录不是严格零点采样。

### Test First

- 新增 `sync captures cash-only account and clears stale positions when portfolio is empty`。
- 修复前测试以 `WantedButNotInvoked` 失败，证明早退路径未记录资产、未清理旧仓位。

### Changes

- Bridge 明确返回空数组时继续同步账户和余额。
- 记录 `availableBalance + 0` 的纯现金每日资产点。
- 清理该钱包不再存在的旧持仓并更新账户同步时间。
- Bridge 返回非空记录但全部非法时仍保守跳过，避免误删真实持仓。

### Verification

- `BridgePortfolioSyncServiceTest` 5 项通过。
- 后端完整测试通过。
- 后端 `/actuator/health` 返回 `UP`。
- Bridge `/status` 返回 `ready=true`、`logged_in=true`、账户 2、3 条跟单配置。

### Real Asset Baseline

- 钱包：`0x0372…4942`
- Bridge 可用余额：`11.70`
- Bridge 持仓：`25` 个，当前价值合计 `74.37`
- 当前可确认总资产：`86.07`
- 当日数据库快照：`12.90 + 74.21 = 87.11`
- 快照日期标签为北京时间 2026-07-11 零点，但实际 `capturedAt=1783755332000`，约在当天 15:35 采集，因此属于当日首次快照，不是严格零点快照。
- 当前数据库 25 个持仓的 `current_value` 均非空；缺失估值风险来自代码语义，需在下一轮建立显式质量字段。

### Next

- Iteration 2：为资产快照增加估值完整性和已知/未知语义，先写缺失 `currentValue` 不得按零静默计入的失败测试。

## Iteration 2 - 估值完整性与未知持仓语义（2026-07-11）

### Objective

当单个持仓缺失 `currentValue` 时，不再把它按零计入并生成看似完整的总资产。

### Test First

- 新增 DailyAssetSnapshot 测试：1 个未知持仓时 `totalAssets=null`、`unknownPositionCount=1`、状态为 `INCOMPLETE`。
- 新增 Bridge 同步测试：已知持仓价值进入小计，未知持仓单独计数。
- 修改生产代码前测试编译失败，证明原模型没有估值完整性字段。

### Changes

- V73 将 `total_assets` 改为可空，并增加：
  - `unknown_position_count`
  - `valuation_status`
  - `snapshot_type`
- 完整估值继续保存余额加持仓价值。
- 不完整估值保存已知余额和已知持仓小计，但 `totalAssets=null`。
- API DTO 返回质量字段。
- 持仓页对不完整点断开折线，并显示未知估值持仓数量。
- 页面标题从误导性的“每日总资产（00:00）”调整为“每日总资产快照”。

### Verification

- `DailyAssetSnapshotServiceTest` 与 `BridgePortfolioSyncServiceTest` 通过。
- 后端完整测试和 `bootJar` 通过。
- 前端 TypeScript 与生产构建通过。
- `git diff --check` 通过。
- 本地后端已替换为新 PID `15036`，`/actuator/health=UP`。
- Flyway V73 在真实数据库执行成功。
- 表结构确认 `total_assets` 可空，三个质量字段存在。
- 既有快照被兼容标记为 `COMPLETE / DAILY_FIRST_SUCCESS`。

### Runtime Safety

- 未修改跟单配置或资金阈值。
- 未触发 BUY、SELL 或减仓。
- Bridge 保持 `ready=true`、`logged_in=true`、账户 2、3 条配置。

### Next

- Iteration 3：设计并实现真正的北京时间零点快照与盘中风险快照分离，确保日线不再使用任意时刻的首次同步冒充零点。

## Iteration 3 - 零点证据、盘中估值与空持仓安全确认（2026-07-11）

### Objective

分离每日历史资产点和盘中风险资产，并让每个日线点能够证明自己距北京时间零点的实际偏移。

### Test First

- 新增零点后 10 秒采样测试，要求类型为 `MIDNIGHT`、偏移为 `10000ms`。
- 新增 15:35 采样测试，要求类型为 `DAILY_FIRST_SUCCESS`、偏移为 `56100000ms`。
- 新增盘中最新资产落库测试。
- 新增余额未知测试，要求状态为 `BALANCE_UNKNOWN` 且不生成日线点。
- 真实运行发现单次瞬时空持仓误清理后，追加连续两次空持仓确认测试；修复前测试失败。

### Changes

- V74：
  - 日快照增加 `capture_offset_ms`。
  - 新增 `current_asset_valuation` 盘中最新资产表。
- V75：盘中余额允许为空，显式保存 `BALANCE_UNKNOWN`。
- 北京时间零点后 120 秒内的首个成功采样标记为 `MIDNIGHT`，并保留实际偏移。
- 超出窗口的首个点只能标记为 `DAILY_FIRST_SUCCESS`。
- 每次可信持仓同步均更新盘中资产；余额未知时总资产为空，供硬风控 fail-closed。
- 持仓页 Tooltip 展示采样类型、实际时间或零点偏移。
- 纯现金状态必须满足余额可用且连续两次空持仓；单次空响应不得清理持仓镜像。

### Runtime Incident and Correction

- 新代码首次运行时，Bridge 在两次正常返回 25 个持仓后瞬时返回空数组。
- 单次空数组规则错误清理了 25 条 `bridge_position_snapshot`。
- 未触发交易，随后从 Bridge 真实持仓恢复全部 25 条镜像。
- 空持仓规则已改为连续两次确认，并由回归测试覆盖。

### Verification

- 后端完整测试与 `bootJar` 通过。
- 前端 TypeScript 与生产构建通过。
- `git diff --check` 通过。
- Flyway V74、V75 在真实数据库执行成功。
- 后端已确保只有一个实例：PID `50156`，`/actuator/health=UP`。
- 真实持仓镜像：25 条，未知估值 0。
- 真实盘中资产：余额 `11.70`，持仓价值 `74.37`，总资产 `86.07`，状态 `COMPLETE`。
- 历史日快照回填偏移 `56132000ms`，继续保持 `DAILY_FIRST_SUCCESS`，没有冒充零点。

### Runtime Safety

- 未修改任何真实资金阈值。
- 未触发 BUY、SELL 或减仓。
- 单次 Bridge 空响应不再被视为清仓证据。

### Next

- Iteration 4：补齐已结算待赎回资产来源与字段，使总资产从“余额 + 开放持仓”升级为“余额 + 开放持仓 + 待赎回”。

## Iteration 4 - 待赎回资产与原子 Portfolio 估值（2026-07-11）

### Objective

将已结算待赎回资产纳入总资产，并区分“确实为零”和“数据源失败”。

### Discover

- 原有赎回汇总只筛 `currentPositions`，结算后进入历史列表的仓位会被遗漏。
- Bridge 只读仓位原先全部强制 `redeemable=false`。
- 后端分开抓 `/portfolio` 和 `/balance` 时，持仓成功但余额经常不可用，分项时间也不一致。

### Test First

- 新增待赎回估值服务测试：成功时按获胜份额 1:1 汇总；异常时返回 `UNKNOWN` 而不是零。
- 新增资产服务测试：完整时把待赎回加入总资产；来源失败时 `totalAssets=null` 且状态为 `REDEEM_VALUE_UNKNOWN`。
- 新增赎回汇总测试：当前与历史列表合并，并对同一结算仓位去重。
- 新增原子 portfolio 测试：后端优先使用同一响应中的钱包和余额，不再额外请求。

### Changes

- 新增 `PendingRedeemValuationService`，读取 Data API `redeemable=true`，成功值缓存 60 秒。
- V76 为日快照和盘中估值增加：
  - `pending_redeem_value`
  - `redeemable_position_count`
  - `redeem_valuation_status`
- 完整总资产口径升级为余额 + 开放持仓 + 待赎回。
- 待赎回来源失败时整体状态为 `REDEEM_VALUE_UNKNOWN`，总资产不生成假值。
- `RedeemablePositionSummaryCalculator` 同时读取当前和历史结算仓位并去重。
- Bridge `/portfolio` 在同一锁和同一页面上下文返回钱包、余额和持仓。
- 后端优先消费原子 portfolio 数据，消除第二次余额抓取竞态。
- 持仓页 Tooltip 展示待赎回价值、数量或未知状态。

### Verification

- 新增及相关定向测试通过。
- 后端完整测试与 `bootJar` 通过。
- Bridge Python 编译通过，相关 45 项测试通过。
- 前端 TypeScript 与生产构建通过。
- `git diff --check` 通过。
- Flyway V76 在真实数据库执行成功。
- Bridge `/portfolio` 实测原子返回：钱包 `0x0372…4942`、余额 `11.70`、25 个持仓。
- 真实待赎回：0 个、价值 `0`、状态 `COMPLETE`。
- 真实开放持仓价值：`74.56`。
- 真实完整总资产：`86.26`。
- 后端 PID `80844`，健康 `UP`；Bridge ready/login 正常且 `last_error=null`。

### Runtime Safety

- 只查询待赎回资产，没有执行赎回。
- 未修改真实资金阈值。
- 未触发 BUY、SELL 或减仓。

### Phase Decision

- Phase 1 的资产口径和数据可信度实现已完成。
- 下一次真实零点窗口仍需时间性验证，保留在 Open 中持续观察。
- 主执行流进入 Phase 2，不等待零点观察阻塞组合暴露建设。

### Next

- Iteration 5：建立账户层暴露快照和 Leader/领域/事件归属基础，所有无法可靠归属的仓位必须进入 `UNKNOWN`，不得静默遗漏。

## Iteration 5 - 四层暴露基础与 Bridge 完整性证据（2026-07-11）

### Objective

建立账户、Leader、领域和事件四层组合暴露，并保证未知归属不会从合计中消失。

### Runtime Discovery

- Bridge 页面曾连续两次瞬时返回空列表，证明“连续两次为空”仍不能作为清仓证据。
- Polymarket Data API 对 Bridge EOA 和代理地址都返回 0，但 Polymtrade 页面真实有 25 个持仓，不能作为托管账户的独立清仓或待赎回证据。

### Safety Correction

- Bridge 抓取器新增：
  - `portfolio_complete`
  - `empty_state_confirmed`
  - 页面 `redeemable` 行识别
  - 页面待赎回价值和数量
- 只有有效持仓行或明确“暂无持仓”UI 才认为 portfolio 完整。
- 空列表缺少明确 UI 完成态时，后端永不清理旧持仓。
- 后端优先使用 Bridge 页面待赎回证据，不再把托管账户的链上地址零结果当成确定值。

### Test First

- 新增未确认空 portfolio 回归测试：连续调用也不得删除旧持仓。
- 新增四层暴露测试：一个已归属仓位和一个未知仓位必须分别进入正常桶和 `UNKNOWN` 桶。
- Leader 暴露按成功成交记录中的 Leader 净数量比例分摊，不简单归给最后一个 Leader。

### Changes

- 新增 `PortfolioExposureService`。
- 新增 `/api/accounts/positions/exposures`。
- 新增账户资产摘要、Leader、领域、事件暴露 DTO。
- 领域优先使用市场元数据，缺失时使用现有 Crypto/Sports/Finance/Politics 分类规则。
- 事件缺少 `eventSlug` 时进入 `UNKNOWN`。
- Leader 无法从成功成交账本解释的数量和价值进入 `UNKNOWN`。
- 暴露桶展示价值、占总资产比例和仓位数。
- 持仓页新增“组合风险暴露”总览和归属覆盖率标签。

### Verification

- 暴露服务测试通过。
- Bridge 空仓安全回归测试通过。
- 后端完整测试和 `bootJar` 通过。
- Bridge Python 编译与相关 45 项测试通过。
- 前端 TypeScript 和生产构建通过。
- `git diff --check` 通过。
- 后端 PID `4984`，健康 `UP`。
- Bridge 原子 portfolio 实测：25 个仓位、钱包和余额一致、`portfolio_complete=true`。

### Real Exposure Baseline

- 账户 2：余额 `11.70`，开放持仓 `74.50`，待赎回 `0`，总资产 `86.20`，状态 `COMPLETE`。
- Leader 暴露合计：`74.50`。
- 领域暴露合计：`74.50`。
- 事件暴露合计：`74.50`。
- Leader 未归属：13/25，价值 `33.48011499`。
- 领域未知：3/25，价值 `2.90`。
- 事件未知：5/25，价值 `4.84`。
- 最大领域暴露：Politics `34.48`，占总资产 `40%`。
- 最大事件暴露：Fed July `24.40`，占总资产 `28.3063%`。

### Runtime Safety

- 本轮只读聚合，没有设置或启用任何风险阈值。
- 未触发 BUY、SELL、赎回或减仓。
- 暴露结果中的 UNKNOWN 明确保留在总和内。

### Next

- Iteration 6：降低 Leader、领域和事件 UNKNOWN 覆盖缺口；在覆盖率达到可接受水平前，不让组合硬风控依据不完整归属自动拒单。

## Iteration 6 - 证据化归因收敛与余额采集韧性（2026-07-11）

### Objective

只使用可复核证据降低 UNKNOWN，不用猜测填充历史仓位；同时消除 Bridge 页面切换后余额偶发为空造成的短暂 `BALANCE_UNKNOWN`。

### Discover

- 2 个 Leader 未归属来自页面份额与成功成交份额的微小显示/计算误差，差值分别约 `0.00694` 和 `0.02550` 份。
- 其余 Leader 未归属主要是历史、人工或无 Bridge 成交来源的仓位；Fed 仓位约 29.6/31.5 份无法被现有成交账本解释，不能强行归属。
- 3 个领域未知标题分别包含 PPI、公司 revenue 和 sales，属于可确定的金融市场。
- 5 个事件未知仓位同时缺少 `marketId`、`marketSlug` 和 `eventSlug`，把它们合并为一个 UNKNOWN 桶会制造虚假的事件聚合。
- Bridge 完成持仓页面滚动后，余额读取偶发第一次失败，但独立余额页随后可读到 `11.70`。

### Changes

- Leader 数量归因允许最大 `0.05` 份或 `2%` 的小额尾差；只在全部差额落入容差时，才把完整仓位价值按已知 Leader 比例分配。
- 金融分类回退补充 PPI、股票、业绩、营收、销售额、市值和 IPO 关键词。
- 缺少事件标识的仓位改为独立 `UNKNOWN:<position-key>` 桶，覆盖率仍计为未知，但不再把无关事件合并。
- 前端把所有 `UNKNOWN:*` 桶统一标为未知归属。
- Bridge 原子 `/portfolio` 的余额读取增加最多 3 次、每次间隔 0.5 秒的有界重试；仍无法读取时保持 fail-closed，不沿用旧余额。

### Verification

- 暴露服务与市场分类定向测试通过。
- 后端完整测试和 `bootJar` 通过。
- 前端 TypeScript 和生产构建通过。
- Bridge Python 编译通过。
- `git diff --check` 通过。
- 后端只有一个实例 PID `15011`，`/actuator/health=UP`。
- Bridge `ready=true`、`logged_in=true`、`last_error=null`。
- 最新盘中资产：余额 `11.70`、开放持仓 `74.63`、待赎回 `0`、总资产 `86.33`、状态 `COMPLETE`。

### Real Exposure Result

- Leader 未归属：`13/25 -> 11/25`；未知价值 `33.55687361`。
- 领域未知：`3/25 -> 0/25`。
- 事件未知：仍为 `5/25`，但已拆成 5 个互不混淆的未知事件桶。
- Leader、领域、事件三维合计均与开放持仓价值严格对账，无静默遗漏。

### Safety Decision

- 不根据标题或相似名称猜测 Leader 和事件标识。
- 当前历史 Leader 归属覆盖率仍不足以直接启用 Leader 集中度硬拒单。
- 新订单本身具备 Leader、领域和事件上下文，下一轮应建立“归因来源 + 覆盖率门槛”，先用于 Shadow 决策。

### Next

- Iteration 7：为每个暴露桶增加归因来源与质量，定义账户/Leader/领域/事件的可用覆盖率门槛；覆盖率不足时组合硬风控必须记录 `INSUFFICIENT_ATTRIBUTION` 并保持 Shadow/fail-closed，而不是给出伪精确结论。

## Iteration 7 - 归因质量与价值覆盖率门槛（2026-07-11）

### Objective

把 UNKNOWN 从单纯仓位数量升级为价值覆盖率和归因证据，让后续风险引擎能够判断某个维度是否具备进入 Shadow 的数据质量。

### Test First

- 新增归因来源和质量断言；生产 DTO 尚无字段时测试编译失败。
- 新增 95% 边界测试：恰好达到门槛才标记 `READY_FOR_SHADOW`。
- 新增未知估值测试：即使归因完整，只要持仓价值缺失，所有维度必须为 `VALUATION_INCOMPLETE`，不得进入 Shadow。

### Changes

- 每个暴露桶新增 `attributionSource` 和 `attributionQuality`：
  - Leader：`TRADE_LEDGER / EXACT`
  - 领域：`MARKET_METADATA / EXACT` 或 `TITLE_PATTERN / INFERRED`
  - 事件：`EVENT_SLUG / EXACT`
  - 无证据：`UNKNOWN / UNKNOWN`
  - 聚合桶包含多种来源时：`MIXED / MIXED`
- 每个维度新增已知价值、未知价值、已知价值覆盖率、最低 Shadow 覆盖率、状态和 Shadow 可用性。
- Shadow 数据质量门槛设为已知价值覆盖率 `95%`；该门槛不启用真实拒单。
- 任一持仓估值未知时优先返回 `VALUATION_INCOMPLETE`，覆盖率不得掩盖估值缺口。
- 持仓页显示归因证据及 Leader、领域、事件三张质量卡片。

### Verification

- `PortfolioExposureServiceTest` 全部通过，包括失败复现、95% 边界和未知估值安全用例。
- 后端完整测试和 `bootJar` 通过。
- 前端 TypeScript 和生产构建通过。
- `git diff --check` 通过。
- 新后端唯一 PID `32507`，`/actuator/health=UP`。
- Bridge `ready=true`、`logged_in=true`、`last_error=null`。

### Real Account Evidence

- 当前资产：余额 `11.70`、开放持仓 `74.61`、待赎回 `0`、总资产 `86.31`、状态 `COMPLETE`。
- Leader：已知 `41.03312639`、未知 `33.57687361`、覆盖率 `54.9968%`，状态 `INSUFFICIENT_ATTRIBUTION`。
- 领域：已知 `74.61`、未知 `0`、覆盖率 `100%`，状态 `READY_FOR_SHADOW`。
- 事件：已知 `69.79`、未知 `4.82`、覆盖率 `93.5397%`，状态 `INSUFFICIENT_ATTRIBUTION`。
- Leader、领域、事件价值合计均为 `74.61`，与开放持仓价值一致。

### Safety Decision

- 95% 是进入 Shadow 评估的数据质量门，不是实盘阈值。
- Leader 和事件维度当前禁止成为自动硬拒单依据；领域维度可以进入 Shadow 观察，但仍不执行真实拦截。
- UNKNOWN 继续留在总值中，无证据时不补猜测归属。

### Next

- Iteration 8：完成 Phase 2 展示契约，为暴露桶补齐成本、未实现盈亏、最早占资时间/时长和持仓下钻键；验证聚合值与原始 25 个持仓逐项对账。

## Iteration 8 - 成本、盈亏、占资观察与双向下钻（2026-07-11）

### Objective

完成 Phase 2 展示契约，使账户、Leader、领域和事件暴露不只有当前价值，还能审计成本、未实现盈亏、占资观察时间，并下钻到组成持仓和跟单配置。

### Data Contract

- 成本使用 Bridge 页面直接提供的 `currentValue - pnl`，不从失败订单或猜测成交价拼接。
- 时间字段命名为 `firstObservedAt`：它表示系统首次观察到仓位，不冒充真实建仓时间。
- 任一组成仓位缺少估值或 PnL 时，整个桶的成本和盈亏返回未知，不按零补齐。
- Leader 分摊的当前价值、成本和 PnL 使用同一成交数量比例，保证三个口径一致。

### Test First

- 新增成本、PnL、最早观察时间和持仓键聚合测试；DTO 尚无字段时测试编译失败。
- 新增 PnL 缺失测试，要求账户与桶成本/PnL 均返回 `null`。
- 新增 Leader 下钻标识测试，已知 Leader 返回数据库 `leaderId`，UNKNOWN 必须返回空。

### Changes

- 账户层新增持仓成本、未实现盈亏和最早观察时间。
- 每个暴露桶新增成本、未实现盈亏、最早观察时间和去重后的 `positionKeys`。
- 页面展示成本/PnL 和“已观察占资”时长。
- 点击暴露桶可筛出其实际组成仓位，并可清除下钻筛选。
- 已知 Leader 显示“跟单配置”入口，跳转到 `/copy-trading?leaderId=...`；复用现有跟单页筛选契约。

### Verification

- 新增定向测试通过。
- 后端完整测试和 `bootJar` 通过。
- 前端 TypeScript 和生产构建通过。
- `git diff --check` 通过。
- 新后端唯一 PID `51648`，`/actuator/health=UP`。
- Bridge `ready=true`、`logged_in=true`、`last_error=null`。

### Real Account Reconciliation

- 25 个开放仓位全部具备估值和 PnL。
- 当前账户：余额 `11.70`、开放持仓 `74.44`、持仓成本 `78.38`、未实现 PnL `-3.94`、总资产 `86.14`。
- Leader、领域、事件三个维度分别聚合后：
  - 当前价值均为 `74.44`
  - 成本均为 `78.38`
  - 未实现 PnL 均为 `-3.94`
  - 去重后的下钻持仓键均为 `25`
- 4 个已知 Leader 桶返回真实 `leaderId`；11 个未归属仓位的 UNKNOWN 桶不提供跟单配置入口。

### Phase Decision

- Phase 2 验收通过：无静默遗漏，暴露与资产账本对账，UNKNOWN 独立展示，成本/PnL/占资观察/可信度和下钻均可用。
- `firstObservedAt` 的历史起点是本功能首次建立快照的时间；它会对后续新仓持续提供真实观察时长，但不是交易所级真实建仓时间。
- 主执行流进入 Phase 3，所有风险规则先以 Shadow 运行，不启用真实资金拒单。

### Next

- Iteration 9：建立版本化、可审计的组合风险决策模型和 BUY Shadow 评估 API；首批只计算现金储备、单笔、单事件、单 Leader、单领域门槛，并明确数据不足时的 `INSUFFICIENT_DATA`，不接管真实交易结果。

## Iteration 9 - 版本化 BUY Shadow 风险决策（2026-07-11）

### Objective

建立可重放、可幂等、可审计的组合风险决策内核，在不改变真实交易结果的前提下计算首批候选规则，并证明 SELL 不受 BUY 集中度限制。

### Policy Contract

- 策略版本：`G3-SHADOW-V1`
- 模式：`SHADOW`
- 候选阈值：现金储备最低 20%、单笔最高 2%、事件最高 15%、Leader 最高 10%、领域最高 35%。
- 所有候选阈值只用于 Shadow，`executionAllowed` 始终为 `true`；正式启用前必须回放、观察并由人工确认。
- BUY 返回 `PASS / WOULD_BLOCK / INSUFFICIENT_DATA`；SELL 只返回 `SELL_PRIORITY`，执行层仍需检查真实持仓和幂等。

### Test First

- BUY 命中多个候选阈值时必须记录 `WOULD_BLOCK`，但仍允许执行。
- SELL 不得调用组合暴露或任何 BUY 集中度规则。
- 账户估值缺失时现金和单笔等规则返回 `INSUFFICIENT_DATA`，不得假通过。
- 相同 `requestId` 返回已保存决策，不重新计算或重复写审计。
- 生产模型不存在时测试编译失败，随后实现使全部用例通过。

### Changes

- V77 新增 `portfolio_risk_decision`，保存请求 ID、账户、策略版本、模式、方向、结果、维度标识、请求快照和逐规则 JSON。
- 新增 `/api/risk/portfolio/evaluate`。
- 新增 `PortfolioRiskEvaluationService`，以当前完整资产与四层暴露作为输入。
- 事件、Leader 或领域覆盖未达到 95% 时，对应规则返回 `INSUFFICIENT_DATA`。
- 请求 ID 唯一并支持幂等读取，便于后续 Bridge 重试。

### Verification

- 新增 Shadow、SELL、数据不足和幂等测试全部通过。
- 后端完整测试和 `bootJar` 通过。
- `git diff --check` 通过。
- Flyway V77 在真实数据库执行成功。
- 新后端唯一 PID `63731`，`/actuator/health=UP`。
- Bridge `ready=true`、`logged_in=true`、`last_error=null`。

### Real Shadow Evidence

- $1 BUY：
  - 总结果 `WOULD_BLOCK`，但 `executionAllowed=true`。
  - 下单后现金储备 `12.4015% < 20%`：`WOULD_BLOCK`。
  - 单笔 `1.159% < 2%`：`PASS`。
  - 事件覆盖率 `93.4835%`：`INSUFFICIENT_DATA`。
  - Leader 覆盖率 `54.9787%`：`INSUFFICIENT_DATA`。
  - 下单后金融领域暴露 `32.8581% < 35%`：`PASS`。
- SELL：只返回 `SELL_PRIORITY / PASS`，`executionAllowed=true`。
- 两次评估均写入 `portfolio_risk_decision`，没有调用 Bridge 下单。

### Safety Decision

- 当前账户现金储备低于候选 20% 门槛，这只是 Shadow 证据，不改变现有真实跟单。
- Leader/事件归因未达门槛，不能用于硬拒单。
- 风险内核尚未进入真实下单路径，下一轮只做双层 Shadow 接入。

### Next

- Iteration 10：在后端发送 Bridge 信号前和 Bridge 最终 BUY UI 执行前调用同一 Shadow API；使用稳定请求 ID串联审计，失败时记录风险服务不可用，但在 Shadow 阶段不改变交易结果；SELL 不调用 BUY 规则。

## Iteration 10 - Bridge 双阶段 Shadow 接入（2026-07-11）

### Objective

把组合风险决策接入真实执行链路，并确保使用我们的实际拟下单金额、SELL 不受影响、Shadow 故障不会误拦截，同时为未来强制模式建立 fail-closed 路径。

### Architecture Correction

- PolyHermes 发出的原始 Leader 信号只有 Leader 的成交规模。
- 我们的实际跟单金额要到 Bridge 按具体 `copyTradingId/accountId` 计算后才产生。
- 因此不能在后端发送原始信号前用 Leader 金额冒充风险输入。
- 双阶段检查放在：
  1. Bridge 计算实际 BUY 金额后，进入其他执行规则前的 `precheck`。
  2. 获得交易锁、通过市场时效检查后、即将执行 UI BUY 前的 `final`。

### Test First

- BUY 使用实际 `1.25 USDC`，按 `precheck -> final` 顺序调用两次风险服务。
- Shadow 返回 `WOULD_BLOCK` 时 BUY 仍执行。
- SELL 测试断言风险服务调用次数为 0。
- 风险服务不可用时 Shadow 显式告警并放行；`PORTFOLIO_RISK_ENFORCEMENT_MODE=ENFORCED` 时同样故障 fail-closed。
- 内部接口正确共享密钥免用户 JWT；缺失或错误密钥拒绝。

### Changes

- 新增 Bridge `PortfolioRiskClient`，2 秒超时，使用稳定请求 ID：`bridge:<tx>:<config>:<stage>`。
- 内部 API：`/api/internal/risk/portfolio/evaluate`。
- 请求头：`X-Bridge-Risk-Secret`；后端使用常量时间比较。
- 共享密钥默认复用现有 `JWT_SECRET`，也支持独立 `BRIDGE_RISK_SHARED_SECRET`。
- 本机风险 HTTP 客户端设置 `trust_env=false`，避免 `ALL_PROXY` 劫持 localhost。
- Bridge 状态增加是否配置与模式；metrics 增加检查、不可用、Would Block 和 Denied 计数。
- 后端可用 `marketId` 补齐 `eventSlug`，Bridge 无需猜测事件。

### Runtime Defect and Correction

- 首次无交易运行验证发现 Bridge 继承 `ALL_PROXY=socks5://...`，localhost 请求因缺少 socksio 失败。
- 该失败在 Shadow 中被明确记录并按设计放行，没有触发交易。
- 修复为内部客户端不读取代理环境后，precheck/final 均成功返回真实 Shadow 决策。

### Verification

- 后端认证、风险服务相关测试通过。
- 后端完整测试和 `bootJar` 通过。
- Bridge 全部 41 项测试通过，Python 编译通过。
- `git diff --check` 通过。
- 内部接口错误密钥返回 `code=2001`；正确密钥返回 `SHADOW / executionAllowed=true`。
- 无交易运行验证：precheck/final 两条决策均为 `WOULD_BLOCK`，并解析到 `fed-decision-in-july-181 / finance`；对应 Bridge 交易记录为 0。
- 后端唯一 PID `82349`，健康 `UP`。
- Bridge PID `98459`，ready/login 正常、账户 2、3 条配置、无错误。
- Bridge 状态：`portfolio_risk_configured=true`、`portfolio_risk_mode=SHADOW`。

### Safety Decision

- 当前仍为 Shadow；风险结果不改变真实 BUY。
- 切换到 ENFORCED 后，后端明确拒绝或风险服务不可用都会阻止 BUY。
- SELL 完全不调用 BUY 风险服务，继续由真实持仓与幂等校验保护。
- 下一笔自然 BUY 需要观察实际两阶段审计；不人为发单验证。

### Next

- Iteration 11：增加 BUY 并发预占和关联 ID，使 precheck 创建预占、final 复用而不是重复计入；加入过期释放和成交/失败终态，再补每日订单数与亏损 Shadow 规则。

## Iteration 11 - 并发预占与每日风险口径（2026-07-11）

### Objective

防止多个并发 BUY 基于同一余额和暴露快照分别通过，并补齐可审计的每日资产亏损与每日 BUY 数量候选规则。

### Reservation Contract

- 策略版本升级为 `G3-SHADOW-V2`。
- `correlationId=bridge:<tx>:<config>` 在 precheck 创建一条预占。
- final 复用同一预占并转为 `EXECUTING`，不得重复计算自己的金额。
- 其他 ACTIVE/EXECUTING 预占计入现金储备，并按相同事件、Leader、领域计入对应投影。
- 成交后为 `SUCCESS`，过滤或执行失败为 `FAILED`，孤儿预占 120 秒后为 `EXPIRED`。
- 账户行使用数据库悲观写锁，多个后端实例也必须串行完成同账户预占投影。

### Daily Rules

- `MAX_DAILY_LOSS=5%`：北京时间当日资产基线相对当前总资产的下降比例。
- 基线或当前估值不完整时返回 `INSUFFICIENT_DATA`。
- `MAX_DAILY_BUY_ORDERS=20`：账户已成功 BUY 加当前其他并发预占和本次 BUY。
- 新成交 raw payload 保存 `copyTradingAccountId`、`copyTradingId`、`portfolioRiskCorrelationId`。
- 当天仍存在 V2 前缺少账户 ID 的成功 BUY 时，订单数规则返回 `INSUFFICIENT_DATA`，不报告虚假的低计数。

### Test First

- precheck 在账户锁内创建预占，并按四个口径看到其他预占。
- final 复用 precheck，不重复占资。
- 过期预占在新投影前释放。
- SUCCESS/FAILED 完成接口幂等。
- 北京时间日资产基线计算亏损；不完整基线保持未知。
- 并发预占、6% 日亏损和超过日订单候选值均产生 `WOULD_BLOCK`。
- Bridge BUY 成功/失败调用终态，SELL 仍完全不触碰预占。

### Changes

- V78 新增 `portfolio_risk_reservation`。
- 内部新增 `/api/internal/risk/portfolio/complete`，与 evaluate 使用相同共享密钥。
- Bridge 风险客户端新增终态调用。
- precheck 移到所有现有 BUY 过滤规则通过后，避免为已知会被过滤的信号创建无意义预占。
- 时效失败、风险拒绝、执行异常和执行成功均结束预占。
- Bridge 执行记录新增账户、配置和风险关联字段。

### Verification

- 后端预占、每日指标、风险评估和认证定向测试通过。
- 后端完整测试与 `bootJar` 通过。
- Bridge 全部 42 项测试和 Python 编译通过。
- Flyway V78 在真实数据库执行成功。
- `git diff --check` 通过。

### No-Trade Runtime Evidence

- c1 预占 `$1` 后现金投影为 `12.3986%`。
- c2 再预占 `$2` 后现金投影为 `10.0811%`，证明读取到 c1。
- c1 final 的现金投影仍为 `10.0811%`，证明复用自身且只叠加 c2，没有重复计算 c1。
- c1、c2 均通过完成接口进入 `FAILED`，无 ACTIVE 残留。
- 日资产亏损为 `0.9299%`，状态 `PASS`，基线类型为 `DAILY_FIRST_SUCCESS`。
- 当天旧成功 BUY 缺少账户字段，日订单规则为 `INSUFFICIENT_DATA`。
- 对应 Bridge 交易记录为 0，未发单。
- 后端 PID `31949`，健康 `UP`；Bridge PID `33009`，ready/login 正常且风险模式为 Shadow。

### Safety Decision

- 预占已真实写入并结束，但所有规则仍为 Shadow，不改变 BUY。
- 下一完整自然日才能验证每日账户订单计数的完整性；当前不把缺失历史归属当作 0。
- 尚未覆盖 Bridge 手工 BUY 和后端其他直接 BUY 入口，不能宣称风险引擎不可绕过。

### Next

- Iteration 12：枚举全部 BUY 执行入口，先把 Bridge 手工 BUY 接入同一 precheck/final/complete 生命周期，再增加单市场暴露规则和决策查询/回放 API；所有入口覆盖前保持 Shadow。

## Iteration 12 - 手工 BUY、单市场规则与审计查询（2026-07-11）

### Objective

封住 Bridge `/execute` 手工 BUY 绕过路径，加入单市场候选限制，并让风险决策可以查询和验证规则结果完整性。

### BUY Entrypoint Audit

- Bridge Leader `/signal`：已覆盖 precheck/final/complete。
- Bridge 手工 `/execute`：本轮完成覆盖。
- 普通账户 `/api/accounts/orders`：后端直连 CLOB，未覆盖。
- Crypto Tail 自动快路径、慢路径和手工订单：后端直连 CLOB，未覆盖。
- 旧 `CopyOrderTrackingService` 直连 CLOB 跟单路径：未覆盖；Bridge 路由是否完全替代仍需逐调用审计。
- Backtest/Paper Trading：非真钱路径，不进入实盘风险引擎。

### Test First

- 手工 BUY 必须按 precheck/final 顺序检查，并在成功时完成预占。
- 手工 BUY 在未来 ENFORCED 拒绝时不得调用 UI executor，预占进入 FAILED。
- 手工 SELL 不调用 BUY 风险服务。
- Bridge 实际执行 raw payload 保存账户、手工风险 correlation 和真实 BUY 金额。
- 单市场当前暴露与同市场并发预占进入同一规则。
- 决策规则重新归并出的结果必须与保存 outcome 一致；不一致需要显式暴露。

### Changes

- Bridge `_execute_and_record` 的 BUY 分支接入手工风险 precheck/final/complete。
- 手工 PENDING 记录保存真实 `amount_usdc`，不再固定为 0。
- 暴露 API 增加内部 markets 维度及市场归因覆盖率，不改变原四层页面定义。
- 策略升级为 `G3-SHADOW-V3`，新增 `MAX_MARKET_EXPOSURE=8%`。
- 新增：
  - `POST /api/risk/portfolio/decisions`
  - `POST /api/risk/portfolio/replay`
- 当前 replay 范围明确标记为 `RULE_OUTCOME_INTEGRITY`，只验证已保存规则与 outcome 的一致性，不冒充历史输入快照重算。

### Verification

- 手工 BUY/SELL/拒绝测试通过。
- 单市场暴露和风险规则定向测试通过。
- 决策查询与一致性回放测试通过。
- 后端完整测试和 `bootJar` 通过。
- Bridge 全部 45 项测试与 Python 编译通过。
- 前端 TypeScript 和生产构建通过。
- `git diff --check` 通过。

### No-Trade Runtime Evidence

- `g3-iteration12-no-trade` 使用 `G3-SHADOW-V3`，总结果 `WOULD_BLOCK`、`executionAllowed=true`。
- 现金储备规则：`1.0753% < 20%`，`WOULD_BLOCK`。
- 单市场覆盖率为 `94.3071% < 95%`，因此 `MAX_MARKET_EXPOSURE=INSUFFICIENT_DATA`。
- 决策列表成功读取该记录。
- 规则结果回放：stored=`WOULD_BLOCK`、replayed=`WOULD_BLOCK`、consistent=`true`。
- Bridge 交易记录 0，预占记录 0；没有发单。
- 后端 PID `91931`，健康 `UP`；Bridge PID `92530`，ready/login 正常、账户 2、3 条配置。

### Safety Decision

- 手工 Bridge BUY 已不能绕过未来强制风险；SELL 保持优先。
- 单市场归因未达门槛，继续返回数据不足，不降低 95% 门槛换取表面可用。
- 后端仍有多个直连 CLOB BUY 入口未覆盖，Phase 3 不能验收，风险模式继续保持 Shadow。
- 当前 replay 不是历史快照重算；完整回放需先持久化风险输入上下文。

### Next

- Iteration 13：建立后端统一 BUY Risk Gateway，先接入普通账户 `/orders` 和 Crypto Tail 手工订单，再逐步迁移自动 Crypto Tail 与旧跟单直连路径；Gateway 必须复用同一预占、SELL 优先和终态生命周期。

## Iteration 13 - 后端 BUY Risk Gateway 与 Crypto Tail 手工订单（2026-07-11）

### Objective

建立后端统一 BUY Risk Gateway，并让 Crypto Tail 手工真钱 BUY 复用 PRECHECK、FINAL 和终态预占生命周期。

### Discovery Correction

- `/api/accounts/orders` 是历史订单查询接口，不是普通账户下单入口。
- `AccountService` 中发现的直连 CLOB 实现是 SELL，继续保持 SELL 优先，不接 BUY 限制。
- 因此本轮不为不存在的普通账户 BUY 路由增加代码，并修正入口审计。

### Test First

- PRECHECK 与 FINAL 使用不同幂等 requestId，但共享同一个 correlationId。
- 未来 ENFORCED 返回 `executionAllowed=false` 时抛出明确拒绝且结束预占。
- CLOB 成功或失败均进入对应终态，不留下 ACTIVE 预占。

### Changes

- 新增 `BackendBuyRiskGateway`，集中封装后端 BUY 的两阶段评估和终态完成。
- Crypto Tail 手工订单使用真实 `price * size` 金额，先预检、签名后最终检查、CLOB 返回后完成预占。
- 风险归因带入账户、事件 slug、市场标题和 `crypto` 类别；没有可靠 marketId 时继续让单市场规则返回数据不足。
- correlationId 带随机后缀，允许失败后安全重试，同时保持单次执行内幂等。

### Verification

- Gateway 3 项定向测试通过。
- 后端全量测试与 `bootJar` 通过。
- Bridge 45 项测试通过。
- 前端 TypeScript 与生产构建通过。
- `git diff --check` 通过。

### No-Trade Runtime Evidence

- 后端已使用新构建干净重启，PID `11690`，8000 端口监听且健康状态 `UP`。
- Bridge 保持 ready/login 正常，账户 2、3 条配置，组合风险配置有效且模式为 Shadow。
- 本轮未调用 Crypto Tail 手工订单，没有为验证而发送真钱交易。

### Safety Decision

- 风险模式仍为 Shadow，本轮不改变真钱交易是否允许。
- 未用手工真钱订单做运行验证；入口行为由单元测试覆盖，部署后仅做健康与无交易检查。
- Crypto Tail 自动快慢路径与旧跟单 CLOB 路径仍可绕过，Phase 3 不能验收。

### Next

- Iteration 14：把 Crypto Tail 自动快路径和慢路径迁移到同一 Gateway，统一真实金额、事件归因和失败终态；随后审计旧跟单直连路径是否仍有可达调用方。

## Iteration 14 - Crypto Tail 自动 BUY 风控收口（2026-07-11）

### Objective

让 Crypto Tail 自动快路径与慢路径在签名和 CLOB 发单前经过统一 BUY Risk Gateway，清除两条真钱 BUY 绕过路径。

### Discovery

- 快路径复用周期预置账户、凭证与 CLOB 客户端，金额在余额/策略比例计算后确定。
- 慢路径在触发时重新加载账户与余额，之后使用同一金额和订单语义。
- 两条路径最终调用同一个 `submitOrderAndSaveRecord`，适合集中执行 FINAL 和终态处理。

### Changes

- 提取两条路径共用的 `signAndSubmitAutoOrder`，不改变价格、数量、触发条件或账户选择。
- 使用计算完成后的真实 `amountUsdc` 做 PRECHECK；签名完成后、CLOB 调用前做 FINAL。
- 成功订单完成 `SUCCESS`，CLOB 拒绝、异常、签名失败或风险拒绝完成 `FAILED`。
- 风险归因带入账户、事件 slug、市场标题和 `crypto` 类别；不伪造未知 marketId。
- 自动执行 correlationId 带策略、周期和随机后缀，单次链路幂等且失败后可重试。

### Safety Decision

- 风险模式继续保持 Shadow，不改变自动策略当前是否发单。
- 没有为验证制造自动触发或真钱订单。
- 旧 `CopyOrderTrackingService.createOrderWithRetry` 仍有来自三类 WebSocket 监听器的可达调用链，是当前最后一个已知后端 BUY 绕过入口。

### Verification

- 后端全量测试与 `bootJar` 通过。
- Bridge 45 项测试通过。
- 前端 TypeScript 与生产构建通过。
- 定向 Gateway 生命周期测试继续通过。

### No-Trade Runtime Evidence

- 新构建已部署，后端 PID `20983`，8000 端口监听且健康状态 `UP`。
- Bridge ready/login 正常，账户 2、3 条配置，组合风险模式保持 Shadow。
- 部署验证未制造 Crypto Tail 触发，未发送真钱订单。

### Next

- Iteration 15：沿 `processTrade` 到 `createOrderWithRetry` 区分 BUY/SELL 和真实金额，在旧跟单 BUY 接入 Gateway；保留 SELL 优先，并确认 Bridge 与旧监听器是否会重复执行同一 Leader 成交。

## Iteration 15 - 旧跟单直连 BUY 与双引擎去重审计（2026-07-11）

### Objective

封住最后一个已知后端直连 CLOB BUY 绕过入口，并确认同一后端处理链不会同时直连 CLOB 和转发 Bridge。

### Discovery

- `CopyOrderTrackingService.processTrade` 仍由链上、Activity 和旧 WebSocket 三类监听器调用，直连路径可达。
- 无 CLOB 凭证且符合 Bridge 条件的账户走 Bridge fallback 后立即 `continue`；有凭证账户走直连，不触发 fallback。
- SELL 复用 `createOrderWithRetry`，但必须继续跳过 BUY 组合限制。
- 全仓 `createOrder` 静态审计只剩 Account SELL、Crypto Tail 已覆盖路径、旧跟单本路径，以及一个无调用方的占位 helper。

### Changes

- 旧跟单 BUY 以最终调整价格乘最终数量作为真实风险金额。
- 风险上下文包含账户、conditionId、市场标题、event slug、Leader 地址和领域。
- PRECHECK 在签名前执行，FINAL 在首次 CLOB 调用紧前执行；重试属于同一预占执行，不重复增加并发金额。
- 成功或最终失败均关闭预占；SELL 调用不携带风险上下文，保持 SELL 优先。
- 更新入口审计，记录当前无已知可达后端 BUY 绕过，并明确这只是 Enforced 的必要条件之一。

### Dual-engine Deduplication

- 后端按 Leader 与交易 ID 去重多监听源。
- Bridge fallback 客户端按交易哈希做内存和数据库去重，Bridge recorder 在执行前再次去重。
- 不同账户若人为配置同一 Leader，仍会各自执行，这是账户级配置语义，不合并为一笔。

### Verification

- 后端全量测试与 `bootJar` 通过。
- Gateway 拒绝路径验证预占进入 `FAILED`。
- 全仓原始 `createOrder` 静态审计完成，未发现未分类的可达 BUY 调用点。
- 新构建已部署，后端 PID `30644`，健康状态 `UP`；Bridge ready/login 正常且风险模式为 Shadow。
- 部署验证未发送真钱订单。

### Next

- Iteration 16：增加执行入口契约测试，防止未来新增 `createOrder` BUY 调用绕过 Gateway；随后转向完整风险输入快照与真正历史重算回放，为 Shadow 样本验收做准备。

## Iteration 16 - BUY 执行入口回归护栏（2026-07-11）

### Objective

把一次性人工入口审计变成自动测试，阻止未来新增原始 CLOB BUY 调用而未接入 Gateway。

### Changes

- 新增 `BuyExecutionEntrypointContractTest`，枚举所有 `clobApi.createOrder` 源文件。
- 已分类集合之外出现新调用点时测试直接失败，并提示先接入 `BackendBuyRiskGateway`。
- Crypto Tail 和旧跟单文件必须保留 FINAL 调用；AccountService 当前执行点必须保持 SELL。
- 无调用方的 `createSignedOrder` 占位 helper 一旦出现调用方，测试会要求重新审计。

### Verification

- 入口契约测试与 Gateway 生命周期测试通过。

### Next

- Iteration 17：持久化风险评估的完整输入快照（资产、暴露、每日指标和并发预占），将 replay 从规则结果校验升级为原始输入的确定性重算。

## Iteration 17 - 完整风险输入快照与确定性 Replay（2026-07-11）

### Objective

让风险决策可以使用评估当时的原始输入重算全部规则，而不是从已保存规则状态反推 outcome。

### Test First

- 同一输入快照重复计算必须产生完全相同的规则列表和 outcome。
- 估值不完整的快照重算后仍为 `INSUFFICIENT_DATA`，不得因当前数据改善而改变历史结论。
- 新记录同时比较重算 outcome 与逐规则列表；旧记录无快照时明确不可回放。

### Changes

- V79 为 `portfolio_risk_decision` 增加 `input_snapshot_json LONGTEXT`。
- 新增纯计算 `PortfolioRiskPolicy`，实时评估和历史 replay 复用同一套 V3 规则实现。
- 快照保存规范化请求、已解析领域/事件、账户总资产、余额、完整四层暴露及覆盖率、每日亏损/订单指标、并发预占投影和策略版本。
- replay 范围升级为 `FULL_INPUT_SNAPSHOT`；只有 outcome 和所有规则均一致才返回 `consistent=true`。
- V79 前记录返回 `INPUT_SNAPSHOT_UNAVAILABLE`，不再进行容易误解的规则结果归并。
- 未支持的策略版本拒绝 replay，避免跨版本误算。

### Verification

- 纯策略确定性、实时持久化和 replay 定向测试通过。
- 后端全量测试与 `bootJar` 通过。
- Flyway V79 在真实数据库执行成功，运行决策快照长度 `29633` 字节，策略版本 `G3-SHADOW-V3`，估值状态 `COMPLETE`。
- 无交易决策 `g3-iteration17-snapshot-1783771299` 保存 outcome=`WOULD_BLOCK`；完整快照 replay 得到相同 outcome、8 条规则且 `consistent=true`。
- 旧决策 `g3-iteration12-no-trade` 返回 `INPUT_SNAPSHOT_UNAVAILABLE`、`snapshotAvailable=false`。
- 该验证产生 0 条预占、0 条 Bridge 交易记录，没有发单。
- 后端 PID `40142`、健康 `UP`；Bridge ready/login 正常且保持 Shadow。

### Safety Decision

- replay 能力已经可信，但单条人工无交易样本不足以通过 Shadow 验收。
- 风险模式继续保持 Shadow；Enforced 仍需自然交易样本、完整自然日订单计数和人工确认。

### Next

- Iteration 18：建立 Shadow 决策样本统计与验收报告，按规则统计 PASS/WOULD_BLOCK/INSUFFICIENT_DATA、输入完整率、replay 一致率和执行结果关联率，形成可量化的 Enforced 准入门槛。

## Iteration 18 - Shadow 量化验收报告（2026-07-11）

### Objective

把 Enforced 准入从人工抽查变成可重复计算的量化门槛，同时保持“只报告、不自动启用”。

### Gates

- BUY 样本不少于 100 条。
- FINAL 样本不少于 20 条。
- 输入快照时代观察跨度不少于 168 小时。
- 输入快照覆盖率 100%。
- 完整 replay 一致率 100%。
- 无 `INSUFFICIENT_DATA` 的 BUY 比例不低于 95%。
- FINAL 与预占终态关联率 100%。

### Test First

- 少样本、归因不足时报告必须列出 blocker，不能误报 ready。
- 100 条 BUY、20 条 FINAL、168 小时跨度且所有完整率达标时，才允许 `readyForEnforcedReview=true`。
- V79 前旧记录不进入快照时代分母，但数量必须显式披露。

### Changes

- 新增 `POST /api/risk/portfolio/shadow-report`。
- 报告包含样本窗口、旧记录排除数、BUY/SELL 数量、逐规则 PASS/WOULD_BLOCK/INSUFFICIENT_DATA 分布、快照率、replay 一致率、FINAL 终态关联和明确 blocker。
- readiness 只代表“可以提交人工 Enforced 评审”，不会修改运行模式或阈值。

### Verification

- 未达标与全达标两类门槛测试通过。
- 后端全量测试与 `bootJar` 通过。
- 当前真实报告：排除 15 条旧决策，快照时代 1 条 BUY；快照覆盖率 100%，replay 一致率 100%。
- 当前完整评估 BUY 为 0，FINAL 为 0，观察跨度 0 小时，`readyForEnforcedReview=false`。
- 当前 blocker：BUY 1/100、FINAL 0/20、观察 0/168 小时、完整 BUY 0/95%、FINAL 终态关联暂无样本。
- 后端 PID `49804`、健康 `UP`；Bridge ready/login 正常且模式为 Shadow。

### Safety Decision

- 当前明确不具备 Enforced 评审条件，系统继续 Shadow。
- Phase 3 的自然样本观察继续积累；不等待时间流逝，工程循环并行进入 Phase 4。

### Next

- Iteration 19：审计现有持仓字段与真实历史样本，定义重复、真对冲、伪对冲、相关、长期占资和未知六类确定性关系模型；先分别建立 Crypto、金融、政治规则测试，再提供只读识别 API。

## Iteration 19 - 六类持仓关系只读识别（2026-07-11）

### Objective

以 condition/event、标准化实体、方向和领域时间窗口识别重复、真对冲、伪对冲、相关、长期占资和未知关系，不把文本相似或相反 outcome 直接当作完全抵消。

### Rules

- `DUPLICATE`：同 condition、同 outcome。
- `TRUE_HEDGE`：同 condition 且仅限已验证二元互补 YES/NO 或 UP/DOWN；同时披露重叠价值和未对冲价值。
- `PSEUDO_HEDGE`：同 condition 的不同 outcome，但不是已验证二元互补。
- `RELATED`：同 event 的不同 condition，或同领域、同标准化实体且结算窗口接近。
- `LONG_OCCUPIED`：Crypto 超过 1 天、Sports 超过 14 天、Finance/Politics 超过 30 天。
- `UNKNOWN`：缺少 condition、event 或领域元数据；未知仓位禁止参与跨 condition 相关推断。

### Domain Rules

- Crypto：BTC/ETH/XRP/SOL 标准化实体，窗口 24 小时。
- Finance：Fed 利率、原油和股票代码实体，窗口 90 天。
- Politics：党派、国家实体，窗口 180 天。
- Sports：同 event 优先；跨 event 只在标准化实体和 30 天窗口同时满足时相关。

### Test First

- 同二元 condition 相反 outcome 必须是真对冲且披露未对冲价值。
- 同 condition 同 outcome 必须是重复。
- 不同 XRP 短周期市场只能是相关，不能当对冲。
- 多结果市场的不同 outcome 必须是伪对冲。
- 缺少确定性身份必须保持 UNKNOWN，且不能通过实体关键词加入跨市场关系。
- 超过领域阈值的单仓位必须进入长期占资。

### Changes

- 新增纯计算 `PortfolioRelationClassifier`。
- 新增只读 `POST /api/risk/portfolio/relations`，返回原始仓位、关系、类型计数和关联价值。
- 识别结果不暂停 BUY、不生成 SELL，也不改变风险阈值。

### Runtime Evidence

- 真实账户 2 当前 27 个仓位。
- 识别出 2 组 `TRUE_HEDGE`：2026 参议院控制权 YES/NO，以及 2026 年 7 月 Fed 利率不变 YES/NO。
- 参议院重叠价值 `$9.91`、未对冲 `$8.19`；Fed 重叠价值 `$1.32`、未对冲 `$23.08`，证明相反 outcome 未被全额抵消。
- 识别出 7 组领域相关关系，关联价值 `$5.11`。
- 5 个缺失 condition/event 的仓位保持 UNKNOWN，价值 `$4.52`，修正前错误加入的 5 个跨市场关系已清除。
- 当前没有满足时间阈值的长期占资仓位，也没有同 outcome 重复或非二元伪对冲。

### Verification

- 六类规则与未知隔离定向测试通过。
- 后端全量测试与 `bootJar` 通过。
- 新构建已部署，后端 PID `61434`、健康 `UP`；Bridge 保持正常和 Shadow。
- 真实核对只调用只读 API，没有触发交易、暂停或减仓。

### Next

- Iteration 20：在持仓页面加入关系风险面板，展示类型、关联价值、未对冲价值、置信度和下钻仓位；为 Phase 5 的人工暂停与减仓预览保留明确入口，但本轮仍不执行任何处置。

## Iteration 20 - 持仓关系风险面板（2026-07-11）

### Objective

把 Phase 4 识别结果放到持仓管理页面，让人可以理解关系证据并下钻原始仓位，同时不产生任何交易副作用。

### Changes

- 前端增加完整关系响应类型和 `/risk/portfolio/relations` 客户端。
- 持仓页按当前账户加载关系，展示六类标签、组数、关联价值、实体、置信度、理由和未对冲价值。
- 点击“查看 N 个仓位”复用现有仓位下钻过滤，定位组成关系的原始仓位。
- “人工处置（待启用）”保持禁用，并明确 Phase 5 必须先预览、再逐笔确认，不直接调用 SELL。
- 表格使用横向滚动，移动端不扩大页面整体宽度。

### Verification

- 前端 TypeScript 与生产构建通过。
- 浏览器真实页面显示 2 组真对冲、7 组相关、5 个未知；真对冲逐组显示关联和未对冲价值。
- 浏览器点击参议院真对冲“查看 2 个仓位”后，页面出现“正在下钻查看 2 个仓位”，证明交互关联正确。
- 390×844 移动端视口下 body 宽度和 scrollWidth 均为 390；关系表在卡片内部横向滚动，没有撑破页面。
- 浏览器验证只读，没有点击卖出、赎回或任何外部链接。

### Safety Decision

- Phase 4 识别与页面展示完成首轮闭环，但典型历史样本仍需随新仓位持续验证。
- 人工处置仍未启用，真实 SELL 必须继续走现有逐笔确认。

### Next

- Iteration 21：进入 Phase 5，先实现账户级“暂停新增 BUY”持久开关和审计记录；该开关必须在所有 BUY Gateway 入口生效、不得阻断 SELL，并提供页面显式恢复操作。

## Iteration 21 - 账户级人工暂停 BUY（2026-07-11）

### Objective

提供账户级持久人工硬开关，暂停所有新增 BUY，同时保持 SELL、赎回和安全退出不受影响；暂停和恢复必须可审计。

### Test First

- 暂停必须填写原因，并保存状态和 PAUSE 审计事件。
- 人工暂停时风险结果必须包含 `ACCOUNT_BUY_PAUSED=WOULD_BLOCK` 且 `executionAllowed=false`，即使候选阈值仍处于 Shadow。
- 其他规则继续计算并保存，不能因暂停而丢失组合风险证据。
- SELL 继续只返回 `SELL_PRIORITY` 且允许执行。

### Changes

- V80 新增 `portfolio_buy_control` 与 `portfolio_buy_control_audit`。
- 新增查询与更新 API：`/api/risk/portfolio/buy-control`、`/buy-control/update`；操作人来自已验证 JWT。
- 风险输入快照增加人工控制状态，策略升级为 `G3-SHADOW-V4`；V3 快照仍可按原规则 replay。
- `PortfolioRiskEvaluationService` 在 Bridge 内部接口和所有后端 Gateway 的共同层读取控制状态，避免执行器绕过。
- 持仓关系面板显示当前 BUY 状态；暂停必须填写原因并确认，恢复也必须二次确认。

### Verification

- 后端全量测试与 `bootJar`、Bridge 45 项测试、前端生产构建通过。
- Flyway V80 成功；真实控制表和审计表均为 0，证明默认未暂停且验证未写入状态。
- 账户 2 查询结果 `paused=false`、审计 0；无交易 BUY EVALUATE 正常允许且没有暂停规则。
- EVALUATE 产生 0 预占、0 Bridge 交易记录。
- V4 SELL 无交易验证返回 `SELL_PRIORITY`、`executionAllowed=true`。
- 浏览器显示“新增 BUY 正常”和唯一可用的“暂停新增 BUY”按钮；验证未点击按钮。
- 后端 PID `90584`、健康 `UP`；Bridge ready/login 正常且保持 Shadow。

### Safety Decision

- 本轮没有暂停或恢复任何真实账户，也没有发送 BUY/SELL。
- 暂停是人工硬开关；候选集中度阈值仍未启用 Enforced。

### Next

- Iteration 22：实现人工减仓预览，只计算建议卖出数量和处置前后现金、市场/事件/Leader/领域暴露变化；预览不调用交易接口，并生成可过期、可审计的确认草案。

## Paused Maintenance A - 历史快照回放兼容（2026-07-11）

### Trigger

- 自动持续目标要求核对 G3，但用户已明确跳过 Phase 5/6 并进入 G4。
- 本轮只修复运行中发现的阻断性审计缺陷，不恢复人工减仓开发，也不启用真钱阈值。

### Discovery

- 最新 7 天 Shadow 报告有 5 个快照样本，快照覆盖率 100%，但 replay 一致率仅 80%。
- 唯一失败样本 `g3-iteration17-snapshot-1783771299` 是 V80 人工暂停字段加入前的合法 G3-SHADOW-V3 快照。
- Gson 对缺失的非空 Kotlin `buyControl` 字段写入运行时 null，`PortfolioRiskPolicy` 直接解引用并令 replay API 返回 500。

### Test First and Fix

- 新增“人工暂停字段出现前的快照仍可完整重放”回归测试；修复前稳定复现 NullPointerException。
- `PortfolioRiskInputSnapshot.buyControl` 改为兼容历史缺失值；策略评估只在该字段缺失时使用未暂停默认值。
- 新生成决策仍显式保存当前人工暂停快照，`executionAllowed` 对真实暂停继续 fail-closed。

### Verification

- 风险回放、策略和 Shadow 报告定向测试通过；后端全量测试与 bootJar 通过。
- 真实历史样本重放恢复为 `FULL_INPUT_SNAPSHOT / consistent=true`。
- 最新 Shadow：快照覆盖 100%、replay 一致率 100%、FINAL 终态关联 100%。
- 后端 PID `44725` 且健康 `UP`；Bridge `ok / executor_ready=true`；`git diff --check` 通过。

### Remaining Gates

- BUY 样本 4/100、FINAL 1/20、观察 0.79/168 小时、完整评估 BUY 0%/95%。
- G3 保持 `PARTIAL / PAUSED BY USER`，不进入 Enforced，不恢复已跳过的 Phase 5/6。

## Iteration 22 - 人工减仓预览草案（2026-07-11）

### Authorization

- 用户明确恢复 G3 Phase 5/6。
- 本轮授权范围仅为只读预览与草案审计；未授权自动 SELL 或启用真钱硬阈值。

### Objective

为关系风险中的单个真实持仓生成可过期的减仓预览，展示处置前后现金、持仓价值、总资产和四层暴露，但不调用任何交易接口。

### Delivered

- V82 新建 `portfolio_reduction_draft`，保存创建人、数量、完整输入输出快照、状态和 10 分钟过期时间。
- 预览仅允许当前镜像中的真实持仓，数量必须大于 0 且不超过可用数量。
- 持仓或账户估值不完整时拒绝生成伪精确预览。
- 按当前镜像价值计算预估回收现金；多 Leader/多仓位分配明确标记 `ESTIMATED_PRO_RATA`。
- 持仓页的“人工处置”升级为可用的“减仓预览”，可选持仓和数量，展示四层变化和计算质量。
- 确认执行按钮仍禁用，后端没有从草案到 SELL 的路由。

### Verification

- 服务测试覆盖草案持久化、数量越界拒绝、过期状态与不可执行语义。
- 后端全量测试和 bootJar 通过；前端 TypeScript 与生产构建通过。
- Flyway V82 在真实 MySQL 成功应用。
- 真实持仓生成一份 10% 只读预览：预计回收 `2.48`，余额 `10.90 → 13.38`，开放持仓 `73.54 → 71.06`，总资产保持 `84.44`，`executionEnabled=false`。
- 后端 PID `93450`、健康 `UP`；Bridge `ok / executor_ready=true`。

### Safety Decision

- 本轮没有执行 SELL，没有更改 BUY 阈值，没有更改 Bridge 账户或跟单配置。
- 草案估值不是限价保证；真实执行前必须重新读取持仓、价格和过期时间。

### Next

- Iteration 23：实现草案逐笔确认状态机与二次持仓校验；先接“确认但不执行”审计态，再单独评审 Bridge SELL 执行路由、幂等键和失败重试边界。

## Iteration 23 - 逐笔确认与二次持仓校验（2026-07-11）

### Delivered

- V83 为减仓草案增加 `confirmed_by / confirmed_at`。
- 状态只允许 `DRAFT → CONFIRMED`；重复确认幂等返回同一草案。
- 确认前重新读取真实持仓；草案过期、持仓消失、数量减少或估值未知时拒绝确认。
- 前端加入独立二次确认弹窗，明确此步不执行 SELL。

### Verification

- 单测覆盖成功确认、过期拒绝和实时数量不足拒绝。
- 真实草案 `095091d5-0b01-4cce-8f41-f020cf50d6b1` 完成 `DRAFT → CONFIRMED`，确认人 `admin`，`executionEnabled=false`，未执行 SELL。
- V83 成功应用于真实 MySQL。

## Iteration 24 - 人工 SELL 提交与幂等保护（2026-07-11）

### Objective

只有经过预览和逐笔确认的草案，才能由人工第三次确认后提交 Bridge SELL；任何重复点击或超时重试不得重复下单。

### Delivered

- V84 增加执行人、请求时间、Bridge 记录、外部幂等键和错误审计字段。
- 执行端点使用数据库悲观行锁，仅允许 `CONFIRMED/FAILED`，并在转发前第三次校验真实持仓和数量。
- 每份草案的 Bridge 幂等键固定为 `reduction-{draftId}`，数据库上具有唯一索引。
- Bridge `/execute` 支持调用方外部键；已存在的键返回 `duplicate`，不创建第二个记录或后台任务。
- Bridge 没有明确接收请求时，后端不再伪造 `accepted`；保留 `FAILED` 和同键安全重试。
- 前端只在草案确认后显示红色真实 SELL 按钮，调用前必须第三次确认真实数量和不可撤销性。

### Verification

- 后端测试覆盖稳定幂等键、单次 Bridge 提交和 `SUBMITTED` 重复点击不再调用 Bridge。
- Bridge 测试证明重复外部键不记录、不创建后台任务；Bridge 全部 47 项测试通过。
- 后端全量测试与 bootJar 通过；前端 TypeScript 和生产构建通过。
- V84 已应用，执行外部键唯一索引存在。
- 后端 PID `44485`、健康 `UP`；Bridge PID `45238`、`ready=true / logged_in=true`。

### Runtime Safety

- 部署验证没有调用 `/reduction/execute`，未触发真实 SELL。
- BUY 规则、Bridge 跟单配置和 G3 Shadow 模式未改变。

### Next

- Iteration 25：建立 `SUBMITTED → EXECUTED/FAILED` 终态对账，只有 Bridge 明确 FAILED 后才开放新尝试键；补充无法卖出和长期占资人工队列。

## Iteration 25 - Bridge 终态对账与人工队列（2026-07-11）

### Delivered

- V85 为减仓草案增加 `execution_attempt`。
- 终态刷新通过外部幂等键查询 `bridge_trade_record`：PENDING 保持 `SUBMITTED`，SUCCESS 转 `EXECUTED`，FAILED 转 `FAILED` 并保存 Bridge 错误。
- 提交结果不确定且 Bridge 无记录时继续复用原键；只有 Bridge 明确 FAILED 时使用 `retry-N` 新键开始新尝试。
- 持仓页增加“人工减仓队列”，草案关闭后仍可重新打开，刷新终态或处理失败重试。
- 关系风险中的 `LONG_OCCUPIED`、`RELATED`、`PSEUDO_HEDGE` 等仍可直接创建预览，无法卖出错误保留在队列。

### Verification

- 单测覆盖 Bridge SUCCESS 终态、明确 FAILED 的 `retry-2` 新键、SUBMITTED 幂等返回和队列过期处理。
- 后端全量测试与 bootJar 通过；前端 TypeScript 与生产构建通过。
- V85 已应用；真实队列 API 返回两份已过期验证草案，均 `executionAttempt=0 / executionEnabled=false`。
- 后端 PID `60430`、健康 `UP`；Bridge `ok / executor_ready=true`。

### Phase Decision

- Phase 5 的代码闭环已完成：暂停 BUY、减仓预览、逐笔确认、真实执行三次确认、幂等、终态对账和失败队列均已建立。
- 本轮没有为验证而执行真实 SELL；真实操作必须由用户在页面逐笔确认。
- 主执行流进入 Phase 6，硬阈值仍保持 Shadow。

### Next

- Iteration 26：建立可重复的历史回放报告，分开 SUCCESS、风控/Policy FAILED、执行 FAILED、未结算和已结算；输出收益可用性、最大回撤、过滤率、资金利用和 SELL 完成率，不用缺失数据伪造指标。

## Iteration 26 - 可重复历史回放报告（2026-07-11）

### Delivered

- 新增与交易路径完全隔离的 `/api/risk/portfolio/historical-replay`。
- 报告只计入 raw payload 中存在 `copyTradingAccountId` 的账户归属 Bridge 记录，未归属历史记录单独计数。
- 统计 BUY/SELL SUCCESS/FAILED、失败类别、保护性过滤率、SELL 完成率、当前资金利用率与完整日资产快照的最大回撤。
- 未建立可靠关联时，`REALIZED_PNL` 和 `SETTLEMENT_COVERAGE` 显式返回 `UNAVAILABLE`；快照小于两个时 `MAX_DRAWDOWN` 返回 `INSUFFICIENT_DATA`。
- 持仓页添加“G3 历史回放与 Shadow 数据质量”卡片，展示指标、口径和硬阈值启用阻断项。

### Verification

- 单测证明账户归属/未归属记录分离、失败分类、SELL 完成率、回撤和未结算 PnL 不可用语义。
- 后端全量测试与 bootJar 通过；前端 TypeScript 与生产构建通过。
- 真实账户 2 的 180 日只读报告：可归属 Bridge 记录 6、未归属 12,811；BUY 成功 6、SELL 终态 0；当前资金利用率 91.5994%。
- 实现的阻断项：SELL 终态样本不足、完整日资产快照仅 1 个、已实现 PnL 和结算覆盖未关联。
- 后端 PID `78241`、健康 `UP`；Bridge `ok / executor_ready=true`。

### Safety Decision

- G3 继续 Shadow，不启用新的真钱阈值。
- 报告不触发 BUY、SELL、减仓确认或 Bridge 执行。

### Next

- Iteration 27：为自然发生的新 Bridge 记录保证账户归属、草案执行实体和终态对账可联系；制定至少 3 天 Shadow 观察的自动检查清单，不自动启用 Enforced。

## Iteration 27 - 新 Bridge 记录归属与 Shadow 观察清单（2026-07-11）

### Discovery and Fix

- Bridge 真实执行记录本来已使用 `_execution_raw_payload(signal, cfg)` 保存账户/配置。
- 规则过滤、风控拒绝、短周期跳过和 SELL 安全跳过另外保存了裸 signal，遗漏 `copyTradingAccountId` 和 `copyTradingId`。
- `_record_failed_signal` 现在必须传入当前配置；所有直接跳过记录也改用统一归属 payload。

### Verification

- Bridge 全部 48 项测试通过，新增过滤 FAILED 记录必须含 accountId/configId 的断言。
- Bridge 优雅重启后，自然进入的 FAILED 记录 `12915/12916` 已实证保存 `copyTradingAccountId=2 / copyTradingId=13`。
- 账户 2 只读历史回放可归属记录增至 27；旧的 10,808 条三日记录仍无法可靠回填，保持单独统计。
- `scripts/g3_shadow_readiness.sql` 在真实 MySQL 成功运行；已使用二进制地址比较解决钱包字段排序规则不一致问题。

### Current Three-Day Shadow Checklist

- 完整日资产快照 1（其中 MIDNIGHT 0）；未满足三天观察。
- 账户归属终态：BUY SUCCESS 7、BUY FAILED 2、SELL FAILED 24、SELL SUCCESS 0。
- 三日风险决策 26，完整输入快照 11，FINAL 5，关联 8；仍不可用于 Enforced 评审。

### Safety Decision

- G3 继续 Shadow，不调整资金阈值，不自动执行减仓。
- 三天观察清单仅读数据，不会产生任何交易。

### Next

- Iteration 28：为日常 Shadow 报告添加可保存的日次观察点，用自然数据连续积累 3 天；同时对三日后的 Enforced 评审保持人工关卡。
