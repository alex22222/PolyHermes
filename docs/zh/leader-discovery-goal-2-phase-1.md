# 第二目标：1000+ 高质量 Leader 候选积累与评分第一阶段规格

## 目标

以 Loop Engineering 模式建立第二条长期目标线：第一阶段先积累并评估 **1000+ 新的高质量 Polymarket Leader 候选**。

这里的重点不是把所有扫到的钱包都加入正式跟单，而是建立一个足够大的、持续更新的候选池，并让每个候选至少具备可审计的来源、交易频次、分类、胜率/收益指标、风险标签和评分结果。

第一阶段完成后，系统应能够每天回答：

1. 今天新增了多少可研究 Leader 候选？
2. 哪些候选具备足够交易频次和高胜率？
3. 候选主要来自哪些渠道？
4. politics / finance / sports / crypto 各有多少可用候选？
5. 哪些候选应该进入纸跟、watchlist 或低额度试跟？
6. 哪些候选虽然表面胜率高，但因僵尸单、长尾低价铺单、做市/套利/对冲特征而应排除？

## 当前基线

截至 2026-06-24 本地数据库基线：

| 指标 | 当前值 |
| --- | ---: |
| `copy_trading_leaders` | 338 |
| `leader_scanner_candidate_pool` | 4865 |
| `leader_research_candidate` | 3 |
| `leader_activity_event` | 207477 |
| activity distinct wallets | 40988 |

当前候选池分类：

| 类别 | 候选数 | PENDING | ANALYZED | REJECTED |
| --- | ---: | ---: | ---: | ---: |
| sports | 2179 | 1718 | 329 | 39 |
| politics | 1505 | 449 | 932 | 28 |
| finance | 674 | 60 | 493 | 34 |
| crypto | 507 | 202 | 228 | 14 |

说明：

- “候选池数量”已经超过 1000，但这还不是第一阶段完成，因为很多候选只是被发现，未进入统一研究评分链路。
- `leader_research_candidate` 只有 3 个，说明 scanner pool 与 research scoring pipeline 尚未充分打通。
- activity 钱包数很大，说明系统有足够的原始发现来源，第一阶段重点应从“继续盲目扩源”转向“把候选高质量筛选、批量分析、统一评分、可视化沉淀”。

## 启动记录

2026-06-24 11:35 已正式启动第二目标，第一目标 Bridge 可靠性新迭代暂时后置。

本轮先打通 `leader_scanner_candidate_pool` 到 `leader_research_candidate` 的批量导入链路，并执行数据库候选扩容：

| 指标 | 启动前 | 启动后 |
| --- | ---: | ---: |
| `leader_research_candidate` | 3 | 1145 |
| `DISCOVERED` | 0 | 1142 |
| `PAPER` | 3 | 3 |
| scanner pool promoted rows | - | 1342 |

启动后按 `source_evidence` 推断的候选分类：

| 类别 | 候选数 |
| --- | ---: |
| politics | 429 |
| finance | 415 |
| sports | 152 |
| crypto | 148 |
| unknown | 1 |

政治+金融候选约占 73.7%，已经接近 80% 主策略目标。下一轮扩源应继续偏向 politics / finance，尤其从 Polyburg、Polymarket Analytics、Dune、热门政治/金融市场 counterparty 中补充更高质量来源，而不是单纯扩大体育类候选。

本轮新增后端接口：

```http
POST /api/copy-trading/leader-research/scanner-pool/import
```

建议默认参数：

```json
{
  "politicsLimit": 350,
  "financeLimit": 350,
  "sportsLimit": 150,
  "cryptoLimit": 150,
  "onlyPending": false,
  "dryRun": false
}
```

说明：当前 scanner pool 中很多 finance / politics 高分候选已处于非 `PENDING` 状态，所以首轮启动需要 `onlyPending=false`，后续日常增量可改回 `onlyPending=true`。

### 2026-06-24 预筛评分进展

已新增并执行 `activity-prescreen-v1` 活动基础预筛评分。该评分不是最终可跟单结论，只用于从 1000+ 候选中先筛出值得进入 paper/backtest 的地址。

本轮评分结果：

| 指标 | 数量 |
| --- | ---: |
| 新增候选已评分 | 1142 |
| 80+ 分候选 | 45 |
| 40-59 分候选 | 37 |
| 20-39 分候选 | 1060 |
| 首批推进 PAPER | 22 |
| 当前 active paper session | 25 |

主要风险标签：

| 风险标签 | 数量 | 含义 |
| --- | ---: | --- |
| `scanner_pool_unverified` | 1011 | 扫链候选在本地 activity 样本不足，暂不进入 paper |
| `small_sample` | 1011 | 交易样本不足 20 条 |
| `low_market_diversity` | 902 | 独立市场数不足，容易是单市场噪音 |
| `low_average_size` | 99 | 平均成交金额偏低 |
| `buy_only_no_exit` | 55 | 买入多但缺少卖出行为，不符合及时跟 sell 目标 |
| `low_safe_price_ratio` | 52 | 价格多在不可复制区间外 |
| `tail_price_spray` | 49 | 长尾低价概率铺单，需屏蔽 Low-Futon 类策略 |

首批 PAPER 配比：

| 类别 | 数量 | 最低预筛分 |
| --- | ---: | ---: |
| politics | 9 | 87.18 |
| finance | 9 | 86.45 |
| sports | 2 | 100.00 |
| crypto | 2 | 97.62 |

本轮还修复了 paper processing 的一个效率瓶颈：待处理事件查询从“全局取最早 200 条再内存过滤”改为“只查询 PAPER/TRIAL_READY 候选钱包的事件”，避免精选候选时 paper 模拟空转。

### 2026-06-24 Paper 处理进展

新增并上线两个后端接口：

```http
POST /api/copy-trading/leader-research/paper/process
POST /api/copy-trading/leader-research/paper/score
```

本轮进一步修复了 paper processing 的批次公平性：每轮按 PAPER/TRIAL_READY 钱包公平采样，避免一个高频钱包吃掉整批处理额度。

已执行两轮公平 paper batch：

| 指标 | 数量 |
| --- | ---: |
| paper trades 总数 | 696 |
| processed | 513 |
| filtered | 183 |
| failed | 0 |
| 剩余 NEW | 3585 |

当前符合下一层深度 paper/backtest 的候选：

| candidate id | wallet | category | score | trade_count | filtered_count | copyable_pnl | max_drawdown | filtered_ratio |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 850 | `0xe9cbb1c9b3f7f411dd4fdf2ea7afa780c8b4d096` | sports | 85.06 | 33 | 3 | 5.6395 | -0.6667 | 0.0833 |
| 617 | `0x9703676286b93c2eca71ca96e8757104519a69c2` | politics | 80.95 | 18 | 8 | 5.2698 | -1.0003 | 0.3077 |
| 786 | `0x30a28af9d4694b1967582a7915c6e048b7bc0b35` | politics | 75.54 | 10 | 0 | 0.2547 | 0.0000 | 0.0000 |
| 340 | `0x0d2d845a6ff64e31e04a70afce8a573940767ff5` | finance | 73.07 | 21 | 5 | 0.4612 | -1.3075 | 0.1923 |

说明：

- `0xe9076a87c5ed90ef16e6fe6529c943baeca0cff6` 的 paper PnL 较高，但 max_drawdown 为 -23.2981，并已标记 `drawdown_gt_15`，暂不进入合格名单。
- 当前合格候选仍偏少，尤其 finance 只有 1 个，下一轮扩源和深度处理应继续偏向 politics / finance。

## 参考方法论

本目标参考 Obsidian 报告：

- `报告/polyburg 报告/report.md`
- `报告/OKComputer_Polymarket_领袖评估/report.md`

关键借鉴：

1. Polyburg 式基础评分：`win_rate * ln(1 + total_trades)`，用于避免小样本高胜率误判。
2. 信念评分：相对历史平均仓位放大的交易更有信息含量，但必须结合胜率和退出纪律。
3. 反机器人过滤：过滤高频做市、双边对冲、纯套利和不活跃钱包。
4. 僵尸单校正：不能只看已平仓胜率，必须纳入未平仓浮亏/浮盈。
5. 板块专长度：一个钱包应按 politics、finance、sports、crypto 分领域评估，而不是混在一起打总分。
6. 可复制收益优先：Leader 自己赚钱不等于系统可复制赚钱，必须按真实延迟、价格偏离、流动性和 sell 成功率重算。

## 第一阶段定义

第一阶段目标不是正式跟单 1000 人，而是形成 **1000+ 已评估候选**。

候选必须满足：

- 钱包地址有效且去重。
- 有至少 1 个可信来源。
- 有主分类，分类置信度可解释。
- 最近 30/90 天至少有一定交易频次。
- 完成基础指标计算。
- 完成研究评分或明确拒绝原因。

### 1000+ 的口径

第一阶段完成口径：

```text
qualified_research_candidates >= 1000
```

其中 `qualified_research_candidates` 指：

- 来自 scanner pool、activity、hot market、manual seed、Polyburg/Analytics/Dune 等来源之一。
- 有基础交易样本：最近 90 天 trade_count >= 20，或历史独立市场数 >= 30。
- 有分类：politics / finance / sports / crypto。
- 有评分：PM-Score 或 research copyability score。
- 状态为 `DISCOVERED` / `CANDIDATE` / `PAPER` / `TRIAL_READY` / `WATCHLIST` 之一。
- 不包含已明确 `REJECTED`、`RETIRED`、market-maker、pure-arb、tail-price-spray 高风险标签。

## 来源渠道

### 已有渠道

1. Polymarket activity 全局交易流
   - 用于捕获最近活跃钱包。
   - 适合高频发现，但需要过滤噪音。

2. Hot market 最近成交钱包
   - 当前候选池主要来源，已有 4000+ 条。
   - 需要加强按 category 的市场选择，尤其 politics / finance。

3. 已有 Leader
   - 用于回填研究候选。
   - 不能作为主要增长来源。

4. Bridge webhook / raw payload
   - 可发现真实跟单链路曾接触过的钱包。
   - 适合作为执行统计归因来源。

5. Leader Research Candidate
   - 当前数量过少，需要与 scanner pool 打通。

### 建议新增渠道

1. Polyburg 公开排行和案例研究
   - 关注：top traders、case studies、conviction score、分类标签。
   - 用途：seed 高质量钱包和验证系统评分方向。

2. Polymarket Analytics
   - 关注：trader leaderboard、PnL、volume、markets、position history。
   - 用途：按 PnL、胜率、活跃度交叉验证 scanner 候选。

3. Dune / Goldsky / Subgraph
   - 关注：历史成交、持仓、PnL、活跃市场参与者。
   - 用途：批量扩展 5000-10000 初始观察池。

4. 热门政治/金融市场 Top counterparties
   - 从 politics / finance 高流动性市场按成交额、盈利、早期建仓提取候选。
   - 用途：补足主策略 80% 的候选质量。

5. 高质量 Leader 的同市场扩散
   - 对 A/B 级 Leader 曾参与且获利的市场，提取同方向早期参与者。
   - 用途：发现同信息源或同能力圈钱包。

6. 手动 seed/watchlist
   - 从 Obsidian 报告、外部工具、人工观察加入。
   - 用途：快速启动高质量候选验证。

## 质量门槛

### 入池门槛

钱包进入 `leader_scanner_candidate_pool`：

- 地址合法。
- 来源可信。
- 至少命中一个 category。
- 非明显 USDC 合约、系统地址、交易所地址。

### 进入研究门槛

钱包进入 `leader_research_candidate`：

- 最近 90 天 trade_count >= 20，或最近 30 天 trade_count >= 8。
- 独立市场数 >= 10。
- category_confidence >= 0.6。
- 非 pure market maker / wash / pure arb / obvious hedger。
- 有至少一个可回填 Data API 或 activity event 证据。

### 高质量候选门槛

标记为 `CANDIDATE`：

- trade_count >= 30。
- win_rate >= 55%，并通过样本量折扣。
- `win_rate * ln(1 + total_trades)` 达到分类内前 30%。
- adjusted win rate 或 mark-to-market 后仍不低于 52%。
- 最近 30 天有交易。
- category trade ratio >= 50%。

### 进入 PAPER 门槛

标记为 `PAPER`：

- PM-Score >= 55。
- 无严重风险标签。
- 有可复制交易样本。
- 市场流动性满足最小跟单金额。

### 进入 TRIAL_READY 门槛

标记为 `TRIAL_READY`：

- paper trade passed count >= 20。
- simulated copy pnl > 0。
- max drawdown 可控。
- buy/sell 可复制延迟在阈值内。
- sell 跟随逻辑可验证。

## 评分模型

第一阶段使用两层评分。

### Discovery Score

用于候选池排序：

```text
discovery_score =
  source_weight
  + hit_count_weight
  + recent_activity_weight
  + category_priority_weight
  + market_quality_weight
```

推荐 source weight：

| 来源 | 权重 |
| --- | ---: |
| manual seed / watchlist | 100 |
| Polyburg / Polymarket Analytics verified | 80 |
| hot politics/finance market | 50 |
| hot sports/crypto market | 35 |
| activity global capture | 25 |
| bridge raw payload | 20 |
| existing leader | 10 |

### PM-Score / Copyability Score

用于研究和晋级：

```text
score =
  win_rate_stability * 0.20
  + profit_factor * 0.18
  + sample_sufficiency * 0.14
  + category_specialization * 0.12
  + recency * 0.10
  + conviction * 0.08
  + liquidity_fit * 0.08
  + reproducible_copy_pnl * 0.07
  + sell_followability * 0.03
  - risk_penalty
```

风险标签必须强制降权：

- `small_sample`
- `zombie_position_risk`
- `tail_price_spray`
- `market_maker_like`
- `pure_arbitrage`
- `hedged_both_sides`
- `low_liquidity`
- `stale_source`
- `category_drift`
- `copy_unprofitable`

## 目标结构

### Goal

第一阶段建立 1000+ 已评估高质量 Leader 候选池。

### Stop Condition

满足以下全部条件：

- `leader_research_candidate` 中合格候选数 >= 1000。
- 每个合格候选有 source evidence。
- 每个合格候选有 category、score、risk flags。
- politics + finance 合格候选占比 >= 60%，目标 80%。
- 每日 loop report 能展示新增、分析、晋级、拒绝、风险原因。
- 至少 100 个候选进入 PAPER 或 WATCHLIST 观察。
- 至少 20 个候选达到 TRIAL_READY 或等效“可试跟研究评分门槛”。

### Trigger

- 手动触发：点击扫链、运行研究、执行脚本。
- 定时触发：每日一次全量扩展，每小时一次增量发现。
- 事件触发：activity global capture、hot market 变化、外部 seed 更新。

### Isolation

- 不自动启用真钱跟单。
- 只写入候选、评分、纸跟、日报。
- 真实跟单仍需要人工启用配置。

### Memory

- `docs/zh/leader-discovery-goal-2-phase-1.md`
- `docs/zh/leader-discovery-copytrading-loop-spec.md`
- `LOOP_STATE.md`
- 后续建议新增 `leader_goal2_daily_report` 或复用优化日报表。

## Loop 流程

```text
discover -> normalize -> classify -> analyze -> score -> paper -> promote/reject -> report
```

### Iteration 1：候选池盘点

输入：

- `leader_scanner_candidate_pool`
- `leader_activity_event`
- `copy_trading_leaders`
- `leader_research_candidate`

输出：

- 当前候选数量、分类、状态、来源分布。
- 低质量或重复候选清单。
- scanner pool 到 research candidate 的转化缺口。

验证：

- SQL 统计可复现。
- 页面/报告可展示候选池状态。

### Iteration 2：scanner pool -> research candidate 打通

动作：

- 从每类 candidate pool 选择高 discovery_score 候选批量 upsert 到 `leader_research_candidate`。
- politics / finance 优先。
- sports / crypto 限量补充。

建议配额：

| 类别 | 首批导入 |
| --- | ---: |
| politics | 350 |
| finance | 350 |
| sports | 150 |
| crypto | 150 |

验证：

- research candidate 增加到 >= 1000。
- 无重复地址。
- source evidence 包含 scanner pool id/source/category。

### Iteration 3：批量回填活动与基础指标

动作：

- 对 1000+ 候选按批次调用 Data API。
- 获取最近 90 天 trade activity。
- 计算 trade_count、unique_market_count、win_rate、volume、last_trade_at、category ratio。

验证：

- 每日最多处理固定批量，避免 API 限速。
- 每个候选有成功或失败原因。

### Iteration 4：评分与风险标签

动作：

- 计算 discovery score、PM-Score、copyability score。
- 给出 risk flags。
- 小样本候选最高只能进入观察，不进入试跟。

验证：

- score 分布可解释。
- 高胜率小样本不会排在大样本稳定钱包前面。

### Iteration 5：纸跟与回测

动作：

- 对 Top 100-200 候选进入 PAPER。
- 跟踪其新交易，模拟真实跟单。
- 回测历史可复制收益。

验证：

- 每个 PAPER 候选有 paper session。
- 过滤原因分布可见。

### Iteration 6：日报与下一轮优化

动作：

- 输出每日新增候选、已评分候选、晋级候选、拒绝原因。
- 自动指出下一步瓶颈，例如 API 限速、分类错误、finance 不足、sell followability 缺失。

验证：

- 页面或 Markdown 报告可读。
- loop state 更新。

## 第一轮执行建议

当前最直接瓶颈不是“没有候选”，而是“scanner pool 没有大规模进入 research scoring”。

建议第一轮：

1. 新增 scanner pool 到 research candidate 的批量晋级任务。
2. 按 politics 350、finance 350、sports 150、crypto 150 的配额导入。
3. source evidence 写入 scanner category/source/discovery_score。
4. 运行 research scoring。
5. 输出候选质量报告。

## 非目标

第一阶段不做：

- 自动启用真钱跟单。
- 直接把 1000 个候选加入 Leader 管理并开启跟单。
- 只凭表面胜率晋级。
- 追踪纯做市、套利和长尾低价概率铺单钱包。
- 大额资金分配。

## 风险

1. Data API 限速或超时。
   - 需要批处理、重试和进度断点。

2. 候选池被 sports 热门市场污染。
   - 需要 politics / finance 配额保护。

3. 高胜率小样本误判。
   - 使用 `ln(1 + total_trades)` 和样本 cap。

4. 僵尸单导致虚高胜率。
   - 必须引入 open position mark-to-market。

5. 长尾低价铺单钱包误入。
   - 对 tail-price-spray 强制降权或拒绝。

6. Leader 自己赚钱但不可复制。
   - 用 paper trading 和真实延迟/价格偏离重算。

## 下一步

### 已完成的落地进展

1. 已完成 `leader_scanner_candidate_pool` -> `leader_research_candidate` 的批量导入服务/API：
   - `POST /api/copy-trading/leader-research/scanner-pool/import`

2. 已完成 activity prescreen 评分与 PAPER 晋级链路：
   - `POST /api/copy-trading/leader-research/activity-score/run`
   - `POST /api/copy-trading/leader-research/activity-score/promote-paper`

3. 已完成基于真实活动事件的 politics/finance 扩源入口：
   - `POST /api/copy-trading/leader-research/activity-source/import`
   - 从 `leader_activity_event` 聚合钱包，要求事件数、市场多样性、buy/sell 双向行为、安全价格比例与长尾价格比例满足阈值。
   - 新增 `sell_only_no_entry` 风控，避免只有卖出样本、没有可跟买入入口的钱包高分晋级。

4. 2026-06-24 执行结果：
   - activity-source 第一轮真实导入 selectedTotal=160、createdTotal=152、updatedTotal=8。
   - activity prescreen 重评 1327 个候选。
   - 真实晋级 PAPER 23 个：politics 3、finance 20。
   - PAPER 总分布变为 politics 15、finance 26、sports 6、crypto 6。
   - politics+finance PAPER 占比 77.4%，接近 80% 主策略目标。

### 继续实施时，优先做：

1. paper process 性能优化：
   - 当前 `paper/process batchSize=500` 在遇到大量需链上估值/结算查询的事件时会超过 300 秒。
   - 下一轮应加入 valuation/settlement 缓存或异步化处理，API 返回 chunk progress，并把默认 batch size 调整到 50-100。

2. politics 来源继续扩容：
   - 严格 activity-source 条件下 politics 只有 9-10 个可选钱包。
   - 下一轮从政治热门市场 counterparty、Polyburg/Analytics/Dune、以及优秀 politics leader 的同市场交易对手继续扩源。

3. finance 来源交叉验证：
   - finance 候选数量充足，但需输出命中 market slug 样本，确认不是 crypto/sports 污染或纯做市流。

4. 候选池日报统计接口和页面展示：
   - 新增每日新增候选、晋级 PAPER 候选、risk flag 分布、paper copyable PnL top/bottom、下一步瓶颈。

5. 评分解释和风险标签页面展示：
   - 在 Leader 管理/Research 页面展示 `sell_only_no_entry`、`buy_only_no_exit`、`tail_price_spray`、`scanner_pool_unverified` 等标签解释。

## 2026-06-25 恢复目标执行记录

本轮恢复第二目标后，目标状态继续保持 active，并执行了一轮 politics/finance 优先的扩源、预筛评分、PAPER 晋级和小批量 paper 处理。

### 本轮增量

- Activity source 导入 politics/finance：
  - selectedTotal=205
  - createdTotal=43
  - updatedTotal=4
  - politics created=18、updated=4
  - finance created=25
- Scanner pool 导入 politics/finance：
  - selectedTotal=200
  - createdTotal=196
  - updatedTotal=4
  - politics created=196、updated=4
  - finance selected=0
- Activity prescreen：
  - scannedCount=1560
  - scoredCount=239
  - politics=214、finance=25
- 晋级 PAPER：
  - minScore=75
  - promotedTotal=49
  - politics promoted=9
  - finance promoted=40

### 当前数据状态

- DISCOVERED=1511
- PAPER=134
- TRIAL_READY=0
- COOLDOWN=5
- activePaperSessions=134
- paper trades=2500
- paper event status：PROCESSED=1683、FILTERED=817、NEW=249260

### 当前优先观察候选

- politics `0x9703676286b93c2eca71ca96e8757104519a69c2`：score=92.2388，paper trades=42，copyablePnL=23.7822，需复核 mixed sports evidence。
- politics `0x31c4578b25af36f34c8aa4cc85f0794bfbea622f`：score=83.7431，paper trades=10，copyablePnL=4.3690，样本刚过线。
- finance `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`：score=87.8093，paper trades=18，copyablePnL=6.7160，filteredRatio=0.10。
- finance `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`：score=85.8934，paper trades=19，copyablePnL=10.2852，filteredRatio=0.05。
- finance `0x7e31c4201a2a040e7c091d26407e4282ada2d45b`：score=85.4866，paper trades=15，copyablePnL=7.1534，unknownRatio=0.0947。

### 本轮判断

当前仍没有 TRIAL_READY，不是候选质量完全不足，而是 PAPER 到 TRIAL_READY 的硬门槛要求观察期至少 7 天。多位 politics/finance 候选已经满足交易数、PnL、回撤、unknown exposure、filtered ratio 等条件，但 session age 只有约 0.01-1.39 天，因此仍应停留在 PAPER。

`paper/process batchSize=100` 会 60 秒客户端超时；`batchSize=10` 可稳定完成，6.4 秒处理 10 条事件。下一轮继续使用 10 或 20 的小批量循环，同时将 paper process 的估值查询缓存或异步化列为工程优化点。

## 2026-06-25 PAPER 处理批量保护

为了让第二目标可以稳定循环执行，本轮把 `paper/process` 从“调用方可请求大批量同步处理”调整为“手动 API 有硬上限并返回实际处理批量”。

### 改动

- `LeaderPaperTradingService.DEFAULT_PROCESSING_BATCH_SIZE=20`
- `LeaderPaperTradingService.DEFAULT_PROCESSING_CHUNK_SIZE=10`
- `LeaderPaperTradingService.MANUAL_MAX_PROCESSING_BATCH_SIZE=20`
- `/api/copy-trading/leader-research/paper/process` 会把手动请求的 batchSize 压到 1-20。
- 响应新增：
  - `requestedBatchSize`
  - `effectiveBatchSize`
  - `maxBatchSize`
  - `truncated`

### 验证

请求：

```json
{"batchSize":100}
```

响应确认：

```json
{
  "processed": 15,
  "filtered": 5,
  "failed": 0,
  "requestedBatchSize": 100,
  "effectiveBatchSize": 20,
  "maxBatchSize": 20,
  "truncated": true
}
```

本次请求耗时 16.3 秒，未再出现 60 秒客户端超时。

### 当前观察进展

- DISCOVERED=1511
- PAPER=134
- TRIAL_READY=0
- paper trades=2810
- paper event status：PROCESSED=1931、FILTERED=879、NEW=250114

当前最值得继续观察的 finance 候选：

- `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`：score=95.2304，paper trades=22，copyablePnL=12.0753，filteredRatio=0.0435。
- `0x31cfb6c5368a727e2a504e2e0e5a18905a6c4de8`：score=88.8265，paper trades=11，copyablePnL=8.5152。
- `0x7e31c4201a2a040e7c091d26407e4282ada2d45b`：score=85.9811，paper trades=18，copyablePnL=7.1534。
- `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`：score=85.0872，paper trades=21，copyablePnL=5.2545。

当前最值得继续观察的 politics 候选：

- `0x9703676286b93c2eca71ca96e8757104519a69c2`：score=92.4348，paper trades=45，copyablePnL=25.4313；但 evidence 混入 sports，必须先做分类复核。

## 2026-06-25 分类复核与混类隔离

本轮修复了高分候选里 politics/finance 与 sports/crypto evidence 混杂的问题。此前系统会读取 `sourceEvidence` 中第一个 `category` 作为候选类别，导致部分 sports 热门市场钱包被误标为 politics 或 finance。

### 新规则

- 解析 `sourceEvidence` 中全部 `category:` / `category=`。
- 统计各类别出现次数。
- 若存在多个类别，且主导类别占比低于 70%，标记为 `mixed_category_evidence`。
- `mixed_category_evidence`：
  - activity prescreen 分数 capped 到 60。
  - 禁止新候选自动晋级 PAPER。
  - 已进入 PAPER 的候选会保留 risk flag。
  - 禁止 PAPER 自动进入 TRIAL_READY。

### 本轮效果

- 重评 DISCOVERED/CANDIDATE：scannedCount=1511、scoredCount=1511。
- 识别 mixed category evidence：47 个。
- PAPER 中已有 mixed 候选：15 个。
- candidate 617 `0x9703676286b93c2eca71ca96e8757104519a69c2` 已标记 `mixed_category_evidence`。
- candidate 340 `0x0d2d845a6ff64e31e04a70afce8a573940767ff5` 已标记 `mixed_category_evidence`。

### 新增 PAPER

在新规则过滤后，本轮正式晋级 PAPER：

- selectedTotal=41
- promotedTotal=41
- politics promoted=1
- finance promoted=40

当前状态：

- DISCOVERED=1470
- PAPER=175
- TRIAL_READY=0
- COOLDOWN=5
- paper trades=2830

当前 clean politics/finance 优先观察：

- politics `0x31c4578b25af36f34c8aa4cc85f0794bfbea622f`：score=80.2914，paper trades=10，copyablePnL=4.3690。
- finance `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`：score=95.2348，paper trades=22，copyablePnL=12.0753。
- finance `0x31cfb6c5368a727e2a504e2e0e5a18905a6c4de8`：score=88.8310，paper trades=11，copyablePnL=8.5152。
- finance `0x7e31c4201a2a040e7c091d26407e4282ada2d45b`：score=85.9856，paper trades=18，copyablePnL=7.1534。
- finance `0x783134dbc526f5fe75dc3e770b9b6bdac39c5eb1`：score=85.0917，paper trades=21，copyablePnL=5.2545。

下一轮继续补 politics 来源。本轮干净 politics 只晋级 1 个，说明 politics 高质量候选供给仍是主瓶颈。

## 2026-06-29 样本量审计与第二目标上下文更新

本轮重新盘点第二目标样本量后，结论更新为：**原始候选广度已经足够，但高质量可跟单样本深度仍不足**。

### 当前样本量

| 层级 | 当前值 | 判断 |
| --- | ---: | --- |
| `copy_trading_leaders` | 686 | 已有 Leader 基数够用 |
| `copy_trading_leader_pool` | 625 | 观察池够大，但大多仍是 WATCH |
| `leader_research_candidate` | 27314 | 原始研究候选已远超 1000 |
| `leader_activity_event` | 486816 | 链上活动样本充足 |
| activity distinct wallets | 63712 | 钱包发现广度充足 |
| 近 24h 活跃钱包 | 13970 | 新鲜来源充足 |
| 有纸跟交易候选 | 249 | 有效验证样本偏少 |
| 纸跟交易总数 | 4194 | 可用于初步筛选 |
| 纸跟交易数 >=20 的候选 | 35 | 高置信样本不足 |
| 纸跟收益为正的候选 | 104 | 需要继续验证稳定性 |
| score >=80 的候选 | 32 | 高分候选数量不足 |
| score >=70 的候选 | 88 | 可作为下一阶段重点池 |
| TRIAL_READY | 0 | 尚未形成正式可试跟候选 |

### 状态分布

| research_state | 数量 | 平均分 |
| --- | ---: | ---: |
| PAPER | 26551 | 20.49 |
| DISCOVERED | 744 | 14.98 |
| COOLDOWN | 15 | 69.61 |
| CANDIDATE | 4 | 51.06 |

### Leader 池状态

| 状态 | 数量 |
| --- | ---: |
| WATCH | 620 |
| CANDIDATE | 3 |
| COOLDOWN | 2 |

现有 Leader 分类分布：

| 类别 | 数量 | 平均 research_score | ELITE/TRADEABLE |
| --- | ---: | ---: | ---: |
| uncategorized | 173 | 17.23 | 0 |
| politics | 139 | 24.00 | 0 |
| sports | 133 | 20.85 | 1 |
| finance | 128 | 24.89 | 0 |
| crypto | 113 | 26.96 | 0 |

### 判断

第二目标的 1000+ 原始候选目标已经在数量上完成，但不能据此认为可以稳定实盘筛 Leader。

当前瓶颈从“发现 leader”切换为：

1. 高分候选的纸跟交易样本不足。
2. `TRIAL_READY` 仍为 0，说明正式可试跟推荐尚未形成。
3. politics / finance 原始来源足够，但 pending 与 PAPER 后续验证没有完全吃完。
4. 很多 PAPER 候选没有产生足够可模拟交易，无法证明可复制收益。
5. 一些高分候选仍带 `mixed_category_evidence`、`high_filtered_ratio`、`tail_price_spray` 等风险，不能直接试跟。

### 新的执行重点

后续第二目标不再优先追求“候选数继续变大”，而是优先追求“高质量样本变厚”：

1. 优先处理 finance / politics pending 候选。
2. 把 score >=70 / score >=80 的 PAPER 候选拉成重点观察名单。
3. 让至少 100 个候选达到 `paper_trade_count >= 20`。
4. 让至少 20 个候选同时满足：
   - `score >= 80`
   - `copyable_pnl > 0`
   - `paper_trade_count >= 20`
   - `filtered_ratio` 可接受
   - 无 `tail_price_spray`
   - 无严重 `mixed_category_evidence`
   - 有 BUY 与 SELL 样本，避免 buy-only / sell-only 假信号
5. 在 finance / politics 中形成 3-5 个禁用试跟配置候选，再由人工决定是否启用。

### 更新后的完成口径

第一阶段完成不再只看 `qualified_research_candidates >= 1000`，需要同时满足：

- 原始研究候选 >= 1000：已满足。
- PAPER 或 WATCH 观察候选 >= 100：已满足数量，但需提高有效交易覆盖。
- 至少 100 个候选有 `paper_trade_count >= 20`：未满足，当前 35。
- 至少 20 个候选达到可试跟研究评分门槛：未满足。
- `TRIAL_READY` 或等效 FAST_WATCH 主候选在 politics / finance 中稳定出现：未满足。

因此当前阶段状态为：

```text
候选广度：达标
验证深度：未达标
跟单准备：未达标
下一步：加速 politics/finance 高分候选纸跟验证与 TRIAL_READY 阻塞原因消解
```

### 2026-06-29 样本是否足够的最终口径

本轮结论需要固化到第二目标上下文：**当前样本量只满足“发现广度”，还不满足“可跟单决策深度”**。

不能再用单一数字判断第二目标是否达标：

| 口径 | 当前判断 | 是否足够 |
| --- | --- | --- |
| 原始研究候选数 | 已远超 1000 | 足够 |
| Leader 管理/观察池记录数 | 可作为初筛池，但多数仍是 WATCH | 不足以决策 |
| 有纸跟交易的候选 | 数量偏少，交易覆盖不厚 | 不足 |
| `paper_trade_count >= 20` | 未达到 100 个候选的阶段目标 | 不足 |
| politics/finance 高质量候选 | finance 有苗子，politics 明显偏薄 | 不足 |
| FAST_WATCH / TRIAL_READY | FAST_WATCH 少量出现，TRIAL_READY 仍为 0 | 不足 |

因此第二目标继续保持 `ACTIVE`，并把执行重心从“继续扩大原始钱包池”切换为：

1. politics / finance 优先，把高分 PAPER 与 FAST_WATCH 候选做厚。
2. 用 targeted score 替代全量 score，避免 3 万级 PAPER 池拖慢闭环。
3. 持续推进 `paper_trade_count >= 20` 的候选数量，先达到 100 个。
4. 只把满足 7 天观察期、稳定高分、正 copyable PnL、BUY/SELL 样本完整、风险标记干净的候选放入可试跟候选。
5. 在 politics / finance 中先形成 3-5 个“禁用试跟配置”候选，人工确认后再启用真钱跟单。

后续任何日报、页面或自动化任务都应使用这个口径：**原始数量达标不等于 Leader 样本够用；只有可验证、可复制、分类稳定、经过观察期的样本才算第二目标的有效进展**。

## 2026-06-29 Loop Iteration：推进 politics/finance PAPER 样本深度

本轮目标不是继续盲目扩大钱包池，而是把已经高分、低风险、偏 politics/finance 的 PAPER 候选推进到更有置信度的模拟样本。

### 服务与数据状态

- 后端健康检查：`http://127.0.0.1:8000/actuator/health` 返回 `UP`。
- 前一次 `localhost` curl 失败是因为 shell 走了本机 SOCKS 代理；后续本地 API 调用统一使用 `--noproxy '*'` 或 `127.0.0.1`。
- Leader Research 定时任务仍在运作，本轮日志显示：
  - politics 写入/更新 `28295` 个 scanner 候选。
  - sports 写入/更新 `2179` 个 scanner 候选。
  - crypto 写入/更新 `1447` 个 scanner 候选。
  - finance 写入/更新 `3122` 个 scanner 候选。
  - 本次合计写入/更新 `35043` 个候选。

### 当前研究池快照

| 指标 | 当前值 |
| --- | ---: |
| `leader_research_candidate` | 33954 |
| PAPER | 33234 |
| DISCOVERED | 701 |
| CANDIDATE | 4 |
| COOLDOWN | 15 |
| TRIAL_READY | 0 |
| score >=80 | 30 |
| score >=70 | 89 |
| `paper_trade_count >=20` | 48 |
| `paper_trade_count >=10` | 97 |
| `paper_trade_count >=5` | 127 |

### 本轮执行

第一批手动处理以下 clean finance/politics PAPER 候选：

- `1697`
- `2063`
- `1699`
- `1704`
- `1669`
- `1755`
- `1678`
- `1747`
- `1708`
- `1689`
- `1724`
- `1666`
- `2061`
- `2064`

结果：

- processed `19`
- filtered `1`
- failed `0`

第二批处理临近 20 笔门槛的候选：

- `2063`
- `1699`
- `1747`
- `2061`

结果：

- processed `18`
- filtered `2`
- failed `0`

两批合计：

- processed `37`
- filtered `3`
- failed `0`
- `paper_trade_count >=20` 从本轮开始时约 `44/45` 推进到 `48`。

### 新增或加厚的重点样本

| candidateId | wallet | score | trade_count | copyable_pnl | filtered_ratio | 判断 |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 2063 | `0x3e5d55e7d987489ceb9a85984b43b75ad3fef957` | 90.32 | 23 | 6.1819 | 0.1481 | 高分 finance，继续重点观察 |
| 1747 | `0x5158f4654de31b60eb4d1973a6eb5aa27c9d7df4` | 78.21 | 29 | 1.8483 | 0.1212 | 样本过线但 score 未到 80 |
| 1724 | `0x6bea93788e55e8cd40ca9768d51242de13ec82fc` | 78.11 | 21 | 0.4850 | 0.0870 | 样本过线但收益边际较薄 |
| 2061 | `0x3a603f6b4354c091f4171c6c40995315df188717` | 74.42 | 22 | -1.7293 | 0.2143 | 处理后 PnL 转负，降级观察 |

### 为什么 TRIAL_READY 仍是 0

状态机要求 PAPER -> TRIAL_READY 同时满足：

- score >= 80。
- riskFlags 为空。
- PAPER 观察期 >= 7 天。
- trade_count >= 10。
- copyable_pnl > 0。
- max_drawdown >= -15。
- unknown valuation exposure <= 20%。
- filtered_ratio < 50%。
- 最近 3 次稳定高分都 >= 80。

本轮诊断发现，已经有多名候选满足分数、收益、样本、稳定高分等条件，但 PAPER 观察期只有约 `70-116` 小时，未达到 7 天。因此 `TRIAL_READY=0` 当前主要是观察期门槛，而不是没有高分候选。

接近 FAST_WATCH 的样本包括：

- `0xe7ce284302936fd06ffc7ad05f13c648c513d53a`：score `97.79`，trade_count `22`，PnL `12.0753`，stable80_last3=`3`，paper_age_hours `115.8`。
- `0x674887d1ac838099a48b629dff53f25b7b87ee08`：score `94.60`，trade_count `54`，PnL `9.0388`，stable80_last3=`3`，paper_age_hours `86.0`。
- `0x5e2b9261b0c4f697b55bf921ff2bc227183d9101`：score `94.44`，trade_count `57`，PnL `10.7818`，stable80_last3=`3`，paper_age_hours `86.3`。
- `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe`：score `93.61`，trade_count `32`，PnL `8.7053`，stable80_last3=`3`，paper_age_hours `83.4`。
- `0x3e5d55e7d987489ceb9a85984b43b75ad3fef957`：score `90.32`，trade_count `23`，PnL `6.1819`，stable80_last3=`3`，paper_age_hours `83.4`。

### 工程发现

`/api/copy-trading/leader-research/paper/score` 当前会全量重算 PAPER/TRIAL_READY。随着 PAPER 候选已到 `33234`，本轮调用 180 秒超时，没有返回结果。后续不应把全量评分作为每轮小闭环的默认动作。

下一步工程优化：

1. 增加候选级或批量指定 candidateIds 的增量评分接口。
2. paper/process 返回 processed candidateIds 与样本变化，方便页面展示“本轮推进了谁”。
3. 增加 FAST_WATCH 列表接口，把“未满 7 天但其他条件已满足”的候选单独展示。
4. 对 PnL 转负候选自动降权或加观察标记，例如本轮 `2061`。
5. 将 `paper_trade_count >=20` 目标继续从 `48` 推到 `100`，但优先处理 score>=80、PnL>0、riskFlags 空、politics/finance 的候选。

## 2026-06-29 Engineering Iteration：增量评分与 FAST_WATCH 输出

上一轮发现 `/paper/score` 对 `33234` 个 PAPER 候选全量评分会在 180 秒内超时。本轮将该瓶颈改成可循环执行的小闭环能力。

### 后端接口更新

`POST /api/copy-trading/leader-research/paper/score`

- 保持旧调用兼容：不传 `candidateIds` 时仍按原有 PAPER/TRIAL_READY 全量逻辑。
- 新增 targeted 模式：传 `candidateIds` 时只重算指定候选。
- 新增返回字段：
  - `targeted`
  - `requestedCandidateIds`
  - `missingCandidateIds`
  - `effectiveCandidateCount`
  - `maxCandidates`
  - `truncated`

示例请求：

```json
{
  "candidateIds": [2063],
  "maxCandidates": 5
}
```

运行时验证结果：

```text
scoredCount=1
targeted=true
requestedCandidateIds=[2063]
missingCandidateIds=[]
effectiveCandidateCount=1
maxCandidates=5
truncated=false
```

`POST /api/copy-trading/leader-research/paper/fast-watch`

- 直接输出 politics/finance 等类别下的 FAST_WATCH 候选。
- 复用系统已有 `buildTrialReadiness` 规则，不引入第二套口径。
- 默认 categories 为 `politics`, `finance`。
- 可通过 `limit` 控制返回数量。
- 可通过 `includeTrialReady` 决定是否把已满足 TRIAL_READY 的候选一起返回。

示例请求：

```json
{
  "categories": ["politics", "finance"],
  "limit": 5
}
```

运行时验证结果：

```text
total=8
fastWatchCount=8
trialReadyCount=0
```

Top FAST_WATCH 候选：

| candidateId | wallet | category | score | trade_count | copyable_pnl | blocker |
| ---: | --- | --- | ---: | ---: | ---: | --- |
| 1742 | `0xe7ce284302936fd06ffc7ad05f13c648c513d53a` | finance | 97.7920 | 22 | 12.0753 | PAPER 观察不足 7 天，当前约 116 小时 |
| 1609 | `0x674887d1ac838099a48b629dff53f25b7b87ee08` | finance | 94.6003 | 54 | 9.0388 | PAPER 观察不足 7 天，当前约 86 小时 |
| 2079 | `0x983848691c445a1e235c1e49a69c49d8c4d3bcfe` | finance | 93.6058 | 32 | 8.7053 | PAPER 观察不足 7 天，当前约 83 小时 |
| 1611 | `0x75cc3b63a2f2423085e10706c78b494017b93ce1` | finance | 91.9332 | 77 | 8.4108 | PAPER 观察不足 7 天，当前约 86 小时 |
| 2063 | `0x3e5d55e7d987489ceb9a85984b43b75ad3fef957` | finance | 90.3215 | 23 | 6.1819 | PAPER 观察不足 7 天，当前约 83 小时 |

### 验证

- 后端单元测试：

```text
./gradlew test --tests 'com.wrbug.polymarketbot.controller.copytrading.research.LeaderResearchControllerTest'
BUILD SUCCESSFUL
```

- 后端打包：

```text
./gradlew bootJar
BUILD SUCCESSFUL
```

- 运行时：
  - backend tmux session：`polyhermes-backend-codex`
  - backend PID：`38933`
  - actuator health：`UP`
  - FAST_WATCH 接口验证通过。
  - targeted score 接口验证通过。

### 下一步

1. 在 Leader 研究页面展示 FAST_WATCH 列表，让候选结果不只停留在 API。
2. 将 loop 每轮处理改为：选择 FAST_WATCH/高分 PAPER -> `/paper/process` -> targeted `/paper/score` -> `/paper/fast-watch` 输出日报。
3. 对 `paper/process` 响应继续增强，返回本轮实际推进的 candidateIds 与 trade_count 变化。
4. 对 FAST_WATCH 中 finance 占比过高的问题继续补 politics 来源，避免第二目标偏离 politics/finance 80% 中的政治质量要求。

## 2026-06-29 UI Iteration：Leader 研究页展示 FAST_WATCH

本轮将上一轮新增的 FAST_WATCH 后端接口接入 Leader 研究页面，目标是让“接近可试跟但还未满 7 天观察期”的候选在系统中直接可见。

### 前端更新

- 新增前端类型：
  - `LeaderResearchFastWatchRequest`
  - `LeaderResearchFastWatchResponse`
- 新增 API client：
  - `apiService.leaderResearch.fastWatch`
  - 对应后端：`POST /api/copy-trading/leader-research/paper/fast-watch`
- Leader 研究页 `loadAll()` 并行拉取：
  - `categories=["politics","finance"]`
  - `limit=12`
  - `includeTrialReady=true`
- 页面新增“快速观察候选”卡片，展示：
  - total
  - FAST_WATCH 数
  - TRIAL_READY 数
  - 覆盖分类
  - 候选 id
  - 钱包地址
  - category
  - score
  - trade_count
  - copyable_pnl
  - filtered_ratio
  - paper age
  - stable high score window
  - 当前阻塞原因

### 运行时验证

后端：

```text
tmux session: polyhermes-backend-codex
backend pid: 38933
health: UP
```

前端：

```text
localhost:3000 正在监听
```

FAST_WATCH API 摘要：

```text
total=8
fastWatchCount=8
trialReadyCount=0
categories=[politics, finance]
top items=[1742, 1609, 2079]
```

前端构建：

```text
npm run build
BUILD SUCCESSFUL
```

### 意义

第二目标现在已经形成更清晰的可观测闭环：

```text
扫链/导入来源
  -> 候选入池
  -> PAPER 纸跟
  -> targeted score 增量评分
  -> FAST_WATCH 页面展示
  -> 等待 7 天观察期或人工复核
  -> TRIAL_READY/禁用试跟配置
```

下一步继续补两件事：

1. 让 FAST_WATCH 卡片支持一键 targeted score / paper process，减少 CLI 介入。
2. 补 politics 高质量来源，因为当前 FAST_WATCH top 仍主要集中在 finance。

## 2026-06-29 UI Action Iteration：FAST_WATCH 一键小闭环

本轮将 FAST_WATCH 卡片从“可见”推进到“可操作”，减少每轮 loop 对 CLI 的依赖。

### 前端更新

新增类型：

- `LeaderResearchPaperProcessRequest`
- `LeaderResearchPaperProcessResponse`
- `LeaderResearchPaperScoreRequest`
- `LeaderResearchPaperScoreResponse`

新增 API client：

- `apiService.leaderResearch.processPaper`
- `apiService.leaderResearch.scorePaper`

Leader 研究页“快速观察候选”卡片新增两个批量动作：

- `增量评分`
  - 读取当前 FAST_WATCH 卡片里的 candidateIds。
  - 调用 targeted `/paper/score`。
  - 完成后刷新页面。
- `推进纸跟`
  - 读取当前 FAST_WATCH 卡片里的 candidateIds。
  - 调用 `/paper/process`，`batchSize=20`。
  - 随后对同一批 candidateIds targeted `/paper/score`。
  - 完成后刷新页面。

### 验证

前端构建：

```text
npm run build
BUILD SUCCESSFUL
```

运行时 targeted score：

```text
candidateIds=[1742,1609,2079]
scoredCount=3
targeted=true
missingCandidateIds=[]
truncated=false
```

服务状态：

```text
backend :8000 UP
frontend :3000 LISTEN
```

### 新闭环

当前 UI 已支持：

```text
FAST_WATCH 页面候选
  -> 点击增量评分
  -> targeted score
  -> 刷新 FAST_WATCH

FAST_WATCH 页面候选
  -> 点击推进纸跟
  -> paper process
  -> targeted score
  -> 刷新 FAST_WATCH
```

下一步需要继续补：

1. `paper/process` 响应中返回实际推进的 candidateIds 与 trade_count 前后变化，页面才能精确显示“谁被推进了多少”。
2. 补 politics 来源，因为当前 FAST_WATCH 候选仍主要集中在 finance。

## 2026-06-29 Paper Process Observability Iteration：候选级推进证据

本轮补齐上一轮遗留的第 1 项：`paper/process` 不再只返回总计数，而是返回候选级推进明细。

### 后端变化

`LeaderPaperProcessingResult` 新增 `candidateSummaries`，每个候选包含：

- `candidateId`
- `wallet`
- `processed`
- `filtered`
- `failed`
- `beforeTradeCount`
- `afterTradeCount`
- `beforeFilteredCount`
- `afterFilteredCount`
- `beforeCopyablePnl`
- `afterCopyablePnl`

`LeaderResearchPaperProcessResponse` 对外新增同名明细，并补充：

- `tradeCountDelta`
- `filteredCountDelta`
- `copyablePnlDelta`

这样每次推进 FAST_WATCH / PAPER 候选时，系统可以知道：

1. 哪些候选真的被推进。
2. 哪些候选只是被过滤，没有增加有效纸跟样本。
3. 哪些候选的 copyable PnL 在本轮变好或变差。
4. 哪些候选接近 `paper_trade_count >= 20` 或更高置信门槛。

### 前端变化

Leader 研究页的“快速观察候选”卡片中，“推进纸跟”动作完成后会展示“最近推进结果”：

- candidate id
- 钱包
- 交易数前后变化
- 过滤数前后变化
- copyable PnL 前后变化
- 本轮处理/过滤/失败数量

这让第二目标的小闭环从：

```text
点推进 -> 只看到总 processed/filtered/failed
```

升级为：

```text
点推进 -> 看见每个候选的实际样本变化 -> targeted score -> 决定下一轮继续推进谁
```

### 验证

- 后端测试通过：
  - `LeaderPaperTradingServiceTest`
  - `LeaderResearchControllerTest`
- 前端构建通过：
  - `npm run build`

### 下一轮

下一轮继续补第 2 项：增强 politics 高质量来源。优先方向：

1. 使用 market peer / official leaderboard / external analytics 中的 politics 来源诊断。
2. 对 politics 候选执行 targeted process + targeted score。
3. 用本轮新增的 `candidateSummaries` 选择 tradeCount delta 为正、过滤率可控、PnL 未恶化的候选继续加厚。
4. 将 politics/finance 中接近 7 天观察期的 FAST_WATCH 候选输出为禁用试跟配置候选。

## 2026-06-29 Politics Recommendation Iteration：政治来源推荐动作队列

本轮补齐上一轮遗留的第 2 项中的第一段：政治来源诊断不再只是告诉系统“为什么少”，而是给出下一轮该做什么。

### 后端变化

`POST /api/copy-trading/leader-research/politics-source/diagnose` 响应新增 `recommendations`。

每条推荐包含：

- `wallet`
- `candidateId`
- `recommendation`
- `priority`
- `reason`
- `action`
- `currentState`
- `currentScore`
- `totalEvents`
- `distinctMarkets`
- `buyEvents`
- `sellEvents`
- `safePriceRatio`
- `tailPriceRatio`
- `paperTradeCount`
- `copyablePnl`
- `blockers`

推荐动作含义：

| recommendation | 含义 | 下一步 |
| --- | --- | --- |
| `IMPORT_NOW` | 未知钱包已通过政治来源导入阈值 | 导入研究池并进入预筛 |
| `SCORE_REFRESH` | 已在研究池、政治样本合格、评分接近晋级 | targeted activity score / paper promotion |
| `PAPER_PROCESS` | 已是政治 PAPER，高分但 paper trade 数不足 | targeted `/paper/process` + `/paper/score` |
| `FAST_WATCH_REVIEW` | paper 样本与 PnL 已较好 | 检查 7 天观察期与稳定评分，准备禁用试跟配置 |
| `WATCH_SOURCE` | 已在研究池但还需要等待样本 | 继续观察，不盲目推进 |

### 前端变化

Leader 研究页新增“政治推荐动作”卡片，展示：

- 推荐动作
- priority
- wallet / candidateId
- 当前 score
- paper trade count
- copyable PnL
- buy/sell 样本数量
- 推荐理由

这让政治来源从：

```text
诊断统计 -> 人工判断下一步
```

推进为：

```text
诊断统计 -> 系统推荐动作 -> 下一轮可批量导入/推进/复核
```

### 验证

- 后端测试通过：
  - `LeaderResearchPoliticsSourceDiagnoseServiceTest`
  - `LeaderResearchControllerTest`
- 前端构建通过：
  - `npm run build`

### 下一轮

把推荐动作接到可执行批处理：

1. `IMPORT_NOW`：批量导入 politics activity source / scanner source。
2. `SCORE_REFRESH`：对 candidateIds 做 targeted activity score 或 targeted paper promotion。
3. `PAPER_PROCESS`：对 candidateIds 做 targeted `/paper/process` 后 targeted `/paper/score`。
4. `FAST_WATCH_REVIEW`：输出禁用试跟配置候选，人工确认后再进入真钱跟单。

## 2026-06-29 Politics Action Iteration：政治推荐动作可执行化

本轮将上一轮的政治推荐动作队列接入第一个安全批处理按钮。

### 已接入动作

Leader 研究页“政治推荐动作”卡片新增：

```text
执行纸跟推荐
```

执行范围：

- 只选择 `recommendation = PAPER_PROCESS`
- 必须有 `candidateId`
- 只执行 targeted `/paper/process`
- 完成后执行 targeted `/paper/score`
- 把返回的 `candidateSummaries` 展示到“最近推进结果”

### 安全边界

本轮刻意只做低风险动作：

- 不导入未知钱包。
- 不创建真钱跟单配置。
- 不自动启用试跟。
- 不处理 `IMPORT_NOW`、`SCORE_REFRESH`、`FAST_WATCH_REVIEW` 的状态转换。

这样可以先把政治 PAPER 样本变厚，并通过 candidateSummaries 观察：

- 交易数是否增加。
- 过滤比例是否过高。
- copyable PnL 是否恶化。
- 是否接近 `paper_trade_count >= 20`。

### 验证

- 前端构建通过：
  - `npm run build`
- 后端测试通过：
  - `LeaderResearchPoliticsSourceDiagnoseServiceTest`
  - `LeaderPaperTradingServiceTest`
  - `LeaderResearchControllerTest`

### 下一轮

继续把剩余推荐动作接入可控批处理：

1. `IMPORT_NOW`：先做 dry-run / preview，再允许人工确认导入。
2. `SCORE_REFRESH`：如果目标仍在 DISCOVERED/CANDIDATE，需要补 targeted activity score 或 promotion 能力。
3. `FAST_WATCH_REVIEW`：输出禁用试跟配置候选，但保持人工确认，不自动真钱启用。

## 2026-06-29 Politics Import Iteration：IMPORT_NOW 定向导入

本轮将 `IMPORT_NOW` 推荐动作接成可控导入闭环。

### 后端变化

`LeaderResearchActivitySourceImportRequest` 新增：

```text
wallets: List<String>
```

当 `wallets` 非空时，activity-source import 不再做宽泛来源扫描，而是：

1. 只检查请求中的合法钱包地址。
2. 仍使用 category 对应的 marketPattern。
3. 仍使用 minEvents / minDistinctMarkets / minBuyEvents / minSellEvents / safe ratio / tail ratio 阈值。
4. 只导入重新通过后端阈值的钱包。

这保证页面上的 `IMPORT_NOW` 不会因为一次宽泛扫描而导入推荐列表之外的钱包。

### 前端变化

Leader 研究页“政治推荐动作”卡片新增：

- `预览导入`
- `确认导入`

执行规则：

- 只取 `recommendation = IMPORT_NOW` 的钱包。
- `预览导入` 使用 `dryRun=true`。
- `确认导入` 弹窗二次确认后使用 `dryRun=false`。
- 导入结果展示 selected / created / updated / skipped，以及前 5 个 preview item。

### 安全边界

确认导入后仍只是进入研究候选池：

- 不创建跟单配置。
- 不启用真钱跟单。
- 不改变 Bridge 执行策略。
- 后续仍需 activity score、paper/process、paper/score、FAST_WATCH / TRIAL_READY 检查。

### 验证

- 后端测试通过：
  - `LeaderResearchActivitySourceImportServiceTest`
  - `LeaderResearchControllerTest`
  - `LeaderResearchPoliticsSourceDiagnoseServiceTest`
- 前端构建通过：
  - `npm run build`

### 下一轮

继续接：

1. `FAST_WATCH_REVIEW`：输出禁用试跟配置候选，人工确认后才创建配置。
2. `SCORE_REFRESH`：补 targeted activity score / targeted promotion，使 DISCOVERED/CANDIDATE 政治推荐也能推进。

## 2026-06-29 Fast Watch Review Iteration：禁用试跟人工复核入口

本轮将 `FAST_WATCH_REVIEW` 推荐动作接入禁用试跟配置候选流程。

### 后端变化

政治来源诊断的推荐逻辑新增：

```text
currentState = TRIAL_READY
copyablePnl > 0
riskBlocked = false
=> FAST_WATCH_REVIEW
```

这表示候选已经通过研究状态机进入 `TRIAL_READY`，且模拟复制收益为正，可以进入人工复核。

### 前端变化

Leader 研究页“政治推荐动作”卡片新增：

- `FAST_WATCH_REVIEW` 数量标签。
- 对 `FAST_WATCH_REVIEW` 且有 `candidateId` 的候选展示按钮。
- 如果 `currentState = TRIAL_READY`，按钮为 `创建禁用试跟`。
- 如果还不是 `TRIAL_READY`，按钮显示 `等待TRIAL_READY` 并禁用。

点击 `创建禁用试跟` 后：

1. 前端先拉取候选详情。
2. 再次确认候选状态是否为 `TRIAL_READY`。
3. 打开已有的禁用试跟配置弹窗。
4. 仍需人工选择账户并确认。

### 安全边界

本轮没有放开真钱自动跟单：

- 页面只是把候选聚合到复核入口。
- 后端 `LeaderResearchApprovalService` 仍强制要求候选为 `TRIAL_READY`。
- 创建出的配置仍为 `enabled=false`。
- 后端仍禁止 Agent 自动创建启用状态的真钱配置。

### 验证

- 后端测试通过：
  - `LeaderResearchPoliticsSourceDiagnoseServiceTest`
  - `LeaderResearchApprovalServiceTest`
  - `LeaderResearchControllerTest`
- 前端构建通过：
  - `npm run build`

### 下一轮

继续补 `SCORE_REFRESH`：

1. 对 DISCOVERED/CANDIDATE 政治推荐做 targeted activity score。
2. 对接近 PAPER 的候选做 targeted promotion。
3. 形成完整链路：`IMPORT_NOW -> SCORE_REFRESH -> PAPER_PROCESS -> FAST_WATCH_REVIEW -> 禁用试跟人工确认`。

## 2026-06-29 Score Refresh Iteration：定向评分与晋级

本轮将 `SCORE_REFRESH` 推荐动作接入 targeted 评分与晋级闭环。

### 后端变化

`LeaderResearchActivityScoreRequest` 新增：

```text
candidateIds: List<Long>
```

当 `candidateIds` 非空时：

1. 只加载指定候选。
2. 只聚合指定候选的 activity metrics。
3. 不再按 state 全量扫描。

`LeaderResearchPaperPromotionRequest` 新增：

```text
candidateIds: List<Long>
```

当 `candidateIds` 非空时：

1. 只从指定候选中筛选 DISCOVERED / CANDIDATE。
2. 仍使用 minScore、category limit、risk flag、source freshness 与 state machine 规则。
3. live promotion 仍受小批量上限保护。

### 前端变化

Leader 研究页“政治推荐动作”卡片新增：

```text
刷新评分晋级
```

执行规则：

1. 取 `recommendation = SCORE_REFRESH` 且有 `candidateId` 的候选。
2. 调用 targeted `/activity-score/run`，`force=true`。
3. 调用 targeted `/activity-score/promote-paper`。
4. 展示 selected / promoted / skippedRisk 与前 5 个晋级项。

### 安全边界

该动作只推进研究链路：

- 不导入未知钱包。
- 不创建跟单配置。
- 不启用真钱跟单。
- 只允许 DISCOVERED / CANDIDATE 进入 PAPER 观察。

### 验证

- 后端测试通过：
  - `LeaderResearchActivityScoringServiceTest`
  - `LeaderResearchPaperPromotionServiceTest`
  - `LeaderResearchControllerTest`
- 前端构建通过：
  - `npm run build`

### 当前完整闭环

政治推荐动作现在已经形成可操作路径：

```text
IMPORT_NOW
  -> 预览导入 / 确认导入
  -> SCORE_REFRESH
  -> targeted activity score
  -> targeted promote-paper
  -> PAPER_PROCESS
  -> targeted paper/process + paper/score
  -> FAST_WATCH_REVIEW
  -> 禁用试跟人工确认
```

下一轮应实际运行一轮 politics 推荐闭环，观察是否能增加 PAPER 样本、FAST_WATCH 或 TRIAL_READY 候选。

## 2026-06-29 第二目标上下文补充：Leader 样本量是否足够

本轮对“现在的 leader 样本量够了吗”的结论正式纳入第二目标上下文。

结论：**原始发现样本已经足够，但可用于跟单决策的高质量样本仍不够**。

这意味着第二目标不能再用以下单一数字判断是否完成：

- Leader 管理页显示的记录数。
- 观察池中的 WATCH 数量。
- 原始研究候选是否超过 1000。
- 某个外部榜单一次性导入的钱包数量。

这些数字只能说明系统有足够的发现广度，不能说明已经有足够的可跟单 leader。

### 新的有效样本定义

后续第二目标中的“有效 leader 样本”必须同时满足更接近实盘决策的条件：

1. 分类稳定，优先 politics / finance。
2. PAPER 交易样本足够，阶段目标先看 `paper_trade_count >= 20`。
3. `copyable_pnl > 0`，且不是少量交易造成的偶然正收益。
4. BUY 与 SELL 样本都存在，不能是 buy-only 或 sell-only 假信号。
5. 过滤率可接受，不能大部分交易都被系统风控跳过。
6. 无明显 `tail_price_spray`、严重 `mixed_category_evidence`、高滑点、低流动性等风险标记。
7. 满足观察期要求，尤其是 7 天稳定观察期。
8. 能进入 FAST_WATCH / TRIAL_READY，或至少能明确说明阻塞原因。

### 第二目标当前状态口径

```text
发现广度：足够
管理页记录数：只能作为初筛池，不代表够用
高质量 PAPER 样本：不足
politics 高质量样本：偏薄
finance 高质量样本：有苗子但仍需观察期和过滤率复核
TRIAL_READY：仍是关键缺口
目标状态：ACTIVE
```

### 后续 KPI 调整

第二目标后续日报、页面和自动化任务应优先跟踪：

- `paper_trade_count >= 20` 的候选数量。
- politics / finance 中 score >= 80 且 copyable PnL 为正的候选数量。
- FAST_WATCH 数量与阻塞原因。
- TRIAL_READY 数量。
- 禁用试跟配置候选数量。
- 每轮 targeted paper/process 后实际新增的有效交易样本。
- 被过滤或淘汰的原因分布。

不再把“继续扩大原始钱包数量”作为核心 KPI。原始钱包池已经够大，下一阶段要把候选推进到可验证、可复制、可复核的决策层。

### 固化到第二目标执行上下文

从本轮开始，第二目标的上下文按以下口径执行：

```text
1000+ 高质量 leader != 1000+ 原始钱包
555/600+ Leader 管理记录 != 样本量足够
scanner 候选很大 != 可以实盘跟单

有效样本 = 分类稳定 + PAPER 样本足够 + 正 copyable PnL + BUY/SELL 样本完整 + 风控过滤可接受 + 观察期达标
```

因此，第二目标仍保持 `ACTIVE`，但目标重心从“继续堆原始候选数量”切换为“把已有 politics / finance 候选推进到有效决策样本”。

后续每一轮 loop 必须回答三个问题：

1. 本轮是否增加了 `paper_trade_count >= 20` 且 PnL 为正的 politics / finance 候选？
2. 本轮是否产生了新的 FAST_WATCH / TRIAL_READY / 禁用试跟候选？
3. 如果没有，阻塞原因是样本不足、观察期不足、过滤率过高、风险标记过重，还是分类来源不足？

如果连续多轮 `PAPER_PROCESS = 0` 且 `FAST_WATCH_REVIEW = 0`，应视为“高质量样本薄”，下一轮优先补 politics / finance 来源或调整 targeted paper/process 目标，而不是继续展示原始池增长。

## 2026-06-29 Recommendation Execution Iteration：后端政治推荐闭环执行器

本轮把政治推荐动作从“前端逐个按钮编排”继续下沉到后端，形成可复用的闭环执行接口。

### 新增接口

```text
POST /api/copy-trading/leader-research/politics-source/execute-recommendations
```

默认请求为 `dryRun=true`，用于预演下一轮政治推荐闭环。

接口会：

1. 重新运行 politics source diagnose。
2. 从 `recommendations` 中抽取：
   - `IMPORT_NOW`
   - `SCORE_REFRESH`
   - `PAPER_PROCESS`
   - `FAST_WATCH_REVIEW`
3. 生成 `plannedActions`，展示每类动作选中了哪些 wallet 或 candidate。
4. 在 dry-run 下只做安全预览。
5. 在 `dryRun=false` 时才真实执行：
   - 定向 activity-source import
   - 定向 activity score
   - 定向 promote-paper
   - 定向 paper/process
   - 定向 paper score

### 安全边界

该接口不会创建真钱跟单配置，也不会启用真钱跟单。

`FAST_WATCH_REVIEW` 只返回候选 id，仍要求人工进入禁用试跟配置复核流程。

`dryRun=true` 时：

- 不执行 activity score 写入。
- 不执行 paper/process。
- 不执行 paper score 写入。
- 只允许 import service 以 dry-run 方式做预览。
- promotion 也以 dry-run 方式返回可晋级预览。

### 前端接入

Leader 研究页“政治推荐动作”卡片新增：

```text
后端预演闭环
```

点击后调用后端新接口，展示：

- recommendationCounts
- plannedActions
- 每个动作 selectedCount
- dry-run 跳过原因

该按钮用于验证后端批处理计划是否与页面上单项按钮一致，也为后续定时任务/日报复用同一套编排逻辑打基础。

### 验证

后端测试通过：

```text
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchControllerTest
```

前端构建通过：

```text
npm run build
```

后端构建通过：

```text
./gradlew bootJar
```

运行态：

- 后端已通过 `run_backend_local.sh` 重新启动到 `:8000`。
- `/actuator/health` 返回 `UP`。
- 未带 token 调用新接口返回“缺少认证令牌”，说明接口路由已进入后端鉴权链；页面登录态下可直接使用。

### 下一轮

下一轮应在页面登录态下实际点击“后端预演闭环”，比对：

1. `plannedActions` 是否与当前政治推荐卡片数量一致。
2. 是否出现可推进的 politics PAPER 候选。
3. 是否有 TRIAL_READY 或 FAST_WATCH_REVIEW 候选。
4. 如果 dry-run 计划合理，再人工决定是否执行 live 模式或做成每日定时任务。

## 2026-06-29 Recommendation Execution Snapshot Iteration：闭环快照持久化

本轮把政治推荐闭环从“可执行接口”继续推进到“可追踪、可日报复用”的状态。

### 新增表

```text
leader_research_recommendation_execution
```

对应 Flyway：

```text
V70__create_leader_recommendation_execution.sql
```

该表记录每次后端推荐闭环 dry-run / live 执行的快照：

- category
- status
- dryRun
- actions
- recommendationCounts
- plannedActions
- resultSummary
- request
- errorMessage
- startedAt / finishedAt / durationMs

### 新增接口

```text
POST /api/copy-trading/leader-research/politics-source/recommendation-executions/latest
```

用途：

1. 页面可以直接看到最近一次后端闭环是否运行过。
2. 后续优化日报可以读取最近快照，展示本轮推荐了多少、计划推进多少、实际执行了多少。
3. 定时任务上线后，可以用同一张表追踪每轮效果，避免状态只留在日志或前端 toast 中。

### 执行器变化

`LeaderResearchPoliticsRecommendationExecutionService` 现在会：

1. 在执行开始时记录 startedAt。
2. 成功后保存 `SUCCESS` 快照。
3. 失败时保存 `FAILED` 快照并保留 errorMessage。
4. 支持查询最近一次 politics 快照。

### 前端变化

Leader 研究页“政治推荐动作”卡片现在会展示：

```text
最近后端闭环
```

显示内容包括：

- execution id
- SUCCESS / FAILED
- dry-run / live
- startedAt
- plannedActions 摘要

点击“后端预演闭环”后会刷新页面数据，让最近快照立刻可见。

### 验证

后端测试通过：

```text
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchControllerTest
```

前端构建通过：

```text
npm run build
```

后端构建通过：

```text
./gradlew bootJar
```

运行态：

- 已使用 `run_backend_local.sh` 干净重启后端。
- 新 Java PID：`88098`。
- `/actuator/health` 返回 `UP`。
- 启动日志显示 Flyway 正常完成，服务启动成功。

### 下一轮

下一轮应使用登录态页面实际点击一次“后端预演闭环”，确认：

1. 页面能写入并展示最新 execution snapshot。
2. plannedActions 和 politics 推荐动作数量一致。
3. resultSummary 能支撑日报展示。
4. 若 dry-run 结果稳定，再增加每日定时 dry-run 或人工确认后的 live 执行入口。

## 2026-06-29 Scheduled Recommendation Dry-run Iteration：定时安全预演

本轮将政治推荐闭环从“页面手动预演”推进到“系统定时安全预演”。

### 新增定时任务

`LeaderResearchJobService` 新增：

```text
scheduledRecommendationDryRun()
```

默认配置：

```properties
leader.research.recommendation-dry-run.enabled=true
leader.research.recommendation-dry-run.fixed-delay-ms=3600000
```

即默认每小时触发一次。

### 启动条件

该定时任务必须同时满足：

1. `leader.research.enabled=true`
2. `leader.research.recommendation-dry-run.enabled=true`
3. 第二目标处于 `ACTIVE`

否则直接跳过。

### 安全边界

定时任务只执行：

```kotlin
execute(dryRun = true)
```

因此只会：

- 重新诊断 politics recommendations。
- 生成 plannedActions。
- 写入 `leader_research_recommendation_execution` 快照。

不会：

- 导入未知钱包。
- 执行 activity score 写入。
- 推进 PAPER。
- 创建禁用试跟配置。
- 启用真钱跟单。

### 目标意义

这让第二目标具备真正的 loop 形态：

```text
定时触发
  -> politics source diagnose
  -> recommendation plan
  -> snapshot 持久化
  -> 页面/日报读取快照
  -> 人工决定是否执行 live 推进
```

即使不打开页面，系统也能持续留下“这一轮有没有更好的 politics 候选、阻塞在哪里、下一步应该做什么”的证据。

### 验证

后端测试通过：

```text
LeaderResearchJobServiceTest
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchControllerTest
```

前端构建通过：

```text
npm run build
```

后端构建通过：

```text
./gradlew bootJar
```

代码检查通过：

```text
git diff --check
```

运行态：

- 后端已重启。
- 当前 Java PID：`21439`。
- `/actuator/health` 返回 `UP`。
- 启动日志显示服务正常启动，无 Flyway/Bean 初始化错误。

### 下一轮

下一轮应把 recommendation execution snapshot 接入优化日报页面，展示：

1. 最近一次 dry-run 时间。
2. IMPORT_NOW / SCORE_REFRESH / PAPER_PROCESS / FAST_WATCH_REVIEW 数量。
3. plannedActions。
4. 如果连续几轮 PAPER_PROCESS 为 0 或 FAST_WATCH_REVIEW 为 0，日报要给出“politics 高质量样本仍不足”的明确提示。

## 2026-06-29 Optimization Daily Snapshot Iteration：日报展示推荐闭环

本轮把 recommendation execution snapshot 接入优化日报页面。

### 页面入口

```text
/optimization-daily
```

新增卡片：

```text
第二目标推荐闭环
```

### 展示内容

卡片展示最近一次 politics recommendation execution snapshot：

- `IMPORT_NOW`
- `SCORE_REFRESH`
- `PAPER_PROCESS`
- `FAST_WATCH_REVIEW`
- dry-run / live 模式
- durationMs
- startedAt
- plannedActions

### 状态判断

日报会根据最近快照给出状态：

- 暂无快照：等待下一次推荐闭环 dry-run。
- 执行失败：展示 errorMessage。
- `PAPER_PROCESS = 0` 且 `FAST_WATCH_REVIEW = 0`：提示 politics 高质量样本仍不足。
- `FAST_WATCH_REVIEW > 0`：提示存在可人工复核候选。
- 仅 `PAPER_PROCESS > 0`：提示可继续加厚纸跟样本。

### 目标意义

第二目标现在从：

```text
扫链/诊断结果只在 Leader 研究页可见
```

推进为：

```text
定时 dry-run -> 快照持久化 -> 优化日报展示 -> 人工/下一轮 loop 决策
```

这让每日检查时可以直接看到：

1. 是否有新的 politics 钱包值得导入。
2. 是否有 politics 候选需要刷新评分。
3. 是否有 politics PAPER 候选需要推进纸跟。
4. 是否已经出现可复核的 FAST_WATCH / TRIAL_READY 候选。

### 验证

前端构建通过：

```text
npm run build
```

代码检查通过：

```text
git diff --check
```

### 下一轮

下一轮应观察 `/optimization-daily` 的快照状态：

1. 如果长期无快照，检查 `LEADER_RESEARCH_ENABLED` 和第二目标状态。
2. 如果连续多轮 `PAPER_PROCESS=0` 且 `FAST_WATCH_REVIEW=0`，继续扩大 politics/finance 高质量来源。
3. 如果出现 `PAPER_PROCESS>0`，执行 targeted paper/process 加厚样本。
4. 如果出现 `FAST_WATCH_REVIEW>0`，进入禁用试跟配置人工复核。

## 2026-06-29 Recommendation History Iteration：最近多轮趋势

本轮把第二目标推荐闭环从“最近一次快照”升级为“最近多轮趋势”。

### 新增接口

```text
POST /api/copy-trading/leader-research/politics-source/recommendation-executions/recent
```

接口返回最近 politics recommendation execution snapshots，默认取最近 5 轮。

### 页面变化

`/optimization-daily` 的“第二目标推荐闭环”卡片现在会展示：

- 最近 5 轮 execution id。
- 每轮运行时间。
- 每轮 `PAPER_PROCESS` 数量。
- 每轮 `FAST_WATCH_REVIEW` 数量。
- 当前连续薄样本轮次。

薄样本轮次定义：

```text
status = SUCCESS
PAPER_PROCESS = 0
FAST_WATCH_REVIEW = 0
```

如果最新一轮不是薄样本，则连续薄样本轮次重置为 0。

### 目标意义

只看最近一次快照容易误判：

- 单轮没有候选，可能只是正常波动。
- 连续多轮没有 `PAPER_PROCESS` 和 `FAST_WATCH_REVIEW`，才说明 politics 高质量来源或 PAPER 加厚链路需要调整。

因此后续日报判断应优先使用“连续薄样本轮次”：

1. `0-1` 轮：观察即可。
2. `2` 轮：开始检查 plannedActions 与来源分布。
3. `>=3` 轮：下一轮 loop 优先补 politics / finance 来源，或调整 targeted paper/process 目标。

### 验证

前端构建通过：

```text
npm run build
```

后端定向测试通过：

```text
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchControllerTest
```

### 下一轮

下一轮应在服务重启后观察 `/optimization-daily`：

1. recent 快照是否随定时 dry-run 增加。
2. 连续薄样本轮次是否与最近 5 轮标签一致。
3. 如果连续薄样本轮次 >= 3，按本文规则优先补源或调整 PAPER 加厚目标。

## 2026-06-29 Startup Recommendation Dry-run Iteration：启动后自举快照

本轮实际检查数据库时发现：

```text
leader_research_recommendation_execution = 0
```

这表示虽然已经有定时 recommendation dry-run 代码，优化日报仍然可能在服务重启后长时间没有任何第二目标推荐闭环证据。

### 根因

recommendation dry-run 被完整扫链开关一起拦住：

```text
leader.research.enabled=false
```

完整扫链可能较重，关闭它是合理的；但 recommendation dry-run 只是重新诊断 politics recommendations 并写入快照，不导入钱包、不推进 PAPER、不创建真钱配置。因此它不应该依赖完整扫链开关。

### 修正

recommendation dry-run 现在只受以下条件控制：

1. `leader.research.recommendation-dry-run.enabled=true`
2. 第二目标 `leader-discovery-goal-2` 处于 `ACTIVE`

并新增启动后自举 dry-run：

```properties
leader.research.recommendation-dry-run.startup-delay-ms=30000
```

含义：

- 默认服务启动 30 秒后执行一次安全 dry-run。
- 之后继续按 `fixed-delay-ms` 定时执行。
- 如果设为负数，则关闭启动自举 dry-run。

### 运行验证

本轮以 1 秒启动延迟重启后端验证，数据库已写入 politics recommendation execution 快照：

```text
execution_count = 2
latest status = SUCCESS
IMPORT_NOW = 1
FAST_WATCH_REVIEW = 3
PAPER_PROCESS = 0
```

最新 FAST_WATCH_REVIEW 候选：

| candidateId | wallet | score | state | trades | copyablePnL | filteredRatio | paperAge |
| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: |
| 2361 | `0xad5353afe30c2da57709e2704ef3ccdcf67eef24` | 88.59 | PAPER | 21 | 8.9957 | 0.4324 | 74h |
| 786 | `0x30a28af9d4694b1967582a7915c6e048b7bc0b35` | 79.16 | PAPER | 22 | 0.3047 | 0.0000 | 123h |
| 153 | `0xc8ab97a9089a9ff7e6ef0688e6e591a066946418` | 77.25 | PAPER | 26 | 1.9726 | 0.3500 | 123h |

当前判断：

- 第二目标不是“无候选”。
- 最新 politics 闭环不是连续薄样本，因为已经有 `FAST_WATCH_REVIEW=3`。
- 三个候选仍是 `PAPER`，不是 `TRIAL_READY`，下一步应继续观察 7 天门槛、过滤率和稳定评分。
- `2361` 分数和 PnL 最强，但过滤率偏高，需要人工复核交易质量。

### 页面增强

`/optimization-daily` 的“第二目标推荐闭环”卡片现在除了数量，还会展示：

- FAST_WATCH_REVIEW 候选 ID。
- IMPORT_NOW 待导入钱包短地址。

这样日报可以直接回答“候选是哪几个”，不需要再去数据库或日志里翻 plannedActions。

### 验证

```text
LeaderResearchJobServiceTest
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchControllerTest
npm run build
./gradlew bootJar
git diff --check
```

均已通过。

## 2026-06-29 Review Decision UI Iteration：复核候选下一步动作

上一轮日报已经能展示 FAST_WATCH_REVIEW 候选质量，但仍需要人工读 blockers 后自行判断下一步。

本轮在 `/optimization-daily` 中新增复核候选动作标签。

### 动作标签

前端根据后端返回的：

- `trialReadiness.level`
- `trialReadiness.blockers`
- `trialReadiness.fastWatchBlockers`
- `filteredRatio`

生成候选下一步：

| 标签 | 含义 |
| --- | --- |
| `可试跟复核` | 已满足 TRIAL_READY，可人工创建禁用试跟配置 |
| `等观察期` | 主要卡在 PAPER 观察不足 7 天 |
| `复核过滤率` | 过滤率偏高，需要检查 leader 交易是否大量不可复制 |
| `等评分稳定` | 评分或稳定高分次数不足 |
| `人工复核` | 其他 blockers，需要人工检查市场类型、交易质量和可复制性 |

### 目标意义

FAST_WATCH_REVIEW 不等于可以直接真钱跟单。

这层提示用于避免两个误判：

1. 只看 score / PnL 高，就把候选直接推入跟单配置。
2. 只看到 blockers，就忽略其实只差观察期的候选。

对于当前 politics 候选：

- `#2361` 分数与 PnL 强，但过滤率偏高，日报应提示复核过滤率。
- `#786` / `#153` 仍需要结合观察期、评分和交易质量继续看。

### 验证

```text
npm run build
git diff --check
```

均已通过，后端保持 `UP`。

## 2026-06-29 Disabled Trial Approval Entry Iteration：日报接入禁用试跟入口

本轮把 `/optimization-daily` 的复核候选从“只给下一步判断”继续推进到“可承接安全审批”。

### 页面变化

在“复核候选质量”中新增按钮：

```text
创建禁用试跟
```

但按钮只有在：

```text
trialReadiness.level = TRIAL_READY
```

时才可点击。

对于当前仍处于 FAST_WATCH / PAPER 的候选，按钮显示：

```text
等待TRIALREADY
```

并保持禁用。

### 安全流程

点击创建时，页面不会直接用列表里的摘要数据创建配置，而是：

1. 调用 `leaderResearch.detail(candidateId)` 重新拉候选详情。
2. 前端再次确认 `candidate.researchState = TRIAL_READY`。
3. 弹出人工确认窗口。
4. 要求选择跟单账户。
5. 调用：

```text
POST /api/copy-trading/leader-research/approval/create-disabled-trial-config
confirm = true
```

### 安全边界

后端仍强制：

- 候选必须是 `TRIAL_READY`。
- 必须显式 `confirm=true`。
- 创建出来的跟单配置为 `enabled=false`。
- 不会自动真钱跟单。

页面弹窗也明确提示：

```text
只创建禁用状态配置；创建后仍需要你在跟单配置中手动启用。
```

### 目标意义

这让第二目标形成更完整但仍安全的人工闭环：

```text
推荐 dry-run
  -> FAST_WATCH_REVIEW
  -> 日报展示质量与下一步动作
  -> 等待 TRIAL_READY
  -> 人工创建禁用试跟配置
  -> 人工另行启用真钱跟单
```

当前 `#2361/#786/#153` 仍未进入 TRIAL_READY，因此不会在日报中允许创建配置。

### 验证

```text
npm run build
git diff --check
```

均已通过，后端保持 `UP`。

## 2026-06-29 Recommendation Review Detail Iteration：复核候选质量进入日报

上一轮 `/optimization-daily` 已经能显示 FAST_WATCH_REVIEW 候选 ID，但仍不足以直接判断“谁值得复核”。

本轮将 recommendation execution snapshot 扩展为可携带候选详情：

```text
reviewCandidates: LeaderResearchFunnelCandidate[]
```

来源：

1. 从最新 / 最近 execution snapshot 的 `plannedActions` 中提取 `FAST_WATCH_REVIEW.candidateIds`。
2. 调用 `LeaderResearchService.funnelCandidatesByIds(candidateIds)`。
3. 复用 Leader 研究页已有的 `trialReadiness` 逻辑，不重复实现第二套复核标准。

### reviewCandidates 字段

每个复核候选包含：

- candidateId
- wallet
- category
- score
- paper trade count
- filtered ratio
- copyable PnL
- max drawdown
- research state
- trialReadiness
  - level
  - label
  - blockers
  - fastWatchBlockers
  - ageHours
  - stableHighScoreCount

### 页面变化

`/optimization-daily` 的“第二目标推荐闭环”卡片新增：

```text
复核候选质量
```

展示每个候选的：

- candidateId
- readiness 标签
- category
- 分数
- paper 交易数
- copyable PnL
- filtered ratio
- PAPER 观察时长
- wallet 短地址

这样日报可以直接回答：

```text
FAST_WATCH_REVIEW 是哪几个？
哪个分数最高？
哪个 PnL 最好？
哪个过滤率过高？
是否只是 PAPER 观察期未满？
```

### 当前运行态验证

重启后端后，推荐闭环快照持续写入：

```text
leader_research_recommendation_execution = 9
latest status = SUCCESS
latest FAST_WATCH_REVIEW = 3
```

这说明当前第二目标不是“完全没有候选”，而是已经出现 politics 复核候选，需要继续判断候选质量与观察期。

### 验证

```text
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchJobServiceTest
LeaderResearchControllerTest
npm run build
./gradlew bootJar
git diff --check
```

均已通过。

## 2026-06-29 Finance Source Diagnose Context Update：金融来源诊断纳入第二目标

本轮将“政治、金融为主，占比 80%”的第二目标口径进一步落到系统上下文。

此前推荐闭环主要围绕 politics：

```text
politics diagnose
  -> recommendation queue
  -> dry-run snapshot
  -> optimization daily review
```

这能解决政治样本的加厚与复核问题，但仍有一个目标偏差：finance 是第二目标的主策略类别之一，却缺少同等的来源诊断可视化。如果只继续强化 politics，系统会误以为第二目标在推进，实际却可能没有把 finance 候选质量纳入每日判断。

### 本轮结论

第二目标后续应按 `politics + finance` 双主线看待主策略样本：

1. politics 与 finance 都属于主策略 80% 的核心候选来源。
2. leader 样本是否足够，不能只看 politics FAST_WATCH / TRIAL_READY。
3. finance 需要先进入诊断层，确认来源质量、PAPER 厚度、过滤率、PnL、risk bucket 后，再决定是否接入自动推荐执行。
4. finance 在未形成稳定 dry-run 证据前，只可用于观察和人工判断，不应自动导入、不应自动创建跟单配置。

### 工程上下文

后端 `LeaderResearchPoliticsSourceDiagnoseRequest` 已新增：

```text
category
```

诊断服务会根据 category 选择市场分类规则：

```text
LeaderResearchMarketCategoryPatterns.patternFor(category)
```

当前支持：

| category | 用途 |
| --- | --- |
| `politics` | 继续服务政治来源诊断、推荐队列和 dry-run 闭环 |
| `finance` | 新增金融来源诊断，先进入可观测层 |

前端 Leader 研究页新增：

```text
金融来源诊断
```

展示内容包括：

- IMPORT_NOW 数量。
- SCORE_REFRESH 数量。
- PAPER_PROCESS 数量。
- FAST_WATCH_REVIEW 数量。
- 扫描钱包数。
- 可导入候选。
- PAPER 候选。
- 高分干净候选。
- 前几类 bucket 分布。

### 安全边界

finance 本轮只接入诊断，不接入自动执行：

```text
可以观察 finance 候选质量
可以看 finance recommendation 分布
不自动导入钱包
不自动推进 PAPER
不自动创建禁用试跟配置
不启用真钱跟单
```

原因是 finance 样本需要先确认是否存在和 politics 不同的风险形态，例如宏观事件拥挤、价格跳变、收盘结算规则差异、流动性不足或短窗口套利噪音。

### 对第二目标的影响

从本轮开始，第二目标的主策略进展应同时看：

| 指标 | 目标含义 |
| --- | --- |
| politics FAST_WATCH / TRIAL_READY | 政治主线是否出现可复核 leader |
| finance diagnose recommendations | 金融主线是否有可加厚来源 |
| finance PAPER / clean high | 金融候选是否从发现广度进入决策深度 |
| recommendation execution snapshot | 是否有持续 dry-run 证据 |
| disabled trial candidates | 是否真正产生人工可复核的禁用试跟候选 |

下一轮建议把 recommendation execution snapshot 从 politics-only 升级为 primary categories：

```text
politics dry-run snapshot
finance dry-run snapshot
primary-category summary
```

只有当 finance dry-run 连续多轮稳定出现 `PAPER_PROCESS` 或 `FAST_WATCH_REVIEW`，再考虑接入确认式导入或 targeted paper/process。

### 验证

本轮相关验证已通过：

```text
LeaderResearchPoliticsSourceDiagnoseServiceTest
LeaderResearchControllerTest
npm run build
./gradlew bootJar
git diff --check
```

后端已重启并保持健康：

```text
/actuator/health = UP
```

## 2026-06-30 Primary Category Snapshot Iteration：主策略类别推荐快照

上一轮已经把 finance 接入来源诊断，但推荐闭环快照仍然只证明 politics。

本轮把第二目标推荐闭环从：

```text
politics-only dry-run snapshot
```

升级为：

```text
politics dry-run snapshot
finance dry-run snapshot
primary-category summary
```

### 本轮结论

第二目标后续每日判断不能只看 politics。主策略 80% 的目标需要同时看到：

1. politics 是否持续出现 PAPER_PROCESS / FAST_WATCH_REVIEW。
2. finance 是否持续出现 PAPER_PROCESS / FAST_WATCH_REVIEW。
3. 两个类别是否都只是“原始候选多”，还是已经进入可复核样本。
4. finance 是否在安全 dry-run 中表现稳定，再决定是否进入确认式导入或 targeted paper/process。

### 后端变化

`LeaderResearchPoliticsRecommendationExecutionService` 已支持按 category 执行和落库：

```text
execute(request.diagnose.category)
```

新增能力：

```text
executePrimaryCategoryDryRuns()
latestPrimaryCategoryExecutions()
recentPrimaryCategoryExecutions()
```

新增接口：

```http
POST /api/copy-trading/leader-research/primary-source/recommendation-executions/latest
POST /api/copy-trading/leader-research/primary-source/recommendation-executions/recent
```

`LeaderResearchJobService` 的 scheduled/startup recommendation dry-run 现在会同时跑：

```text
politics
finance
```

### 安全边界

finance 仍然不进入自动真钱链路。

即使外部请求把 finance 设为 `dryRun=false`，后端也会强制按 safe dry-run 处理：

```text
finance import = dry-run only
finance activity score = not executed
finance paper/process = not executed
finance paper score = not executed
finance follow config creation = not executed
```

这保证 finance 先积累可观测证据，不会因为页面或定时任务误操作进入实盘。

### 前端变化

`/optimization-daily` 的“第二目标推荐闭环”改为主类别汇总：

- IMPORT_NOW / SCORE_REFRESH / PAPER_PROCESS / FAST_WATCH_REVIEW 使用 politics + finance 合计。
- 展示每个 category 的最新快照标签。
- 最近轮次标签包含 category，避免 politics / finance 混在一起。
- 复核候选质量从各主类别快照聚合。
- 健康提示从“politics 样本偏薄”升级为“politics / finance 主策略样本偏薄”。

### 运行态验证

后端重启后健康检查：

```text
/actuator/health = UP
```

数据库已有新快照：

| id | category | status | dry_run | FAST_WATCH_REVIEW |
| ---: | --- | --- | ---: | ---: |
| 24 | politics | SUCCESS | 1 | 3 |
| 25 | finance | SUCCESS | 1 | 2 |

这证明主策略类别推荐闭环已经能在服务启动后自动留下 politics + finance 两条证据链。

### 验证

本轮通过：

```text
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchJobServiceTest
LeaderResearchControllerTest
npm run build
./gradlew bootJar
git diff --check
```

### 下一步

下一轮应重点观察 finance dry-run 是否连续多轮稳定出现候选：

1. 如果 finance 连续出现 FAST_WATCH_REVIEW，进入人工复核质量与过滤率。
2. 如果 finance 只有 IMPORT_NOW / SCORE_REFRESH，先加厚 activity sample 与 PAPER。
3. 如果 politics / finance 任一类别连续 3 轮薄样本，优先补该类别来源，而不是继续扩大原始钱包总数。

## 2026-06-30 Category Bottleneck Observability Iteration：按类别观察瓶颈

主类别快照已经能同时写入 politics 与 finance，但如果页面只显示合并后的连续薄样本轮次，仍然容易误判：

```text
politics 有候选，finance 偏薄
finance 有候选，politics 偏薄
两者都薄
两者都出现 FAST_WATCH_REVIEW
```

这四种情况需要不同动作，不能被一个合并数字覆盖。

### 本轮运行态证据

数据库已连续产出 primary category 快照：

| id | category | status | dry_run | IMPORT_NOW | FAST_WATCH_REVIEW |
| ---: | --- | --- | ---: | ---: | ---: |
| 26 | politics | SUCCESS | 1 | 4 | 3 |
| 27 | finance | SUCCESS | 1 | 0 | 2 |

当前含义：

- politics：仍有待导入来源，同时已有 3 个 FAST_WATCH_REVIEW。
- finance：暂无 IMPORT_NOW，但已有 2 个 FAST_WATCH_REVIEW。
- 两个主策略类别都不是完全断供，下一步应看复核候选质量、观察期、过滤率和是否进入 TRIAL_READY。

### 页面变化

`/optimization-daily` 的“第二目标推荐闭环”卡片新增 politics / finance 独立状态块：

每个类别展示：

- 类别健康标签：
  - 暂无快照
  - 失败
  - 可复核
  - 可加厚
  - 待推进
  - 样本偏薄
- 连续薄样本轮次。
- IMPORT / SCORE / PAPER / REVIEW 计数。
- 最近快照 id 与时间。

### 执行规则

后续日报判断按以下口径执行：

| 情况 | 下一步 |
| --- | --- |
| 某类别连续薄样本 >= 3 | 优先补该类别来源 |
| 某类别 PAPER_PROCESS > 0 | 执行 targeted paper/process 加厚，不扩大原始钱包 |
| 某类别 FAST_WATCH_REVIEW > 0 | 进入复核候选质量、过滤率、观察期检查 |
| politics 有 IMPORT_NOW 但 finance 没有 | politics 可继续补源；finance 先复核现有候选质量 |
| finance 有 REVIEW 但无 IMPORT_NOW | 不急于扩 finance 来源，先看候选是否能转 TRIAL_READY |

### 验证

```text
npm run build
```

已通过。

## 2026-07-01 Trial Readiness ETA Iteration：可试跟倒计时

当前第二目标已经能产出 FAST_WATCH_REVIEW 候选，但人工仍需要知道：

```text
这个 leader 是质量不够，还是只是观察期没到？
还差多久可以再次复核 TRIAL_READY？
```

### 当前候选证据

| candidate | score | paper trades | copyable PnL | filtered ratio | 观察期状态 |
| ---: | ---: | ---: | ---: | ---: | --- |
| 2361 | 88.59 | 21 | 8.9957 | 43.24% | 距离 7 天还差约 39.5h |
| 786 | 79.16 | 22 | 0.3047 | 0.00% | 观察期够，但 score < 80 |
| 153 | 77.25 | 26 | 1.9726 | 35.00% | 观察期够，但 score < 80 |

结论：

- `#2361` 是当前最强候选，但还不能创建禁用试跟配置，因为 PAPER 观察期未满 7 天。
- `#153/#786` 不能仅因观察期满足就推进，当前主要 blocker 是评分低于 TRIAL_READY 门槛。

### 工程变化

`LeaderResearchTrialReadinessDto` 新增字段：

```text
requiredAgeHours
hoursUntilTrialReady
trialReadyAt
```

这些字段由 `LeaderResearchService.buildTrialReadiness()` 根据 PAPER session startedAt 和 7 天观察期计算。

前端展示：

- `/leader-research`：
  - 优先候选展示“还差 Xh / 预计时间”。
  - 快速观察候选展示“还差 Xh / 预计时间”。
- `/optimization-daily`：
  - 复核候选质量标签中展示 TRIAL_READY ETA。

### 执行意义

后续第二目标日报可以明确区分：

| 情况 | 操作 |
| --- | --- |
| 高分、PnL 正、观察期未满 | 等待 ETA，到点自动/人工复核 |
| 观察期已满但 score < 80 | 不推进，继续加厚样本或观察评分 |
| 过滤率偏高 | 人工复核可复制性，避免风控大面积跳过 |
| ETA 已到且 blockers 清空 | 创建禁用试跟配置，等待人工启用 |

### 验证

```text
LeaderResearchPoliticsRecommendationExecutionServiceTest
LeaderResearchControllerTest
npm run build
./gradlew bootJar
git diff --check
```

均已通过；后端已重启并保持：

```text
/actuator/health = UP
```
