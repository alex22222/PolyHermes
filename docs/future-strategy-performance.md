# BTC 5m / 15m 已结算表现

Future Bridge 页在当前钱包资产下分别显示两个周期的已结算胜率、扣费后净盈亏、按实际买入总成本计算的收益率和累计净盈亏曲线。沿用每 5 秒页面轮询及后端 10 秒完整结果缓存；切换钱包、数据过期或读取失败会清除旧钱包指标。

统计范围是当前钱包的全部 BTC5m / BTC15m 市场，包含同周期手动买入，不声称全部来自扩展。一个市场一个方向的多次成交合并为一个仓位，胜率表示该方向是否命中最终结算结果。原买入表仍逐笔展示。

后端完整翻页读取 v2 activity，不加 BUY/TRADE 限制，按同一市场、token 和方向核对 BUY、SELL 和 REDEEM。结算方向沿用独立 CLOB 最终结果校验。净盈亏等于实际卖出及兑付的 `usdc_size` 总和减 BUY `usdc_size`，使用十进制汇总，买入已含手续费，不重复扣费。按市场结束时间累加曲线，纵轴为 USDC 净盈亏金额，不是年化收益。

只计最终结果已确认且流水可核对的仓位。输家已结算终值为零，无需等待零值 token 销毁或仓位变成 CLOSED；赢家剩余份额尚未兑付的，暂不纳入。部分卖出结合实际卖出收入与剩余份额兑付对账。未结算、未兑付、金额/身份异常、特殊转换流水或历史不完整保持待核实；历史尚未完整翻页时不发布累计净值或曲线。界面显示排除数量和首笔时间。

验证入口：

```sh
source scripts/java-env.sh && (cd backend && ./gradlew test --tests '*FutureBtc*')
node --test scripts/test_future_strategy_performance.mjs scripts/test_future_btc5m_page_component.mjs
(cd frontend && npm run build)
```

固定真实回执样本 `backend/src/test/resources/future-btc15m-settled-receipts.json` 含 18 笔买入与 14 笔兑付；应得到 14 赢、4 亏、成本 18.559177、回款 20.251591、净盈亏 +1.692414 USDC。
