# G3 Phase 3：Shadow 组合风险策略

## 当前版本

- 版本：`G3-SHADOW-V4`
- 模式：`SHADOW`
- 实盘效果：候选阈值仍只记录 Shadow；人工账户暂停 BUY 是独立硬开关，命中时立即 `executionAllowed=false`。
- 审计表：`portfolio_risk_decision`
- API：`POST /api/risk/portfolio/evaluate`

## 候选规则

| 规则 | Shadow 阈值 | 数据要求 |
|---|---:|---|
| MIN_CASH_RESERVE | 下单后现金至少占总资产 20% | 总资产和余额估值完整 |
| MAX_SINGLE_ORDER | 单笔不超过总资产 2% | 总资产估值完整 |
| MAX_MARKET_EXPOSURE | 下单后单市场不超过总资产 8% | 市场归因价值覆盖率至少 95% |
| MAX_EVENT_EXPOSURE | 下单后事件不超过总资产 15% | 事件归因价值覆盖率至少 95% |
| MAX_LEADER_EXPOSURE | 下单后 Leader 不超过总资产 10% | Leader 归因价值覆盖率至少 95% |
| MAX_CATEGORY_EXPOSURE | 下单后领域不超过总资产 35% | 领域归因价值覆盖率至少 95% |
| MAX_DAILY_LOSS | 当日资产亏损不超过 5% | 当日资产基线和当前总资产完整 |
| MAX_DAILY_BUY_ORDERS | 当日成功 BUY 与并发预占合计不超过 20 | 成交记录具备账户归属 |
| ACCOUNT_BUY_PAUSED | 人工暂停时拒绝所有新增 BUY | 持久控制状态与操作审计 |

阈值是回放和 Shadow 观察的候选值，不是已批准的实盘限制。正式启用必须经过历史回放、至少三天 Shadow、人工确认和独立关闭开关。

## 决策语义

- `PASS`：按当前候选阈值未发现命中。
- `WOULD_BLOCK`：若未来启用该规则，这笔 BUY 会被拒绝；Shadow 阶段仍允许执行。
- `INSUFFICIENT_DATA`：估值或归因不足，不能给出可信结论，不得转换成 PASS。
- `SELL_PRIORITY`：不运行 BUY 现金和集中度规则；执行层继续校验真实持仓、数量和幂等。
- `ACCOUNT_BUY_PAUSED`：人工硬停止，不受 Shadow 模式影响；Bridge、自动策略和手工 BUY 都必须拒绝，SELL 不受影响。

## 接入边界

Bridge 已在两个拥有真实拟下单金额的阶段调用风险决策：

1. Bridge 按具体跟单配置计算实际 BUY 金额后的 `precheck`。
2. Bridge 获得交易锁并即将执行 BUY UI 操作前的 `final`。

后端发送原始 Leader 信号时尚不知道我们的实际金额，因此不使用 Leader 成交金额冒充风险输入。双阶段使用同一策略版本和稳定关联请求 ID。Bridge 内部接口使用共享密钥，localhost 调用不继承外部代理；当前版本仍只记录 Shadow。

Bridge 运行态暴露：

- `portfolio_risk_configured`
- `portfolio_risk_mode`
- `portfolio_risk_checks`
- `portfolio_risk_unavailable`
- `portfolio_risk_would_block`
- `portfolio_risk_denied`

## 并发预占

`G3-SHADOW-V4` 使用 `portfolio_risk_reservation` 对同账户 BUY 串行预占：

- precheck：`ACTIVE`
- final：`EXECUTING`
- 成功：`SUCCESS`
- 过滤或失败：`FAILED`
- 120 秒无终态：`EXPIRED`

同一 correlation 的 final 复用 precheck；其他并发预占会计入现金、事件、Leader 和领域投影。Bridge 成交 raw payload 保存账户 ID、跟单配置 ID 和风险 correlation。当天存在旧的无账户成功 BUY 时，每日订单规则返回数据不足，直到进入完整的新自然日。

## 决策查询与回放范围

- `/api/risk/portfolio/decisions`：按账户读取最近决策与逐规则结果。
- `/api/risk/portfolio/replay`：对 V79 后的新决策使用 `FULL_INPUT_SNAPSHOT`，从保存的请求、资产、四层暴露、覆盖率、每日指标和并发预占输入重新计算全部规则与 outcome。

重算结果必须同时满足 outcome 和逐规则列表一致才返回 `consistent=true`。V79 前的旧决策没有输入快照，明确返回 `INPUT_SNAPSHOT_UNAVAILABLE`、`snapshotAvailable=false`，不以旧规则结果冒充完整历史回放。策略版本不受当前 replay 实现支持时拒绝重算，避免用新规则错误解释旧输入。
