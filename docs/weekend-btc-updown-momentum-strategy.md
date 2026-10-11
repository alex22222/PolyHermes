# 周末 BTC 涨跌盘「开盘 1 分钟顺势」策略

日期：2026-10-10。本文是研究和模拟盘记录，不构成投资建议。

- 回测脚本、模拟盘机器人和完整回测报告在 binance 项目里，见第 8 节。
- 本文的目的是把策略、市场规则和结论沉淀到 PolyHermes，后续如果要在 PolyHermes 里实现，可以直接参考。

## 1. 策略定义

| 项目 | 规则 |
|---|---|
| 市场 | Polymarket "Bitcoin Up or Down" 系列。future.news（GMGN）只是这些市场的前端，订单最终在 Polymarket CLOB 成交 |
| 周期 | 5 分钟、15 分钟、1 小时、4 小时 |
| 时间 | 只做美东时间周六 00:00 到周日 23:59 之间开盘的轮次 |
| 入场 | 开盘后第 60 秒，比较当前价和本轮开盘价（Price to beat），涨就买 Up，跌就买 Down，持平则跳过 |
| 下单方式 | taker 市价买入固定金额 |
| 离场 | 持有到结算，不中途卖出 |

**策略背后的假设**：周末 BTC 波动小，开盘 1 分钟形成的方向更容易保持到结算。第 3 节的回测证明这个假设不成立。

## 2. 结论

1. **不建议实盘。**
   - 回测区间：2026-04-04 到 2026-10-04，共 27 个周末、14,299 注。
   - 入场价：每注取开盘后第 60–75 秒真实 taker 成交的均价。
   - 结果：扣费后合计每注 −0.85%（t=−1.24）。
2. **"周末更稳"不成立。**
   - 周末第一分钟的波动只有工作日的 2/3，但"第 60 秒方向 = 最终方向"的概率和工作日几乎一样。
   - 这个概率由「1 分钟 ÷ 每轮时长」决定，和随机游走理论值只差 1–2 个百分点，跟波动大小无关。
3. **到第 60 秒，盘口已经计价了这部分优势。**
   - 毛优势（胜率 − 买价）约 1 个百分点。
   - taker 手续费按本金算是 7% × (1 − 买价)，在 0.6 买入时约 2.8%，比毛优势大。
4. **1 小时盘看似为正（每注 +4.8%，t=1.82），但不可靠。**
   - 样本期周末 1 小时盘的命中率偏高：59.1%，之前三个半年都只有 55–57%。按两年均值估算，长期期望约为 0。
   - 改用"盘口倾向"判定方向后，收益只剩 +0.7%。
   - 入场窗口内同方向 taker 成交的中位数只有 $12，基本放不进资金。
5. **"只在便宜时买"的过滤反而更差。**
   - 做法：用历史数据估算公平概率，在样本外只买"公平概率 > 买价 + 手续费"的轮次。
   - 结果：5 分钟盘每注 −5.3%（t=−3.2）。
   - 原因：模型认为该赢 64% 的那些轮次，实际只赢了 53%。盘口掌握的信息比"第一分钟涨跌"多。

## 3. 市场规则（2026-10 核实）

### 3.1 Slug 与周期

5 分钟和 15 分钟的规则见 `docs/crypto-tail-strategy/zh/crypto-tail-strategy-market-data.md`，这里补上 1 小时和 4 小时。

| 周期 | Event slug | 对齐方式 |
|---|---|---|
| 5 分钟 | `btc-updown-5m-{periodStartUnix}` | 300 秒 |
| 15 分钟 | `btc-updown-15m-{periodStartUnix}` | 900 秒 |
| 4 小时 | `btc-updown-4h-{periodStartUnix}` | 14400 秒，按 UTC 0/4/8/12/16/20 点对齐 |
| 1 小时 | `bitcoin-up-or-down-{month}-{day}-{year}-{h}{am\|pm}-et` | 按美东整点，例如 `bitcoin-up-or-down-october-10-2026-11am-et` |

- Gamma 支持一次传多个 `slug` 参数批量查询，例如 `/events?slug=a&slug=b`。
- 1 小时盘 Gamma 返回的 `startDate` 是挂牌时间，一般提前约 2 天。真正的周期起点要看 `markets[0].eventStartTime`。

### 3.2 结算规则

| 周期 | 结算依据 | 开盘价（Price to beat） |
|---|---|---|
| 5m / 15m / 4h，2026-08-08 之前 | Chainlink BTC/USD 结算时刻价格 ≥ 开盘价 → Up | Chainlink 开盘时刻价格 |
| 5m / 15m / 4h，2026-08-08 起 | Chainlink BTC/USD **60 秒 TWAP** ≥ 开盘价 → Up（`cryptoMarketConfig.twapEnabled=true, twapLookbackSeconds=60`） | 上一轮的结算值，即开盘时刻的 60 秒 TWAP，不是开盘那一刻的现价 |
| 1 小时 | Binance BTC/USDT 1H K 线 close ≥ open → Up | Binance 1H open |

- 平局都算 Up。
- 开盘价可以通过 `https://polymarket.com/api/crypto/crypto-price?symbol=BTC&eventStartTime=…&variant=…&endDate=…` 查询，返回 `openPrice` 和 `closePrice`，只保留最近 30 天。
  - `variant` 的取值：5 分钟 `fiveminute`，15 分钟 `fifteen`，4 小时 `fourhour`。
  - 已核对：上一轮的 `closePrice` 等于下一轮的 `openPrice`。
- 实时 Chainlink 价格（也就是 future.news 页面上的 Current Price）来自 `wss://ws-live-data.polymarket.com`。
  - 订阅 `crypto_prices_chainlink`，filter 设为 `{"symbol":"btc/usd"}`。
  - 每 5 秒发一次 `PING` 保活。

### 3.3 手续费

- 2026-04 起，这些市场的 `feeType` 是 `crypto_fees_v2`，`feeSchedule = {rate: 0.07, exponent: 1, takerOnly: true, rebateRate: 0.2}`。
- taker 手续费 = 股数 × 0.07 × p × (1 − p)，按本金算是 7% × (1 − p)：0.5 买入 3.5%，0.65 买入 2.45%，0.8 买入 1.4%。
- maker 不付手续费，另有 20% 返佣。
- 更早的费率：2026-03 是 `crypto_fees`，2026-01 到 02 是 `crypto_15_min`，再往前不收费。
- PolyHermes 现有的 `PolymarketClobService.getFeeRate(tokenId)` 可以复用，但计费公式要按上面的 `p × (1 − p)` 形式计算。

### 3.4 其他

- 最小下单 5 股，价格最小变动 0.01。
- 这些 event 带 `restricted: true`。`https://polymarket.com/api/geoblock` 会返回当前出口 IP 是否被限制交易。

## 4. 回测方法

| 数据 | 来源 | 区间 |
|---|---|---|
| BTCUSDT 1 分钟 K 线 | `data-api.binance.vision`（`api.binance.com` 在美国出口返回 451） | 2024-10-05 → 2026-10-05 |
| 每轮的元数据和结算结果 | Gamma `/events?slug=…` | 2026-04-04 → 2026-10-04 |
| 开盘后 30–130 秒的成交 | Data API `/trades?market={conditionId}&takerOnly=true&start=…&end=…` | 同上 |

- **入场价**：所选方向在第 60–75 秒的 taker 买入 VWAP，这段时间没有成交就放宽到 60–120 秒。
- **方向判定**
  - 主口径：第 60 秒的价格对比开盘价。
  - 对照口径：开盘后 30–60 秒最近 5 笔成交隐含的 Up 价格（盘口倾向）。
- **对照组**：同期 26 个周三。
- **抽样**：5 分钟盘每隔一轮取一轮，其余周期全量。
- **数据核对**
  - 1 小时盘用 Binance 复算的结果和市场结算 100% 一致。
  - Chainlink 结算的轮次，复算一致率 96–99.7%。
  - 5 分钟 TWAP 轮次一致率 93.2%，差异来自 Chainlink 和 Binance 的价差。
- **接口限速**：`/trades` 限 200 次 / 10 秒，Gamma `/events` 限 500 次 / 10 秒。

## 5. 回测结果

### 5.1 纯价格：周末并不特殊

两年数据中第 60 秒方向的命中率，「/」后面是 TWAP 口径。

| 周期 | 随机游走理论值 | 周末 | 工作日 | 周末第一分钟波动（中位数） | 工作日 |
|---|---|---|---|---|---|
| 5 分钟 | 64.8% / 68.0% | 66.0% / 68.7% | 65.5% / 67.9% | 2.1 bp | 3.2 bp |
| 15 分钟 | 58.3% / 59.7% | 59.1% / 59.2% | 58.7% / 59.3% | 2.2 bp | 3.4 bp |
| 1 小时 | 54.1% | 56.6% | 55.7% | 2.3 bp | 3.5 bp |
| 4 小时 | 52.1% / 52.4% | 52.9% / 53.2% | 53.3% / 53.0% | 2.3 bp | 3.7 bp |

### 5.2 真实盘口（周末，主口径）

| 周期 | 注数 | 胜率 | 平均买价 | 毛优势 | 手续费 | 每注净收益 | 再加 1¢ 滑点 | t | 窗口内 taker 成交中位数 |
|---|---|---|---|---|---|---|---|---|---|
| 5 分钟 | 7,924 | 65.8% | 0.650 | +0.8pp | 2.45% | −1.78% | −3.31% | −2.03 | $510 |
| 15 分钟 | 4,987 | 60.4% | 0.591 | +1.3pp | 2.86% | −0.51% | −2.18% | −0.42 | $69 |
| 1 小时 | 1,178 | 59.3% | 0.549 | +4.4pp | 3.16% | +4.82% | +2.93% | 1.82 | $12 |
| 4 小时 | 210 | 51.9% | 0.529 | −1.0pp | 3.30% | −5.52% | −7.26% | −0.84 | $1 |
| **合计** | 14,299 | | | +1.26pp | 2.67% | **−0.85%** | | −1.24 | |

- 周三对照组合计 6,915 注，每注 −3.02%（t=−3.12），毛优势 −0.04pp。周末确实比工作日略好，但扣费后仍为负。
- 按结算规则拆分（周末）：
  - 5 分钟盘：Chainlink 现价结算时期 −2.02%，TWAP 时期 −1.30%。
  - 15 分钟盘：−0.87%，+0.17%。
  - 4 小时盘：−7.92%，−0.29%。
- 入场窗口换成 60–70 秒或 60–90 秒，结果基本不变。
- 买价分档后，胜率紧贴买价，没有看到"热门方向被系统性低估"。

## 6. 实现：实时模拟盘

模拟盘机器人在 binance 项目里，2026-10-10 16:31 UTC 开始运行。它用实时数据模拟成交，不发任何订单：

1. 每秒检查一次各周期的当前轮次。只处理美东周末开盘的轮次，到达 +60 秒时触发；超过 +80 秒才处理的轮次记为错过。
2. 并行获取三样东西：
   - 开盘价：5m/15m/4h 用 crypto-price 接口的 `openPrice`，1h 用 Binance 1H K 线的 open。
   - 当前价：5m/15m/4h 用 RTDS 推送的 Chainlink 价，超过 5 秒没更新则跳过本轮；1h 用 Binance 现价。
   - 市场信息：从 Gamma 查 token ID。
3. 按方向读取该 token 的 CLOB `/book`，从最低卖价往上吃单，模拟买入固定金额（默认 $10，最高价 0.99），逐档计算手续费。同时记录对手方向的最优卖价和本方向的最优买价，用于事后分析。
4. 结算：
   - 每 30 秒用 Gamma 检查 `closed` 和 `outcomePrices`，以官方结算结果为准。
   - 3 小时后仍未结算的，按价格数据临时判定，并标记为非官方。
5. 所有下注、跳过和结算都记录到 `ledger.jsonl`，用 `--status` 汇总各周期的胜率、平均买价、手续费和盈亏。
6. 在状态目录下创建 `STOP` 文件后，不再开新仓，已开的仓照常结算。

## 7. 如果要在 PolyHermes 中实现

- **复用**：crypto-tail 策略的 Gamma slug 推导和周期对齐逻辑，以及 `PolymarketClobService` 的下单和查费率接口。
- **需要新增**
  - 1 小时和 4 小时的 slug 规则（见 3.1）。
  - 开盘价来源：crypto-price 接口和 Binance 1H K 线。
  - Chainlink 实时价订阅（RTDS）。
  - 美东周末判定，要处理夏令时切换。
- **方向判定要和结算口径一致**：TWAP 轮次的开盘价是 60 秒 TWAP，不能拿开盘那一刻的现价比较。
- **默认只跑模拟**，实盘需要单独开关。
- **风控**：单注上限不超过入场窗口成交量的一半、每日亏损上限、停止开关。
- **启动前检查**：调用 `/api/geoblock`，返回 `blocked` 就拒绝下单。
- **先跑 maker 方案的数据收集**：挂单没有手续费，是唯一可能绕开费用的路线，但有逆向选择问题。用现有的成交记录回测不了，需要先录制盘口深度数据。

## 8. 风险与合规

- 回测和模拟盘都显示，扣费后的期望收益不为正。
- 运行环境的代理出口（美国加州）被 Polymarket geoblock 判定为限制交易。中国大陆对加密货币交易和这类盘口也有监管限制，实盘前请自行确认合规风险。
- 这份文档和配套代码都只用于研究和模拟，没有发出任何真实订单。

## 9. 参考文件（binance 项目）

| 文件 | 用途 |
|---|---|
| `/Users/henry/projects/binance/docs/2026-10-10-weekend-btc-updown-backtest.md` | 完整回测报告，含全部稳健性检验 |
| `/Users/henry/projects/binance/scripts/run-weekend-updown-backtest.mjs` | 回测脚本，缓存在 `artifacts/weekend-updown/` |
| `/Users/henry/projects/binance/scripts/run-weekend-updown-paper.mjs` | 实时模拟盘机器人 |
| `/Users/henry/projects/binance/src/polymarket-updown.mjs` | 共用规则：slug、周末判定、手续费、吃单模拟 |
| `/Users/henry/projects/binance/test/polymarket-updown.test.mjs` | 单元测试 |
| `/Users/henry/projects/binance/state/weekend-updown-paper/` | 模拟盘账本 `ledger.jsonl` 和日志 `runner.log` |

模拟盘的常用命令（在 binance 项目目录下执行）：

```bash
NODE_USE_ENV_PROXY=1 nohup node scripts/run-weekend-updown-paper.mjs --stake=10 >> state/weekend-updown-paper/runner.log 2>&1 &
node scripts/run-weekend-updown-paper.mjs --status
touch state/weekend-updown-paper/STOP
```

三条命令依次是：启动、查看汇总、停止开新仓。
