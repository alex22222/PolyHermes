# G4 Phase 1：标签数据合同与真实基线

## 结论

当前数据可以支持 PAPER 离线基线，但不能直接训练或上线真实跟单模型。系统尚无统一的“每个账户、每条配置、每次 Leader 信号”candidate 主键；真实成功 BUY 也没有可归属的结算盈亏标签。

## 事件链合同

目标链路为：

`candidate → deterministic filter → model shadow decision → G3 risk decision → execution → settlement`

稳定 candidate 粒度必须是：

`leaderId + leaderTradeId + copyTradingId + accountId`

仅用 `leaderTradeId` 不够，因为同一 Leader 成交可能对应多个账户和跟单配置。每一阶段都必须保存统一 `candidateId`，不能依靠市场标题、时间邻近或金额反推。

## 当前数据源

| 阶段 | 当前来源 | 可用键 | 主要缺口 |
|---|---|---|---|
| Leader 信号去重 | `processed_trade` | `leader_id + leader_trade_id` | 没有配置/账户粒度；成功只表示处理函数返回，不等于下单成功 |
| 原规则过滤 | `filtered_order` | `copy_trading_id + leader_trade_id` | 当前真实数据为 0；并非所有 Bridge 过滤都写入此表 |
| Bridge 过滤/执行 | `bridge_trade_record` | `external_trade_id`，新记录部分有 raw payload 配置键 | 历史配置/账户键覆盖不足；FAILED 混合过滤、风控、资金和 UI 失败 |
| 后端直连执行 | `copy_order_tracking` | `copy_trading_id + leader_buy_trade_id` | 当前真实数据为 0；只保存成功订单，不保存全部候选 |
| G3 风控 | `portfolio_risk_decision` | 新快照含 correlation | 自 V79/V80 后才完整；自然 FINAL 样本仍不足 |
| Crypto Tail | `crypto_tail_strategy_trigger` | `strategy_id + period_start_unix` | 当前真实数据为 0 |
| PAPER | `leader_paper_trade` | `candidate_id + leader_trade_id` | 标签完整，但 quote 时间晚于事件，不能当作事件时特征 |
| 真实结算 | 无统一表 | 无 | Bridge 成功 BUY 没有 realized PnL、winner 和退出归因 |

## 真实基线（2026-07-11）

- `processed_trade`：2 条，BUY/SELL 各 1，均为 SUCCESS；不能代表完整候选历史。
- `filtered_order`：0；`copy_order_tracking`：0。
- `bridge_trade_record`：12,764 条。
  - BUY：238 SUCCESS、9,574 FAILED。
  - SELL：81 SUCCESS、2,871 FAILED。
  - `external_trade_id` 与合法 raw payload 覆盖 100%。
  - `copyTradingId` 覆盖 12,725/12,764；账户 ID 与风险 correlation 仅各 3 条，属于新链路样本。
- Bridge FAILED 的主要原因不是成交亏损：领域不匹配 4,533、关键词白名单 1,721、持仓不足 1,053、高价低收益 741、重复市场 BUY 336 等。
- `portfolio_risk_decision`：18 条，仅 3 条有完整输入快照，0 条自然 FINAL/correlation 样本。
- `leader_paper_trade`：4,500 条，candidate/trade 键唯一且无标签冲突。
  - 3,208 PASSED；1,292 FILTERED。
  - PASSED 中 1,749 AVAILABLE、1,456 CONFIRMED_ZERO、3 UNKNOWN。
  - 3,208 条 PASSED 均有 `realized_pnl`。
  - 4,500/4,500 的 `quote_timestamp > event_time`，事件后报价禁止作为事件时模型输入。
- 真实 Bridge BUY SUCCESS 为 238 条，但当前 0 条具备统一 realized PnL 结算标签。

## 标签语义

Bridge `FAILED` 必须先拆分，不能直接映射成负收益：

- `POLICY_FILTER`：领域、币种、关键词等人工配置不允许。
- `RISK_FILTER`：价格、重复下单、G3 或既有风险规则拒绝。
- `SELL_SAFETY_SKIP`：无真实持仓或数量不足。
- `ACCOUNT_FUNDING`：余额、充值或账户资金问题。
- `UI_EXECUTION_FAILURE`：结果选择、金额输入、页面交互失败。
- `EXECUTION_FAILURE`：通过所有过滤后，真实提交失败。
- `EXECUTED_SUCCESS`：只代表执行成功，不能直接当作正收益。
- `SETTLED_WIN/SETTLED_LOSS/SETTLED_FLAT`：必须来自可归属结算数据。

## 特征可用时间

- 只能使用 `availableAt <= candidate.eventTime` 的特征。
- Leader 历史统计必须截止到 candidate 之前，不能使用包含本次或未来交易的聚合。
- 市场最终结果、结算价格、事后 quote、未来持仓和后续风险决策只能作为标签或评估，不得进入输入。
- 当前 PAPER `quote_timestamp` 全部晚于 event，因此 `simulated_price`、quote confidence/source 必须先证明当时可用，未证明前排除。

## Phase 1 阻断项

1. 新建统一 candidate 审计表，在任何过滤之前写入账户/配置粒度候选。
2. 所有 deterministic filter、模型建议、G3 决策和执行记录保存 candidate ID。
3. Bridge FAILED 写入结构化 `failure_stage` 与 `failure_class`，停止依赖错误文本训练。
4. 建立真实执行到结算/退出的归属表；在此之前真实样本只能训练执行可达性，不能训练收益标签。
5. 重建事件时点可用的价格、流动性和 Leader 历史特征快照。

## 可重复报告

使用 `scripts/g4_label_coverage.sql` 生成只读覆盖率报告。该脚本不得写库，后续每次数据合同迁移都应以同一报告对比覆盖率变化。
