## Why

PolyHermes Bridge 的 BUY/SELL 执行成功率直接影响跟单收益。从现有日志和数据库记录来看，BUY 执行存在两个突出问题：

1. **网络/代币选择模态框反复阻塞**：当 Bridge 账户在 Polymtrade 上未设置默认网络/代币时，点击 outcome 后会弹出“选择网络和代币”模态框。当前代码仅尝试关闭该模态框，未真正选择网络，导致模态框反复出现，最终误判为余额不足而失败。
2. **BUY 缺少成交后校验**：SELL 已有持仓减少的 live check，但 BUY 在提交后没有验证持仓或余额是否变化，可能出现“假成功”。

本次迭代先聚焦 BUY 路径的可靠性提升，降低因 UI 模态框导致的误判失败，并补充成交前后的显式校验。

## What Changes

- 在 `polymtrade_executor.py` 中新增“选择网络和代币”模态框的主动处理能力：优先选择 Polygon + USDC，而非简单关闭。
- 新增 BUY 前余额检查：若页面可读取的 USDC/pUSD 余额明显低于下单金额，则快速失败并给出明确错误。
- 新增 BUY 后成交校验：通过 portfolio API 或页面余额变化确认订单已提交，减少假成功。
- 改善 `_enrich_position` 等路径的异常日志，确保失败原因完整输出。
- 为网络选择模态框和余额检查新增静态/单元测试。

### Out of Scope

- 本次不改动 SELL 执行主路径（已有 live position check）。
- 本次不新增数据库表结构，仅使用现有 `bridge_trade_record` 记录状态。
- 本次不处理后端 copy-trading 规则引擎的风控逻辑。

## Capabilities

### New Capabilities

- `bridge-trade-reliability`: Bridge 端 BUY 执行具备网络/代币模态框主动处理能力、前置余额检查和后置成交校验。

### Modified Capabilities

- `polymtrade-executor`: BUY 执行流程更健壮，失败原因更准确。

## Impact

- 修改 `polymtrade-bridge/polymtrade_executor.py` 的模态框处理、BUY 执行和校验逻辑。
- 新增/更新 `polymtrade-bridge/test_selector_fixture.py` 或新增测试文件覆盖网络选择模态框和余额解析。
- 可能降低 `bridge_trade_record` 中因模态框阻塞导致的 FAILED 记录比例。
- 交易安全影响：本改动涉及真实资金下单路径，所有变更需保持保守，新增校验不得绕过现有风控。
