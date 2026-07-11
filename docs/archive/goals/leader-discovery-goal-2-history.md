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

- `docs/archive/goals/leader-discovery-goal-2-history.md`
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

## 2026-07-09 Copyable Smart Money Plan：从“盈利钱包”升级为“可复制 leader”

### 背景

基于对 X 文章 `MrRyanChi` 关于“蒸馏聪明钱/盈利钱包分层”的公开摘要分析，第二目标需要进一步收紧定义：

```text
不是所有盈利钱包都值得跟单。
目标不是找到“赚钱钱包”，而是找到“赚钱方式可复制、可执行、可退出”的 leader。
```

这与当前第二目标一致，但需要把“可复制性”从人工判断升级为系统评分与日报可观测指标。

### 核心判断

盈利钱包至少应拆成以下机制类型：

| 类型 | 是否适合自动跟单 | 原因 |
| --- | --- | --- |
| human_directional | 可进入试跟候选 | 主要靠方向判断，交易节奏可能可复制 |
| whale | 默认不自动跟 | 大仓位可能影响盘口，我们跟随会变成被动接盘 |
| insider_like | 观察信号，不直接跟 | 信息优势不可复制，且入场窗口很短 |
| bot_hft | 不跟 | 速度优势不可复制 |
| market_maker_lp | 不跟 | 收益来自价差、库存和做市结构，不是方向判断 |
| arbitrage | 不跟 | 收益来自路径/执行能力，不适合 Polymtrade bridge 跟单 |
| low_price_tail_risk | 不跟或强限制 | 长尾低价分散铺单会被固定金额放大风险 |
| rebalance_churn | 不跟或降权 | 频繁同价买卖/调仓会制造执行成本与噪音 |

### 第二目标口径调整

原目标：

```text
积累 1000+ 高质量 leader，按政治、金融为主进行分类评分。
```

升级后目标：

```text
积累 1000+ 已分层的钱包样本，并从中筛出可复制 leader。
可进入禁用试跟/真钱跟单的 leader 必须优先满足 human_directional 或等价可复制机制。
```

也就是说，原始样本数、胜率、PnL 只能作为入口指标，不能直接决定跟单。

### 改进计划

#### 阶段 1：增加 leader 机制标签

目标：

- 为候选 leader 增加 `strategy_type` 或等价风险标签。
- 最低要能识别：
  - `human_directional`
  - `whale`
  - `bot_hft`
  - `market_maker_lp`
  - `arbitrage`
  - `low_price_tail_risk`
  - `rebalance_churn`
  - `unknown`

初始可用规则：

| 信号 | 标签倾向 |
| --- | --- |
| 交易频次极高、间隔稳定、单笔小且重复 | bot_hft |
| 同一市场/互斥 outcome 高频双向进出 | market_maker_lp 或 arbitrage |
| 大额交易占比极高、会明显影响盘口 | whale |
| 大量低价 `<0.10` 分散 BUY | low_price_tail_risk |
| 同市场短窗口多次高买低卖/同价买卖 | rebalance_churn |
| 中低频、方向明确、有 BUY/SELL 闭环 | human_directional |

#### 阶段 2：把“可复制性”纳入评分

新增或强化评分项：

| 评分项 | 含义 |
| --- | --- |
| copyability_score | 我们按 Bridge 规则能否复制成交 |
| exit_quality_score | SELL 是否及时、完整、可跟 |
| mechanism_score | 赚钱方式是否属于可复制方向判断 |
| execution_fit_score | 价格、金额、频次是否适合小账户 |
| churn_penalty | 频繁调仓/同价买卖惩罚 |
| tail_risk_penalty | 低价长尾铺单惩罚 |

候选进入 `TRIAL_READY` 前必须满足：

```text
strategy_type in [human_directional, unknown_but_copyable]
copyability_score >= 阈值
exit_quality_score >= 阈值
tail_risk_penalty 不为 hard block
churn_penalty 不为 hard block
```

#### 阶段 3：回测改为“可复制回测”

现有 paper/backtest 需要继续从 leader 原始收益，升级到本地可复制收益：

- 按本地 Bridge 延迟模拟成交。
- 按当前 BUY 风控模拟过滤。
- SELL 按本地持仓封顶。
- 固定金额/比例金额都要模拟。
- 记录“leader 赚钱但本地不可复制”的原因。

输出字段建议：

```text
leader_pnl
copyable_pnl
copy_gap
filtered_buy_count
missed_sell_count
same_market_churn_count
low_price_tail_count
high_price_low_upside_count
```

#### 阶段 4：页面和日报可观测

`/leader-research` 和 `/optimization-daily` 应展示：

- 各 `strategy_type` 的数量。
- politics / finance 中可复制 leader 数量。
- 被排除的盈利钱包原因排行。
- 最近新增 `human_directional` 候选。
- 当前可试跟候选是否存在不可复制标签。

日报判断从：

```text
有没有高分候选
```

升级为：

```text
有没有高分、正 copyable PnL、BUY/SELL 闭环完整、机制可复制的候选
```

### Loop 执行路径

| 迭代 | 动作 | 验证 |
| --- | --- | --- |
| Iteration A | 数据库/DTO 增加 strategy type 与 risk flags | migration + mapper/unit tests |
| Iteration B | 实现机制标签分类器 | 用已知 XAE/Low-Futon/Research 样本做回归测试 |
| Iteration C | 评分服务接入 copyability/mechanism score | LeaderResearch scoring tests |
| Iteration D | Leader 研究页展示机制标签与阻断原因 | frontend build + 页面检查 |
| Iteration E | 优化日报展示分层漏斗 | frontend build + API 快照验证 |
| Iteration F | TRIAL_READY 门槛加入可复制机制 hard block | trial-ready recheck tests |

### 当前优先级

最高优先级不是继续扩大原始钱包，而是先让系统能回答：

```text
这个 leader 为什么赚钱？
他的赚钱方式我们能不能复制？
如果不能复制，是因为速度、盘口、做市、套利、内幕窗口、低价长尾，还是调仓噪音？
```

这应作为第二目标后续几轮 loop 的主线。

## 2026-07-09 Strategy Type Phase 1：机制标签进入候选模型

本轮开始执行 `Copyable Smart Money Plan` 的阶段 1：让系统先能保存和输出 leader 的赚钱机制标签。

### 已完成

- `leader_research_candidate` 新增 `strategy_type` 字段。
- `LeaderResearchCandidate` 实体新增 `strategyType`。
- `LeaderResearchCandidateDto` 与 mapper 输出 `strategyType`。
- 新增 `LeaderResearchStrategyTypeClassifier`，第一版支持：
  - `human_directional`
  - `whale`
  - `bot_hft`
  - `market_maker_lp`
  - `arbitrage`
  - `low_price_tail_risk`
  - `rebalance_churn`
  - `unknown`
- `LeaderResearchActivityScoringService` 在 activity prescreen 时写入 `strategyType`。
- 不可复制机制会同步写入 `riskFlags`：
  - `strategy_whale`
  - `strategy_bot_hft`
  - `strategy_market_maker_lp`
  - `strategy_arbitrage`
  - `strategy_low_price_tail_risk`
  - `strategy_rebalance_churn`
- `LeaderResearchScoringService` 在后续 copyability 评分时保留这些策略风险，避免重新评分后丢失机制标签阻断。

### 第一版分类规则

| 规则 | strategy_type |
| --- | --- |
| 平均金额极大且有一定样本 | whale |
| 低价/极端价格占比高，且 BUY 多于 SELL | low_price_tail_risk |
| 高频、小额、事件数极高 | bot_hft |
| 少数市场内反复买卖 | rebalance_churn |
| 高频、买卖比例接近平衡且平均金额较小 | market_maker_lp |
| 只有 SELL、没有 BUY 的样本 | arbitrage |
| 样本足够、市场分散、BUY/SELL 闭环、价格安全 | human_directional |
| 证据不足或不确定 | unknown |

### 验证

```text
./gradlew test --tests com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivityScoringServiceTest --tests com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScoringServiceTest
```

结果：

```text
BUILD SUCCESSFUL
```

### 下一步

1. 在 `/leader-research` 和 `/optimization-daily` 展示 `strategyType`。
2. 将 `TRIAL_READY` recheck 的 blocker 从“有任意 riskFlags”细化为展示具体机制阻断原因。
3. 用真实样本复核分类器：
   - XAE12Archangel：识别是否偏 `rebalance_churn` 或 `human_directional`。
   - Low-Futon：识别为 `low_price_tail_risk`。
   - Research 样本：识别是否因缺 SELL 或小样本被阻断。

## 2026-07-09 Strategy Type Phase 1.1：机制标签进入页面和日报

本轮把 `strategyType` 从后端候选模型继续推进到前端可观测层，避免“系统已经识别不可复制机制，但人工页面仍只看到分数”的断层。

### 已完成

- `LeaderResearchFunnelCandidateDto` 新增 `strategyType`。
- `/leader-research`：
  - 候选表展示“机制类型”。
  - 候选详情展示“机制类型”。
  - 快速观察候选卡片展示机制标签。
- `/optimization-daily`：
  - “复核候选质量”展示机制标签。
  - 日报可以直接看到候选是 `human_directional`、`market_maker_lp`、`low_price_tail_risk` 还是其他机制。
- 前端类型 `LeaderResearchFunnelCandidate` 和 `LeaderResearchCandidate` 均支持 `strategyType`。

### 验证

```text
frontend npm run build
backend ./gradlew test --tests LeaderResearchActivityScoringServiceTest --tests LeaderResearchScoringServiceTest --tests LeaderResearchControllerTest --tests LeaderResearchPoliticsRecommendationExecutionServiceTest
backend ./gradlew bootJar
```

结果：

```text
BUILD SUCCESSFUL
```

### 下一轮改进计划

1. **真实样本校准**
   - 对 XAE12Archangel、Low-Futon、Research 样本执行 targeted scoring。
   - 检查分类器输出是否符合人工判断。
   - 把错判样本固化成回归测试。

2. **TRIAL_READY 机制阻断**
   - `strategy_low_price_tail_risk`、`strategy_bot_hft`、`strategy_market_maker_lp`、`strategy_arbitrage`、`strategy_rebalance_churn` 默认不能自动进入真钱跟单。
   - 页面 blocker 必须显示具体机制原因，而不是笼统显示 risk flags。

3. **可复制回测指标**
   - 在 paper session 或日报中补充 `copyable_pnl` 和 `copy_gap` 解释。
   - 把 leader 原始盈利和本地可复制盈利拆开看，避免再用“leader 赚钱”直接推导“我们跟单赚钱”。

4. **日报分布**
   - `/optimization-daily` 增加 strategy type 分布。
   - 增加不可复制 leader 排除原因排行。
   - 目标日报结论从“有没有高分候选”升级为“有没有可复制机制的高分候选”。

## 2026-07-09 Strategy Type Phase 1.2：不可复制机制接入 TRIAL_READY 阻断

本轮把机制标签从“可观察”推进到“可执行门槛”。目标是避免 `riskFlags` 缺失或被重算清空时，`market_maker_lp`、`low_price_tail_risk`、`rebalance_churn` 等不可复制机制仍被高分放进试跟候选。

### 已完成

- `LeaderResearchStrategyTypeClassifier` 新增：
  - `isTrialReadyCopyable(strategyType)`
  - `trialReadyBlocker(strategyType)`
  - `trialReadyBlockerCode(strategyType)`
- `/leader-research` 和 `/optimization-daily` 的 readiness 计算会展示具体机制阻断原因，例如：
  - 低价长尾铺单会提示固定金额跟单会放大尾部亏损。
  - 短窗口反复调仓会提示本地跟单易高买低卖。
  - 做市/LP 会提示买卖平衡收益不适合方向跟单。
- `LeaderResearchStateMachine` 自动晋级 `TRIAL_READY` 时，会直接检查 `strategyType` 是否可复制。
- `LeaderResearchTrialReadyRecheckService`：
  - recheck 输出具体阻断码，例如 `strategy_not_copyable_rebalance_churn`。
  - 自动候选筛选排除不可复制机制。

### 验证覆盖

- 状态机测试：`strategyType=low_price_tail_risk` 且 `riskFlags=null` 时不会晋级 `TRIAL_READY`。
- Fast watch 测试：`strategyType=market_maker_lp` 且 `riskFlags=null` 时不会进入可试跟候选。
- Recheck 测试：`strategyType=rebalance_churn` 时返回明确阻断码。

### 验证

```text
backend ./gradlew test --tests LeaderResearchStateMachineTest --tests LeaderResearchServiceTest --tests LeaderResearchTrialReadyRecheckServiceTest --tests LeaderResearchActivityScoringServiceTest --tests LeaderResearchScoringServiceTest
frontend npm run build
backend ./gradlew bootJar
```

结果：

```text
BUILD SUCCESSFUL
```

### 下一轮改进计划

1. 执行真实样本校准：
   - XAE12Archangel
   - Low-Futon
   - Research 0xad53...ef24
2. 把校准结果写成固定回归测试，减少策略标签误判。
3. 在 `/optimization-daily` 增加 strategy type 分布和不可复制原因排行。

## 2026-07-09 Strategy Type Phase 1.3：真实样本校准

本轮使用本地真实 activity 数据校准第一版分类器，样本来自当前库：

- XAE12Archangel：`0xfbfd14dd4bb607373119de95f1d4b21c3b6c0029`
- Low-Futon：`0xc21ea96be762bb55041529af6e386e7c53b80215`
- Research 0xad53...ef24：`0xad5353afe30c2da57709e2704ef3ccdcf67eef24`

### 数据观察

| leader | total events | markets | BUY | SELL | safe price events | tail price events | avg amount | 结论 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| XAE12Archangel | 63 | 9 | 19 | 44 | 16 | 27 | 55.4046 | 尾部价格占比 42.86%，SELL-heavy，不应作为可复制方向型 leader |
| Low-Futon | 1753 | 119 | 945 | 808 | 0 | 1752 | 0.4868 | 极端低价长尾铺单，固定金额跟单会放大尾部亏损 |
| Research 0xad53...ef24 | 245 | 188 | 153 | 92 | 140 | 30 | 11.3545 | 市场分散、BUY/SELL 闭环、安全价格占比过半，符合 human directional |

### 分类器修正

- 原规则只在 `tailPriceRatio >= 0.50 && buyEvents > sellEvents` 时识别为 `low_price_tail_risk`。
- XAE 的真实数据是 `tailPriceRatio=0.4286` 且 SELL-heavy，原规则会落到 `unknown`，这会让不可复制候选被当作“未知但可观察”继续保留。
- 新增校准规则：

```text
totalEvents >= 20 && tailPriceRatio >= 0.40 -> low_price_tail_risk
```

该规则只针对有一定样本量且尾部价格占比显著的 leader，避免将少量偶发尾部价格误判为不可复制机制。

### 固化测试

新增 `LeaderResearchStrategyTypeClassifierTest`：

- Low-Futon 真实指标必须分类为 `low_price_tail_risk`。
- XAE12Archangel 真实指标必须分类为 `low_price_tail_risk`，不能再落 `unknown`。
- Research 0xad53...ef24 真实指标必须分类为 `human_directional`。

### 运行态验证

- 本地 MySQL 已应用 Flyway `V71__add_strategy_type_to_leader_research_candidate.sql`。
- `leader_research_candidate.strategy_type` 列已存在。
- 后端已重启，`http://127.0.0.1:8000/actuator/health` 返回 `UP`。
- 注意：本机 `localhost` 会被 `ALL_PROXY` 代理接管，命令行健康检查应使用 `127.0.0.1` 或 `curl --noproxy '*'`。

### 下一轮改进计划

1. 通过正式 targeted activity score 重新评分这三个候选，让 `strategy_type` 写入数据库。
2. 在 `/optimization-daily` 增加 strategy type 分布和不可复制原因排行。
3. 继续校准更多样本，重点区分：
   - `human_directional`
   - `rebalance_churn`
   - `market_maker_lp`
   - `low_price_tail_risk`

## 2026-07-09 Strategy Type Phase 1.4：正式 targeted score 写回和 TRIAL_READY 降级

本轮通过正式后端接口执行 targeted activity score，将三组真实样本的 `strategy_type` 写回数据库，并修复一个实际暴露的问题：候选重评分后不再合格，但仍停留在 `TRIAL_READY`。

### 正式写回

调用：

```text
POST /api/copy-trading/leader-research/activity-score/run
body: {"states":["PAPER","TRIAL_READY"],"force":true,"candidateIds":[3237,168,2361]}
```

结果：

```text
scannedCount=3
scoredCount=3
skippedCount=0
strategy_low_price_tail_risk=2
```

### 写回结果

| candidate | leader | state | score | strategy_type | risk flags |
| ---: | --- | --- | ---: | --- | --- |
| 3237 | XAE12Archangel | PAPER | 20.0000 | low_price_tail_risk | low_safe_price_ratio,strategy_low_price_tail_risk |
| 168 | Low-Futon | PAPER | 20.0000 | low_price_tail_risk | tail_price_spray,low_average_size,low_safe_price_ratio,strategy_low_price_tail_risk |
| 2361 | Research 0xad53...ef24 | PAPER | 91.5049 | human_directional | mixed_category_evidence |

### 暴露并修复的问题

`2361` 原本处于 `TRIAL_READY`。targeted activity score 一度把它重评分为低分/带风险，但旧状态机没有从 `TRIAL_READY` 降级的路径。

修复：

- `LeaderResearchStateMachine` 在 `TRIAL_READY` 状态下也重新校验：
  - score 是否仍 >= 80
  - risk flags 是否为空
  - strategy type 是否可复制
  - paper session 是否仍满足 trial ready 条件
  - 最近 3 次高分是否稳定
- 如果不再满足，则从 `TRIAL_READY` 降回 `PAPER`。
- leader pool 同步为：
  - `research_state=PAPER`
  - `research_badge=RESEARCH_PAPER`

### 验证

```text
backend ./gradlew test --tests LeaderResearchStateMachineTest --tests LeaderResearchTrialReadyRecheckServiceTest --tests LeaderResearchStrategyTypeClassifierTest --tests LeaderResearchActivityScoringServiceTest
backend ./gradlew bootJar
```

运行态验证：

```text
POST /api/copy-trading/leader-research/paper/trial-ready/recheck
body: {"dryRun":false,"candidateIds":[2361],"maxCandidates":1}
```

结果：

```text
trialReadyCandidateIds=[]
candidate 2361 research_state=PAPER
leader_pool 957 research_state=PAPER
leader_pool 957 research_badge=RESEARCH_PAPER
```

### 下一轮改进计划

1. 在 `/optimization-daily` 增加 strategy type 分布和不可复制原因排行。
2. 在 Leader Research 页面增加“TRIAL_READY 被降级”事件/提示，避免人工误以为候选消失。
3. 继续校准更多真实样本，尤其区分 `human_directional` 与 `rebalance_churn`。

## 2026-07-09 Strategy Type Phase 1.5：优化日报展示机制分布

本轮把 strategy type 从候选详情推进到日报级别，目标是每天打开 `/optimization-daily` 就能看到当前可观察候选池的机制结构，以及不可复制机制数量。

### 后端输出

`LeaderResearchSummaryDto` 新增：

- `strategyTypeCounts`
- `nonCopyableStrategyBlockers`

统计口径：

```text
PAPER + TRIAL_READY
```

这是当前可能进入纸跟/试跟链路的有效候选池，不包含 DISCOVERED/CANDIDATE 的早期噪音。

### 前端展示

`/optimization-daily` 的“第二目标推荐闭环”卡片新增：

- 机制分布：
  - `human_directional`
  - `low_price_tail_risk`
  - `market_maker_lp`
  - `rebalance_churn`
  - `unknown`
- 不可复制原因：
  - 低价长尾
  - 高频小额
  - 做市/LP
  - 套利/缺入场
  - 反复调仓
  - 巨鲸大额

### 运行态结果

当前 summary API 返回：

```text
paperCount=22631
trialReadyCount=17
activePaperSessions=22648
strategyTypeCounts:
  unknown=22645
  low_price_tail_risk=2
  human_directional=1
nonCopyableStrategyBlockers:
  strategy_not_copyable_low_price_tail_risk=2
```

结论：

- 新指标已可用。
- 当前绝大多数 PAPER/TRIAL_READY 候选仍是 `unknown`，说明旧候选尚未完成 strategy type 补评分。
- 下一轮不应继续只看少数样本，而应做批量 targeted activity score，把旧 PAPER/TRIAL_READY 候选补齐机制标签。

### 验证

```text
backend ./gradlew test --tests LeaderResearchServiceTest --tests LeaderResearchControllerTest
frontend npm run build
backend ./gradlew bootJar
```

运行态验证：

```text
POST /api/copy-trading/leader-research/summary
```

返回包含 `strategyTypeCounts` 和 `nonCopyableStrategyBlockers`。

### 下一轮改进计划

1. 增加“批量补 strategy type”的安全动作：
   - 只处理 PAPER/TRIAL_READY。
   - 每轮限量。
   - force=false 默认跳过已是当前 scoreVersion 的候选。
2. 在日报中显示 unknown 比例，并把 unknown 过高作为下一步行动提示。
3. 继续扩展真实样本校准，减少 unknown 和误判。

## 2026-07-09 第二目标改进计划：从“高分”转向“可复制机制”

当前第二目标不再以原始 leader 数量作为主要瓶颈。原始发现池和 PAPER 池已经足够大，真正瓶颈是：

- PAPER/TRIAL_READY 中大量候选仍是 `strategy_type=unknown`，不能判断是否可复制。
- 旧评分容易把长尾低价铺单、调仓 churn、做市/套利、高频小额策略误判为高质量。
- 可试跟候选必须同时满足方向性、人类可跟随、SELL 可复制、样本足够和主类别配比，而不是只看 PnL 或胜率。

### 改进目标

下一阶段把第二目标口径升级为：

```text
发现足够多 leader -> 识别交易机制 -> 排除不可复制机制 -> 加厚 paper 样本 -> 输出可试跟候选
```

有效候选必须同时满足：

1. `strategy_type` 已识别，且不是不可复制机制。
2. politics / finance 优先，占可试跟资金和候选复核精力约 80%。
3. sports / crypto 只保留少量高确定性样本，占比约 20%。
4. paper trade count 达到最低样本门槛，BUY 与 SELL 都有样本。
5. copyable PnL 为正，filtered ratio、drawdown、unknown valuation exposure 在阈值内。
6. Bridge 执行历史没有暴露出无法及时 SELL 或价格明显劣化的问题。

### 第一优先级：补齐 Strategy Type

目标：把 PAPER/TRIAL_READY 中的 `unknown` 从当前主导状态降下来。

执行规则：

- 新增“批量补 strategy type”安全动作。
- 默认每轮处理 100 个候选。
- 只处理 `PAPER` / `TRIAL_READY`。
- 不直接创建跟单配置。
- 只做 targeted activity score 和机制标签写回。
- 每轮后在 `/optimization-daily` 显示：
  - 本轮选中数量。
  - 成功评分数量。
  - `unknown` 剩余数量和比例。
  - 新增不可复制 blocker 数量。

成功标准：

```text
PAPER/TRIAL_READY strategy_type unknown ratio < 20%
```

在 unknown ratio 高于 50% 时，日报必须优先提示“先补机制标签”，而不是推荐试跟。

### 第二优先级：不可复制机制硬排除

以下机制默认不能进入 TRIAL_READY：

| strategy_type | 处理 |
| --- | --- |
| `low_price_tail_risk` | 禁止试跟，最多保留研究记录 |
| `rebalance_churn` | 禁止自动试跟，需人工确认是否只是正常减仓 |
| `market_maker_lp` | 禁止试跟 |
| `arbitrage` | 禁止试跟 |
| `bot_hft` | 禁止试跟 |
| `whale` | 降权，只允许人工小额观察 |

这条规则优先级高于评分。即使 score >= 80，只要命中不可复制机制，也不能创建或启用跟单模板。

### 第三优先级：加厚主类别 Paper 样本

目标：让 politics / finance 的候选有足够 paper 交易样本，而不是只停留在高分少样本。

执行顺序：

1. 每天先看 `/optimization-daily` 的 politics / finance 推荐闭环。
2. 对 `PAPER_PROCESS` 候选执行 targeted paper process。
3. 对 process 后的候选执行 targeted paper score。
4. 对达到门槛的候选执行 trial-ready recheck。
5. 只把 clean human directional 候选推进到禁用试跟配置。

阶段 KPI：

```text
politics/finance paper_trade_count >= 20 的候选数 >= 100
politics/finance clean human_directional 候选数 >= 20
TRIAL_READY 中不可复制机制候选数 = 0
```

### 第四优先级：Bridge 可复制性纳入最终门槛

Leader 自己赚钱不代表本地可以跟赚。最终试跟前必须检查：

- BUY 是否会因固定金额放大 leader 小单名义金额。
- SELL 是否能按本地实际持仓及时减仓/清仓。
- 同市场短窗口重复 BUY 是否被限制。
- BTC 5M 等特殊市场硬规则是否优先拦截。
- Bridge 失败或跳过是否有记录，不能静默无记录。

若候选历史交易依赖极低价、极短窗口、频繁反向、小额调仓或高买低卖修正，默认降权并进入人工复核。

### 每日 Loop 路径

每日优化按以下顺序执行：

1. 检查目标状态是否 `ACTIVE`，后端与 Bridge 是否运行。
2. 拉取 `/optimization-daily`：
   - unknown strategy ratio。
   - politics/finance 推荐快照。
   - FAST_WATCH/TRIAL_READY 候选。
   - Bridge 健康和最近交易记录。
3. 如果 unknown ratio 高，先执行批量补 strategy type。
4. 如果 politics/finance 样本薄，执行 targeted paper process + score。
5. 如果出现 clean TRIAL_READY，创建禁用试跟配置，不自动真钱启用。
6. 如果出现 Bridge SELL 或记录缺口，暂停推进新候选，优先修执行链路。
7. 将本轮动作、指标变化和下一步写入 `LOOP_STATE.md`。

### 当前最近下一步

先完成“批量补 100 个 unknown strategy type”闭环：

- 后端提供正式接口。
- 优化日报提供按钮。
- 修复并通过目标单测。
- 重启后端后用正式 API 验证。
- 将 unknown 数量变化写回本目标文档和 loop state。

### 2026-07-09 批量补 Strategy Type 闭环结果

本轮已完成第一轮安全 backfill：

```http
POST /api/copy-trading/leader-research/activity-score/backfill-strategy-type
```

默认请求：

```json
{
  "states": ["PAPER", "TRIAL_READY"],
  "limit": 100,
  "force": false
}
```

运行态结果：

| 指标 | 执行前 | 执行后 |
| --- | ---: | ---: |
| activePaperSessions | 22648 | 22648 |
| `unknown` | 22645 | 22584 |
| `low_price_tail_risk` | 2 | 41 |
| `human_directional` | 1 | 14 |
| `market_maker_lp` | 0 | 6 |
| `arbitrage` | 0 | 1 |
| `bot_hft` | 0 | 1 |
| `whale` | 0 | 1 |

本轮 backfill 选中 100 个候选，成功评分 100 个，跳过 0 个。

新增不可复制 blocker：

| blocker | 数量 |
| --- | ---: |
| `strategy_not_copyable_low_price_tail_risk` | 41 |
| `strategy_not_copyable_market_maker_lp` | 6 |
| `strategy_not_copyable_arbitrage` | 1 |
| `strategy_not_copyable_bot_hft` | 1 |
| `strategy_not_copyable_whale` | 1 |

结论：

- backfill 接口和日报按钮所需 API 已可用。
- 旧 PAPER/TRIAL_READY 中确实混有大量不可复制机制，说明“先补机制标签再推试跟”的优先级正确。
- unknown 仍然很高，下一轮继续按 100/轮补齐；如果连续多轮选出的不可复制比例仍高，应先清理候选池，再加厚主类别 paper 样本。

验证：

```text
backend ./gradlew test --tests LeaderResearchActivityScoringServiceTest --tests LeaderResearchControllerTest
frontend npm run build
backend ./gradlew bootJar
curl --noproxy '*' http://127.0.0.1:8000/actuator/health
POST /api/copy-trading/leader-research/activity-score/backfill-strategy-type
POST /api/copy-trading/leader-research/summary
```

### 2026-07-09 第二轮 Backfill 结果

第二轮继续使用相同安全参数：

```json
{
  "states": ["PAPER", "TRIAL_READY"],
  "limit": 100,
  "force": false
}
```

本轮选中 100 个候选，成功评分 100 个，跳过 0 个。

本轮输入候选分类：

| category | 数量 |
| --- | ---: |
| finance | 74 |
| politics | 26 |

本轮风险/机制标记：

| risk flag | 数量 |
| --- | ---: |
| `mixed_category_evidence` | 28 |
| `strategy_low_price_tail_risk` | 19 |
| `tail_price_spray` | 15 |
| `low_safe_price_ratio` | 18 |
| `small_sample` | 52 |
| `low_market_diversity` | 37 |
| `scanner_pool_unverified` | 52 |
| `buy_only_no_exit` | 12 |
| `low_average_size` | 7 |
| `sell_only_no_entry` | 1 |

累计分布变化：

| 指标 | 第二轮前 | 第二轮后 |
| --- | ---: | ---: |
| activePaperSessions | 22648 | 22648 |
| `unknown` | 22584 | 22556 |
| `low_price_tail_risk` | 41 | 60 |
| `human_directional` | 14 | 23 |
| `market_maker_lp` | 6 | 6 |
| `arbitrage` | 1 | 1 |
| `bot_hft` | 1 | 1 |
| `whale` | 1 | 1 |

结论：

- 第二轮主要补到 finance / politics，符合第二目标主类别优先。
- unknown 只减少 28，说明不少旧候选即使重新评分后仍缺足够机制证据。
- 不可复制 blocker 继续增加，低价长尾从 41 增至 60，旧 PAPER 池需要持续清理/降权。
- 下一轮继续 backfill；同时应开始统计“本轮评分后仍 unknown 的原因”，否则单纯补标签会遇到信息不足瓶颈。

### 2026-07-09 Unknown 原因统计落地

本轮将 backfill 响应从“只告诉补了多少”升级为“解释为什么仍 unknown”。

`LeaderResearchActivityScoreResponse` 新增：

```text
unknownStrategyReasonCounts
```

统计口径：

- 只统计本轮已评分候选。
- 只有 `strategy_type=unknown` 的候选会进入原因统计。
- 一个候选可以命中多个原因。

当前原因维度：

| reason | 含义 |
| --- | --- |
| `insufficient_sample` | 活动样本不足 20 |
| `insufficient_market_diversity` | 独立市场不足 5 |
| `no_buy_sample` | 缺少 BUY 样本 |
| `no_sell_sample` | 缺少 SELL 样本 |
| `sell_ratio_outside_copyable_range` | SELL 占比不在可复制方向型范围 |
| `low_safe_price_ratio_for_directional` | 安全价格区间占比不足 |
| `high_tail_price_ratio` | 长尾低价占比偏高 |
| `low_average_size` | 平均金额偏小 |
| `unknown_category` | 分类未知 |
| `mixed_category_evidence` | 分类证据混杂 |
| `stale_or_missing_activity` | 活跃度过期或缺失 |
| `unclassified_pattern` | 有样本但规则暂未归类 |

运行态小批验证：

```json
{
  "states": ["PAPER", "TRIAL_READY"],
  "limit": 20,
  "force": false
}
```

结果：

| 指标 | 数量 |
| --- | ---: |
| selectedCount | 20 |
| scoredCount | 20 |
| skippedCount | 0 |
| finance | 16 |
| politics | 4 |

本轮仍 unknown 原因：

| reason | 数量 |
| --- | ---: |
| `insufficient_sample` | 15 |
| `insufficient_market_diversity` | 6 |
| `no_buy_sample` | 4 |
| `sell_ratio_outside_copyable_range` | 7 |
| `no_sell_sample` | 2 |
| `low_safe_price_ratio_for_directional` | 4 |
| `mixed_category_evidence` | 1 |
| `high_tail_price_ratio` | 2 |

执行后累计分布：

| strategy_type | 数量 |
| --- | ---: |
| `unknown` | 22553 |
| `low_price_tail_risk` | 62 |
| `human_directional` | 23 |
| `market_maker_lp` | 6 |
| `arbitrage` | 2 |
| `bot_hft` | 1 |
| `whale` | 1 |

结论：

- 当前 unknown 的主要瓶颈不是分类规则缺失，而是样本不足和买卖结构不足。
- 下一步要补 activity 样本和 paper 样本，尤其是 politics/finance 的 BUY/SELL 闭环样本；单纯继续扩大候选数量或盲目刷新评分收益有限。
- `/optimization-daily` 的“补齐100个unknown”按钮执行后会显示最近一轮 unknown 原因标签。

### 2026-07-09 Unknown 样本加厚动作落地

本轮把 unknown 原因诊断继续推进为可执行动作。

新增接口：

```http
POST /api/copy-trading/leader-research/activity-score/unknown-strategy/sample-enrich
```

默认用途：

- 只处理 `PAPER` / `TRIAL_READY`。
- 只选 `strategy_type` 为空或 `unknown` 的候选。
- 默认只看 politics / finance。
- 只选择命中样本或买卖结构缺口的候选：
  - `insufficient_sample`
  - `insufficient_market_diversity`
  - `no_buy_sample`
  - `no_sell_sample`
  - `sell_ratio_outside_copyable_range`
- `dryRun=true` 时只返回候选和原因，不处理 paper。
- `dryRun=false` 时执行 targeted `paper/process`，随后执行 targeted `paper/score`。

优化日报新增：

- “预览加厚”按钮。
- “加厚20个样本”按钮。
- 最近一轮加厚候选数量、处理/过滤数量和原因标签展示。

运行态验证：

1. dry-run：

```json
{
  "categories": ["politics", "finance"],
  "limit": 20,
  "batchSize": 20,
  "dryRun": true
}
```

结果：

| 指标 | 数量 |
| --- | ---: |
| selectedCount | 20 |
| finance | 2 |
| politics | 18 |
| `insufficient_sample` | 18 |
| `insufficient_market_diversity` | 9 |
| `high_tail_price_ratio` | 11 |
| `no_buy_sample` | 4 |
| `sell_ratio_outside_copyable_range` | 8 |
| `low_safe_price_ratio_for_directional` | 12 |
| `no_sell_sample` | 2 |
| `mixed_category_evidence` | 13 |
| `low_average_size` | 2 |

2. live 小批：

```json
{
  "categories": ["politics", "finance"],
  "limit": 5,
  "batchSize": 10,
  "dryRun": false
}
```

结果：

| 指标 | 数量 |
| --- | ---: |
| selectedCount | 5 |
| finance | 2 |
| politics | 3 |
| paper processed | 5 |
| paper filtered | 5 |
| paper failed | 0 |
| paper scored | 5 |

候选推进结果：

| candidate | trade delta | filtered delta | copyable PnL delta |
| ---: | ---: | ---: | ---: |
| 482 | +2 | 0 | -0.33333333 |
| 486 | +1 | 0 | 0 |
| 489 | 0 | +2 | 0 |
| 491 | 0 | +2 | 0 |
| 501 | +2 | +1 | -1 |

结论：

- 新动作已经把 unknown 原因从诊断推进到 targeted paper 加厚。
- 小批加厚显示部分候选新增 paper trade 后 copyable PnL 立即为负，说明“样本不足”候选不能直接晋级，只能先补样本再复评分。
- 下一轮应对加厚后的 candidate `482/486/489/491/501` 执行 backfill/score 观察是否脱离 unknown；若仍 unknown 或 PnL 恶化，应降权或进入 cooldown。

### 2026-07-09 加厚候选复查与弱退出评分修复

本轮复查上一轮加厚的 5 个候选：

```text
482, 486, 489, 491, 501
```

#### 复查发现

`501` 在 activity score 中一度被打到 `100`，但它的活动结构是：

| 指标 | 数值 |
| --- | ---: |
| activity events | 64 |
| BUY | 60 |
| SELL | 4 |
| SELL ratio | 6.25% |
| paper trades | 2 |
| copyable PnL | -1 |

这不是干净的方向型 leader。它缺少足够退出样本，且 paper 加厚后已经出现负收益。

修复：

- activity scoring 新增 `weak_exit_sample` 风险标记。
- 条件：`buyEvents >= 20` 且 `sellRatio < 0.10`。
- 命中后 activity score 封顶 `55`。

#### Targeted activity score 复查

执行：

```json
{
  "states": ["PAPER", "TRIAL_READY"],
  "force": true,
  "candidateIds": [482, 486, 489, 491, 501]
}
```

结果：

| 指标 | 数量 |
| --- | ---: |
| scoredCount | 5 |
| `small_sample` | 4 |
| `low_market_diversity` | 2 |
| `scanner_pool_unverified` | 4 |
| `weak_exit_sample` | 1 |

unknown 原因：

| reason | 数量 |
| --- | ---: |
| `insufficient_sample` | 4 |
| `insufficient_market_diversity` | 2 |
| `high_tail_price_ratio` | 3 |
| `no_buy_sample` | 1 |
| `sell_ratio_outside_copyable_range` | 2 |
| `low_safe_price_ratio_for_directional` | 2 |

#### 恢复 paper score 后最终状态

| candidate | state | strategy | score | risk flags | trades | filtered | copyable PnL |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: |
| 482 | PAPER | unknown | 59.0000 | small_sample | 2 | 0 | -0.33333333 |
| 486 | PAPER | unknown | 57.7788 | small_sample | 1 | 0 | 0 |
| 489 | PAPER | unknown | 45.0000 | high_filtered_ratio,small_sample | 0 | 2 | 0 |
| 491 | PAPER | unknown | 45.0000 | high_filtered_ratio,small_sample | 0 | 2 | 0 |
| 501 | PAPER | unknown | 58.0000 | small_sample | 2 | 1 | -1 |

结论：

- 5 个候选都没有脱离 `unknown`。
- `482/501` 出现负 copyable PnL。
- `489/491` 加厚后全被过滤，说明交易样本不适合复制。
- `486` 样本仍不足，暂时只保留观察，不应继续优先消耗资源。

下一步：

- 增加“加厚失败 cooldown”规则：
  - targeted 加厚后 `tradeCountDelta=0` 且 `filteredCountDelta>0`。
  - 或 `copyablePnlDelta<0` 且仍 `strategy_type=unknown`。
  - 或加厚后 `paper_trade_count < 3` 且仍 `small_sample`。
- 命中后进入 COOLDOWN 或降权，不继续进入主策略复核队列。

### 2026-07-09 加厚失败 Cooldown 规则落地

本轮将“加厚失败候选不应反复消耗资源”固化到状态机。

规则位置：

```text
LeaderResearchStateMachine.cooldownReason()
```

新增保守 cooldown 条件：

| 条件 | reason |
| --- | --- |
| `strategy_type=unknown` 且 `trade_count=0` 且 `filtered_count>=2` | `unknown_strategy_all_filtered_after_enrichment` |
| `strategy_type=unknown` 且 `trade_count` 在 1 到 2 之间，且 `copyable_pnl<0` | `unknown_strategy_negative_pnl_after_enrichment` |

说明：

- 该规则不会冷却仅仅样本少但没有恶化的候选。
- 例如 `486` 只有 1 笔 paper trade，但 PnL 没变负、没有全过滤，因此继续留在 PAPER 观察。
- 该规则会冷却 `482/501` 这类加厚后 PnL 为负的候选，以及 `489/491` 这类加厚后全过滤的候选。

运行态验证：

执行：

```json
{
  "dryRun": false,
  "candidateIds": [482, 486, 489, 491, 501],
  "maxCandidates": 5
}
```

最终状态：

| candidate | state | cooldown_count | reason |
| ---: | --- | ---: | --- |
| 482 | COOLDOWN | 1 | `unknown_strategy_negative_pnl_after_enrichment` |
| 486 | PAPER | 0 | 保留观察 |
| 489 | COOLDOWN | 1 | `unknown_strategy_all_filtered_after_enrichment` |
| 491 | COOLDOWN | 1 | `unknown_strategy_all_filtered_after_enrichment` |
| 501 | COOLDOWN | 1 | `unknown_strategy_negative_pnl_after_enrichment` |

结论：

- 加厚失败的 unknown 候选已能自动退出主策略加厚队列。
- 这样 politics/finance 样本加厚资源会优先留给仍有机会形成 clean human directional 的候选。
- 下一轮应继续从 unknown 样本池中预览加厚候选，但每轮后必须执行复查和 cooldown 清理，避免低质量候选反复循环。

### 2026-07-09 下一阶段改进计划：样本加厚闭环升级

当前第二目标已经完成三个关键基础能力：

1. `strategy_type` 能保存、展示并参与 TRIAL_READY 阻断。
2. `unknownStrategyReasonCounts` 能解释为什么候选仍无法归类。
3. unknown 候选可以通过 targeted paper 加厚，并在失败后自动进入 cooldown。

下一阶段不再继续单纯扩大 leader 数量，而是把每一轮运行固定成“预览 -> 加厚 -> 复评 -> 清理 -> 晋级”的闭环。

#### Loop 入口

每日或手动执行时按以下顺序运行：

1. 检查 `/optimization-daily` 中 PAPER/TRIAL_READY 的 strategy type 分布。
2. 如果 `unknown` 占比仍高，先执行 `backfill-strategy-type`，每轮 100 个。
3. 对 politics / finance 的 unknown 候选执行 `sample-enrich` dry-run，确认候选原因分布。
4. 只对命中样本不足、市场不足、缺 BUY/SELL 或 SELL 比例异常的候选执行 live 加厚。
5. 加厚后立即执行 targeted activity score、paper score 和 trial-ready recheck。
6. 命中加厚失败规则的候选进入 COOLDOWN，不再占用主策略样本资源。
7. 只有 clean human directional 且 paper 样本足够的候选进入 FAST_WATCH / TRIAL_READY 复核。

#### 每轮批量控制

默认批量保持小而可观察：

| 动作 | 默认批量 | 原因 |
| --- | ---: | --- |
| backfill strategy type | 100 | 降低 unknown，但不触发交易模拟 |
| unknown sample dry-run | 20 | 先看候选质量和原因 |
| unknown sample live enrich | 5 到 10 | 避免一次性把低质量样本大量写入 |
| trial-ready recheck | 与 live enrich candidateIds 一致 | 保证加厚后立即清理 |

如果连续三轮 live enrich 中超过 60% 候选进入 COOLDOWN，应暂停扩大 live 加厚，改为调整来源质量或 sample-enrich 选择规则。

#### 准入规则

候选进入可试跟候选前必须满足：

- `strategy_type=human_directional`。
- category 为 `politics` 或 `finance` 优先；sports / crypto 只保留少量高确定性样本。
- paper trade count 达到最低样本门槛，且 BUY / SELL 都有样本。
- copyable PnL 为正。
- filtered ratio、max drawdown、unknown valuation exposure 不触发风险阻断。
- 不命中 `weak_exit_sample`、`buy_only_no_exit`、`tail_price_spray`、`strategy_not_copyable_*`。
- Bridge 历史没有暴露固定金额放大、小额 SELL 被挡、重复 BUY 或静默无记录问题。

#### 淘汰规则

以下候选应自动退出主策略加厚队列：

- unknown 加厚后 `trade_count=0` 且 `filtered_count>=2`。
- unknown 加厚后 `trade_count<=2` 且 `copyable_pnl<0`。
- BUY 很多但 SELL 占比低于 10%，命中 `weak_exit_sample`。
- 长尾低价比例高、平均金额过小、或依赖极低价概率铺单。
- 市场类别证据长期混杂，无法稳定归入 politics / finance。

#### 验收指标

下一阶段的有效进展用以下指标判断：

| 指标 | 目标 |
| --- | ---: |
| PAPER/TRIAL_READY unknown ratio | 逐轮下降，阶段目标低于 50%，长期低于 20% |
| politics/finance clean human_directional 候选 | 逐轮增加 |
| politics/finance paper_trade_count >= 20 候选 | 阶段目标 100 个 |
| TRIAL_READY 中不可复制机制候选 | 0 |
| live enrich 后 COOLDOWN 比例 | 用于反向评估来源质量，连续偏高则先改来源 |

#### 下一轮具体动作

1. 复查最近 live enrich 的 `517/522/544/555/592` 最终状态，确认 cooldown 清理是否按规则生效。
2. 记录本轮 selected、processed、filtered、copyable PnL delta 和最终状态。
3. 如果 `517/544/555` 这类全过滤候选已进入 COOLDOWN，继续下一批 unknown dry-run。
4. 如果 `522/592` 因正 PnL 留在 PAPER，继续观察但不直接晋级，直到样本和机制标签满足准入规则。
5. 把每轮结果写入 `LOOP_STATE.md`，并在日报中保留可见的原因分布和冷却结果。

### 2026-07-09 第二批 Unknown 加厚复查结果

本轮复查上一轮 live enrich 的 5 个候选：

```text
517, 522, 544, 555, 592
```

后端健康状态：

```text
/actuator/health = UP
```

最终 DB 状态：

| candidate | state | strategy | score | risk flags | trades | filtered | filtered ratio | copyable PnL | 处理结论 |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 517 | COOLDOWN | unknown | 45.0000 | high_filtered_ratio,small_sample | 0 | 2 | 1.0000 | 0 | 全过滤，退出主加厚队列 |
| 522 | PAPER | unknown | 55.2966 | mixed_category_evidence,high_filtered_ratio,small_sample | 1 | 1 | 0.5000 | 0.6483 | 正 PnL 但样本薄，保留观察 |
| 544 | COOLDOWN | unknown | 45.0000 | mixed_category_evidence,high_filtered_ratio,small_sample | 0 | 2 | 1.0000 | 0 | 全过滤，退出主加厚队列 |
| 555 | COOLDOWN | unknown | 45.0000 | mixed_category_evidence,high_filtered_ratio,small_sample | 0 | 2 | 1.0000 | 0 | 全过滤，退出主加厚队列 |
| 592 | PAPER | unknown | 54.1211 | high_filtered_ratio,small_sample | 1 | 1 | 0.5000 | 0.0605 | 正 PnL 但样本薄，保留观察 |

事件证据：

| candidate | 关键事件 |
| ---: | --- |
| 517 | `COOLDOWN -> COOLDOWN: unknown_strategy_all_filtered_after_enrichment` |
| 544 | `COOLDOWN -> COOLDOWN: unknown_strategy_all_filtered_after_enrichment` |
| 555 | `COOLDOWN -> COOLDOWN: unknown_strategy_all_filtered_after_enrichment` |
| 522 | 1 笔 BUY paper recorded，另 1 笔因 `price_outside_safe_band` filtered |
| 592 | 1 笔 BUY paper recorded，另 1 笔 SELL 因 `price_outside_safe_band` filtered |

结论：

- cooldown 规则按预期清理了全过滤 unknown 候选。
- `522/592` 虽然 copyable PnL 为正，但仍是 `unknown + small_sample + high_filtered_ratio`，不能进入 FAST_WATCH / TRIAL_READY。
- 本轮 live enrich 的有效晋级产出为 0，但有效清理了 3 个低质量 unknown，加厚资源没有继续被这些候选占用。

下一步：

1. 继续执行下一批 `unknown-strategy/sample-enrich` dry-run，只预览 politics / finance。
2. live enrich 仍保持 5 到 10 个小批量。
3. 如果下一批 COOLDOWN 比例仍超过 60%，暂停加厚，转向优化来源或选择规则。
4. `522/592` 只保留观察，必须继续积累 BUY/SELL 样本并脱离 `unknown` 后才可复核晋级。

### 2026-07-09 第三批 Unknown 加厚与闭环修复

本轮继续执行下一批 unknown 加厚 dry-run。

dry-run 结果：

| 指标 | 数量 |
| --- | ---: |
| selectedCount | 20 |
| politics | 20 |

主要 unknown 原因：

| reason | 数量 |
| --- | ---: |
| `insufficient_sample` | 17 |
| `mixed_category_evidence` | 17 |
| `sell_ratio_outside_copyable_range` | 12 |
| `low_safe_price_ratio_for_directional` | 10 |
| `high_tail_price_ratio` | 8 |
| `insufficient_market_diversity` | 8 |
| `low_average_size` | 3 |
| `no_buy_sample` | 3 |
| `no_sell_sample` | 2 |

随后执行 live 小批：

```text
601, 605, 612, 613, 617
```

加厚结果：

| candidate | trade delta | filtered delta | copyable PnL delta | 结果 |
| ---: | ---: | ---: | ---: | --- |
| 601 | +2 | +1 | 0 | 样本仍薄，保留 PAPER |
| 605 | 0 | +1 | 0 | 全过滤不足 2，保留 PAPER 但不优先 |
| 612 | +1 | +1 | -1 | 进入 COOLDOWN |
| 613 | 0 | +2 | 0 | 进入 COOLDOWN |
| 617 | +2 | 0 | +5.5691 | 高分但仍被风险标记阻断 |

recheck 结果：

| candidate | state | score | trades | filtered | copyable PnL | blocker |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 601 | PAPER | 58.0000 | 2 | 1 | 0 | `score_below_80` |
| 605 | PAPER | 45.0000 | 0 | 1 | 0 | `score_below_80` |
| 612 | COOLDOWN | 54.0000 | 1 | 1 | -1 | 负 PnL 后冷却 |
| 613 | COOLDOWN | 45.0000 | 0 | 2 | 0 | 全过滤后冷却 |
| 617 | PAPER | 91.5574 | 47 | 14 | 31.0004 | `risk_flags_present` |

#### 闭环缺口修复

本轮发现 `unknown-strategy/sample-enrich` 的 live 分支存在闭环缺口：

- 旧逻辑执行了 paper process。
- 旧逻辑执行了 paper score。
- 但旧逻辑没有执行 targeted activity score。

结果是新加厚候选的 `strategy_type` 仍可能停留在 `NULL`，不符合“加厚后立即复评机制标签”的第二目标计划。

修复：

- `LeaderResearchUnknownStrategySampleEnrichResponse` 新增 `activityScoreResult`。
- `enrichUnknownStrategySamples(dryRun=false)` 在 paper process 后补跑：

```json
{
  "states": ["PAPER", "TRIAL_READY"],
  "force": true,
  "candidateIds": "本轮 selectedCandidateIds"
}
```

- 然后再执行 paper score。
- `/optimization-daily` 的最近加厚结果展示“机制复评”数量。

对本轮 5 个候选补跑 targeted activity score 后，最终 `strategy_type` 已从 `NULL` 补为 `unknown`：

| candidate | state | strategy | score | risk flags |
| ---: | --- | --- | ---: | --- |
| 601 | PAPER | unknown | 58.0000 | mixed_category_evidence,small_sample |
| 605 | PAPER | unknown | 45.0000 | mixed_category_evidence,high_filtered_ratio,small_sample |
| 612 | COOLDOWN | unknown | 30.0000 | small_sample,low_market_diversity,mixed_category_evidence,scanner_pool_unverified |
| 613 | COOLDOWN | unknown | 30.0000 | small_sample,mixed_category_evidence,scanner_pool_unverified |
| 617 | PAPER | unknown | 91.5574 | mixed_category_evidence |

结论：

- 本轮清理 2 个低质量 unknown。
- `617` 是值得下一轮重点拆解的候选：paper 样本和 copyable PnL 很强，但当前仍被 `mixed_category_evidence` 阻断。
- 下一轮不要直接试跟 `617`，应先检查其市场类别证据是否被 sports/finance/politics 混淆；如果只是导入来源分类错误，应修复分类归属或建立“按市场拆分评分”的规则。

### 2026-07-09 Candidate 617 复查与风险保留修复

本轮继续拆解 `617`：

```text
0x9703676286b93c2eca71ca96e8757104519a69c2
```

#### 真实活动结构

DB 活动统计显示：

| side | events | safe price | tail price | markets | avg amount |
| --- | ---: | ---: | ---: | ---: | ---: |
| BUY | 2619 | 1992 | 49 | 289 | 80.4013 |
| SELL | 15 | 1 | 14 | 11 | 30.9416 |

主要 market slug 高度集中在 `fifwc-*` 世界杯市场，例如：

- `fifwc-esp-aut-2026-07-02-aut`
- `fifwc-ecu-ger-2026-06-25-draw`
- `fifwc-can-mar-2026-07-04-draw`
- `fifwc-nor-fra-2026-06-26-draw`

结论：

- `617` 并不是 politics / finance 主策略候选。
- 它更像世界杯体育方向的大量 BUY 策略。
- BUY/SELL 极度不平衡，SELL ratio 约 `0.57%`，不满足可复制退出条件。

#### 发现的评分漏洞

activity score 已经识别出：

```text
weak_exit_sample
mixed_category_evidence
```

但 paper score 重新保存 candidate 时，只保留了 strategy/category/paper 风险，覆盖掉了 `weak_exit_sample`。

这会导致：

- 候选虽然有弱退出结构风险；
- 但 paper score 仍显示高分；
- 页面上容易误判为“高质量但只是分类混杂”。

#### 修复

`LeaderResearchScoringService` 现在会：

1. 在 paper score 阶段保留 activity 层结构风险：
   - `weak_exit_sample`
   - `buy_only_no_exit`
   - `sell_only_no_entry`
   - `low_market_diversity`
   - `low_average_size`
   - `low_safe_price_ratio`
   - `scanner_pool_unverified`
2. paper score 根据这些风险继续做分数封顶。
3. `weak_exit_sample` 封顶 `55`。
4. reason 中写入 `risk_cap_flags`，方便复查为什么高 PnL 没有高分。

#### 运行态修正结果

对 `617` 补跑：

1. targeted activity score
2. targeted paper score
3. trial-ready recheck

最终状态：

| candidate | state | strategy | score | risk flags | trades | filtered | copyable PnL | recheck |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| 617 | PAPER | unknown | 55.0000 | weak_exit_sample,mixed_category_evidence | 47 | 14 | 31.0004 | `score_below_80` |

结论：

- `617` 从“高分但混杂”被修正为“PnL 强但退出结构不可复制”。
- 它不应进入 FAST_WATCH / TRIAL_READY。
- 下一轮应继续寻找 politics / finance 的 clean human directional，而不是继续加厚 `617` 这类体育 BUY-heavy 钱包。

### 2026-07-09 真实活动市场类别分布接入

上一轮虽然修复了 `617` 的弱退出风险，但仍有一个系统性问题：

- 来源证据 `source_evidence` 可能同时包含 politics、finance、sports。
- 真实交易活动却可能高度集中在某一类市场。
- 如果只看来源证据，sports leader 仍可能被带入 politics / finance 主线。

本轮将 activity score 从“只看来源分类”升级为“来源分类 + 真实活动市场分类”。

#### 实现

`LeaderResearchActivityMetricProjection` 增加：

- `politicsEvents`
- `financeEvents`
- `sportsEvents`
- `cryptoEvents`

activity aggregate SQL 通过 market slug/title 统计真实活动类别：

- politics：election、president、senate、congress、war、iran 等。
- finance：fed、rate、inflation、cpi、gdp、gold、yield 等。
- sports：`fifwc`、FIFA、World Cup、Team to Advance、draw、NBA/NFL/MLB/NHL 等。
- crypto：bitcoin、btc、ethereum、solana、xrp、doge 等。

activity scoring 新增逻辑：

1. 如果真实活动类别样本数 >= 20，且 dominant ratio >= 70%，则优先采用真实活动类别。
2. 如果来源分类与真实活动主类别冲突，则加入：

```text
activity_category_mismatch
```

3. `activity_category_mismatch` 会：
   - 进入 risk flags。
   - 进入 unknownStrategyReasonCounts。
   - paper score 阶段继续保留。
   - paper score 封顶 `50`。
   - 从 politics / finance unknown sample enrich 队列中排除。

#### Candidate 617 验证

补跑正式 API：

```json
{
  "states": ["PAPER", "TRIAL_READY"],
  "force": true,
  "candidateIds": [617]
}
```

activity score 返回：

| 指标 | 结果 |
| --- | --- |
| categoryCounts | `sports=1` |
| riskFlagCounts | `weak_exit_sample=1`, `mixed_category_evidence=1`, `activity_category_mismatch=1` |
| unknownStrategyReasonCounts | `sell_ratio_outside_copyable_range=1`, `mixed_category_evidence=1`, `activity_category_mismatch=1` |

paper score 后最终 DB：

| candidate | state | strategy | score | risk flags | trades | copyable PnL |
| ---: | --- | --- | ---: | --- | ---: | ---: |
| 617 | PAPER | unknown | 50.0000 | weak_exit_sample,activity_category_mismatch,mixed_category_evidence | 47 | 31.0004 |

结论：

- `617` 已被系统明确识别为 sports 主活动候选。
- 它不会再污染 politics / finance 主线加厚。
- 这类候选即使 copyable PnL 为正，也必须被视为“非主策略、弱退出、不可直接试跟”。

下一步：

1. 继续下一批 politics / finance unknown dry-run。
2. 观察 `activity_category_mismatch` 是否大量出现；如果大量出现，说明来源导入层需要进一步按真实市场类别重分桶。
3. 后续页面可增加“真实活动类别”展示，让人工复核不再只看来源标签。

### 2026-07-09 第四批 Unknown 加厚：真实类别过滤后的小批验证

本轮在“真实活动市场类别分布”修复后，继续执行 politics / finance unknown dry-run。

运行前状态：

| 指标 | 数量 |
| --- | ---: |
| PAPER/TRIAL_READY unknown 或 null | 22544 |

#### dry-run 结果

请求：

```json
{
  "categories": ["politics", "finance"],
  "limit": 20,
  "batchSize": 20,
  "dryRun": true
}
```

结果：

| 指标 | 数量 |
| --- | ---: |
| selectedCount | 20 |
| politics | 20 |
| `activity_category_mismatch` | 0 |

unknown 原因：

| reason | 数量 |
| --- | ---: |
| `insufficient_sample` | 17 |
| `mixed_category_evidence` | 14 |
| `sell_ratio_outside_copyable_range` | 10 |
| `insufficient_market_diversity` | 8 |
| `high_tail_price_ratio` | 8 |
| `low_safe_price_ratio_for_directional` | 6 |
| `no_buy_sample` | 3 |
| `low_average_size` | 2 |
| `no_sell_sample` | 2 |

结论：

- `activity_category_mismatch=0`，说明 sports 主活动候选已不再进入 politics / finance 加厚预览。
- 当前候选仍然以样本不足、分类证据混杂和 SELL 比例异常为主。

#### live 小批结果

本轮按小批规则执行 5 个候选：

```text
621, 622, 628, 629, 632
```

paper process：

| 指标 | 数量 |
| --- | ---: |
| processed | 4 |
| filtered | 6 |
| failed | 0 |

candidate deltas：

| candidate | trade delta | filtered delta | copyable PnL delta |
| ---: | ---: | ---: | ---: |
| 621 | 0 | +2 | 0 |
| 622 | +2 | +1 | +0.1154 |
| 628 | +2 | +1 | -0.4975 |
| 629 | 0 | +1 | 0 |
| 632 | 0 | +1 | 0 |

recheck / DB 最终状态：

| candidate | state | score | risk flags | trades | filtered | copyable PnL | 结论 |
| ---: | --- | ---: | --- | ---: | ---: | ---: | --- |
| 621 | COOLDOWN | 45.0000 | scanner_pool_unverified,mixed_category_evidence,high_filtered_ratio,small_sample | 0 | 2 | 0 | 全过滤，冷却 |
| 622 | PAPER | 58.2308 | scanner_pool_unverified,mixed_category_evidence,small_sample | 2 | 1 | +0.1154 | 样本薄，保留观察 |
| 628 | COOLDOWN | 58.0000 | low_market_diversity,scanner_pool_unverified,mixed_category_evidence,small_sample | 2 | 1 | -0.4975 | 负 PnL，冷却 |
| 629 | PAPER | 45.0000 | low_market_diversity,scanner_pool_unverified,mixed_category_evidence,high_filtered_ratio,small_sample | 0 | 1 | 0 | 样本不足，不优先 |
| 632 | PAPER | 45.0000 | low_market_diversity,low_average_size,scanner_pool_unverified,mixed_category_evidence,high_filtered_ratio,small_sample | 0 | 1 | 0 | 样本不足，不优先 |

结论：

- 本轮没有产生 FAST_WATCH / TRIAL_READY 候选。
- 真实类别过滤有效，但 politics unknown 队列当前质量仍偏弱。
- 5 个 live enrich 中 2 个进入 COOLDOWN，3 个保留 PAPER 但均不满足晋级条件。

下一步：

1. 不扩大 live enrich 批量，继续保持 5 个小批。
2. 如果后续连续多批仍主要是 `scanner_pool_unverified + mixed_category_evidence + small_sample`，应优先改来源选择，而不是继续消耗 paper 加厚。
3. 下一轮应优先尝试 finance unknown 队列或 official leaderboard / external analytics 来源，寻找更接近 clean human directional 的候选。

### 2026-07-09 Finance Unknown 小批验证与扫描窗口修复

本轮按上一轮结论切到 finance unknown 队列。

运行前只读检查：

| 指标 | 数量 |
| --- | ---: |
| finance evidence unknown | 593 |
| politics evidence unknown | 403 |

#### finance dry-run

请求：

```json
{
  "categories": ["finance"],
  "limit": 20,
  "batchSize": 20,
  "dryRun": true
}
```

结果：

| 指标 | 数量 |
| --- | ---: |
| selectedCount | 20 |
| finance | 20 |
| `mixed_category_evidence` | 0 |
| `activity_category_mismatch` | 0 |

unknown 原因：

| reason | 数量 |
| --- | ---: |
| `insufficient_sample` | 19 |
| `insufficient_market_diversity` | 11 |
| `high_tail_price_ratio` | 6 |
| `low_safe_price_ratio_for_directional` | 5 |
| `no_sell_sample` | 5 |
| `sell_ratio_outside_copyable_range` | 3 |
| `no_buy_sample` | 1 |

结论：

- finance 队列比当前 politics unknown 队列更干净。
- 主要问题是样本不足，而不是分类混杂。
- 这符合第二目标“政治、金融优先”的下一步方向，应继续小批加厚 finance。

#### 发现的执行问题

第一次执行 live：

```json
{
  "categories": ["finance"],
  "limit": 5,
  "batchSize": 10,
  "dryRun": false
}
```

返回 `selectedCount=0`。

原因：

- `sample-enrich` 原逻辑用 `limit * 10` 作为扫描窗口。
- finance 候选相对稀疏。
- dry-run `limit=20` 会扫描 200 个，所以能选出 finance。
- live `limit=5` 只扫描 50 个，所以扫不到 finance。

修复：

- unknown sample enrich 的扫描窗口增加下限：

```text
scanLimit = max(limit * 10, 200)，上限仍为 500
```

这样小批 live 仍能在稀疏类别中选到足够候选，不需要扩大真实处理批量。

#### 修复后 live 小批

选中：

```text
1316, 1318, 1319, 1321, 1324
```

activity score：

| 指标 | 数量 |
| --- | ---: |
| scanned | 5 |
| scored | 5 |
| finance | 5 |
| `activity_category_mismatch` | 0 |

paper process：

| 指标 | 数量 |
| --- | ---: |
| processed | 4 |
| filtered | 6 |
| failed | 0 |

candidate deltas：

| candidate | trade delta | filtered delta | copyable PnL delta |
| ---: | ---: | ---: | ---: |
| 1316 | 0 | +3 | 0 |
| 1318 | +1 | 0 | -0.0349 |
| 1319 | +1 | 0 | +2.1250 |
| 1321 | +1 | +1 | +0.0467 |
| 1324 | +1 | +2 | 0 |

最终状态：

| candidate | state | score | risk flags | trades | filtered | copyable PnL | 结论 |
| ---: | --- | ---: | --- | ---: | ---: | ---: | --- |
| 1316 | COOLDOWN | 45.0000 | low_market_diversity,scanner_pool_unverified,high_filtered_ratio,small_sample | 0 | 3 | 0 | 全过滤，冷却 |
| 1318 | COOLDOWN | 59.0000 | low_market_diversity,scanner_pool_unverified,small_sample | 1 | 0 | -0.0349 | 负 PnL，冷却 |
| 1319 | PAPER | 59.0000 | low_market_diversity,scanner_pool_unverified,small_sample | 1 | 0 | +2.1250 | 正向但样本薄，保留观察 |
| 1321 | PAPER | 54.0933 | low_market_diversity,scanner_pool_unverified,high_filtered_ratio,small_sample | 1 | 1 | +0.0467 | 样本薄，保留观察 |
| 1324 | PAPER | 51.5000 | scanner_pool_unverified,high_filtered_ratio,small_sample | 1 | 2 | 0 | 过滤偏高，不优先 |

结论：

- 修复后 finance live 小批能正常执行。
- 本批没有 FAST_WATCH / TRIAL_READY。
- `1319` 是本批唯一值得继续观察的正向 finance 样本，但还远未达到晋级门槛。
- finance 队列质量优于当前 politics unknown 队列，下一轮应继续 finance 小批或切 official leaderboard / external analytics 补源。

### 2026-07-09 改进计划 v2：从加厚 unknown 转向高质量来源转化

本轮把第二目标的下一阶段执行计划进一步收敛为“少量高质量来源优先转化”。此前几轮已经证明：

- 原始候选数量不是瓶颈。
- politics unknown 队列存在较多 `mixed_category_evidence`、`small_sample` 和 SELL 结构问题。
- finance unknown 队列相对干净，但仍以样本不足为主。
- 单纯按 unknown 队列顺序加厚，容易产生 COOLDOWN 清理价值，但难以快速产出可试跟候选。
- official leaderboard / external analytics 中已经出现少数 CLEAN_HIGH / TRIAL_READY 级别候选，应优先复核和转化。

#### 阶段 1：高质量来源优先复核

目标：先把 official leaderboard / external analytics 中已经接近可试跟的候选复核清楚。

执行动作：

1. 每轮先跑 official leaderboard diagnose，记录 `CLEAN_HIGH`、`FAST_WATCH`、`TRIAL_READY` 数量。
2. 对 `CLEAN_HIGH` 和 `TRIAL_READY` 候选执行 targeted activity score。
3. 立即执行 targeted paper score 和 trial-ready recheck。
4. 如果候选仍是 `strategy_type=NULL/unknown`，必须补出机制标签或明确阻断原因。
5. 对 clean human directional 的 politics / finance 候选，输出“禁用试跟配置候选”，不自动启用真钱跟单。

优先复核队列：

| candidate | 类别 | 当前判断 | 下一步 |
| ---: | --- | --- | --- |
| 1660 | finance | official leaderboard CLEAN_HIGH，已达到 TRIAL_READY，但 strategy type 仍需补齐 | targeted activity score + paper score + recheck |
| 153 | politics | official leaderboard CLEAN_HIGH，score 高但 strategy type 仍为 unknown | targeted activity score + paper score + recheck |

#### 阶段 2：finance 小批加厚

目标：继续利用相对干净的 finance unknown 队列，但保持小批量，避免低质量样本大量写入。

执行规则：

- dry-run 每轮 20 个。
- live enrich 每轮 5 个。
- 每轮后必须执行 targeted activity score、paper score、trial-ready recheck。
- 命中全过滤或负 PnL 的 unknown 候选进入 COOLDOWN。
- 正 PnL 但 `small_sample` 的候选只保留 PAPER 观察，不进入试跟。

继续观察对象：

| candidate | 当前状态 | 原因 |
| ---: | --- | --- |
| 1319 | PAPER | finance 小批中正 PnL，但只有 1 笔 paper trade |
| 1321 | PAPER | 正 PnL 很薄，且 filtered ratio 偏高 |
| 1324 | PAPER | 样本薄且过滤偏高，不优先 |

#### 阶段 3：改来源选择，而不是无限加厚

触发条件：

```text
连续 3 轮 live enrich 中，COOLDOWN 比例 >= 60%
或
连续 3 轮没有新增 clean human_directional 候选
```

触发后不再扩大 unknown live enrich 批量，改为：

1. 提高 official leaderboard / external analytics 的权重。
2. 降低 scanner_pool_unverified 候选的处理优先级。
3. 对 politics 候选增加真实活动类别一致性要求。
4. 对 finance 候选优先选择 BUY/SELL 都存在、distinct markets 足够的样本。
5. 在日报中明确显示“当前瓶颈是来源质量，而不是处理批量”。

#### 阶段 4：可试跟前最终门槛

进入跟单配置前必须全部满足：

- `strategy_type=human_directional`。
- category 为 politics 或 finance 优先。
- paper trade count 达到阶段样本门槛，且 BUY/SELL 都有样本。
- copyable PnL 为正。
- 不命中 `weak_exit_sample`、`activity_category_mismatch`、`strategy_not_copyable_*`。
- filtered ratio 和 max drawdown 在阈值内。
- Bridge 对该类市场没有未解决的 BUY 放大、SELL 不及时、重复 BUY、静默无记录问题。

#### 下一轮具体动作

1. 复核 `1660` 和 `153` 是否已经在 leader pool / copy trading 配置中。
2. 对 `1660`、`153` 执行 targeted activity score、paper score、trial-ready recheck。
3. 如果 `1660` 保持 finance clean 且 TRIAL_READY，记录为下一位禁用试跟配置候选。
4. 如果 `153` 仍为 unknown 或存在 SELL/样本结构 blocker，继续 PAPER 观察，不推进跟单。
5. 再执行一轮 finance unknown dry-run；只有候选质量明显优于上一批时才 live enrich 5 个。
6. 将本轮 official leaderboard 复核结果、候选最终状态和下一步写回 `LOOP_STATE.md`。

#### 验收指标

| 指标 | 目标 |
| --- | ---: |
| official leaderboard CLEAN_HIGH 复核覆盖率 | 100% |
| finance / politics TRIAL_READY 中 `strategy_type=NULL/unknown` | 0 |
| 新增 clean human_directional politics / finance 候选 | 每轮至少尝试推进 |
| 不可复制机制进入 TRIAL_READY | 0 |
| 连续加厚失败轮次 | 达到 3 轮后必须切换来源策略 |

### 2026-07-09 Official Leaderboard 候选复核：1660 / 153

按“高质量来源优先转化”计划，本轮优先复核 official leaderboard / external analytics 中的两个 CLEAN_HIGH 候选：

```text
1660 finance
153 politics
```

#### 配置与池子状态

| candidate | wallet | leader pool | copy trading config | 结论 |
| ---: | --- | --- | --- | --- |
| 1660 | `0x5b6331e7ff0831a3fe2ed12004747db1a9c911a4` | pool `99`，leader `516`，`RESEARCH_TRIAL_READY` | 无 | 可作为禁用试跟配置候选，不自动启用 |
| 153 | `0xc8ab97a9089a9ff7e6ef0688e6e591a066946418` | pool `277`，leader `337`，`RESEARCH_PAPER` | 无 | 继续 PAPER，不推进跟单 |

额外发现：

- `153` 的 activity / market peer source 都显示 politics。
- 但其 `copy_trading_leaders.category` 仍为 `crypto`。
- 这不影响本轮阻断结论，因为 `153` score 仍低于 80；但后续应修复 leader pool / leader category 与 research candidate 真实类别不同步的问题，避免页面或分领域资金分配误判。

#### Targeted activity score

请求：

```json
{
  "states": ["PAPER", "TRIAL_READY"],
  "force": true,
  "candidateIds": [1660, 153]
}
```

结果：

| 指标 | 数量 |
| --- | ---: |
| scannedCount | 2 |
| scoredCount | 2 |
| skippedCount | 0 |
| politics | 1 |
| finance | 1 |
| unknown reason: `low_safe_price_ratio_for_directional` | 1 |

#### Paper score + trial-ready recheck

paper score：

```text
scoredCount=2
scoreVersion=research-copyability-v1
missingCandidateIds=[]
```

trial-ready recheck：

| candidate | before | after | score | trades | filtered | PnL | filtered ratio | action | reason |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1660 | TRIAL_READY | TRIAL_READY | 90.1471 | 23 | 11 | 13.5642 | 0.3235 | PROMOTED_TRIAL_READY | meets_trial_ready_threshold |
| 153 | PAPER | PAPER | 77.9036 | 31 | 14 | 1.2851 | 0.3111 | BLOCKED | score_below_80 |

#### 最终 DB 状态

| candidate | state | strategy_type | score | risk_flags | paper trades | filtered | copyable PnL | 结论 |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| 1660 | TRIAL_READY | human_directional | 90.1471 | 空 | 23 | 11 | 13.5642 | finance clean，可进入禁用试跟人工确认 |
| 153 | PAPER | unknown | 77.9036 | 空 | 31 | 14 | 1.2851 | 分数不足且机制 unknown，继续观察 |

#### 本轮决策

- `1660` 是当前最明确的 finance 可试跟候选：`human_directional`、PnL 正、无风险标记、TRIAL_READY。
- 由于本轮没有收到“创建配置”的明确指令，系统不自动创建 copy trading config。
- `153` 不推进：虽然 paper 样本和 PnL 为正，但 score 低于 80，且机制仍是 `unknown`。
- 下一步应优先：
  1. 在页面或接口中把 `1660` 标为“禁用试跟配置候选”。
  2. 修复/检查 leader pool category 与 research candidate 真实类别不同步问题，尤其是 `153` 的 leader category 仍显示 `crypto`。
  3. 继续 official leaderboard diagnose，找下一个 politics / finance CLEAN_HIGH 候选。

### 2026-07-09 Research Leader 分类同步修复

上一轮发现 `153` 的研究证据是 politics，但 Leader 管理侧 `copy_trading_leaders.category` 仍显示 `crypto`。这会影响：

- leader 管理页面按领域筛选。
- 第二目标 politics / finance 主策略统计。
- 后续按领域分配跟单金额。
- finance / politics source diagnose 的候选解释。

#### 根因

`LeaderResearchPoolMappingService.fillMissingCategory()` 原逻辑只在 leader.category 为空时补 research category：

```text
leader.category 非空 -> 不覆盖
```

这能保护手工 leader 分类，但会留下一个漏洞：

- 旧 leader 曾经被错误标成 sports / crypto / finance / politics。
- 后续 research evidence 已经明确为另一个单一分类。
- pool.source 是 `RESEARCH_AGENT`，说明该 pool 行由研究代理维护。
- 系统仍不会修正旧分类。

#### 修复

新增 research-managed 分类同步规则：

```text
pool.source == RESEARCH_AGENT
且 pool.locked == false
且 researchCategory 单一明确
且 leader.category != researchCategory
=> 同步 leader.category = researchCategory
```

边界：

- 手工 pool / manual leader 不覆盖。
- locked pool 不覆盖。
- mixed / unknown research evidence 不覆盖。
- 只修正 research agent 管理范围内的旧错误分类。

#### 回归测试

新增/更新：

```text
LeaderResearchPoolMappingServiceTest
```

覆盖：

1. category 为空时从 research evidence 补齐。
2. 手工已有 category 时不覆盖。
3. `RESEARCH_AGENT` 管理的旧错误 category 会被修正。

#### 运行态验证

后端已重新 `bootJar` 并重启到 tmux：

```text
polyhermes-backend-codex
/actuator/health = UP
```

对 candidate `153` 执行：

```json
{
  "dryRun": false,
  "candidateIds": [153],
  "maxCandidates": 1
}
```

结果：

| candidate | state | score | action | reason |
| ---: | --- | ---: | --- | --- |
| 153 | PAPER | 77.9036 | BLOCKED | score_below_80 |

DB 验证：

| candidate | pool_source | pool_locked | leader_name | 修复前 | 修复后 |
| ---: | --- | ---: | --- | --- | --- |
| 153 | RESEARCH_AGENT | 0 | Hideous-Racer | crypto | politics |

`1660` 保持 finance：

| candidate | state | strategy_type | leader_category |
| ---: | --- | --- | --- |
| 1660 | TRIAL_READY | human_directional | finance |

#### 结论

- `153` 不再污染 crypto 分组，已回到 politics。
- `153` 仍不进入试跟，因为 score 低于 80 且 strategy type 仍 unknown。
- 第二目标的分领域筛选口径更一致，后续 politics / finance 候选统计更可靠。

### 2026-07-09 Official Diagnose 禁用试跟入口补齐

上一轮确认 `1660` 是当前最明确的 finance clean candidate：

```text
candidate=1660
category=finance
bucket=CLEAN_HIGH
researchState=TRIAL_READY
strategy_type=human_directional
score=90.1471
copyablePnl=13.5642
```

但 Leader 研究页的 official leaderboard diagnose 样本列表原本只展示：

- wallet
- category
- bucket
- score
- research state

没有直接操作入口。用户需要再去候选列表或待决策卡片里找，容易漏掉 official 来源跑出的可试跟候选。

#### 修复

在 `/leader-research` 的 official leaderboard diagnose 样本列表中：

- 当 `item.researchState == TRIAL_READY` 时，展示“创建禁用试跟”按钮。
- 点击后复用现有 `openApprovalByCandidateId(candidateId)`。
- 后端仍会再次校验：
  - candidate 必须是 `TRIAL_READY`。
  - 创建的 copy trading config 必须是 `enabled=false`。
  - 如已存在同账户同 leader 配置，会拒绝重复创建。

#### 运行态验证

正式 diagnose 返回：

| candidate | category | bucket | state | score |
| ---: | --- | --- | --- | ---: |
| 1660 | finance | CLEAN_HIGH | TRIAL_READY | 90.1471 |

因此页面 official diagnose 第一条样本现在会出现“创建禁用试跟”入口。该入口仍是人工确认，不会自动真钱跟单。

#### 验证

```text
frontend npm run build
official-leaderboard/diagnose
```

结论：

- 第二目标从“发现 clean candidate”推进到“用户能直接看到并人工创建禁用试跟配置”。
- 当前不自动创建配置，保持研究闭环和真钱执行边界分离。

### 2026-07-09 Official Candidate 174 复核：清理伪 finance 高分样本

本轮继续执行“official leaderboard 高质量来源优先转化”。

official diagnose 中，除 `1660` 外最接近的候选是：

```text
candidate=174
wallet=0xe74d4976e5e034182d708a3b9df602e72d4722fd
source category=finance
bucket=PAPER_OBSERVING
activity score=100
strategy_type=human_directional
paper trades=0
```

它看起来像 finance 高分候选，但没有 paper 样本，因此本轮对它做单独加厚和复评。

#### 执行动作

1. `paper/process`
2. targeted `activity-score/run`
3. targeted `paper/score`
4. `trial-ready/recheck`

paper process 结果：

| 指标 | 数量 |
| --- | ---: |
| processed | 9 |
| filtered | 11 |
| failed | 0 |
| trade delta | +9 |
| filtered delta | +11 |
| copyable PnL delta | +1.5350 |

#### 复评结果

activity score 返回：

| 指标 | 结果 |
| --- | --- |
| categoryCounts | sports=1 |
| riskFlagCounts | activity_category_mismatch=1 |

最终 DB 状态：

| candidate | state | strategy_type | score | risk flags | trades | filtered | copyable PnL | filtered ratio |
| ---: | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| 174 | PAPER | human_directional | 50.0000 | activity_category_mismatch,high_filtered_ratio,tail_price_spray,small_sample | 9 | 11 | 1.5350 | 0.5500 |

trial-ready recheck：

| candidate | action | reason |
| ---: | --- | --- |
| 174 | BLOCKED | score_below_80 |

#### 真实活动摘要

`174` 的活动并非 finance 为主，而是明显偏体育：

| side | events | markets | avg amount |
| --- | ---: | ---: | ---: |
| BUY | 69 | 10 | 152.9286 |
| SELL | 11 | 9 | 505.0993 |

主要市场：

- `Will Argentina win the 2026 FIFA World Cup?`
- `Will Norway win the 2026 FIFA World Cup?`
- `Will Norway win on 2026-07-05?`
- `Paraguay vs. France: O/U 1.5`
- `Brazil vs. Norway: O/U 1.5`

结论：

- `174` 是 official finance 来源中的伪 finance 高分样本。
- 它的真实活动主类是 sports，触发 `activity_category_mismatch`。
- 过滤率 55%，不适合进入 politics / finance 主策略试跟。
- 本轮没有新增可试跟候选，但清理了一个会污染 finance 主线的高分样本。

#### Diagnose 复查

复查 official diagnose 后：

| 指标 | 结果 |
| --- | ---: |
| CLEAN_HIGH | 1 |
| PAPER_OBSERVING | 25 |
| HARD_RISK | 30 |

`174` 已不再出现在 top samples 中，当前唯一 CLEAN_HIGH 仍是 `1660`。

#### 下一步

1. 继续寻找下一个 politics / finance official CLEAN_HIGH。
2. 对 official finance 候选提高真实活动类别一致性要求。
3. 对 `source category=finance` 但真实活动为 sports 的候选，优先降权或转入 sports 队列，不占用 finance 主策略复核资源。

### 2026-07-09 Official Diagnose 真实活动类别预检

上一轮 `174` 证明 official leaderboard 的 source category 不能直接等同于可跟单分类：

- source category = finance。
- 真实活动主类 = sports。
- 如果未先跑 targeted activity score，它会以 finance 高分样本出现在 official diagnose 前列。

本轮将这个经验固化到 official diagnose 服务本身。

#### 修复

`LeaderResearchOfficialLeaderboardDiagnoseService` 现在会在诊断时读取候选 activity metrics：

```text
candidateRepository.aggregateActivityMetricsForCandidateIds(...)
```

并复用 activity scoring 的一致性口径：

```text
total activity category events >= 20
dominant activity category ratio >= 70%
dominant activity category != source category
=> 添加 activity_category_mismatch
=> bucket = CATEGORY_CONFLICT
```

这样即使候选还没有跑 targeted activity score，只要系统已有足够 activity events，official diagnose 也会提前发现真实活动类别冲突。

#### 回归测试

新增测试：

```text
LeaderResearchOfficialLeaderboardDiagnoseServiceTest
```

覆盖场景：

- official source 标为 finance。
- paper session 看起来 clean。
- activity metrics 显示 sports 30、finance 2。
- diagnose 不再输出 CLEAN_HIGH。
- bucket 为 `CATEGORY_CONFLICT`。
- riskFlagCounts 包含 `activity_category_mismatch=1`。

#### 运行态验证

重新打包并重启后端：

```text
backend bootJar
tmux polyhermes-backend-codex
/actuator/health = UP
```

正式 official diagnose：

| 指标 | 结果 |
| --- | ---: |
| CLEAN_HIGH | 1 |
| activity_category_mismatch | 49 |
| top sample | 1660 |

当前唯一 CLEAN_HIGH 仍为：

```text
1660 finance TRIAL_READY score=90.1471
```

`174` 不再进入前 50 个可复核样本。新预检在 official diagnose 层直接识别出 49 个 source category 与真实活动类别不一致的候选，说明 official 来源需要先经过真实活动分类校验，不能只按榜单分类进入 politics / finance 主策略复核。

#### 结论

- 第二目标 official 来源闭环现在多了一层“真实活动类别一致性”防线。
- 这能减少 finance / politics 主策略被 sports 或其他领域污染。
- 后续 official diagnose 的 CLEAN_HIGH 更接近真正可按领域分配资金的 leader。

### 2026-07-09 Official Leaderboard 刷新与 Top No-session 复核

本轮继续执行“补源 + 复核”闭环。

#### Official leaderboard 刷新

请求范围：

```json
{
  "categories": ["politics", "finance"],
  "timePeriods": ["WEEK", "MONTH"],
  "orderBys": ["PNL", "VOL"],
  "limitPerPage": 50,
  "maxPagesPerQuery": 2,
  "maxItems": 500
}
```

dry-run 先确认安全边界：

| 指标 | 数量 |
| --- | ---: |
| fetchedTotal | 500 |
| dedupedTotal | 334 |
| would create | 29 |
| would update | 305 |
| fetch errors | 0 |

随后执行真实导入，仍只写 research candidate / source evidence，不创建跟单配置：

| 指标 | 数量 |
| --- | ---: |
| createdTotal | 29 |
| updatedTotal | 305 |
| skippedLockedTotal | 0 |
| skippedInvalidTotal | 0 |

#### 导入后 diagnose

| 指标 | 导入后 |
| --- | ---: |
| official candidates total | 1078 |
| PAPER total | 278 |
| CLEAN_HIGH | 1 |
| READY_FOR_PAPER | 0 |
| activity_category_mismatch | 51 |

top sample 仍然只有：

```text
1660 finance CLEAN_HIGH TRIAL_READY score=90.1471
```

#### Top no-session 候选 targeted 复核

导入后 top official candidates 中出现一批 `PAPER_OBSERVING + no_paper_session` 候选。选取前 10 个执行 targeted activity score + paper score：

```text
61235, 52591, 58959, 58958, 49736, 60080, 49179, 60873, 56030, 49175
```

activity score 结果：

| 指标 | 数量 |
| --- | ---: |
| scanned | 10 |
| scored | 10 |
| politics | 2 |
| finance | 8 |
| small_sample | 10 |
| low_market_diversity | 9 |
| strategy_low_price_tail_risk | 3 |
| low_average_size | 1 |

unknown 原因：

| reason | 数量 |
| --- | ---: |
| insufficient_sample | 7 |
| insufficient_market_diversity | 6 |
| no_buy_sample | 2 |
| sell_ratio_outside_copyable_range | 2 |
| low_safe_price_ratio_for_directional | 3 |
| high_tail_price_ratio | 2 |
| low_average_size | 1 |
| no_sell_sample | 3 |

最终状态：

| 分类 | candidate | 结论 |
| --- | --- | --- |
| 样本不足 unknown | 49175, 52591, 56030, 58959, 60080, 60873, 61235 | score=59，仍无 paper trades，不晋级 |
| 低价长尾 | 49179, 49736, 58958 | score=20，`low_price_tail_risk`，不晋级 |

#### 本轮结论

- Official leaderboard 刷新增大了来源池：新增 29，更新 305。
- 但没有新增可试跟 CLEAN_HIGH。
- 新增/更新后的 top no-session 候选主要问题是样本不足，少数为低价长尾。
- 下一步不应盲目扩大 official import 页数，而应：
  1. 对新增 official 候选补 activity 样本。
  2. 过滤低价长尾和样本不足钱包。
  3. 继续寻找 politics / finance 中已有 BUY/SELL 样本、真实活动类别一致、paper PnL 为正的候选。

### 2026-07-09 Official BUY/SELL 活跃候选加厚复核

本轮按上一轮结论，不继续扩大 official import 页数，而是在现有 official 候选中筛选：

```text
source = polymarket_official_leaderboard
category = politics / finance
research_state in PAPER / TRIAL_READY
BUY > 0
SELL > 0
total activity events >= 20
distinct markets >= 5
真实活动类别 politics/finance 占比 >= 70%
未命中 activity_category_mismatch
未命中低价长尾风险
```

第一轮宽松筛选找到一批活跃 politics 候选，其中前 5 个是：

```text
503, 512, 3048, 3043, 1761
```

这些候选的共同特点：

- BUY/SELL 都存在。
- 真实活动类别主要为 politics。
- paper trades 原来为 0。
- 旧分数多为 59，risk flag 主要是 small_sample。

#### Targeted 复核

对 5 个候选执行：

1. targeted activity score
2. targeted paper/process
3. targeted paper score
4. trial-ready recheck

activity score 结果：

| 指标 | 数量 |
| --- | ---: |
| scanned | 5 |
| scored | 5 |
| politics | 5 |
| tail_price_spray | 5 |
| low_safe_price_ratio | 5 |
| strategy_low_price_tail_risk | 5 |
| low_average_size | 2 |

paper process 结果：

| candidate | processed | filtered | trade delta | filtered delta | PnL delta |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 503 | 0 | 4 | 0 | +4 | 0 |
| 512 | 1 | 3 | +1 | +3 | 0 |
| 3048 | 0 | 4 | 0 | +4 | 0 |
| 3043 | 0 | 4 | 0 | +4 | 0 |
| 1761 | 0 | 4 | 0 | +4 | 0 |

recheck 结果：

| candidate | final score | action | reason |
| ---: | ---: | --- | --- |
| 503 | 20 | BLOCKED | score_below_80 |
| 512 | 20 | BLOCKED | score_below_80 |
| 3048 | 20 | BLOCKED | score_below_80 |
| 3043 | 20 | BLOCKED | score_below_80 |
| 1761 | 20 | BLOCKED | score_below_80 |

#### 严格筛选复查

随后加入更严格条件：

```text
safe_price_ratio >= 0.50
tail_price_ratio <= 0.15
BUY > 0
SELL > 0
markets >= 5
真实活动类别 politics/finance >= 70%
```

结果：

```text
0 个候选
```

#### 结论

- Official 来源中确实存在活跃 politics 钱包，但当前这批主要是低价长尾策略。
- 它们不是可复制的 high-quality leader。
- 单靠 official leaderboard 的 PNL/VOL 扩源会持续引入大量“盈利但不可跟”的钱包。
- 下一轮需要把 official source 的预筛进一步改成：
  - 先看真实 activity safe/tail ratio。
  - 低价长尾直接排除或降到 sports/研究观察。
  - 只有 safe ratio 足够、BUY/SELL 完整、类别一致的候选才进入 paper 加厚。

### 2026-07-09 Official Safe/Tail 预筛落地

本轮将上一节的结论固化到 official leaderboard 诊断链路。

#### 改动

`LeaderResearchOfficialLeaderboardDiagnoseService` 现在会在诊断阶段读取真实活动聚合指标：

```text
total_events >= 20
safe_price_ratio = safe_price_events / total_events
tail_price_ratio = tail_price_events / total_events
```

并新增硬风险预筛：

| 条件 | 风险标记 | 诊断桶 |
| --- | --- | --- |
| safe_price_ratio < 0.50 | low_safe_price_ratio | HARD_RISK |
| tail_price_ratio > 0.15 | tail_price_spray | HARD_RISK |

这一步发生在 official diagnose 阶段，因此会阻止“paper 高分、短期盈利，但靠低价长尾铺单盈利”的候选继续显示为 CLEAN_HIGH。

#### 验证

新增测试覆盖：

```text
paper session 看起来干净：
- score > 90
- trade_count >= 10
- copyable_pnl > 0
- filtered_ratio < 0.20

但真实价格分布不可复制：
- safe_price_ratio < 0.50
或
- tail_price_ratio > 0.15

结果必须进入 HARD_RISK，而不是 CLEAN_HIGH。
```

通过的验证：

```text
LeaderResearchOfficialLeaderboardDiagnoseServiceTest
LeaderResearchControllerTest
bootJar
后端 health = UP
```

正式 diagnose 结果：

| 指标 | 数值 |
| --- | ---: |
| official total | 1078 |
| PAPER | 278 |
| CLEAN_HIGH | 0 |
| READY_FOR_PAPER | 0 |
| HARD_RISK | 116 |
| low_safe_price_ratio | 149 |
| tail_price_spray | 157 |
| activity_category_mismatch | 51 |

#### 1660 复核

本轮规则没有误伤 `1660`：

| 指标 | 数值 |
| --- | ---: |
| total_events | 1381 |
| safe_price_ratio | 0.7502 |
| tail_price_ratio | 0.1064 |
| paper trades | 23 |
| filtered_count | 11 |
| copyable_pnl | 13.5642 |

但 `1660` 当前 `source_evidence` 已混入 `activity_source:finance` 与 official 来源证据，official diagnose 不再稳定把它作为唯一 CLEAN_HIGH 输出。因此需要单独处理 official 来源证据口径：

1. 区分“官方榜单来源存在”与“当前 source_evidence 首段分类”。
2. 避免 activity score 覆盖或稀释 official source 分类。
3. 对 `1660` 保留人工复核入口，但不因来源证据混杂自动启用真钱跟单。

#### 下一步

- 修正 official diagnose 的来源分类口径，使 `source_evidence` 多来源时仍能稳定识别 official leaderboard 的原始 category。
- 继续从 politics / finance 中寻找同时满足以下条件的候选：
  - safe_price_ratio >= 0.50
  - tail_price_ratio <= 0.15
  - BUY/SELL 都存在
  - 真实活动类别与目标类别一致
  - paper PnL 为正
  - strategy_type = human_directional

### 2026-07-09 Official Source Category 优先级修复

本轮完成上一节的第一项下一步：修正 official diagnose 的来源分类口径。

#### 问题

通用 `LeaderResearchCategoryEvidenceClassifier` 会统计 `source_evidence` 中所有 `category:`：

```text
activity_source:sports | category:sports
scanner_pool:88 | category:sports
external_analytics:polymarket_official_leaderboard | category:finance
```

在这种多来源 evidence 中，通用分类会把候选判成 sports，而 official diagnose 的目标是复核 official leaderboard 来源，因此应优先尊重 official leaderboard 段里的原始 category。

#### 修复

`LeaderResearchOfficialLeaderboardDiagnoseService` 新增 official source category 优先解析：

```text
external_analytics:polymarket_official_leaderboard ... category:<category>
```

规则：

1. official leaderboard 段存在合法 category 时，diagnose 使用该 category。
2. official leaderboard 段不存在或 category 无法识别时，才回退通用分类器。
3. `bucketOf` 使用同一个 sourceCategory，不再二次调用通用分类器，避免 CATEGORY_CONFLICT 误判。

该改动只影响 official leaderboard diagnose，不改变 activity score、paper promotion、leader pool 同步等通用分类逻辑。

#### 验证

新增测试覆盖：

```text
source_evidence 中 sports category 占多数
official leaderboard 段 category=finance
diagnose category 必须是 finance
```

通过的验证：

```text
LeaderResearchOfficialLeaderboardDiagnoseServiceTest
LeaderResearchControllerTest
bootJar
后端 health = UP
```

正式 diagnose 结果：

| 指标 | 数值 |
| --- | ---: |
| official total | 1078 |
| PAPER | 278 |
| CLEAN_HIGH | 0 |
| READY_FOR_PAPER | 0 |
| HARD_RISK | 116 |
| CATEGORY_CONFLICT | 24 |
| low_safe_price_ratio | 149 |
| tail_price_spray | 157 |
| activity_category_mismatch | 57 |

#### 1660 当前状态

修复后 `1660` 仍未进入 official diagnose top 50 sample。直接原因不是分类解析失败，而是来源已过期：

| 指标 | 数值 |
| --- | ---: |
| research_state | TRIAL_READY |
| score | 90.1471 |
| last_source_age | 56.1h |
| diagnose staleHours | 48h |
| safe_price_ratio | 0.7502 |
| tail_price_ratio | 0.1064 |
| paper trades | 23 |
| copyable_pnl | 13.5642 |

结论：

- `1660` 没有被 safe/tail 规则误伤。
- `1660` 也不是因为 official category 解析失败而消失。
- 当前阻断点是 official source 新鲜度，说明它需要重新刷新官方榜单来源，或在页面上单独展示“过期但历史高质量”的人工复核对象。

#### 下一步

- 增加 official stale high-quality 观察口径：不要把 stale 直接混入 CLEAN_HIGH，但应在 diagnose 或日报中单独显示“过期高质量候选”，方便决定是否刷新来源或降权。
- 继续寻找 politics / finance 中同时满足 safe/tail、BUY/SELL、类别一致、paper PnL 正、`human_directional` 的候选。

### 2026-07-09 Official Stale High-Quality 观察桶

本轮完成上一节的第一项下一步：新增 official stale high-quality 观察口径。

#### 问题

之前所有过期来源都会进入 `STALE_ACTIVITY`。这会导致两类完全不同的候选混在一起：

1. 普通 stale 候选：来源过期，且没有足够质量证据。
2. 过期高质量候选：来源过期，但历史 paper 表现、评分和风险标记仍然较好。

对第二目标来说，第二类不应进入 `CLEAN_HIGH`，因为 official 来源不新鲜；但也不应该被普通 stale 淹没，因为它们是优先刷新来源的对象。

#### 修复

新增 diagnose bucket：

```text
STALE_HIGH_QUALITY
```

准入条件：

| 条件 | 要求 |
| --- | --- |
| official category | politics / finance |
| state | PAPER / TRIAL_READY |
| score | >= 80 |
| paper trades | >= 10 |
| copyable PnL | > 0 |
| risk flags | 除 stale_activity 外为空 |

优先级：

1. 硬风险仍优先于 stale high-quality。
2. 类别冲突仍优先于 stale high-quality。
3. `STALE_HIGH_QUALITY` 不计入 `CLEAN_HIGH`。
4. `STALE_HIGH_QUALITY` 在 sample 排序中靠前，方便人工刷新或降权。

#### 验证

新增测试覆盖：

```text
finance TRIAL_READY
score=90
paper trades=23
copyable PnL=13.5
last_source_age=56h
staleHours=48

结果：
bucket=STALE_HIGH_QUALITY
cleanHighTotal=0
```

通过的验证：

```text
LeaderResearchOfficialLeaderboardDiagnoseServiceTest
LeaderResearchControllerTest
bootJar
后端 health = UP
```

正式 diagnose 结果：

| 指标 | 数值 |
| --- | ---: |
| official total | 1078 |
| PAPER | 278 |
| CLEAN_HIGH | 0 |
| READY_FOR_PAPER | 0 |
| STALE_HIGH_QUALITY | 1 |
| HARD_RISK | 169 |
| CATEGORY_CONFLICT | 51 |
| PAPER_OBSERVING | 19 |
| low_safe_price_ratio | 149 |
| tail_price_spray | 157 |
| activity_category_mismatch | 57 |

`STALE_HIGH_QUALITY` 当前唯一样本：

| candidate | category | state | score | paper trades | copyable PnL | source age |
| ---: | --- | --- | ---: | ---: | ---: | ---: |
| 1660 | finance | TRIAL_READY | 90.1471 | 23 | 13.5642 | 56h |

结论：

- `1660` 已重新出现在 official diagnose top sample。
- 它不会被当作新鲜 `CLEAN_HIGH`。
- 它应该进入“刷新 official source / 人工复核是否保留”的队列。

#### 下一步

- 在 Leader 研究页或优化日报中显式展示 `STALE_HIGH_QUALITY` 数量和样本。
- 对 `1660` 这类 stale high-quality 候选，优先执行 official source refresh，而不是直接创建或启用真钱跟单配置。

### 2026-07-09 Stale High-Quality 前端可观测

本轮完成上一节第一项：在 Leader 研究页 official diagnose 卡片中展示 `STALE_HIGH_QUALITY`。

#### 页面变化

Leader 研究页的“官方榜单质量诊断”现在新增：

| UI 元素 | 行为 |
| --- | --- |
| 过期高质量统计 | 显示 `STALE_HIGH_QUALITY` bucket 数量 |
| bucket tag | `STALE_HIGH_QUALITY` 使用 gold 色 |
| 样本行 | 显示 bucket、research state、以及“需刷新来源”提示 |
| 试跟按钮 | `STALE_HIGH_QUALITY` 即使是 `TRIAL_READY`，也不显示“创建禁用试跟”按钮 |

#### 安全边界

这个 UI 改动只提高可观测性，不改变准入规则：

- 不创建 copy trading config。
- 不启用真钱跟单。
- 不把 stale 候选计入 `CLEAN_HIGH`。
- stale high-quality 候选必须先刷新 official source 或人工确认 stale 策略。

#### 验证

```text
frontend npm run build
```

构建通过。

#### 下一步

- 在 official diagnose 卡片上增加“刷新 official 来源”动作，针对 stale high-quality 候选优先刷新来源。
- 刷新后再决定候选应回到 `CLEAN_HIGH`、继续 `STALE_HIGH_QUALITY`，还是降权。

### 2026-07-09 Official Source Refresh 动作

本轮完成上一节第一项：为 stale high-quality 候选增加定向刷新 official source 的动作。

#### 后端接口

新增接口：

```text
POST /api/copy-trading/leader-research/official-leaderboard/refresh-candidates
```

请求支持：

| 字段 | 说明 |
| --- | --- |
| dryRun | 默认 true |
| candidateIds | 按研究候选 ID 刷新 |
| wallets | 直接按钱包刷新 |
| categories | 默认 politics / finance |
| timePeriods | 默认 MONTH |
| orderBys | 默认 PNL |
| limitPerPage / maxPagesPerQuery | 控制 official leaderboard 抓取范围 |

安全边界：

- 只筛选请求中的目标钱包。
- 复用 external analytics import 的去重、锁定保护、evidence 追加、`lastSourceSeenAt` 更新。
- 不创建 copy trading config。
- 不启用真钱跟单。

#### 前端动作

Leader 研究页 official diagnose 样本行中：

- `STALE_HIGH_QUALITY` 候选显示“需刷新来源”按钮。
- 点击后执行定向 official refresh。
- 刷新后自动重跑 official diagnose。

#### 运行态验证

对 candidate `1660` 执行 dry-run：

| 指标 | 数值 |
| --- | ---: |
| requestedWallets | 0x5b6331e7ff0831a3fe2ed12004747db1a9c911a4 |
| fetchedTotal | 1000 |
| matchedTotal | 1 |
| official rank | 114 |
| category | finance |
| period/order | MONTH / PNL |

随后正式刷新：

| 指标 | 数值 |
| --- | ---: |
| updatedTotal | 1 |
| skippedLockedTotal | 0 |
| lastSourceAgeHours | 0 |

再次 official diagnose：

| 指标 | 数值 |
| --- | ---: |
| CLEAN_HIGH | 1 |
| STALE_HIGH_QUALITY | 0 |
| candidate 1660 bucket | CLEAN_HIGH |
| score | 90.1471 |
| paper trades | 23 |
| copyable PnL | 13.5642 |
| risk flags | 空 |

#### 验证

```text
LeaderResearchOfficialLeaderboardImportServiceTest
LeaderResearchControllerTest
frontend npm run build
bootJar
```

均通过。

#### 下一步

- 将 `CLEAN_HIGH + TRIAL_READY + human_directional + riskFlags 空` 的 official 候选纳入“禁用试跟人工确认”主队列。
- 对 `1660` 继续保持不自动启用真钱；下一步应检查是否已存在重复配置，若无则只创建 disabled trial config 供人工确认。

### 2026-07-09 改进计划 v3：Official Clean High 转禁用试跟主队列

本轮把第二目标的下一步从“发现并刷新高质量 official 候选”收敛为“建立可控的禁用试跟人工确认主队列”。目标不是自动实盘，而是让系统能稳定回答：

```text
哪些 official 来源的 politics / finance leader 已经足够干净，可以交给人工确认创建 disabled trial config？
```

#### 改进目标

1. official diagnose 不只展示样本，还要输出“可进入禁用试跟人工确认”的数量。
2. 只有满足完整可复制条件的候选才显示创建入口。
3. stale、分类冲突、低价长尾、非 human directional、risk flags 非空的候选不得进入主队列。
4. 对 `1660` 这类候选保持人工确认边界：可以创建 disabled trial config，但绝不自动启用真钱跟单。

#### 主队列准入条件

候选必须同时满足：

| 条件 | 要求 |
| --- | --- |
| official bucket | `CLEAN_HIGH` |
| research state | `TRIAL_READY` |
| strategy type | `human_directional` |
| risk flags | 空 |
| category | politics / finance 优先 |
| source freshness | 不 stale，`lastSourceAgeHours <= staleHours` |
| paper result | paper trades 达标，copyable PnL 为正 |
| config 状态 | 不存在重复 copy trading config |

明确排除：

- `STALE_HIGH_QUALITY`：只能先刷新来源或人工降权。
- `HARD_RISK`：包括低安全价格比例、长尾低价铺单、不可复制机制。
- `CATEGORY_CONFLICT`：official 来源类别与真实活动类别冲突。
- `strategy_type=unknown` 或非 `human_directional`。
- 任意非空 risk flag。

#### 工程落地计划

阶段 1：后端诊断口径

1. `LeaderResearchOfficialLeaderboardSampleDto` 增加 `strategyType`。
2. `LeaderResearchOfficialLeaderboardDiagnoseResponse` 增加 `disabledTrialCandidateTotal`。
3. 在 diagnose service 中新增统一判定函数：

```text
bucket=CLEAN_HIGH
researchState=TRIAL_READY
strategyType=human_directional
riskFlags empty
category in politics/finance
```

4. 单测覆盖：
   - clean human directional TRIAL_READY 计入主队列。
   - unknown strategy 不计入。
   - stale high-quality 不计入。
   - risk flags 非空不计入。

阶段 2：前端人工确认入口

1. Leader 研究页 official diagnose 卡片显示“禁用试跟候选”统计。
2. 样本行展示 `strategyType` 标签。
3. “创建禁用试跟”按钮仅在主队列条件满足时显示。
4. `STALE_HIGH_QUALITY` 继续只显示“刷新 official 来源”，不显示试跟按钮。

阶段 3：重复配置与安全边界

1. 创建 disabled trial config 前检查重复配置。
2. 后端继续强制 `enabled=false`。
3. 页面文案明确这是“人工确认/禁用试跟”，不是启用真钱。
4. 日志记录 candidateId、wallet、bucket、strategyType、riskFlags、创建结果。

阶段 4：运行态验证

1. 重启后端并验证 `/actuator/health=UP`。
2. 调用 official diagnose，确认：

```text
disabledTrialCandidateTotal >= 1
1660 bucket=CLEAN_HIGH
1660 researchState=TRIAL_READY
1660 strategyType=human_directional
1660 riskFlags=[]
```

3. 前端构建通过。
4. 页面上只对符合条件的样本展示“创建禁用试跟”。

#### 验收指标

| 指标 | 目标 |
| --- | ---: |
| official 主队列统计 | 有 `disabledTrialCandidateTotal` |
| 主队列误入 stale 候选 | 0 |
| 主队列误入 unknown strategy | 0 |
| 主队列误入 risk flags 非空候选 | 0 |
| 创建配置默认 enabled | false |
| 自动启用真钱跟单 | 0 |

#### 下一步执行

下一轮直接实施阶段 1 和阶段 2：

1. 后端 DTO / diagnose service / 单测。
2. 前端类型 / Leader 研究页统计与按钮 gating。
3. 构建与后端目标测试。
4. 运行态验证 `1660` 是否进入禁用试跟人工确认主队列。

### 2026-07-09 Official Clean High 禁用试跟主队列落地

本轮完成 v3 的阶段 1 和阶段 2：official diagnose 已能输出“禁用试跟人工确认主队列”，Leader 研究页也已按同一口径展示统计和创建入口。

#### 后端变化

- `LeaderResearchOfficialLeaderboardSampleDto` 新增 `strategyType`。
- `LeaderResearchOfficialLeaderboardDiagnoseResponse` 新增 `disabledTrialCandidateTotal`。
- official diagnose 中新增主队列判定：

```text
bucket=CLEAN_HIGH
researchState=TRIAL_READY
strategyType=human_directional
riskFlags empty
category in politics/finance
```

#### 前端变化

- Leader 研究页 official diagnose 卡片新增“禁用试跟候选”统计。
- official sample 行展示 `strategyType` 标签。
- “创建禁用试跟”按钮只在主队列条件全部满足时显示。
- `STALE_HIGH_QUALITY` 仍只显示刷新 official 来源按钮，不显示试跟入口。

#### 运行态验证

后端重启后：

```text
/actuator/health = UP
```

正式 official diagnose：

| 指标 | 数值 |
| --- | ---: |
| total | 1078 |
| CLEAN_HIGH | 1 |
| disabledTrialCandidateTotal | 1 |

当前主队列样本：

| candidate | category | bucket | state | strategyType | score | riskFlags |
| ---: | --- | --- | --- | --- | ---: | --- |
| 1660 | finance | CLEAN_HIGH | TRIAL_READY | human_directional | 90.1471 | 空 |

#### 验证命令

```text
backend ./gradlew test --tests LeaderResearchOfficialLeaderboardDiagnoseServiceTest --tests LeaderResearchControllerTest
frontend npm run build
backend ./gradlew bootJar
```

均通过。

#### 下一步

- 对 `1660` 执行人工确认式的 disabled trial config 创建前检查：确认无重复配置、账户选择正确、默认 `enabled=false`。
- 继续 official leaderboard / external analytics 复核，寻找下一个 politics / finance `CLEAN_HIGH + human_directional` 候选。

### 2026-07-09 Disabled Trial Approval Precheck 落地

本轮继续推进 `1660` 从“主队列候选”到“可人工确认创建 disabled trial config”的前置检查闭环。

#### 修复的问题

此前 Leader 研究页已经收紧按钮显示条件，但后端 `approval/create-disabled-trial-config` 仍主要依赖 `TRIAL_READY` 和 `enabled=false`，直接调用 API 时没有再次强制校验：

```text
strategyType=human_directional
riskFlags empty
category in politics/finance
```

这会导致页面外调用绕过“可复制 leader”门槛。

#### 后端变化

- `LeaderResearchApprovalService.createDisabledTrialConfig()` 增加审批硬门槛：
  - 必须 `TRIAL_READY`。
  - 必须 `strategyType=human_directional`。
  - `riskFlags` 必须为空。
  - official/category evidence 必须落在 politics / finance。
  - 必须已有 leader mapping。
- 新增错误码：
  - `LEADER_RESEARCH_CANDIDATE_NOT_COPYABLE`
- 新增只读预检接口：

```text
POST /api/copy-trading/leader-research/approval/preview-disabled-trial-config
```

预检返回：

- candidate / leader / pool id。
- category、strategyType、researchState、riskFlags、locked。
- `canCreate` 与 blocker codes。
- 每个账户是否已有重复 copy trading config。

#### 前端变化

Leader 研究页创建禁用试跟弹窗：

- 打开前先调用 approval preview。
- 默认选择第一个没有重复配置的账户。
- 展示预检通过/阻断原因。
- 账户下拉中标记已有配置的账户，并禁用这些选项。
- 如果 `canCreate=false`，禁用提交按钮。

#### 运行态验证

对 candidate `1660` 调用正式 preview：

| 字段 | 值 |
| --- | --- |
| code | 0 |
| candidateId | 1660 |
| leaderId | 516 |
| poolId | 99 |
| category | finance |
| strategyType | human_directional |
| researchState | TRIAL_READY |
| riskFlags | 空 |
| locked | false |
| canCreate | true |
| blockerCodes | 空 |

账户预检：

| accountId | accountName | readOnly | duplicateConfigId |
| ---: | --- | --- | --- |
| 1 | Binance - EVM | false | 空 |
| 2 | zhangmin0421@gmail.com | true | 空 |
| 3 | kimi05082021@163.com | true | 空 |

#### 验证命令

```text
backend ./gradlew test --tests LeaderResearchApprovalServiceTest --tests LeaderResearchControllerTest
frontend npm run build
backend ./gradlew bootJar
```

均通过。后端已重启，`/actuator/health=UP`。

#### 下一步

- 等待人工选择账户后再创建 disabled trial config；本轮不自动创建。
- 继续查找下一个 politics / finance `CLEAN_HIGH + human_directional` 候选，避免第二目标只依赖单一 finance 样本。

### 2026-07-10 改进计划 v4：把“近期活跃 + 全年盈利”升级为硬门槛

本轮根据最新筛选结果反馈更新第二目标：当前系统已经能排除一批低价长尾、类别错配、不可复制机制和 stale official source，但筛出的 leader 仍存在两个质量缺口：

1. 有些候选近期不活跃，source 曾经高分但实际已经不适合跟单。
2. 有些候选短周期或局部市场表现好，但全年或长期维度是亏损的，容易被短期 PnL / paper copyable PnL 误判为高质量。

因此，第二目标下一阶段不再只看：

```text
CLEAN_HIGH + TRIAL_READY + human_directional + riskFlags empty
```

而要升级为：

```text
CLEAN_HIGH + TRIAL_READY + human_directional + riskFlags empty
+ active_recently + profitable_multi_window + half_year_pnl_positive
+ paper copyable PnL positive + source fresh + category stable
```

#### 新准入原则

| 维度 | 旧口径 | 新口径 |
| --- | --- | --- |
| 活跃度 | source fresh / activity freshness 粗过滤 | 必须有近 7 天或近 14 天真实成交，且近 72 小时来源刷新只是最低要求 |
| 盈利 | paper copyable PnL > 0 | 必须同时看 30D / 90D / 180D 或 6M，半年亏损直接阻断 |
| 稳定性 | 稳定高分 3 次 | 连续多窗口盈利一致，不允许只靠单个短周期 spike 晋级 |
| 样本 | paper trades >= 10/20 | paper trades 仍保留，但需要覆盖 BUY 和 SELL，且不能只集中在一个市场 |
| 来源 | official / Falcon / Polymarket Analytics 作为候选来源 | 外部 source 只作为发现入口，必须被本地活动和 paper 回测复核 |
| 试跟 | disabled trial 人工确认 | 创建前必须再执行质量复核 preview，阻断不活跃和全年亏损 |

#### 新增硬阻断规则

以下任意一条命中，候选不得进入 disabled trial 主队列，也不得创建跟单模板：

1. `inactive_recently`：近 7 天没有真实成交，或近 14 天成交数低于最低样本要求。
2. `half_year_pnl_negative`：180D / 6M PnL 为负。
3. `multi_window_profit_inconsistent`：短周期为正，但 90D 或 180D 为负。
4. `recent_pnl_negative`：近 30D 明显亏损，即使全年为正也先进入观察。
5. `single_market_concentration`：主要利润来自单一市场或单一事件，不能证明 leader 能长期复制。
6. `stale_profitable_snapshot`：历史高分但最近 source / activity 没刷新，只能进 stale high quality，不进试跟。

#### 数据补强计划

第一阶段先不扩大扫链数量，而是补齐现有候选的数据质量字段。

1. 为 official leaderboard / Falcon / Polymarket Analytics / Polyburg 来源统一解析多周期指标：
   - `pnl_7d`
   - `pnl_30d`
   - `pnl_90d`
   - `pnl_180d`
   - `pnl_6m`
   - `trade_count_7d`
   - `trade_count_30d`
   - `last_trade_at`

2. 在 `source_evidence` 中追加标准化证据：

```text
profit_window:7d:<value>
profit_window:30d:<value>
profit_window:90d:<value>
profit_window:180d:<value>
profit_window:6m:<value>
profit_window:all:<value>
activity_window:7d_trades:<count>
activity_window:30d_trades:<count>
last_trade_at:<timestamp>
```

3. 后续再考虑单独建表 `leader_research_external_metric_snapshot`，但第一轮先复用 `source_evidence`，避免过早扩表。

#### 评分与状态机改造计划

##### 阶段 1：新增质量解析器

新增一个轻量解析器，例如：

```text
LeaderResearchProfitWindowParser
```

职责：

- 从 `source_evidence` 解析多周期 PnL 和活跃度。
- 输出 `halfYearPnlPositive`、`recentlyActive`、`multiWindowConsistent`。
- 生成 blocker codes：
  - `inactive_recently`
  - `half_year_pnl_negative`
  - `multi_window_profit_inconsistent`
  - `recent_pnl_negative`

验收：

- 单测覆盖缺失数据、全年亏损、短期盈利但长期亏损、近期不活跃、全窗口盈利。

##### 阶段 2：收紧 official diagnose

在 `LeaderResearchOfficialLeaderboardDiagnoseService` 中加入新 blocker：

- 若缺少长期 PnL 数据，不直接归入 `CLEAN_HIGH`，改为 `NEEDS_PROFIT_WINDOW`.
- 若全年亏损，归入 `HARD_RISK`。
- 若近期不活跃，归入 `STALE_ACTIVITY` 或新增 `INACTIVE_RECENTLY`。
- 只有多周期盈利和近期活跃都满足时，才能进入 `CLEAN_HIGH`。

验收：

- `disabledTrialCandidateTotal` 不包含全年亏损候选。
- `CLEAN_HIGH` 不包含近 7 天无成交候选。
- 页面能看到被阻断的具体原因。

##### 阶段 3：收紧 trial-ready recheck

在 `LeaderResearchTrialReadyRecheckService` 中追加硬门槛：

```text
half_year_pnl_positive
recently_active
multi_window_profit_consistent
```

即使候选已有 paper PnL 正数，只要外部长期 PnL 显示全年亏损，也不能从 PAPER 晋级到 TRIAL_READY。

验收：

- 已经 TRIAL_READY 但后续发现全年亏损的候选，recheck 后应降级或进入 COOLDOWN。
- `trialReadyCandidateIds` 不再包含长期亏损候选。

##### 阶段 4：收紧 disabled trial approval preview

在 `approval/preview-disabled-trial-config` 和 `createDisabledTrialConfig` 中加入同样硬校验：

- 不活跃：拒绝创建。
- 全年亏损：拒绝创建。
- 多周期盈利不一致：拒绝创建。
- 数据缺失：允许显示“需补数据”，但不允许创建。

验收：

- 页面按钮即使误显示，后端也必须拒绝。
- blocker codes 能直接解释拒绝原因。

##### 阶段 5：Leader 研究页展示

Leader 研究页 official diagnose / 主队列样本新增展示：

- 近 7 天成交数。
- 近 30 天 PnL。
- 近 90 天 PnL。
- 180D / 6M PnL。
- 最近成交时间。
- 阻断原因标签。

目标是让人工复核时不用再猜：

```text
这个 leader 是真的持续赚钱，还是只在某个短窗口/单市场碰巧好看？
```

#### Loop Engineering 执行路径

Goal：把第二目标从“筛出高分 leader”升级为“筛出近期活跃、长期盈利、可复制的 politics / finance leader”。

Trigger：每次 leader research recommendation dry-run 后，自动输出不活跃/全年亏损/多周期不一致的统计；人工点击执行下一步时，只处理通过多周期质量门槛的候选。

Memory：继续写入：

- `LOOP_STATE.md`
- `docs/archive/goals/leader-discovery-goal-2-history.md`

执行顺序：

1. 先补 `ProfitWindowParser` 和 evidence 标准化，不改交易执行。
2. 再把 blocker 接入 official diagnose，先观察阻断数量。
3. 再接入 trial-ready recheck，防止长期亏损候选晋级。
4. 最后接入 approval preview，防止页面或 API 绕过。
5. 每轮输出：
   - `CLEAN_HIGH`
   - `NEEDS_PROFIT_WINDOW`
   - `INACTIVE_RECENTLY`
   - `ANNUAL_PNL_NEGATIVE`
   - `MULTI_WINDOW_INCONSISTENT`
   - `disabledTrialCandidateTotal`

#### 下一步执行

下一轮直接实施阶段 1 和阶段 2：

1. 新增多周期盈利/活跃度解析器和单测。
2. official diagnose 增加 `NEEDS_PROFIT_WINDOW`、`INACTIVE_RECENTLY`、`ANNUAL_PNL_NEGATIVE` 等 bucket/risk flags。
3. Leader 研究页展示新 bucket 与阻断原因。
4. 运行 official diagnose，重新评估当前筛出的候选是否仍然合格。
