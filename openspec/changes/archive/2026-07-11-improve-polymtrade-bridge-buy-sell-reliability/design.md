## 1. 模态框处理改进

### 1.1 现状
- `_is_network_modal_open()` 通过文本匹配检测“选择网络和代币 / Select Network / Select Token”等模态框。
- `_dismiss_modal_dialogs()` 只尝试关闭模态框，未真正选择网络。若账户未设置默认网络，关闭后下次点击 outcome 会再次弹出。

### 1.2 改进方案
- 新增 `_select_network_and_token_in_modal(preferred_network='Polygon', preferred_token='USDC')`。
  - 在模态框内查找包含 `Polygon`、`USDC`、`pUSD` 等文本的可点击项。
  - 先点选网络，再点选代币，最后确认（查找“确认 / Confirm / Done”按钮）。
  - 若找不到首选项，记录警告并返回 False，让上层回退到关闭模态框。
- 修改 `_dismiss_modal_dialogs()`：
  - 第一步：尝试 `_select_network_and_token_in_modal()`。
  - 第二步：若选择失败或模态框仍在，再执行原有关闭逻辑。
- 修改 `_execute_buy()` 的模态框重试循环：
  - 检测到模态框时，先尝试选择网络；选择成功后继续检测 buy dialog。
  - 若连续多次选择失败且模态框仍在，再抛出“余额不足或需要充值”错误。

## 2. BUY 前余额检查

### 2.1 现状
- 当前无显式余额检查，依赖模态框是否出现作为间接判断。

### 2.2 改进方案
- 新增 `_get_usdc_balance()`：
  - 通过页面 DOM 抓取余额文本（支持 `USDC`、`pUSD`、`余额` 等关键词）。
  - 返回可解析的浮点数，若无法解析返回 None。
- 在 `_execute_buy()` 开始阶段调用：
  - 若余额 < `amount_usdc * 1.05`（预留 5% 缓冲），直接抛出 `Insufficient balance: ...`。
  - 余额不可解析时，记录警告但不阻塞，继续执行。

## 3. BUY 后成交校验

### 3.1 现状
- `_confirm_trade()` 只检测对话框消失或成功文案，未验证链上/账户状态变化。

### 3.2 改进方案
- 新增 `_verify_buy_executed(event_id, outcome, amount_usdc, timeout=15.0)`：
  - 提交后等待 2-3 秒让页面/合约状态刷新。
  - 调用 `fetch_portfolio_positions()` 或页面余额抓取，检查：
    - 是否出现对应 market/outcome 的持仓；或
    - USDC/pUSD 余额是否下降（近似）。
  - 若两者均未变化，记录警告但 **不** 将交易标为 FAILED（因为链上确认可能延迟），返回 `verified=False` 给调用方。
- 在 `execute_trade()` 中，根据 `_verify_buy_executed()` 结果在返回数据中附加 `verified` 字段，便于后端/审计判断。

## 4. 日志改进

- `_enrich_position()` 等路径捕获异常时，使用 `logger.warning(..., exc_info=True)` 或把异常文本拼入消息，避免当前日志里出现空原因（如 `Failed to enrich position ...:` 后无内容）。

## 5. 测试策略

- 静态 HTML 测试：构造包含“选择网络和代币”模态框的页面，验证 `_select_network_and_token_in_modal()` 能正确点击 Polygon 和 USDC。
- 静态 HTML 测试：构造包含余额元素的页面，验证 `_get_usdc_balance()` 解析逻辑。
- 运行现有 `test_selector_fixture.py` 确保 outcome/sell 选择器未回归。
- 运行 `python -m py_compile polymtrade_executor.py main.py` 确保语法正确。
