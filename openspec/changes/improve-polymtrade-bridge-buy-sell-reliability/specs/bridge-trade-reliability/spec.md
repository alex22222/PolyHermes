# Bridge 交易可靠性提升

## 需求

### REQ-1: 网络/代币模态框主动处理

当 Polymtrade 在 outcome 点击后弹出“选择网络和代币”模态框时，Bridge 应尝试主动选择 Polygon 网络和 USDC 代币，而不是仅关闭模态框。若找不到首选项，再回退到关闭。

### REQ-2: BUY 前余额检查

在执行 BUY 前，Bridge 应尝试从页面读取 USDC/pUSD 余额。若可读取余额且明显低于下单金额（含 5% 缓冲），应快速失败并返回清晰错误，避免进入反复弹窗循环。

### REQ-3: BUY 后成交校验

BUY 提交后，Bridge 应尝试通过 portfolio 或余额变化间接验证订单是否生效。验证不通过时不得将交易标为 SUCCESS，应返回 `verified: false` 供后续审计。

### REQ-4: 失败日志完整

所有捕获异常并记录为警告的路径，必须将异常原因完整写入日志，禁止出现空原因的日志条目。

### REQ-5: 持仓 enrich 避免页面跳转

`fetch_portfolio_positions()` 在 enrich 每个持仓时，不得通过点击 card 触发页面导航；应优先使用 card 中已存在的 `href`/`data-*` 或 Gamma API title search。

### REQ-6: Gamma API 调用带重试

所有从 Bridge 发往 Gamma API（events/markets）的请求必须具备指数退避重试机制，默认至少重试 3 次。

### REQ-7: 持仓 enrich 并发执行

当 enrichment 不再依赖页面点击/导航后，多个持仓的 enrichment 应并发执行，降低 `/portfolio` 接口延迟。

### REQ-8: BUY 后精确成交校验

BUY 提交后，Bridge 应在提交前捕获 USDC 余额与目标 event-page 持仓数量基线；提交后再次读取余额与持仓数量。若余额下降达到下单金额的 50% 以上，或 event-page 持仓数量增加，则视为成交通过；否则仍保留 success indicator 兜底校验。校验结果通过 `verified` 字段返回。

## 场景

### SC-1: 未设置默认网络时执行 BUY

**Given** Bridge 账户在 Polymtrade 未设置默认网络  
**When** 收到 BUY 信号并点击 outcome  
**Then** 模态框弹出后，Bridge 选择 Polygon + USDC  
**And** 继续填写金额并提交订单  
**And** 不再因同一模态框反复失败

### SC-2: 余额不足时执行 BUY

**Given** Bridge 账户 USDC 余额为 $0.50  
**When** 收到 BUY $2.00 的信号  
**Then** Bridge 在尝试点击 outcome 前快速失败  
**And** 返回错误信息包含当前余额和所需金额  
**And** `bridge_trade_record` 状态为 FAILED

### SC-3: BUY 提交后未检测到账户变化

**Given** BUY 订单已提交  
**When** 15 秒内 portfolio 和余额均未发生变化  
**Then** 交易仍记录为执行过  
**And** 返回结果中 `verified: false`  
**And** 日志记录待审计警告

### SC-4: 异常日志完整

**Given** `_enrich_position` 调用 Gamma API 或页面操作时抛出异常  
**When** 异常被捕获并记录  
**Then** 日志消息包含异常类型和具体原因  
**And** 不出现以冒号结尾但无后续内容的日志

### SC-5: 持仓 enrich 不触发页面导航

**Given** `/portfolio` 页面已加载并包含多个持仓卡片  
**When** Bridge 调用 `fetch_portfolio_positions()`  
**Then** enrichment 优先通过 Gamma markets/events title search 完成  
**And** 不出现 `net::ERR_ABORTED at https://polym.trade/portfolio`  
**And** `/portfolio` 接口返回 200

### SC-6: Gamma API 瞬断时自动重试

**Given** Gamma API 前两次请求超时/连接失败  
**When** Bridge 调用 `_gamma_request_with_retry()`  
**Then** 第 3 次请求成功并返回数据  
**And** 日志记录前两次失败及退避等待时间

### SC-7: BUY 成交后精确校验

**Given** Bridge 已执行 BUY $2.00  
**When** `_capture_buy_baseline()` 在提交前记录余额 $100.00 与持仓数量 0  
**And** 提交后余额变为 $97.90，event-page 持仓数量变为 10  
**Then** `_verify_buy_executed()` 返回 `verified: true`  
**And** 返回结果中包含前后余额与持仓数量供审计

### SC-8: BUY 未成交时精确校验失败

**Given** Bridge 已执行 BUY $2.00  
**When** 提交前后余额均为 $100.00 且 event-page 持仓数量均为 0  
**And** 页面未出现 success indicator  
**Then** `_verify_buy_executed()` 返回 `verified: false`  
**And** 返回结果中标记 `verified: false` 并记录审计日志
