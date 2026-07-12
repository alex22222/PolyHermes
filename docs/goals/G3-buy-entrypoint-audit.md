# G3 BUY 实盘入口审计

## 已覆盖

| 入口 | 实际金额位置 | 风险阶段 | SELL |
|---|---|---|---|
| Bridge `/signal` Leader 跟单 | Bridge 配置计算后 | precheck + final + complete | 跳过 BUY 风险 |
| Bridge `/execute` 手工交易 | ExecuteRequest `amount_usdc` | precheck + final + complete | 跳过 BUY 风险并校验持仓 |
| Crypto Tail 手工订单 | `price * size` | 后端 Gateway precheck + final + complete | 仅 BUY |
| Crypto Tail 自动快路径 | 余额/策略计算后的 `amountUsdc` | 后端 Gateway precheck + final + complete | 仅 BUY |
| Crypto Tail 自动慢路径 | 余额/策略计算后的 `amountUsdc` | 后端 Gateway precheck + final + complete | 仅 BUY |
| 旧跟单直连 CLOB | 调整后 `price * quantity` | 后端 Gateway precheck + final + complete | SELL 跳过 BUY 风险 |

## 尚未覆盖

| 入口 | 执行实现 | 风险 |
|---|---|---|
| 无 | - | 当前未发现仍可达的后端 BUY 执行绕过 |

## 非实盘范围

- Backtest
- Leader Paper Trading
- 研究与回放任务
- `/api/accounts/orders`：只查询历史订单，不执行 CLOB 下单；此前审计把 `AccountService` 的 SELL 实现误关联到该路由，现已纠正。
- `PolymarketClobService.createSignedOrder`：当前无调用方且代码标明为占位实现，不是可达执行入口；未来新增调用方必须先接入 Gateway。

## 双执行引擎去重结论

- 无 CLOB 凭证且符合 Bridge 条件的账户只转发 Bridge，同一后端处理链不会再直接执行 CLOB。
- 有 CLOB 凭证的账户走旧直连路径，同一处理链不会触发 Bridge fallback。
- `processTrade` 按 Leader 与交易 ID 去重；`BridgeWebhookClient` 另有内存和数据库去重，Bridge 执行前也检查本地 recorder。
- 若人为把同一 Leader 配置到不同账户或不同执行引擎，系统会按账户分别执行；这是跨账户配置结果，不视为单账户重复下单。

入口表清零只是启用 Enforced 的必要条件；历史回放、Shadow 样本、数据完整性和人工确认全部通过前，仍不允许切换为 Enforced。
