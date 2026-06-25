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
