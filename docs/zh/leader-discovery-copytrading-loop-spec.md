# 扫链发现高质量可跟单 Leader 项目规格

## 目标

建立一套以“扫链发现高胜率、高质量、可复制跟单 Leader”为核心的自动优化系统。

系统目标不是简单扩大 Leader 数量，而是持续发现、分类、评分、回测、告警、淘汰，并持续优化真实跟单执行链路，尤其是 sell 跟随时效和成功率。

本规格以 Loop Engineering 模式运行：每天自动发现问题、执行优化、验证结果、输出日报，并把优化点展示在独立页面中。

关联原则文档：

- [Leader 筛选和交易原则](./leader%20筛选和交易原则.md)

## 核心业务目标

1. 扫链发现高质量 Leader。
2. 按领域准确分类和评分。
3. 以政治、金融为主要资金配置方向，占比 80%。
4. 体育、加密货币作为机会型配置，占比 20%。
5. 为所有 Leader 建立持续回测。
6. Leader 评分低于阈值时自动告警。
7. 持续优化跟单执行链路。
8. sell 跟随必须强调第一时间执行和成功率。
9. 每日自动生成优化日报，并在新页面展示。

## 领域与资金分配

系统支持四类 Leader：

- politics
- finance
- sports
- crypto

默认资金分配原则：

| 领域 | 占比 | 策略定位 |
| --- | ---: | --- |
| politics | 40% | 主策略，偏中低频、信息型跟单 |
| finance | 40% | 主策略，宏观/数据事件驱动 |
| sports | 10% | 机会策略，严格限价和延迟控制 |
| crypto | 10% | 机会策略，高风险、低额度、严格过滤 |

主策略合计 80%，机会策略合计 20%。

实际资金分配应由领域占比、Leader 评分、可复制收益、回撤和近期状态共同决定。

示例：

```text
leader_allocation =
  account_available_balance
  * category_weight
  * leader_score_weight
  * risk_adjustment
```

## Leader 生命周期

Leader 不应从发现后直接进入真钱跟单，应经历以下状态：

1. DISCOVERED  
   扫链发现的钱包，尚未完成评分。

2. CANDIDATE  
   有明确分类和初步指标，可进入观察。

3. BACKTESTING  
   已纳入历史回测和纸交易验证。

4. WATCHLIST  
   评分达标，但尚未开启真钱跟单。

5. TRIAL  
   小额试跟，严格风控。

6. ACTIVE  
   正式跟单，但仍持续监控。

7. DEGRADED  
   评分下降、sell 失败率升高、回撤异常或近期表现恶化。

8. DISABLED  
   暂停跟单。

9. RETIRED  
   淘汰，不再参与自动资金分配。

## 扫链发现策略

候选发现源应持续扩展，避免候选池过小。

### 数据源

必须支持：

- Polymarket activity 全局交易流。
- 热门 market 最近成交钱包。
- 已有 Leader。
- Leader Research Candidate。
- Bridge trade raw payload。
- 手动 seed wallets。
- 按类别 seed wallets。

建议新增：

- 每日热门 market 扫描。
- 按 category 拉取最近活跃 market。
- 按成交量/交易频率提取活跃钱包。
- 从高质量 Leader 的对手盘和同市场活跃钱包扩散候选。

### 候选池沉淀

应建立持久化 candidate pool，而不是每次临时扫描。

候选池至少记录：

- wallet address
- inferred category
- source
- source confidence
- first seen time
- last seen time
- hit count
- related market count
- analyzed count
- last analysis time
- latest score
- latest status
- disabled reason

## 分类原则

每个 Leader 必须有明确主分类，也允许存在多分类画像。

分类来源包括：

- market category
- market title
- market slug
- event title
- event slug
- activity history
- position history
- user manual override

分类置信度低时，不应直接进入真钱跟单。

最低要求：

- politics / finance 必须能清晰识别事件类别。
- sports 必须识别体育、电竞、O/U、赛事类关键词。
- crypto 必须识别币种、链上、交易所、短周期涨跌市场。

## 评分模型

Leader Score 应服务于“是否值得跟单”，而不是只证明 Leader 自己赚过钱。

推荐总分为 0 到 100：

```text
leader_score =
  category_fit_score * 0.15
  + historical_win_score * 0.15
  + reproducible_pnl_score * 0.25
  + sell_follow_score * 0.15
  + liquidity_score * 0.10
  + recency_score * 0.10
  + risk_score * 0.10
```

### 分类匹配分

衡量 Leader 是否在该领域持续交易，而不是偶然出现。

指标：

- category trade ratio
- category pnl ratio
- category market count
- category active days

### 历史胜率分

不能只看绝对胜率，应结合样本量。

指标：

- total trades
- closed position count
- win rate
- confidence interval
- minimum sample threshold

### 可复制收益分

这是最重要的评分。

衡量系统按真实延迟、真实价格和真实风控规则跟单后是否仍然赚钱。

指标：

- simulated copy pnl
- simulated copy roi
- average entry slippage
- missed opportunity rate
- rejection reason distribution

### Sell 跟随分

sell 是跟单系统的核心风控指标。

指标：

- leader sell detected count
- system sell attempted count
- system sell success count
- average sell detection delay
- average sell order submit delay
- average sell fill delay
- sell failure rate
- stale position count

### 流动性分

指标：

- average market depth
- average spread
- average executable size
- slippage by order size

### 活跃度分

指标：

- last trade time
- active days in recent window
- trades in recent window
- decay-adjusted performance

### 风险分

指标：

- max drawdown
- consecutive loss count
- market concentration
- category drift
- abnormal trade size
- suspected wash/market-maker pattern

## 入选和淘汰阈值

默认阈值：

| 状态 | 条件 |
| --- | --- |
| CANDIDATE | score >= 45 |
| WATCHLIST | score >= 60，且完成基础回测 |
| TRIAL | score >= 70，且 paper trading 可复制收益为正 |
| ACTIVE | score >= 80，sell 跟随分达标 |
| DEGRADED | score < 60 或 sell 失败率异常 |
| DISABLED | score < 50 或触发严重风控 |

强制告警条件：

- ACTIVE Leader score 低于 70。
- 任意 Leader score 单日下降超过 15。
- sell failure rate 超过 10%。
- average sell detection delay 超过 3 秒。
- average sell submit delay 超过 5 秒。
- 单 Leader 当日回撤超过阈值。
- category drift 明显，Leader 交易领域发生变化。

## 回测体系

所有 Leader 都必须建立回测，不仅是已启用跟单的 Leader。

### 回测类型

1. 历史行为回测  
   用 Leader 历史交易和 market 结果评估自身表现。

2. 可复制跟单回测  
   按系统实际延迟、限价、滑点和风控规则模拟跟单。

3. Paper Trading 前向验证  
   发现 Leader 后，从下一笔交易开始模拟，避免历史幸存者偏差。

4. Sell 跟随回测  
   检查 Leader sell 后系统是否能及时检测、提交、成交。

### 回测输出

每个 Leader 至少输出：

- score
- category
- category confidence
- backtest pnl
- reproducible pnl
- win rate
- max drawdown
- sell success rate
- sell average delay
- recommended status
- recommended allocation weight
- warning list

## 跟单执行原则

系统不应直接复制所有信号，必须经过交易门禁。

### Buy 门禁

必须通过：

- Leader 状态允许跟单。
- market category 与 Leader category 匹配。
- 当前价格未超过最大偏离。
- 成交延迟未超过最大阈值。
- 市场深度足够。
- spread 未超过阈值。
- 单市场仓位未超限。
- 单 Leader 仓位未超限。
- 单日亏损未超限。
- 不在 DISABLED / DEGRADED 状态。

### Sell 门禁

sell 与 buy 不同。sell 的优先级更高，应以降低风险和同步退出为目标。

当 Leader 出现 sell 行为时，系统应：

1. 第一时间检测到 sell。
2. 确认对应系统持仓。
3. 立即生成 sell intent。
4. 以最快路径提交订单。
5. 失败后进入快速重试。
6. 多次失败后告警。
7. 记录完整延迟链路。

sell 不应被普通 buy 风控阻塞。除非出现极端保护条件，否则应优先执行。

## Sell 时效性目标

目标 SLO：

| 指标 | 目标 |
| --- | ---: |
| sell detection p50 | <= 1 秒 |
| sell detection p95 | <= 3 秒 |
| sell intent created p95 | <= 1 秒 |
| sell order submitted p95 | <= 5 秒 |
| sell success rate | >= 95% |
| sell retry visible alert | <= 30 秒 |

必须记录链路时间戳：

- leader sell event time
- activity received time
- parsed time
- matched position time
- sell intent created time
- order submitted time
- order acknowledged time
- order filled time
- final status time

## 告警体系

告警分为 Leader 质量告警和执行链路告警。

### Leader 质量告警

- score 低于阈值。
- 回测收益转负。
- 近期胜率快速下滑。
- 领域漂移。
- 样本不足但被分配资金。
- paper trading 与真实表现偏离过大。

### 执行链路告警

- sell 检测延迟超阈值。
- sell 提交失败。
- sell 成交失败。
- buy 成功但 sell 链路不可用。
- bridge webhook 失败率升高。
- API 凭证/签名/余额异常。
- WebSocket 断连或长时间无消息。

告警渠道：

- 系统页面。
- Telegram/通知系统。
- 每日优化日报。

## 每日 Loop Engineering 优化循环

每日自动执行一个优化循环。

### Loop 目标

每天识别至少一个可验证的系统改进点，并完成以下闭环：

```text
discover -> analyze -> propose -> implement -> verify -> report
```

### 输入

- Leader scan result
- candidate pool changes
- backtest result
- paper trading result
- buy/sell execution logs
- bridge trade records
- webhook logs
- failed order reasons
- system error logs

### 每日流程

1. Discover  
   自动聚合过去 24 小时的问题和机会。

2. Rank  
   按收益影响、风险影响、失败频率、实现成本排序。

3. Select  
   选择 1 到 3 个优化点。

4. Implement  
   自动生成或执行代码/配置/数据修正方案。

5. Verify  
   运行测试、构建、接口验证、数据验证。

6. Report  
   生成日报，写入数据库并展示到页面。

7. Escalate  
   需要人工决策时标记为 blocked，并说明原因。

### 每日优化优先级

优先级从高到低：

1. sell 失败或延迟。
2. buy/sell 链路异常。
3. Leader score 错误或分类错误。
4. 回测与真实表现偏离。
5. 候选池过小。
6. API 限速或数据缺失。
7. 页面可观察性不足。

## 优化日报页面

需要新增页面：

```text
/leader-optimization-report
```

中文名称：

```text
Leader 优化日报
```

### 页面目标

让用户每天看到系统做了什么、发现了什么、修了什么、还有什么风险。

### 页面模块

1. 今日摘要

- scan candidate count
- new leaders
- updated leaders
- degraded leaders
- disabled leaders
- sell success rate
- average sell delay
- failed sell count
- alerts count

2. 今日优化点

- title
- category
- priority
- status
- reason
- action taken
- verification result
- related files or config

3. Leader 评分变化

- leader address
- category
- previous score
- current score
- delta
- status change
- alert reason

4. Sell 链路健康

- detected sells
- attempted sells
- successful sells
- failed sells
- p50/p95 delay
- top failure reasons

5. 候选池增长

- discovered candidates
- candidates by category
- candidates promoted to watchlist
- candidates rejected
- rejection reasons

6. 回测结果

- leaders backtested
- reproducible pnl summary
- leaders below threshold
- recommended actions

7. Blocked / Needs Human Decision

- issue
- impact
- attempted actions
- required decision

### 页面交互

- 按日期筛选。
- 按 category 筛选。
- 按 severity 筛选。
- 点击 Leader 地址跳转 Leader 详情。
- 点击告警查看原始日志。
- 支持重新运行某天报告生成。

## 数据模型建议

### leader_candidate_pool

用于沉淀扫链候选。

关键字段：

- id
- wallet_address
- category
- category_confidence
- source
- hit_count
- first_seen_at
- last_seen_at
- last_analyzed_at
- latest_score
- status
- disabled_reason
- created_at
- updated_at

### leader_score_snapshot

用于记录评分历史。

关键字段：

- id
- leader_id
- wallet_address
- category
- score
- score_breakdown_json
- status
- warning_json
- snapshot_at

### leader_backtest_result

用于记录回测。

关键字段：

- id
- leader_id
- category
- window_start
- window_end
- trade_count
- win_rate
- pnl
- reproducible_pnl
- max_drawdown
- sell_success_rate
- sell_average_delay_ms
- result_json
- created_at

### leader_execution_health_daily

用于记录 buy/sell 链路健康。

关键字段：

- id
- date
- leader_id
- category
- buy_detected_count
- buy_success_count
- sell_detected_count
- sell_attempted_count
- sell_success_count
- sell_failed_count
- sell_delay_p50_ms
- sell_delay_p95_ms
- failure_reason_json

### leader_optimization_report

用于日报页面。

关键字段：

- id
- report_date
- summary_json
- optimization_items_json
- leader_score_changes_json
- sell_health_json
- candidate_pool_json
- backtest_summary_json
- blocked_items_json
- generated_at

## API 建议

### 扫链与评分

- `POST /api/copy-trading/leaders/scan/run`
- `POST /api/copy-trading/leaders/score/recompute`
- `POST /api/copy-trading/leaders/backtest/run`

### 优化日报

- `POST /api/leader-optimization/reports/generate`
- `POST /api/leader-optimization/reports/list`
- `POST /api/leader-optimization/reports/detail`
- `POST /api/leader-optimization/items/rerun`

### 执行链路健康

- `POST /api/copy-trading/execution-health/daily`
- `POST /api/copy-trading/execution-health/sell-latency`
- `POST /api/copy-trading/execution-health/failures`

## 自动化任务建议

### 高频任务

每 1 到 5 分钟：

- 检查 sell 失败和未同步退出。
- 检查 WebSocket 断连。
- 检查 bridge webhook 失败。

### 日内任务

每 30 到 60 分钟：

- 更新 candidate pool。
- 重新分析活跃候选。
- 更新 Leader score。

### 每日任务

每天固定时间：

- 扫链扩展候选。
- 所有 Leader 回测。
- 评分快照。
- 资金分配建议。
- 生成优化日报。

## 验收标准

第一阶段验收：

- 页面能看到每日优化日报。
- 扫链结果能显示候选数量和分类分布。
- 每个 Leader 有 score 和 category。
- politics + finance 资金建议合计为 80%。
- sports + crypto 资金建议合计为 20%。
- 所有 Leader 至少有一次回测结果。
- score 低于阈值会生成告警。

第二阶段验收：

- sell 检测和执行链路有完整时间戳。
- sell success rate 可统计。
- sell delay p50/p95 可统计。
- sell 失败会告警。
- 每日报告能指出至少一个优化点。

第三阶段验收：

- 系统能每日自动执行 discover -> analyze -> implement -> verify -> report。
- 低分 Leader 自动降权或暂停。
- 高分 Leader 自动进入 watchlist 或 trial 建议。
- 可复制收益成为资金分配核心指标。

## 当前实施顺序

建议按以下顺序落地：

1. Leader score snapshot。
2. 所有 Leader 的基础回测。
3. sell 链路时间戳和健康统计。
4. 优化日报数据表和 API。
5. 优化日报页面。
6. candidate pool 持久化。
7. 每日自动优化任务。
8. 资金分配建议模块。
9. 自动告警和降权。

## 非目标

当前阶段不追求：

- 全自动大额真钱加仓。
- 无人工确认的高风险策略上线。
- 对低流动性市场强行追单。
- 只基于 Leader 自身收益做资金分配。

## 最终原则

系统要持续回答一个问题：

> 哪些 Leader 的信号，在我们的真实延迟、真实价格、真实风控和真实 sell 能力下，仍然可以被稳定复制并盈利？

只有这个问题的答案稳定为“是”，该 Leader 才应该获得真实资金分配。
