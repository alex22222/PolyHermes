# G3 Phase 1：资产数据源与失败语义

## 当前数据源

| 分项 | 当前来源 | 当前失败行为 | G3 要求 |
|---|---|---|---|
| 可用余额 | Bridge `/balance.available_balance` | 日快照不生成；盘中快照标记 `BALANCE_UNKNOWN` | 已完成，不写零 |
| 当前持仓 | Bridge `/portfolio.positions` | 请求失败跳过；单次空数组等待再次确认 | 连续两次空且余额可用才确认纯现金 |
| 持仓价值 | `positions[].currentValue` | 缺失时保存已知小计并标记 `INCOMPLETE` | 已完成；风险决策不得使用不完整总资产 |
| 钱包身份 | Bridge `/account.wallet_address` | 缺失时跳过同步 | 保持安全失败；与 portfolio 钱包交叉核对 |
| 已结算待赎回 | Data API `/positions?redeemable=true` | 失败标记 `UNKNOWN`，不写零 | 已纳入总资产，成功零值与失败分开 |
| 每日资产 | `daily_asset_snapshot` | 零点后 120 秒内标记 `MIDNIGHT`，否则标记 `DAILY_FIRST_SUCCESS` | 保存实际偏移，不冒充零点 |
| 盘中资产 | `current_asset_valuation` | 每次可信同步覆盖最新值 | 已完成，供后续硬风控读取 |
| 原子身份与余额 | Bridge `/portfolio` | 同一页面上下文返回钱包和余额 | 已完成，后端不再依赖第二次抓取 |

## 当前已验证基线

- 时间：2026-07-11
- 钱包：`0x0372…4942`
- 可用余额：`11.70`
- 持仓数量：`25`
- 持仓已知价值：`74.37`
- 可确认总资产：`86.07`
- 未知持仓估值数量：`0`

数据库当日唯一快照为 `12.90 + 74.21 = 87.11`，反映较早的当日采集状态。其日期标签为零点，但实际采集发生在约 15:35。

## 安全判定

- `/portfolio` 明确成功返回空数组：可信纯现金状态，可以清理旧持仓。
- `/portfolio` 请求失败：未知状态，不得清理旧持仓或写零持仓价值。
- `/portfolio` 非空但全部非法：数据不可信，不得清理旧持仓。
- 单个持仓缺失 `currentValue`：组合估值标记 `INCOMPLETE`，`totalAssets=null`，仅保留已知小计。
- `/balance` 失败：余额未知，不得生成声称完整的总资产快照。
